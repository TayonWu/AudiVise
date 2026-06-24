import json
from collections.abc import Iterator

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from sse_starlette.sse import EventSourceResponse

from app.agent.graph import VideoAgent
from app.core.database import get_db
from app.models import AgentTrace
from app.schemas.chat import (
    ChatRequest,
    ChatResponse,
    CitationResponse,
    TraceResponse,
)
from app.services.hybrid_retrieval import hybrid_search

router = APIRouter(tags=["agent"])


def _build_agent(db: Session) -> VideoAgent:
    return VideoAgent(
        db,
        search_transcript=lambda selected_video_id, query: hybrid_search(
            db, selected_video_id, query
        ),
    )


@router.post("/videos/{video_id}/chat", response_model=ChatResponse)
def chat(
    video_id: str,
    payload: ChatRequest,
    db: Session = Depends(get_db),
) -> ChatResponse:
    agent = _build_agent(db)
    try:
        result = agent.invoke(video_id, payload.question)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    return ChatResponse(
        trace_id=result.trace_id,
        answer=result.answer,
        citations=[
            CitationResponse(
                chunk_id=item.chunk_id,
                start_ms=item.start_ms,
                end_ms=item.end_ms,
                text=item.text,
                score=item.score,
            )
            for item in result.evidence
            if item.chunk_id in result.citations
        ],
    )


@router.post("/videos/{video_id}/chat/stream")
def stream_chat(
    video_id: str,
    payload: ChatRequest,
    db: Session = Depends(get_db),
) -> EventSourceResponse:
    def generate() -> Iterator[dict[str, str]]:
        yield {
            "event": "status",
            "data": json.dumps(
                {"stage": "analyzing", "message": "正在分析问题并选择工具"},
                ensure_ascii=False,
            ),
        }
        try:
            result = _build_agent(db).invoke(video_id, payload.question)
            trace = db.get(AgentTrace, result.trace_id)
            for tool_call in json.loads(trace.tool_calls_json or "[]") if trace else []:
                yield {
                    "event": "tool",
                    "data": json.dumps(tool_call, ensure_ascii=False),
                }
            for evidence in result.evidence:
                yield {
                    "event": "evidence",
                    "data": json.dumps(
                        {
                            "chunk_id": evidence.chunk_id,
                            "start_ms": evidence.start_ms,
                            "end_ms": evidence.end_ms,
                            "text": evidence.text,
                            "score": evidence.score,
                        },
                        ensure_ascii=False,
                    ),
                }
            yield {
                "event": "token",
                "data": json.dumps({"text": result.answer}, ensure_ascii=False),
            }
            yield {
                "event": "final",
                "data": json.dumps(
                    {
                        "trace_id": result.trace_id,
                        "answer": result.answer,
                        "citations": result.citations,
                    },
                    ensure_ascii=False,
                ),
            }
        except Exception as exc:
            yield {
                "event": "error",
                "data": json.dumps(
                    {"type": type(exc).__name__, "message": str(exc)},
                    ensure_ascii=False,
                ),
            }

    return EventSourceResponse(generate())


@router.get("/traces/{trace_id}", response_model=TraceResponse)
def get_trace(trace_id: str, db: Session = Depends(get_db)) -> TraceResponse:
    trace = db.get(AgentTrace, trace_id)
    if trace is None:
        raise HTTPException(status_code=404, detail="trace not found")
    return TraceResponse(
        id=trace.id,
        video_id=trace.video_id,
        question=trace.question,
        status=trace.status,
        intent=trace.intent,
        model_name=trace.model_name,
        node_timings=json.loads(trace.node_timings_json or "[]"),
        tool_calls=json.loads(trace.tool_calls_json or "[]"),
        evidence_ids=json.loads(trace.evidence_ids_json or "[]"),
        answer=trace.answer,
        error_type=trace.error_type,
        error_message=trace.error_message,
        latency_ms=trace.latency_ms,
    )
