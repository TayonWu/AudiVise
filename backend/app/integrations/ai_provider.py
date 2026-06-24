from pathlib import Path
from typing import Any

import httpx

from app.core.config import get_settings
from app.services.retrieval import Evidence
from app.services.transcripts import AsrSegment


class ProviderConfigurationError(RuntimeError):
    pass


class RetryableExternalError(RuntimeError):
    pass


class PermanentExternalError(RuntimeError):
    pass


_RETRYABLE_STATUS_CODES = {408, 409, 425, 429, 500, 502, 503, 504}


def build_asr_form_data(api_url: str, model: str) -> dict[str, str]:
    data = {"model": model}
    if "api.siliconflow.cn" not in api_url.lower():
        data.update(
            {
                "response_format": "verbose_json",
                "timestamp_granularities[]": "segment",
            }
        )
    return data


def ensure_retryable_response(response: httpx.Response) -> httpx.Response:
    if response.is_success:
        return response
    message = f"provider returned HTTP {response.status_code}: {response.text[:500]}"
    if response.status_code in _RETRYABLE_STATUS_CODES:
        raise RetryableExternalError(message)
    raise PermanentExternalError(message)


def _post_with_classified_errors(**kwargs: Any) -> httpx.Response:
    try:
        response = httpx.request(**kwargs)
    except (httpx.TimeoutException, httpx.NetworkError) as exc:
        raise RetryableExternalError(str(exc)) from exc
    return ensure_retryable_response(response)


class OpenAICompatibleProvider:
    def route_tool(self, question: str) -> str | None:
        settings = get_settings()
        if not settings.llm_api_key or not settings.llm_base_url:
            return None
        tools = [
            _tool_definition(
                "search_transcript",
                "Search timestamped transcript evidence for content questions.",
            ),
            _tool_definition(
                "get_video_metadata",
                "Get video filename, size, duration, and state.",
            ),
            _tool_definition("get_video_summary", "Get the generated video summary."),
            _tool_definition("get_task_status", "Get the latest parsing task status and progress."),
        ]
        response = _post_with_classified_errors(
            url=f"{settings.llm_base_url.rstrip('/')}/chat/completions",
            method="POST",
            headers={"Authorization": f"Bearer {settings.llm_api_key}"},
            json={
                "model": settings.llm_model,
                "messages": [
                    {
                        "role": "system",
                        "content": "Select exactly one tool for the user's video question.",
                    },
                    {"role": "user", "content": question},
                ],
                "tools": tools,
                "tool_choice": "auto",
                "temperature": 0,
            },
            timeout=60,
        )
        tool_calls = response.json()["choices"][0]["message"].get("tool_calls") or []
        if not tool_calls:
            return None
        tool_name = str(tool_calls[0]["function"]["name"])
        return {
            "search_transcript": "TRANSCRIPT",
            "get_video_metadata": "METADATA",
            "get_video_summary": "SUMMARY",
            "get_task_status": "TASK_STATUS",
        }.get(tool_name)

    def answer_question(self, question: str, evidence: list[Evidence]) -> str | None:
        settings = get_settings()
        if not settings.llm_api_key or not settings.llm_base_url or not evidence:
            return None
        context = "\n".join(
            f"{item.citation} {item.text}"
            for item in evidence
        )
        response = httpx.post(
            f"{settings.llm_base_url.rstrip('/')}/chat/completions",
            headers={"Authorization": f"Bearer {settings.llm_api_key}"},
            json={
                "model": settings.llm_model,
                "messages": [
                    {
                        "role": "system",
                        "content": (
                            "仅根据提供的视频字幕证据回答。每个结论必须引用原样时间戳；"
                            "不得编造或使用证据列表之外的时间戳。"
                        ),
                    },
                    {
                        "role": "user",
                        "content": f"问题：{question}\n\n证据：\n{context}",
                    },
                ],
                "temperature": 0.1,
            },
            timeout=120,
        )
        response.raise_for_status()
        return str(response.json()["choices"][0]["message"]["content"]).strip()

    def transcribe(self, audio_path: str) -> list[AsrSegment]:
        settings = get_settings()
        if not settings.asr_api_url or not settings.asr_api_key:
            raise ProviderConfigurationError(
                "ASR is not configured; set DOVIDEO_ASR_API_URL and DOVIDEO_ASR_API_KEY"
            )
        with Path(audio_path).open("rb") as audio:
            response = _post_with_classified_errors(
                url=settings.asr_api_url,
                method="POST",
                headers={"Authorization": f"Bearer {settings.asr_api_key}"},
                files={"file": (Path(audio_path).name, audio, "audio/mpeg")},
                data=build_asr_form_data(settings.asr_api_url, settings.asr_model),
                timeout=600,
            )
        payload = response.json()
        segments = payload.get("segments") or []
        if segments:
            return [
                AsrSegment(
                    start_ms=round(float(segment["start"]) * 1_000),
                    end_ms=round(float(segment["end"]) * 1_000),
                    text=str(segment["text"]).strip(),
                )
                for segment in segments
                if str(segment.get("text", "")).strip()
            ]
        text = str(payload.get("text", "")).strip()
        return [AsrSegment(start_ms=0, end_ms=0, text=text)] if text else []

    def summarize(self, transcript: str) -> str:
        settings = get_settings()
        if not settings.llm_api_key or not settings.llm_base_url:
            return _extractive_summary(transcript)
        response = _post_with_classified_errors(
            url=f"{settings.llm_base_url.rstrip('/')}/chat/completions",
            method="POST",
            headers={"Authorization": f"Bearer {settings.llm_api_key}"},
            json={
                "model": settings.llm_model,
                "messages": [
                    {
                        "role": "system",
                        "content": "你是视频内容分析助手。仅基于字幕生成简洁、结构化的中文摘要。",
                    },
                    {"role": "user", "content": transcript[:40_000]},
                ],
                "temperature": 0.1,
            },
            timeout=180,
        )
        return str(response.json()["choices"][0]["message"]["content"]).strip()


def _extractive_summary(transcript: str) -> str:
    normalized = " ".join(transcript.split())
    if not normalized:
        return "字幕为空，无法生成摘要。"
    return f"自动摘要（未配置 LLM）：{normalized[:600]}"


def _tool_definition(name: str, description: str) -> dict[str, object]:
    return {
        "type": "function",
        "function": {
            "name": name,
            "description": description,
            "parameters": {
                "type": "object",
                "properties": {
                    "video_id": {"type": "string"},
                    "query": {"type": "string"},
                },
                "required": ["video_id"],
            },
        },
    }
