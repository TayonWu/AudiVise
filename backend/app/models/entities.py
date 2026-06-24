from datetime import UTC, datetime
from uuid import uuid4

from sqlalchemy import (
    BigInteger,
    DateTime,
    Enum,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.models.enums import TaskStatus, UploadStatus, VideoStatus


def new_id() -> str:
    return str(uuid4())


def utc_now() -> datetime:
    return datetime.now(UTC)


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, onupdate=utc_now, nullable=False
    )


class UploadSession(TimestampMixin, Base):
    __tablename__ = "upload_sessions"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    filename: Mapped[str] = mapped_column(String(512), nullable=False)
    content_type: Mapped[str] = mapped_column(String(128), nullable=False)
    size_bytes: Mapped[int] = mapped_column(BigInteger, nullable=False)
    object_key: Mapped[str] = mapped_column(String(1024), unique=True, nullable=False)
    multipart_upload_id: Mapped[str | None] = mapped_column(String(512))
    status: Mapped[UploadStatus] = mapped_column(
        Enum(UploadStatus), default=UploadStatus.INITIATED, nullable=False
    )
    completed_parts: Mapped[str | None] = mapped_column(Text)
    video_id: Mapped[str | None] = mapped_column(ForeignKey("videos.id"), unique=True)


class Video(TimestampMixin, Base):
    __tablename__ = "videos"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    filename: Mapped[str] = mapped_column(String(512), nullable=False)
    content_type: Mapped[str] = mapped_column(String(128), nullable=False)
    size_bytes: Mapped[int] = mapped_column(BigInteger, nullable=False)
    object_key: Mapped[str] = mapped_column(String(1024), unique=True, nullable=False)
    sha256: Mapped[str | None] = mapped_column(String(64), index=True)
    duplicate_of_id: Mapped[str | None] = mapped_column(ForeignKey("videos.id"))
    status: Mapped[VideoStatus] = mapped_column(
        Enum(VideoStatus), default=VideoStatus.UPLOADED, nullable=False
    )
    duration_seconds: Mapped[int | None] = mapped_column(Integer)
    summary: Mapped[str | None] = mapped_column(Text)

    tasks: Mapped[list["AnalysisTask"]] = relationship(back_populates="video")


class AnalysisTask(TimestampMixin, Base):
    __tablename__ = "analysis_tasks"
    __table_args__ = (
        UniqueConstraint("video_id", "idempotency_key", name="uq_task_video_idempotency"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    video_id: Mapped[str] = mapped_column(ForeignKey("videos.id"), nullable=False, index=True)
    idempotency_key: Mapped[str] = mapped_column(String(255), nullable=False)
    status: Mapped[TaskStatus] = mapped_column(
        Enum(TaskStatus), default=TaskStatus.PENDING, nullable=False
    )
    progress: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    current_stage: Mapped[str | None] = mapped_column(String(64))
    attempts: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    error_code: Mapped[str | None] = mapped_column(String(128))
    error_message: Mapped[str | None] = mapped_column(Text)

    video: Mapped[Video] = relationship(back_populates="tasks")


ACTIVE_TASK_STATUSES = (
    TaskStatus.PENDING,
    TaskStatus.PROBING,
    TaskStatus.EXTRACTING,
    TaskStatus.TRANSCRIBING,
    TaskStatus.INDEXING,
    TaskStatus.SUMMARIZING,
)

Index(
    "uq_analysis_tasks_active_video",
    AnalysisTask.video_id,
    unique=True,
    postgresql_where=AnalysisTask.status.in_(ACTIVE_TASK_STATUSES),
)


class TranscriptChunk(TimestampMixin, Base):
    __tablename__ = "transcript_chunks"
    __table_args__ = (
        UniqueConstraint("video_id", "chunk_index", name="uq_chunk_video_index"),
    )

    id: Mapped[str] = mapped_column(String(128), primary_key=True, default=new_id)
    video_id: Mapped[str] = mapped_column(ForeignKey("videos.id"), nullable=False, index=True)
    chunk_index: Mapped[int] = mapped_column(Integer, nullable=False)
    start_ms: Mapped[int] = mapped_column(Integer, nullable=False)
    end_ms: Mapped[int] = mapped_column(Integer, nullable=False)
    text: Mapped[str] = mapped_column(Text, nullable=False)


class AgentTrace(TimestampMixin, Base):
    __tablename__ = "agent_traces"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    video_id: Mapped[str] = mapped_column(ForeignKey("videos.id"), nullable=False, index=True)
    question: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(String(32), default="RUNNING", nullable=False)
    intent: Mapped[str | None] = mapped_column(String(32))
    model_name: Mapped[str | None] = mapped_column(String(255))
    node_timings_json: Mapped[str | None] = mapped_column(Text)
    tool_calls_json: Mapped[str | None] = mapped_column(Text)
    evidence_ids_json: Mapped[str | None] = mapped_column(Text)
    answer: Mapped[str | None] = mapped_column(Text)
    error_type: Mapped[str | None] = mapped_column(String(128))
    error_message: Mapped[str | None] = mapped_column(Text)
    latency_ms: Mapped[int | None] = mapped_column(Integer)
    prompt_tokens: Mapped[int | None] = mapped_column(Integer)
    completion_tokens: Mapped[int | None] = mapped_column(Integer)
