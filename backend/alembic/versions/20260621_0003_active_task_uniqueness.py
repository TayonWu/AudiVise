"""Add one-active-analysis-task invariant per media item."""

from collections.abc import Sequence

from alembic import op

revision: str = "20260621_0003"
down_revision: str | Sequence[str] | None = "20260620_0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_ACTIVE_STATUSES = (
    "'PENDING'",
    "'PROBING'",
    "'EXTRACTING'",
    "'TRANSCRIBING'",
    "'INDEXING'",
    "'SUMMARIZING'",
)


def upgrade() -> None:
    statuses = ", ".join(_ACTIVE_STATUSES)
    status_expression = "status::text" if op.get_bind().dialect.name == "postgresql" else "status"
    op.execute(
        f"""
        WITH ranked AS (
            SELECT id,
                   row_number() OVER (
                       PARTITION BY video_id
                       ORDER BY created_at, id
                   ) AS position
            FROM analysis_tasks
            WHERE {status_expression} IN (
                'PENDING', 'PROBING', 'EXTRACTING',
                'TRANSCRIBING', 'INDEXING', 'SUMMARIZING'
            )
        )
        UPDATE analysis_tasks
        SET status = 'CANCELLED',
            current_stage = 'CANCELLED',
            error_code = 'SupersededActiveTask',
            error_message = 'Cancelled while enforcing one active task per media item'
        WHERE id IN (SELECT id FROM ranked WHERE position > 1)
        """
    )
    op.execute(
        "CREATE UNIQUE INDEX uq_analysis_tasks_active_video "
        "ON analysis_tasks (video_id) "
        f"WHERE status IN ({statuses})"
    )


def downgrade() -> None:
    op.drop_index("uq_analysis_tasks_active_video", table_name="analysis_tasks")
