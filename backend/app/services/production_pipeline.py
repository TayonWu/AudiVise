import hashlib
import re
import shutil
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.integrations.ai_provider import OpenAICompatibleProvider
from app.integrations.ffmpeg import FFmpeg
from app.integrations.object_storage import ObjectStorage
from app.integrations.vector_store import QdrantTranscriptStore
from app.models import TranscriptChunk, Video, VideoStatus
from app.services.transcripts import AsrSegment, TranscriptDocument, build_transcript_chunks


class ProductionPipelineHandlers:
    def __init__(
        self,
        db: Session,
        storage: ObjectStorage,
        *,
        ffmpeg: FFmpeg | None = None,
        ai: OpenAICompatibleProvider | None = None,
        vectors: QdrantTranscriptStore | None = None,
    ) -> None:
        self.db = db
        self.storage = storage
        self.ffmpeg = ffmpeg or FFmpeg()
        self.ai = ai or OpenAICompatibleProvider()
        self.vectors = vectors or QdrantTranscriptStore()

    def probe(self, video: Video) -> None:
        source = self._source_path(video)
        self._download_if_missing(video, source)
        if not video.sha256:
            video.sha256 = sha256_file(source)
            self.resolve_ready_duplicate(video)
        if video.duration_seconds is None:
            video.duration_seconds = self.ffmpeg.probe(str(source)).duration_seconds
            self.db.commit()

    def resolve_ready_duplicate(self, video: Video) -> None:
        if not video.sha256 or video.duplicate_of_id:
            return
        canonical = self.db.scalar(
            select(Video)
            .where(
                Video.sha256 == video.sha256,
                Video.id != video.id,
                Video.status == VideoStatus.READY,
            )
            .order_by(Video.created_at)
            .limit(1)
        )
        if canonical:
            video.duplicate_of_id = canonical.id
            video.duration_seconds = canonical.duration_seconds
            self.db.commit()

    def extract(self, video: Video) -> None:
        if video.duplicate_of_id:
            return
        audio = self._audio_path(video)
        if audio.exists():
            return
        artifact_key = f"artifacts/{video.id}/audio.mp3"
        if self.storage.object_exists(artifact_key):
            self.storage.download_file(artifact_key, str(audio))
            return
        source = self._source_path(video)
        self._download_if_missing(video, source)
        self.ffmpeg.extract_audio(str(source), str(audio))
        self.storage.upload_file(artifact_key, str(audio), "audio/mpeg")

    def transcribe(self, video: Video) -> None:
        existing = self.db.scalar(
            select(TranscriptChunk.id).where(TranscriptChunk.video_id == video.id).limit(1)
        )
        if existing:
            return
        if video.duplicate_of_id:
            canonical_chunks = list(
                self.db.scalars(
                    select(TranscriptChunk)
                    .where(TranscriptChunk.video_id == video.duplicate_of_id)
                    .order_by(TranscriptChunk.chunk_index)
                )
            )
            for chunk in canonical_chunks:
                self.db.add(
                    TranscriptChunk(
                        id=f"{video.id}:{chunk.chunk_index}",
                        video_id=video.id,
                        chunk_index=chunk.chunk_index,
                        start_ms=chunk.start_ms,
                        end_ms=chunk.end_ms,
                        text=chunk.text,
                    )
                )
            self.db.commit()
            return
        audio = self._audio_path(video)
        if not audio.exists():
            self.storage.download_file(f"artifacts/{video.id}/audio.mp3", str(audio))
        segments = assign_missing_timestamps(
            self.ai.transcribe(str(audio)),
            duration_seconds=video.duration_seconds or 0,
        )
        documents = build_transcript_chunks(video.id, segments)
        for document in documents:
            self.db.add(
                TranscriptChunk(
                    id=document.id,
                    video_id=document.video_id,
                    chunk_index=document.chunk_index,
                    start_ms=document.start_ms,
                    end_ms=document.end_ms,
                    text=document.text,
                )
            )
        self.db.commit()

    def index(self, video: Video) -> None:
        documents = [
            TranscriptDocument(
                id=chunk.id,
                video_id=chunk.video_id,
                chunk_index=chunk.chunk_index,
                start_ms=chunk.start_ms,
                end_ms=chunk.end_ms,
                text=chunk.text,
            )
            for chunk in self.db.scalars(
                select(TranscriptChunk)
                .where(TranscriptChunk.video_id == video.id)
                .order_by(TranscriptChunk.chunk_index)
            )
        ]
        self.vectors.upsert(documents)

    def summarize(self, video: Video) -> None:
        if video.summary:
            return
        if video.duplicate_of_id:
            canonical = self.db.get(Video, video.duplicate_of_id)
            if canonical and canonical.summary:
                video.summary = canonical.summary
                self.db.commit()
                return
        transcript = "\n".join(
            self.db.scalars(
                select(TranscriptChunk.text)
                .where(TranscriptChunk.video_id == video.id)
                .order_by(TranscriptChunk.chunk_index)
            )
        )
        video.summary = self.ai.summarize(transcript)
        self.db.commit()

    def cleanup(self, video: Video) -> None:
        shutil.rmtree(Path(get_settings().artifact_dir) / video.id, ignore_errors=True)

    def _workspace(self, video: Video) -> Path:
        path = Path(get_settings().artifact_dir) / video.id
        path.mkdir(parents=True, exist_ok=True)
        return path

    def _source_path(self, video: Video) -> Path:
        suffix = Path(video.filename).suffix or ".mp4"
        return self._workspace(video) / f"source{suffix}"

    def _audio_path(self, video: Video) -> Path:
        return self._workspace(video) / "audio.mp3"

    def _download_if_missing(self, video: Video, destination: Path) -> None:
        if not destination.exists():
            self.storage.download_file(video.object_key, str(destination))


def sha256_file(path: Path, block_size: int = 1024 * 1024) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        while block := source.read(block_size):
            digest.update(block)
    return digest.hexdigest()


def assign_missing_timestamps(
    segments: list[AsrSegment],
    *,
    duration_seconds: int,
) -> list[AsrSegment]:
    if not segments or any(segment.end_ms > segment.start_ms for segment in segments):
        return segments
    duration_ms = duration_seconds * 1_000
    if duration_ms <= 0:
        return segments

    sentences = [
        sentence.strip()
        for segment in segments
        for sentence in re.findall(r"[^.!?。！？]+[.!?。！？]?", segment.text)
        if sentence.strip()
    ]
    if not sentences:
        return segments

    weights = [max(1, len(sentence)) for sentence in sentences]
    total_weight = sum(weights)
    timed: list[AsrSegment] = []
    elapsed_weight = 0
    for index, (sentence, weight) in enumerate(zip(sentences, weights, strict=True)):
        start_ms = round(duration_ms * elapsed_weight / total_weight)
        elapsed_weight += weight
        end_ms = (
            duration_ms
            if index == len(sentences) - 1
            else round(duration_ms * elapsed_weight / total_weight)
        )
        timed.append(
            AsrSegment(
                start_ms=start_ms,
                end_ms=max(start_ms + 1, end_ms),
                text=sentence,
            )
        )
    return timed
