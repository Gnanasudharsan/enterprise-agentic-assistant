"""Agent actions (proposed tool calls and their outcome) and the action audit log.

Revision ID: 0004
Revises: 0003
Create Date: 2026-10-30
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0004"
down_revision: str | None = "0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "agent_actions",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("run_id", sa.Uuid(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column("server", sa.String(length=64), nullable=False),
        sa.Column("tool", sa.String(length=64), nullable=False),
        sa.Column("arguments", sa.JSON(), nullable=False),
        sa.Column("args_hash", sa.String(length=64), nullable=False),
        sa.Column("rationale", sa.Text(), nullable=True),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("requested_by", sa.String(length=64), nullable=False),
        sa.Column("decided_by", sa.String(length=64), nullable=True),
        sa.Column("decided_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("executed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("result", sa.JSON(), nullable=True),
        sa.Column("error", sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(
            ["run_id"], ["agent_runs.id"], name=op.f("fk_agent_actions_run_id_agent_runs")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_agent_actions")),
    )
    op.create_index(op.f("ix_agent_actions_run_id"), "agent_actions", ["run_id"])
    op.create_index(op.f("ix_agent_actions_status"), "agent_actions", ["status"])

    op.create_table(
        "action_audit",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column("action_id", sa.Uuid(), nullable=True),
        sa.Column("run_id", sa.Uuid(), nullable=True),
        sa.Column("event", sa.String(length=16), nullable=False),
        sa.Column("actor", sa.String(length=64), nullable=False),
        sa.Column("detail", sa.JSON(), nullable=True),
        sa.ForeignKeyConstraint(
            ["action_id"],
            ["agent_actions.id"],
            name=op.f("fk_action_audit_action_id_agent_actions"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_action_audit")),
    )
    op.create_index(op.f("ix_action_audit_action_id"), "action_audit", ["action_id"])
    op.create_index(op.f("ix_action_audit_created_at"), "action_audit", ["created_at"])


def downgrade() -> None:
    op.drop_index(op.f("ix_action_audit_created_at"), table_name="action_audit")
    op.drop_index(op.f("ix_action_audit_action_id"), table_name="action_audit")
    op.drop_table("action_audit")
    op.drop_index(op.f("ix_agent_actions_status"), table_name="agent_actions")
    op.drop_index(op.f("ix_agent_actions_run_id"), table_name="agent_actions")
    op.drop_table("agent_actions")
