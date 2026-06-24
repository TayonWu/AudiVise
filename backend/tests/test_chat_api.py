from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.models import TranscriptChunk, Video


def test_chat_returns_grounded_answer_and_trace(
    client: TestClient,
    db_session: Session,
) -> None:
    video = Video(
        filename="chat.mp4",
        content_type="video/mp4",
        size_bytes=100,
        object_key="videos/chat.mp4",
    )
    db_session.add(video)
    db_session.flush()
    db_session.add(
        TranscriptChunk(
            video_id=video.id,
            chunk_index=0,
            start_ms=1_000,
            end_ms=5_000,
            text="LangGraph 负责 Agent 工作流中的状态和条件路由。",
        )
    )
    db_session.commit()

    response = client.post(
        f"/api/videos/{video.id}/chat",
        json={"question": "LangGraph 有什么作用？"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["citations"][0]["start_ms"] == 1_000
    assert "[00:01-00:05]" in body["answer"]

    trace = client.get(f"/api/traces/{body['trace_id']}")
    assert trace.status_code == 200
    assert trace.json()["status"] == "SUCCEEDED"
    assert trace.json()["intent"] == "TRANSCRIPT"
    assert [item["node"] for item in trace.json()["node_timings"]] == [
        "analyze_question",
        "search_evidence",
        "generate_answer",
    ]


def test_chat_stream_emits_agent_event_types(
    client: TestClient,
    db_session: Session,
) -> None:
    video = Video(
        filename="stream.mp4",
        content_type="video/mp4",
        size_bytes=100,
        object_key="videos/stream.mp4",
        summary="这是一个流式问答演示。",
    )
    db_session.add(video)
    db_session.commit()

    with client.stream(
        "POST",
        f"/api/videos/{video.id}/chat/stream",
        json={"question": "请总结视频"},
    ) as response:
        body = "".join(response.iter_text())

    assert response.status_code == 200
    assert "event: status" in body
    assert "event: tool" in body
    assert "event: final" in body
