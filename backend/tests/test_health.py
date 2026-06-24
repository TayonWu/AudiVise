from fastapi.testclient import TestClient

from app.main import create_app


def test_health_reports_service_status() -> None:
    client = TestClient(create_app())

    response = client.get("/api/health")

    assert response.status_code == 200
    assert response.json() == {
        "service": "audivise",
        "status": "ok",
    }


def test_openapi_uses_audivise_brand() -> None:
    client = TestClient(create_app())

    response = client.get("/openapi.json")

    assert response.status_code == 200
    assert response.json()["info"]["title"] == "AudiVise API"
