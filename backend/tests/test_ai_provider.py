import httpx
import pytest

import app.integrations.ai_provider as ai_provider
from app.integrations.ai_provider import (
    OpenAICompatibleProvider,
    PermanentExternalError,
    RetryableExternalError,
    build_asr_form_data,
    ensure_retryable_response,
)


def _response(status_code: int) -> httpx.Response:
    return httpx.Response(
        status_code,
        request=httpx.Request("POST", "https://example.test/v1"),
        text="provider error",
    )


@pytest.mark.parametrize("status_code", [408, 409, 425, 429, 500, 502, 503, 504])
def test_retryable_provider_statuses_raise_retryable_error(status_code: int) -> None:
    with pytest.raises(RetryableExternalError):
        ensure_retryable_response(_response(status_code))


@pytest.mark.parametrize("status_code", [400, 401, 403, 404, 422])
def test_permanent_provider_statuses_do_not_retry(status_code: int) -> None:
    with pytest.raises(PermanentExternalError):
        ensure_retryable_response(_response(status_code))


def test_successful_provider_response_is_returned() -> None:
    response = _response(200)

    assert ensure_retryable_response(response) is response


def test_siliconflow_asr_uses_only_supported_form_fields() -> None:
    data = build_asr_form_data(
        "https://api.siliconflow.cn/v1/audio/transcriptions",
        "FunAudioLLM/SenseVoiceSmall",
    )

    assert data == {"model": "FunAudioLLM/SenseVoiceSmall"}


def test_openai_asr_keeps_verbose_segment_timestamps() -> None:
    data = build_asr_form_data(
        "https://api.openai.com/v1/audio/transcriptions",
        "whisper-1",
    )

    assert data["response_format"] == "verbose_json"
    assert data["timestamp_granularities[]"] == "segment"


def test_deepseek_tool_routing_uses_auto_tool_choice(monkeypatch) -> None:
    captured: dict[str, object] = {}

    def fake_request(**kwargs):
        captured.update(kwargs)
        return httpx.Response(
            200,
            request=httpx.Request("POST", str(kwargs["url"])),
            json={"choices": [{"message": {"tool_calls": []}}]},
        )

    monkeypatch.setattr(ai_provider, "_post_with_classified_errors", fake_request)
    monkeypatch.setattr(
        ai_provider,
        "get_settings",
        lambda: type(
            "Settings",
            (),
            {
                "llm_api_key": "test-key",
                "llm_base_url": "https://api.deepseek.com",
                "llm_model": "deepseek-v4-pro",
            },
        )(),
    )

    result = OpenAICompatibleProvider().route_tool("What is the objective?")

    assert result is None
    assert captured["json"]["tool_choice"] == "auto"
