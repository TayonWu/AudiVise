from fastapi.testclient import TestClient


def test_upload_accepts_audio_and_rejects_non_media(client: TestClient) -> None:
    audio = client.post(
        "/api/uploads",
        json={
            "filename": "interview.mp3",
            "content_type": "audio/mpeg",
            "size_bytes": 2048,
        },
    )
    document = client.post(
        "/api/uploads",
        json={
            "filename": "notes.txt",
            "content_type": "text/plain",
            "size_bytes": 128,
        },
    )

    assert audio.status_code == 201
    assert document.status_code == 422


def test_complete_upload_is_idempotent(client: TestClient) -> None:
    created = client.post(
        "/api/uploads",
        json={
            "filename": "interview.mp4",
            "content_type": "video/mp4",
            "size_bytes": 1024,
        },
    )
    assert created.status_code == 201
    upload = created.json()
    part = client.post(
        f"/api/uploads/{upload['id']}/parts",
        json={"part_number": 1},
    )
    assert part.status_code == 200
    assert part.json()["url"].startswith("memory://")

    first = client.post(
        f"/api/uploads/{upload['id']}/complete",
        json={"parts": [{"part_number": 1, "etag": "etag-1"}]},
    )
    second = client.post(
        f"/api/uploads/{upload['id']}/complete",
        json={"parts": [{"part_number": 1, "etag": "etag-1"}]},
    )

    assert first.status_code == 200
    assert second.status_code == 200
    assert first.json()["video_id"] == second.json()["video_id"]
    assert second.json()["status"] == "COMPLETED"


def test_upload_session_tracks_confirmed_parts_for_resume(client: TestClient) -> None:
    upload = client.post(
        "/api/uploads",
        json={
            "filename": "resume.mp4",
            "content_type": "video/mp4",
            "size_bytes": 20 * 1024 * 1024,
        },
    ).json()

    confirmed = client.put(
        f"/api/uploads/{upload['id']}/parts/1",
        json={"etag": "etag-1"},
    )
    resumed = client.get(f"/api/uploads/{upload['id']}")

    assert confirmed.status_code == 200
    assert resumed.status_code == 200
    assert resumed.json()["completed_parts"] == [{"part_number": 1, "etag": "etag-1"}]
    assert resumed.json()["status"] == "INITIATED"


def test_list_videos_returns_completed_upload(client: TestClient) -> None:
    upload = client.post(
        "/api/uploads",
        json={
            "filename": "demo.mp4",
            "content_type": "video/mp4",
            "size_bytes": 2048,
        },
    ).json()
    client.post(
        f"/api/uploads/{upload['id']}/complete",
        json={"parts": [{"part_number": 1, "etag": "etag-1"}]},
    )

    response = client.get("/api/videos")

    assert response.status_code == 200
    assert response.json()[0]["filename"] == "demo.mp4"
    assert response.json()[0]["status"] == "UPLOADED"

    playback = client.get(f"/api/videos/{response.json()[0]['id']}/playback")
    assert playback.status_code == 200
    assert playback.json()["url"].startswith("memory://")
