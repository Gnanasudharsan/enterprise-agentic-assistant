"""Analytics schema (synthetic company data), read-only reader role, agent runs.

Revision ID: 0003
Revises: 0002
Create Date: 2026-10-30
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0003"
down_revision: str | None = "0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

SCHEMA = "analytics"
READER = "analytics_reader"


def upgrade() -> None:
    op.create_table(
        "agent_runs",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("question", sa.Text(), nullable=False),
        sa.Column("provider", sa.String(length=32), nullable=False),
        sa.Column("model", sa.String(length=128), nullable=True),
        sa.Column("plan", sa.JSON(), nullable=True),
        sa.Column("trace", sa.JSON(), nullable=True),
        sa.Column("answer", sa.Text(), nullable=True),
        sa.Column("sources", sa.JSON(), nullable=True),
        sa.Column("tables", sa.JSON(), nullable=True),
        sa.Column("citations", sa.JSON(), nullable=True),
        sa.Column("error_type", sa.String(length=64), nullable=True),
        sa.Column("latency_ms", sa.Integer(), nullable=True),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_agent_runs")),
    )
    op.create_index(op.f("ix_agent_runs_created_at"), "agent_runs", ["created_at"])

    op.execute(f"CREATE SCHEMA {SCHEMA}")
    op.create_table(
        "customers",
        sa.Column("customer_id", sa.Integer(), primary_key=True),
        sa.Column("name", sa.String(120), nullable=False),
        sa.Column("plan", sa.String(16), nullable=False),
        sa.Column("segment", sa.String(16), nullable=False),
        sa.Column("region", sa.String(8), nullable=False),
        sa.Column("industry", sa.String(32), nullable=False),
        sa.Column("arr_usd", sa.Integer(), nullable=False),
        sa.Column("contract_signed_on", sa.Date(), nullable=False),
        sa.Column("went_live_on", sa.Date()),
        sa.Column("onboarding_business_days", sa.Numeric(4, 1)),
        schema=SCHEMA,
    )
    for name, columns in (
        (
            "onboarding_events",
            [
                sa.Column("event_id", sa.Integer(), primary_key=True),
                sa.Column("stage", sa.String(24), nullable=False),
                sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
                sa.Column("completed_at", sa.DateTime(timezone=True)),
                sa.Column("business_hours", sa.Numeric(6, 1)),
            ],
        ),
        (
            "verification_checks",
            [
                sa.Column("check_id", sa.Integer(), primary_key=True),
                sa.Column("requested_at", sa.DateTime(timezone=True), nullable=False),
                sa.Column("latency_ms", sa.Integer(), nullable=False),
                sa.Column("result", sa.String(16), nullable=False),
            ],
        ),
        (
            "support_tickets",
            [
                sa.Column("ticket_id", sa.Integer(), primary_key=True),
                sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
                sa.Column("resolved_at", sa.DateTime(timezone=True)),
                sa.Column("priority", sa.String(2), nullable=False),
                sa.Column("tag", sa.String(32), nullable=False),
                sa.Column("status", sa.String(16), nullable=False),
                sa.Column("first_response_minutes", sa.Integer(), nullable=False),
            ],
        ),
    ):
        customer_id = sa.Column(
            "customer_id",
            sa.Integer(),
            sa.ForeignKey(f"{SCHEMA}.customers.customer_id"),
            nullable=False,
            index=True,
        )
        op.create_table(name, columns[0], customer_id, *columns[1:], schema=SCHEMA)

    # Least-privilege role for agent SQL: it can read the analytics schema and nothing
    # else. NOLOGIN: the app switches to it per query with SET LOCAL ROLE.
    op.execute(
        f"""
        DO $$ BEGIN
            IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = '{READER}') THEN
                CREATE ROLE {READER} NOLOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE;
            END IF;
        END $$
        """
    )
    op.execute(f"GRANT USAGE ON SCHEMA {SCHEMA} TO {READER}")
    op.execute(f"GRANT SELECT ON ALL TABLES IN SCHEMA {SCHEMA} TO {READER}")
    op.execute(f"GRANT {READER} TO CURRENT_USER")


def downgrade() -> None:
    # The role is cluster-wide (other databases may use it), so it is left in place.
    op.execute(f"REVOKE ALL ON ALL TABLES IN SCHEMA {SCHEMA} FROM {READER}")
    op.execute(f"REVOKE ALL ON SCHEMA {SCHEMA} FROM {READER}")
    op.execute(f"DROP SCHEMA {SCHEMA} CASCADE")
    op.drop_index(op.f("ix_agent_runs_created_at"), table_name="agent_runs")
    op.drop_table("agent_runs")
