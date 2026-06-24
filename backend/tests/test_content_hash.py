from pathlib import Path

from app.services.production_pipeline import sha256_file


def test_sha256_file_is_stable(tmp_path: Path) -> None:
    video = tmp_path / "video.bin"
    video.write_bytes(b"dovideo-agent")

    assert sha256_file(video) == sha256_file(video)
    assert len(sha256_file(video)) == 64
