from fastapi.testclient import TestClient

from app.api.tasks import should_close_task_stream
from app.models import TaskStatus


def test_pending_task_stream_stays_open_by_default() -> None:
    assert should_close_task_stream(TaskStatus.PENDING, once=False) is False
    assert should_close_task_stream(TaskStatus.PENDING, once=True) is True
    assert should_close_task_stream(TaskStatus.SUCCEEDED, once=False) is True


def test_task_events_emit_current_state(client: TestClient) -> None:
    upload = client.post(
        "/api/uploads",
        json={
            "filename": "events.mp4",
            "content_type": "video/mp4",
            "size_bytes": 100,
        },
    ).json()
    video_id = client.post(
        f"/api/uploads/{upload['id']}/complete",
        json={"parts": [{"part_number": 1, "etag": "etag"}]},
    ).json()["video_id"]
    task_id = client.post(
        f"/api/videos/{video_id}/analysis",
        headers={"Idempotency-Key": "events-1"},
    ).json()["task_id"]

    with client.stream("GET", f"/api/tasks/{task_id}/events?once=true") as response:
        body = "".join(response.iter_text())

    assert response.status_code == 200
    assert "event: status" in body
    assert '"status":"PENDING"' in body
