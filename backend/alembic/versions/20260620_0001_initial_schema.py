"""Initial AudiVise schema."""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "20260620_0001"
down_revision: str | Sequence[str] | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    upload_status = sa.Enum("INITIATED", "COMPLETED", "ABORTED", name="uploadstatus")
    video_status = sa.Enum("UPLOADED", "PROCESSING", "READY", "FAILED", name="videostatus")
    task_status = sa.Enum(
        "PENDING",
        "PROBING",
        "EXTRACTING",
        "TRANSCRIBING",
        "INDEXING",
        "SUMMARIZING",
        "SUCCEEDED",
        "FAILED",
        "CANCELLED",
        name="taskstatus",
    )

    op.create_table(
        "videos",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("filename", sa.String(512), nullable=False),
        sa.Column("content_type", sa.String(128), nullable=False),
        sa.Column("size_bytes", sa.BigInteger(), nullable=False),
        sa.Column("object_key", sa.String(1024), nullable=False, unique=True),
        sa.Column("sha256", sa.String(64)),
        sa.Column("duplicate_of_id", sa.String(36), sa.ForeignKey("videos.id")),
        sa.Column("status", video_status, nullable=False),
        sa.Column("duration_seconds", sa.Integer()),
        sa.Column("summary", sa.Text()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_videos_sha256", "videos", ["sha256"])
    op.create_table(
        "upload_sessions",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("filename", sa.String(512), nullable=False),
        sa.Column("content_type", sa.String(128), nullable=False),
        sa.Column("size_bytes", sa.BigInteger(), nullable=False),
        sa.Column("object_key", sa.String(1024), nullable=False, unique=True),
        sa.Column("multipart_upload_id", sa.String(512)),
        sa.Column("status", upload_status, nullable=False),
        sa.Column("completed_parts", sa.Text()),
        sa.Column("video_id", sa.String(36), sa.ForeignKey("videos.id"), unique=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_table(
        "analysis_tasks",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("video_id", sa.String(36), sa.ForeignKey("videos.id"), nullable=False),
        sa.Column("idempotency_key", sa.String(255), nullable=False),
        sa.Column("status", task_status, nullable=False),
        sa.Column("progress", sa.Integer(), nullable=False),
        sa.Column("current_stage", sa.String(64)),
        sa.Column("attempts", sa.Integer(), nullable=False),
        sa.Column("error_code", sa.String(128)),
        sa.Column("error_message", sa.Text()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("video_id", "idempotency_key", name="uq_task_video_idempotency"),
    )
    op.create_index("ix_analysis_tasks_video_id", "analysis_tasks", ["video_id"])
    op.create_table(
        "transcript_chunks",
        sa.Column("id", sa.String(128), primary_key=True),
        sa.Column("video_id", sa.String(36), sa.ForeignKey("videos.id"), nullable=False),
        sa.Column("chunk_index", sa.Integer(), nullable=False),
        sa.Column("start_ms", sa.Integer(), nullable=False),
        sa.Column("end_ms", sa.Integer(), nullable=False),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("video_id", "chunk_index", name="uq_chunk_video_index"),
    )
    op.create_index("ix_transcript_chunks_video_id", "transcript_chunks", ["video_id"])
    op.create_table(
        "agent_traces",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("video_id", sa.String(36), sa.ForeignKey("videos.id"), nullable=False),
        sa.Column("question", sa.Text(), nullable=False),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("model_name", sa.String(255)),
        sa.Column("tool_calls_json", sa.Text()),
        sa.Column("evidence_ids_json", sa.Text()),
        sa.Column("answer", sa.Text()),
        sa.Column("error_type", sa.String(128)),
        sa.Column("latency_ms", sa.Integer()),
        sa.Column("prompt_tokens", sa.Integer()),
        sa.Column("completion_tokens", sa.Integer()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_agent_traces_video_id", "agent_traces", ["video_id"])


def downgrade() -> None:
    op.drop_table("agent_traces")
    op.drop_table("transcript_chunks")
    op.drop_table("analysis_tasks")
    op.drop_table("upload_sessions")
    op.drop_table("videos")
