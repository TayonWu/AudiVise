from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.api.videos import get_task_dispatcher
from app.main import create_app


def _create_video(client: TestClient) -> str:
    upload = client.post(
        "/api/uploads",
        json={
            "filename": "agent.mp4",
            "content_type": "video/mp4",
            "size_bytes": 4096,
        },
    ).json()
    completed = client.post(
        f"/api/uploads/{upload['id']}/complete",
        json={"parts": [{"part_number": 1, "etag": "etag"}]},
    ).json()
    return completed["video_id"]


def test_analysis_creation_is_idempotent_while_task_is_active(client: TestClient) -> None:
    video_id = _create_video(client)

    first = client.post(
        f"/api/videos/{video_id}/analysis",
        headers={"Idempotency-Key": "analysis-request-1"},
    )
    second = client.post(
        f"/api/videos/{video_id}/analysis",
        headers={"Idempotency-Key": "analysis-request-1"},
    )

    assert first.status_code == 202
    assert second.status_code == 202
    assert first.json()["task_id"] == second.json()["task_id"]
    assert first.json()["status"] == "PENDING"


def test_analysis_reuses_active_task_across_different_idempotency_keys(
    client: TestClient,
) -> None:
    video_id = _create_video(client)

    first = client.post(
        f"/api/videos/{video_id}/analysis",
        headers={"Idempotency-Key": "concurrent-request-1"},
    )
    second = client.post(
        f"/api/videos/{video_id}/analysis",
        headers={"Idempotency-Key": "concurrent-request-2"},
    )

    assert first.status_code == 202
    assert second.status_code == 202
    assert second.json()["task_id"] == first.json()["task_id"]


def test_task_status_can_be_queried(client: TestClient) -> None:
    video_id = _create_video(client)
    task = client.post(
        f"/api/videos/{video_id}/analysis",
        headers={"Idempotency-Key": "analysis-request-2"},
    ).json()

    response = client.get(f"/api/tasks/{task['task_id']}")

    assert response.status_code == 200
    assert response.json()["video_id"] == video_id
    assert response.json()["progress"] == 0


def test_new_analysis_is_dispatched_once(db_session: Session) -> None:
    dispatched: list[str] = []
    app = create_app()

    def override_db():
        yield db_session

    class RecordingDispatcher:
        def dispatch(self, task_id: str) -> None:
            dispatched.append(task_id)

    from app.core.database import get_db

    app.dependency_overrides[get_db] = override_db
    app.dependency_overrides[get_task_dispatcher] = RecordingDispatcher
    with TestClient(app) as local_client:
        video_id = _create_video(local_client)
        first = local_client.post(
            f"/api/videos/{video_id}/analysis",
            headers={"Idempotency-Key": "dispatch-1"},
        )
        second = local_client.post(
            f"/api/videos/{video_id}/analysis",
            headers={"Idempotency-Key": "dispatch-1"},
        )

    assert dispatched == [first.json()["task_id"]]
    assert second.json()["task_id"] == first.json()["task_id"]
