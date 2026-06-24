from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.models import TranscriptChunk, Video


def test_list_transcript_chunks_in_timestamp_order(
    client: TestClient,
    db_session: Session,
) -> None:
    video = Video(
        filename="agent-demo.mp4",
        content_type="video/mp4",
        size_bytes=1024,
        object_key="videos/agent-demo.mp4",
    )
    db_session.add(video)
    db_session.flush()
    db_session.add_all(
        [
            TranscriptChunk(
                id=f"{video.id}:1",
                video_id=video.id,
                chunk_index=1,
                start_ms=12_000,
                end_ms=18_000,
                text="第二段字幕",
            ),
            TranscriptChunk(
                id=f"{video.id}:0",
                video_id=video.id,
                chunk_index=0,
                start_ms=1_000,
                end_ms=6_000,
                text="第一段字幕",
            ),
        ]
    )
    db_session.commit()

    response = client.get(f"/api/videos/{video.id}/transcript")

    assert response.status_code == 200
    assert response.json() == [
        {
            "chunk_id": f"{video.id}:0",
            "chunk_index": 0,
            "start_ms": 1_000,
            "end_ms": 6_000,
            "text": "第一段字幕",
        },
        {
            "chunk_id": f"{video.id}:1",
            "chunk_index": 1,
            "start_ms": 12_000,
            "end_ms": 18_000,
            "text": "第二段字幕",
        },
    ]


def test_transcript_returns_not_found_for_unknown_video(client: TestClient) -> None:
    response = client.get("/api/videos/missing/transcript")

    assert response.status_code == 404
