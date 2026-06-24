from pathlib import Path
from types import SimpleNamespace

from sqlalchemy.orm import Session

from app.models import TranscriptChunk, Video, VideoStatus
from app.services.production_pipeline import (
    ProductionPipelineHandlers,
    assign_missing_timestamps,
    sha256_file,
)
from app.services.transcripts import AsrSegment


class FileStorage:
    def __init__(self, payload: bytes) -> None:
        self.payload = payload

    def download_file(self, object_key: str, destination: str) -> None:
        Path(destination).write_bytes(self.payload)

    def upload_file(self, object_key: str, source: str, content_type: str) -> None:
        raise AssertionError("duplicate videos must not upload extracted audio")

    def object_exists(self, object_key: str) -> bool:
        return False


class NoMediaWork:
    def probe(self, source: str):
        raise AssertionError("duplicate videos must reuse media metadata")

    def extract_audio(self, source: str, destination: str) -> None:
        raise AssertionError("duplicate videos must not run FFmpeg extraction")


class NoAiCalls:
    def transcribe(self, audio_path: str):
        raise AssertionError("duplicate videos must not call ASR")

    def summarize(self, transcript: str) -> str:
        raise AssertionError("duplicate videos must not call the LLM")


class RecordingVectors:
    def __init__(self) -> None:
        self.documents = []

    def upsert(self, documents) -> None:
        self.documents.extend(documents)


def test_untimed_asr_text_is_split_across_real_media_duration() -> None:
    segments = assign_missing_timestamps(
        [
            AsrSegment(
                start_ms=0,
                end_ms=0,
                text="First objective. The workflow stays simple. Merchants scan containers.",
            )
        ],
        duration_seconds=79,
    )

    assert len(segments) == 3
    assert segments[0].start_ms == 0
    assert segments[-1].end_ms == 79_000
    assert all(segment.end_ms > segment.start_ms for segment in segments)
    assert all(
        left.end_ms == right.start_ms
        for left, right in zip(segments, segments[1:], strict=False)
    )


class ExistingArtifactStorage:
    def __init__(self) -> None:
        self.downloaded: list[str] = []

    def object_exists(self, object_key: str) -> bool:
        return object_key.endswith("/audio.mp3")

    def download_file(self, object_key: str, destination: str) -> None:
        self.downloaded.append(object_key)
        Path(destination).write_bytes(b"normalized-audio")

    def upload_file(self, object_key: str, source: str, content_type: str) -> None:
        raise AssertionError("existing audio artifact must not be uploaded again")


def test_extract_restores_existing_audio_artifact_without_transcoding(
    db_session: Session,
    tmp_path: Path,
    monkeypatch,
) -> None:
    video = Video(
        filename="recovered.mp4",
        content_type="video/mp4",
        size_bytes=10,
        object_key="videos/recovered.mp4",
        sha256="a" * 64,
    )
    db_session.add(video)
    db_session.commit()
    monkeypatch.setattr(
        "app.services.production_pipeline.get_settings",
        lambda: SimpleNamespace(artifact_dir=str(tmp_path / "artifacts")),
    )
    storage = ExistingArtifactStorage()
    handlers = ProductionPipelineHandlers(
        db_session,
        storage,
        ffmpeg=NoMediaWork(),
        ai=NoAiCalls(),
        vectors=RecordingVectors(),
    )

    handlers.extract(video)

    assert storage.downloaded == [f"artifacts/{video.id}/audio.mp3"]
    assert (tmp_path / "artifacts" / video.id / "audio.mp3").read_bytes() == b"normalized-audio"


def test_duplicate_video_reuses_transcript_and_summary(
    db_session: Session,
    tmp_path: Path,
    monkeypatch,
) -> None:
    payload = b"same-video-content"
    source = tmp_path / "canonical.mp4"
    source.write_bytes(payload)
    canonical = Video(
        filename="canonical.mp4",
        content_type="video/mp4",
        size_bytes=len(payload),
        object_key="videos/canonical.mp4",
        sha256=sha256_file(source),
        status=VideoStatus.READY,
        duration_seconds=42,
        summary="复用的摘要",
    )
    duplicate = Video(
        filename="duplicate.mp4",
        content_type="video/mp4",
        size_bytes=len(payload),
        object_key="videos/duplicate.mp4",
    )
    db_session.add_all([canonical, duplicate])
    db_session.flush()
    db_session.add(
        TranscriptChunk(
            id=f"{canonical.id}:0",
            video_id=canonical.id,
            chunk_index=0,
            start_ms=0,
            end_ms=3_000,
            text="复用的字幕证据",
        )
    )
    db_session.commit()
    monkeypatch.setattr(
        "app.services.production_pipeline.get_settings",
        lambda: SimpleNamespace(artifact_dir=str(tmp_path / "artifacts")),
    )

    vectors = RecordingVectors()
    handlers = ProductionPipelineHandlers(
        db_session,
        FileStorage(payload),
        ffmpeg=NoMediaWork(),
        ai=NoAiCalls(),
        vectors=vectors,
    )

    handlers.probe(duplicate)
    handlers.extract(duplicate)
    handlers.transcribe(duplicate)
    handlers.index(duplicate)
    handlers.summarize(duplicate)

    db_session.refresh(duplicate)
    assert duplicate.duplicate_of_id == canonical.id
    assert duplicate.duration_seconds == 42
    assert duplicate.summary == "复用的摘要"
    assert [document.text for document in vectors.documents] == ["复用的字幕证据"]
