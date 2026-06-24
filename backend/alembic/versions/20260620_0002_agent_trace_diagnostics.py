"""Add Agent Trace intent and node diagnostics."""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "20260620_0002"
down_revision: str | Sequence[str] | None = "20260620_0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("agent_traces", sa.Column("intent", sa.String(32)))
    op.add_column("agent_traces", sa.Column("node_timings_json", sa.Text()))
    op.add_column("agent_traces", sa.Column("error_message", sa.Text()))


def downgrade() -> None:
    op.drop_column("agent_traces", "error_message")
    op.drop_column("agent_traces", "node_timings_json")
    op.drop_column("agent_traces", "intent")
