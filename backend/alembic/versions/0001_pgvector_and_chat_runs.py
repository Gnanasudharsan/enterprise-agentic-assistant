"""Enable pgvector and create chat_runs.

Revision ID: 0001
Revises:
Create Date: 2026-10-29
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Needed from Phase 2 (embeddings); enabled now so the environment is verified early.
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")

    op.create_table(
        "chat_runs",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("provider", sa.String(length=32), nullable=False),
        sa.Column("model", sa.String(length=128), nullable=True),
        sa.Column("prompt", sa.Text(), nullable=False),
        sa.Column("answer", sa.Text(), nullable=True),
        sa.Column("error_type", sa.String(length=64), nullable=True),
        sa.Column("latency_ms", sa.Integer(), nullable=False),
        sa.Column("prompt_tokens", sa.Integer(), nullable=True),
        sa.Column("completion_tokens", sa.Integer(), nullable=True),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_chat_runs")),
    )
    op.create_index(op.f("ix_chat_runs_created_at"), "chat_runs", ["created_at"])


def downgrade() -> None:
    op.drop_index(op.f("ix_chat_runs_created_at"), table_name="chat_runs")
    op.drop_table("chat_runs")
    # The vector extension is left installed; other objects may depend on it.
