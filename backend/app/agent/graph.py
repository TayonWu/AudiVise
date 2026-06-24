import json
import re
from collections.abc import Callable
from dataclasses import dataclass
from time import perf_counter
from typing import Any, Protocol

from langgraph.graph import END, START, StateGraph
from sqlalchemy.orm import Session

from app.agent.state import AgentState
from app.agent.tools import SearchTranscriptInput, SearchTranscriptTool, VideoToolInput
from app.core.config import get_settings
from app.integrations.ai_provider import OpenAICompatibleProvider
from app.models import AgentTrace, AnalysisTask, Video
from app.services.retrieval import Evidence


@dataclass(frozen=True, slots=True)
class AgentResult:
    trace_id: str
    answer: str
    citations: list[str]
    evidence: list[Evidence]


class AgentModel(Protocol):
    def route_tool(self, question: str) -> str | None: ...

    def answer_question(self, question: str, evidence: list[Evidence]) -> str | None: ...


class VideoAgent:
    def __init__(
        self,
        db: Session,
        *,
        search_transcript: Callable[[str, str], list[Evidence]],
        model: AgentModel | None = None,
    ) -> None:
        self.db = db
        self.search_tool = SearchTranscriptTool(search_transcript)
        self.model = model or OpenAICompatibleProvider()
        self.graph = self._build_graph()

    def invoke(self, video_id: str, question: str) -> AgentResult:
        video = self.db.get(Video, video_id)
        if video is None:
            raise LookupError(f"video {video_id} does not exist")

        settings = get_settings()
        trace = AgentTrace(
            video_id=video_id,
            question=question,
            model_name=settings.llm_model if settings.llm_api_key else "deterministic-fallback",
        )
        self.db.add(trace)
        self.db.commit()
        self.db.refresh(trace)
        started = perf_counter()

        initial: AgentState = {
            "trace_id": trace.id,
            "video_id": video_id,
            "question": question,
            "intent": "",
            "node_timings": [],
            "tool_calls": [],
            "evidence": [],
            "tool_result": {},
            "answer": "",
            "citations": [],
        }
        try:
            result = self.graph.invoke(initial)
            trace.status = "SUCCEEDED"
            trace.intent = result["intent"]
            trace.node_timings_json = json.dumps(
                result["node_timings"],
                ensure_ascii=False,
            )
            trace.tool_calls_json = json.dumps(result["tool_calls"], ensure_ascii=False)
            trace.evidence_ids_json = json.dumps(
                [item.chunk_id for item in result["evidence"]],
                ensure_ascii=False,
            )
            trace.answer = result["answer"]
            trace.latency_ms = int((perf_counter() - started) * 1_000)
            self.db.commit()
            return AgentResult(
                trace_id=trace.id,
                answer=result["answer"],
                citations=result["citations"],
                evidence=result["evidence"],
            )
        except Exception as exc:
            trace.status = "FAILED"
            trace.error_type = type(exc).__name__
            trace.error_message = str(exc)
            trace.latency_ms = int((perf_counter() - started) * 1_000)
            self.db.commit()
            raise

    def _build_graph(self) -> Any:
        graph = StateGraph(AgentState)
        graph.add_node(
            "analyze_question",
            self._timed_node("analyze_question", self._analyze_question),
        )
        graph.add_node(
            "search_evidence",
            self._timed_node("search_evidence", self._search_evidence),
        )
        graph.add_node("get_summary", self._timed_node("get_summary", self._get_summary))
        graph.add_node("get_metadata", self._timed_node("get_metadata", self._get_metadata))
        graph.add_node(
            "get_task_status",
            self._timed_node("get_task_status", self._get_task_status),
        )
        graph.add_node(
            "generate_answer",
            self._timed_node("generate_answer", self._generate_answer),
        )
        graph.add_edge(START, "analyze_question")
        graph.add_conditional_edges(
            "analyze_question",
            lambda state: state["intent"],
            {
                "TRANSCRIPT": "search_evidence",
                "SUMMARY": "get_summary",
                "METADATA": "get_metadata",
                "TASK_STATUS": "get_task_status",
            },
        )
        for node in ("search_evidence", "get_summary", "get_metadata", "get_task_status"):
            graph.add_edge(node, "generate_answer")
        graph.add_edge("generate_answer", END)
        return graph.compile()

    @staticmethod
    def _timed_node(
        name: str,
        handler: Callable[[AgentState], dict[str, object]],
    ) -> Any:
        def invoke(state: AgentState) -> dict[str, object]:
            started = perf_counter()
            result = handler(state)
            timing = {
                "node": name,
                "duration_ms": int((perf_counter() - started) * 1_000),
            }
            return {
                **result,
                "node_timings": [*state["node_timings"], timing],
            }

        return invoke

    def _analyze_question(self, state: AgentState) -> dict[str, object]:
        question = state["question"].lower()
        model_intent = self.model.route_tool(state["question"])
        if model_intent in {"TRANSCRIPT", "SUMMARY", "METADATA", "TASK_STATUS"}:
            return {"intent": model_intent}
        if any(keyword in question for keyword in ("摘要", "总结", "概括", "summary")):
            return {"intent": "SUMMARY"}
        if any(keyword in question for keyword in ("状态", "进度", "完成了吗", "task")):
            return {"intent": "TASK_STATUS"}
        if any(keyword in question for keyword in ("文件", "时长", "大小", "格式", "metadata")):
            return {"intent": "METADATA"}
        return {"intent": "TRANSCRIPT"}

    def _search_evidence(self, state: AgentState) -> dict[str, object]:
        payload = SearchTranscriptInput(
            video_id=state["video_id"],
            query=state["question"],
        )
        evidence = self.search_tool.invoke(payload)
        return {
            "evidence": evidence,
            "tool_calls": [
                {
                    "name": self.search_tool.name,
                    "arguments": payload.model_dump(),
                    "result_count": len(evidence),
                }
            ],
        }

    def _get_summary(self, state: AgentState) -> dict[str, object]:
        payload = VideoToolInput(video_id=state["video_id"])
        video = self.db.get(Video, payload.video_id)
        result = {"summary": video.summary if video else None}
        return {
            "tool_result": result,
            "tool_calls": [
                {"name": "get_video_summary", "arguments": payload.model_dump(), "result": result}
            ],
        }

    def _get_metadata(self, state: AgentState) -> dict[str, object]:
        payload = VideoToolInput(video_id=state["video_id"])
        video = self.db.get(Video, payload.video_id)
        result = (
            {
                "filename": video.filename,
                "size_bytes": video.size_bytes,
                "duration_seconds": video.duration_seconds,
                "status": video.status.value,
            }
            if video
            else {}
        )
        return {
            "tool_result": result,
            "tool_calls": [
                {"name": "get_video_metadata", "arguments": payload.model_dump(), "result": result}
            ],
        }

    def _get_task_status(self, state: AgentState) -> dict[str, object]:
        from sqlalchemy import select

        payload = VideoToolInput(video_id=state["video_id"])
        task = self.db.scalar(
            select(AnalysisTask)
            .where(AnalysisTask.video_id == payload.video_id)
            .order_by(AnalysisTask.created_at.desc())
            .limit(1)
        )
        result = (
            {
                "task_id": task.id,
                "status": task.status.value,
                "progress": task.progress,
                "current_stage": task.current_stage,
            }
            if task
            else {"status": "NOT_STARTED", "progress": 0}
        )
        return {
            "tool_result": result,
            "tool_calls": [
                {"name": "get_task_status", "arguments": payload.model_dump(), "result": result}
            ],
        }

    def _generate_answer(self, state: AgentState) -> dict[str, object]:
        if state["intent"] != "TRANSCRIPT":
            result = state["tool_result"]
            if state["intent"] == "SUMMARY":
                answer = str(result.get("summary") or "该视频尚未生成摘要。")
            elif state["intent"] == "METADATA":
                answer = (
                    f"文件名：{result.get('filename')}；大小：{result.get('size_bytes')} 字节；"
                    f"时长：{result.get('duration_seconds') or '未知'} 秒；"
                    f"状态：{result.get('status')}。"
                )
            else:
                answer = (
                    f"解析状态：{result.get('status')}，进度：{result.get('progress', 0)}%，"
                    f"当前阶段：{result.get('current_stage') or '尚未开始'}。"
                )
            return {"answer": answer, "citations": []}

        evidence = state["evidence"]
        if not evidence:
            return {
                "answer": "无法从当前视频证据中确认该问题。",
                "citations": [],
            }

        selected = evidence[:3]
        model_answer = self.model.answer_question(state["question"], selected)
        allowed_citations = {item.citation for item in selected}
        used_citations = set(re.findall(r"\[\d{2,}:\d{2}-\d{2,}:\d{2}\]", model_answer or ""))
        if model_answer and used_citations and used_citations.issubset(allowed_citations):
            answer = model_answer
        else:
            answer_body = "\n".join(item.text for item in selected)
            citation_text = " ".join(item.citation for item in selected)
            answer = f"{answer_body} {citation_text}"
        citations = [item.chunk_id for item in selected]
        allowed = {item.chunk_id for item in evidence}
        if not set(citations).issubset(allowed):
            raise ValueError("answer contains citations outside the retrieved evidence set")
        return {
            "answer": answer,
            "citations": citations,
        }
