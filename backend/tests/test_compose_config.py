import tomllib
from pathlib import Path

import yaml


def test_compose_passes_minio_credentials_to_api_and_worker() -> None:
    compose_path = Path(__file__).parents[2] / "docker-compose.yml"
    compose = yaml.safe_load(compose_path.read_text(encoding="utf-8"))

    api_environment = compose["services"]["api"]["environment"]
    worker_environment = compose["services"]["worker"]["environment"]

    assert api_environment["DOVIDEO_MINIO_ACCESS_KEY"] == "${MINIO_ROOT_USER:-minioadmin}"
    assert (
        api_environment["DOVIDEO_MINIO_SECRET_KEY"]
        == "${MINIO_ROOT_PASSWORD:-minioadmin}"
    )
    assert worker_environment["DOVIDEO_MINIO_ACCESS_KEY"] == api_environment[
        "DOVIDEO_MINIO_ACCESS_KEY"
    ]
    assert worker_environment["DOVIDEO_MINIO_SECRET_KEY"] == api_environment[
        "DOVIDEO_MINIO_SECRET_KEY"
    ]


def test_compose_configures_global_minio_cors_without_bucket_api() -> None:
    compose_path = Path(__file__).parents[2] / "docker-compose.yml"
    compose = yaml.safe_load(compose_path.read_text(encoding="utf-8"))

    minio_environment = compose["services"]["minio"]["environment"]
    minio_init = compose["services"]["minio-init"]

    assert "http://localhost:8080" in minio_environment["MINIO_API_CORS_ALLOW_ORIGIN"]
    assert "mc cors set" not in minio_init["entrypoint"]


def test_compose_initializes_artifact_volume_for_non_root_backend() -> None:
    compose_path = Path(__file__).parents[2] / "docker-compose.yml"
    compose = yaml.safe_load(compose_path.read_text(encoding="utf-8"))

    artifact_init = compose["services"]["artifact-init"]

    assert artifact_init["user"] == "0:0"
    assert "chown" in artifact_init["command"]
    assert artifact_init["volumes"] == ["artifact_data:/app/artifacts"]
    assert (
        compose["services"]["api"]["depends_on"]["artifact-init"]["condition"]
        == "service_completed_successfully"
    )
    assert (
        compose["services"]["worker"]["depends_on"]["artifact-init"]["condition"]
        == "service_completed_successfully"
    )


def test_qdrant_client_minor_matches_server_image() -> None:
    project_root = Path(__file__).parents[2]
    compose = yaml.safe_load(
        (project_root / "docker-compose.yml").read_text(encoding="utf-8")
    )
    pyproject = tomllib.loads(
        (project_root / "backend" / "pyproject.toml").read_text(encoding="utf-8")
    )

    dependencies = pyproject["project"]["dependencies"]

    assert compose["services"]["qdrant"]["image"] == "qdrant/qdrant:v1.15.4"
    assert "qdrant-client>=1.15,<1.16" in dependencies
