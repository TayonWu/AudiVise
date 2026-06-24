import pytest
from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.agent.graph import VideoAgent
from app.agent.tools import SearchTranscriptInput
from app.models import AgentTrace, Video
from app.services.retrieval import Evidence


def test_tool_input_rejects_empty_query() -> None:
    with pytest.raises(ValidationError):
        SearchTranscriptInput(video_id="video-1", query=" ")


def test_agent_returns_timestamped_evidence_and_persists_trace(db_session: Session) -> None:
    video = Video(
        filename="agent.mp4",
        content_type="video/mp4",
        size_bytes=100,
        object_key="videos/agent.mp4",
    )
    db_session.add(video)
    db_session.commit()

    agent = VideoAgent(
        db_session,
        search_transcript=lambda video_id, query: [
            Evidence(
                chunk_id=f"{video_id}:0",
                start_ms=12_000,
                end_ms=18_000,
                text="Celery 将耗时的视频处理任务从 API 请求中解耦。",
                score=0.93,
            )
        ],
    )

    result = agent.invoke(video.id, "Celery 在项目里有什么作用？")

    assert result.answer.endswith("[00:12-00:18]")
    assert result.citations == [f"{video.id}:0"]
    trace = db_session.get(AgentTrace, result.trace_id)
    assert trace is not None
    assert trace.status == "SUCCEEDED"
    assert trace.intent == "TRANSCRIPT"
    assert '"analyze_question"' in (trace.node_timings_json or "")
    assert '"search_evidence"' in (trace.node_timings_json or "")
    assert '"generate_answer"' in (trace.node_timings_json or "")
    assert video.id in (trace.evidence_ids_json or "")


def test_agent_refuses_to_guess_without_evidence(db_session: Session) -> None:
    video = Video(
        filename="empty.mp4",
        content_type="video/mp4",
        size_bytes=100,
        object_key="videos/empty.mp4",
    )
    db_session.add(video)
    db_session.commit()
    agent = VideoAgent(db_session, search_transcript=lambda _video_id, _query: [])

    result = agent.invoke(video.id, "视频里提到了什么薪资？")

    assert result.citations == []
    assert "无法从当前视频证据中确认" in result.answer


def test_agent_routes_summary_question_to_summary_tool(db_session: Session) -> None:
    video = Video(
        filename="summary.mp4",
        content_type="video/mp4",
        size_bytes=100,
        object_key="videos/summary.mp4",
        summary="视频介绍了 FastAPI、Celery 和 LangGraph 的协作方式。",
    )
    db_session.add(video)
    db_session.commit()
    searches: list[str] = []
    agent = VideoAgent(
        db_session,
        search_transcript=lambda _video_id, query: searches.append(query) or [],
    )

    result = agent.invoke(video.id, "请给我视频摘要")

    assert "FastAPI" in result.answer
    assert searches == []


class RecordingAgentModel:
    def __init__(self) -> None:
        self.questions: list[str] = []

    def route_tool(self, question: str) -> str | None:
        self.questions.append(question)
        return "TRANSCRIPT"

    def answer_question(self, question: str, evidence: list[Evidence]) -> str | None:
        return f"Celery 用于异步处理。{evidence[0].citation}"


def test_agent_uses_model_tool_routing_and_grounded_generation(db_session: Session) -> None:
    video = Video(
        filename="function-calling.mp4",
        content_type="video/mp4",
        size_bytes=100,
        object_key="videos/function-calling.mp4",
    )
    db_session.add(video)
    db_session.commit()
    model = RecordingAgentModel()
    agent = VideoAgent(
        db_session,
        search_transcript=lambda video_id, _query: [
            Evidence(f"{video_id}:0", 2_000, 4_000, "Celery 异步执行任务。", 0.9)
        ],
        model=model,
    )

    result = agent.invoke(video.id, "Celery 有什么作用？")

    assert model.questions == ["Celery 有什么作用？"]
    assert result.answer == "Celery 用于异步处理。[00:02-00:04]"


def test_agent_persists_classified_exception_details(db_session: Session) -> None:
    video = Video(
        filename="failed-agent.mp4",
        content_type="video/mp4",
        size_bytes=100,
        object_key="videos/failed-agent.mp4",
    )
    db_session.add(video)
    db_session.commit()
    agent = VideoAgent(
        db_session,
        search_transcript=lambda _video_id, _query: (_ for _ in ()).throw(
            RuntimeError("vector store unavailable")
        ),
    )

    with pytest.raises(RuntimeError, match="vector store unavailable"):
        agent.invoke(video.id, "视频讲了什么？")

    trace = db_session.scalar(
        select(AgentTrace)
        .where(AgentTrace.video_id == video.id)
        .order_by(AgentTrace.created_at.desc())
    )
    assert trace is not None
    assert trace.status == "FAILED"
    assert trace.error_type == "RuntimeError"
    assert trace.error_message == "vector store unavailable"
