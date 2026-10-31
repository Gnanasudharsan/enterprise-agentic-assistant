"""The `analytics` schema: synthetic CRM, onboarding, verification, and support data.

These tables live outside the application's ORM metadata on purpose: the app never
writes to them at runtime, and agents may only read them through the SQL guard and
the read-only `analytics_reader` role (see app.analytics.sql).
"""

from sqlalchemy import (
    Column,
    Date,
    DateTime,
    ForeignKey,
    Integer,
    MetaData,
    Numeric,
    String,
    Table,
)

SCHEMA = "analytics"
READER_ROLE = "analytics_reader"

metadata = MetaData(schema=SCHEMA)

customers = Table(
    "customers",
    metadata,
    Column("customer_id", Integer, primary_key=True),
    Column("name", String(120), nullable=False),
    Column("plan", String(16), nullable=False),
    Column("segment", String(16), nullable=False),
    Column("region", String(8), nullable=False),
    Column("industry", String(32), nullable=False),
    Column("arr_usd", Integer, nullable=False),
    Column("contract_signed_on", Date, nullable=False),
    Column("went_live_on", Date),
    Column("onboarding_business_days", Numeric(4, 1)),
)

onboarding_events = Table(
    "onboarding_events",
    metadata,
    Column("event_id", Integer, primary_key=True),
    Column("customer_id", ForeignKey("customers.customer_id"), nullable=False, index=True),
    Column("stage", String(24), nullable=False),
    Column("started_at", DateTime(timezone=True), nullable=False),
    Column("completed_at", DateTime(timezone=True)),
    Column("business_hours", Numeric(6, 1)),
)

verification_checks = Table(
    "verification_checks",
    metadata,
    Column("check_id", Integer, primary_key=True),
    Column("customer_id", ForeignKey("customers.customer_id"), nullable=False, index=True),
    Column("requested_at", DateTime(timezone=True), nullable=False),
    Column("latency_ms", Integer, nullable=False),
    Column("result", String(16), nullable=False),
)

support_tickets = Table(
    "support_tickets",
    metadata,
    Column("ticket_id", Integer, primary_key=True),
    Column("customer_id", ForeignKey("customers.customer_id"), nullable=False, index=True),
    Column("created_at", DateTime(timezone=True), nullable=False),
    Column("resolved_at", DateTime(timezone=True)),
    Column("priority", String(2), nullable=False),
    Column("tag", String(32), nullable=False),
    Column("status", String(16), nullable=False),
    Column("first_response_minutes", Integer, nullable=False),
)

TABLES = (customers, onboarding_events, verification_checks, support_tickets)
ALLOWED_TABLES = frozenset(t.name for t in TABLES)

# Shown to the model when it writes SQL. Keep it in sync with the tables above.
SCHEMA_DOC = """\
Schema `analytics` (PostgreSQL 16). Synthetic data for Helio Systems, July–October 2026.
Convention: monthly onboarding metrics are reported by contract signing month (the cohort,
contract_signed_on) unless the question explicitly asks about go-live month.
Not recorded here: customer churn or cancellations, invoices and payments, product usage,
satisfaction scores (NPS, CSAT), and anything about employees.

analytics.customers — one row per paying customer
  customer_id int PK, name text, plan text ('Standard' | 'Enterprise'),
  segment text ('SMB' | 'Mid-Market' | 'Enterprise'), region text ('NA' | 'EMEA' | 'APAC'),
  industry text, arr_usd int (annual recurring revenue),
  contract_signed_on date, went_live_on date (NULL while onboarding is in progress),
  onboarding_business_days numeric (business days from signature to go-live; NULL if not live)

analytics.onboarding_events — one row per customer per onboarding stage
  event_id int PK, customer_id int FK, stage text ('kickoff' | 'kyb_verification' |
  'provisioning' | 'data_import' | 'admin_training' | 'go_live'),
  started_at timestamptz, completed_at timestamptz (NULL if in progress),
  business_hours numeric (working hours the stage took, 8 per business day)

analytics.verification_checks — every KYB call to the verification provider (VeriTrust)
  check_id int PK, customer_id int FK, requested_at timestamptz, latency_ms int,
  result text ('passed' | 'timeout' | 'manual_review')

analytics.support_tickets — customer support tickets
  ticket_id int PK, customer_id int FK, created_at timestamptz, resolved_at timestamptz,
  priority text ('P1'..'P4'), tag text (e.g. 'kyb-verification', 'data-import',
  'provisioning', 'billing', 'sso', 'bug', 'how-to'), status text ('open' | 'resolved'),
  first_response_minutes int
"""
