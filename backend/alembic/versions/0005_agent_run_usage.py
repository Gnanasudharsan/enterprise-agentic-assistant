"""Token usage per agent run (every model call the run made), for cost reporting.

Revision ID: 0005
Revises: 0004
Create Date: 2026-10-31
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0005"
down_revision: str | None = "0004"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("agent_runs", sa.Column("llm_calls", sa.Integer(), nullable=True))
    op.add_column("agent_runs", sa.Column("prompt_tokens", sa.Integer(), nullable=True))
    op.add_column("agent_runs", sa.Column("completion_tokens", sa.Integer(), nullable=True))


def downgrade() -> None:
    op.drop_column("agent_runs", "completion_tokens")
    op.drop_column("agent_runs", "prompt_tokens")
    op.drop_column("agent_runs", "llm_calls")
