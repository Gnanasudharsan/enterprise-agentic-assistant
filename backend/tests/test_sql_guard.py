import pytest

from app.agents.catalog import CERTIFIED_QUERIES
from app.analytics.sql import SQLGuardError, validate_sql


@pytest.mark.parametrize(
    "sql",
    [
        "SELECT to_char(created_at, 'YYYY-MM') AS month, count(*) FROM analytics.support_tickets "
        "WHERE tag = 'kyb-verification' GROUP BY 1 ORDER BY 1",
        "SELECT plan, percentile_cont(0.5) WITHIN GROUP (ORDER BY onboarding_business_days) "
        "FROM analytics.customers GROUP BY plan",
        "WITH w AS (SELECT date_trunc('week', requested_at) AS wk, count(*) FILTER "
        "(WHERE result = 'timeout') AS t FROM analytics.verification_checks GROUP BY 1) "
        "SELECT * FROM w",
        "SELECT c.plan, avg(e.business_hours) FROM analytics.customers c JOIN "
        "analytics.onboarding_events e USING (customer_id) WHERE e.stage = 'kyb_verification' "
        "AND c.contract_signed_on >= DATE '2026-09-01' GROUP BY 1",
        "SELECT name FROM analytics.customers WHERE name ILIKE '%labs%' AND region IN ('NA')",
        "SELECT ntile(4) OVER (ORDER BY arr_usd) FROM analytics.customers",
    ],
)
def test_allows_analytical_selects(sql):
    validated = validate_sql(sql, max_rows=200)
    assert validated.sql.endswith("LIMIT 200")
    assert all(t.startswith("analytics.") for t in validated.tables)


@pytest.mark.parametrize(
    ("sql", "reason"),
    [
        ("DELETE FROM analytics.customers", "Only SELECT"),
        ("UPDATE analytics.customers SET plan = 'x'", "Only SELECT"),
        ("DROP TABLE analytics.customers", "Only SELECT"),
        ("COPY analytics.customers TO '/tmp/x'", "Only SELECT"),
        ("SELECT 1; DROP TABLE analytics.customers", "one statement"),
        ("WITH d AS (DELETE FROM analytics.customers RETURNING *) SELECT * FROM d", "read-only"),
        ("SELECT * INTO analytics.copy FROM analytics.customers", "read-only"),
        ("SELECT * FROM analytics.customers FOR UPDATE", "read-only"),
        ("SELECT * FROM chat_runs", "not allowed"),
        ("SELECT * FROM public.documents", "not allowed"),
        ("SELECT * FROM pg_catalog.pg_roles", "not allowed"),
        ("SELECT * FROM analytics.secrets", "not allowed"),
        ("SELECT (SELECT usename FROM pg_user) FROM analytics.customers", "not allowed"),
        ("SELECT pg_sleep(10) FROM analytics.customers", "pg_sleep"),
        ("SELECT set_config('role', 'postgres', false) FROM analytics.customers", "set_config"),
        ("SELECT current_setting('is_superuser') FROM analytics.customers", "current_setting"),
        ("SELECT pg_read_file('/etc/passwd') FROM analytics.customers", "pg_read_file"),
        ("SELECT * FROM analytics.customers, dblink('db', 'SELECT 1') AS t(a int)", "dblink"),
        ("SELECT 1", "at least one analytics table"),
        ("SELEC * FROM analytics.customers", "parse"),
    ],
)
def test_rejects_unsafe_sql(sql, reason):
    with pytest.raises(SQLGuardError, match=reason):
        validate_sql(sql, max_rows=200)


def test_caps_row_limit_but_keeps_smaller_limits():
    assert validate_sql("SELECT * FROM analytics.customers LIMIT 5", max_rows=50).sql.endswith(
        "LIMIT 5"
    )
    assert validate_sql("SELECT * FROM analytics.customers LIMIT 5000", max_rows=50).sql.endswith(
        "LIMIT 50"
    )
    union = validate_sql(
        "SELECT plan FROM analytics.customers UNION SELECT tag FROM analytics.support_tickets",
        max_rows=50,
    )
    assert union.sql.endswith("LIMIT 50")


def test_ctes_are_not_mistaken_for_tables():
    sql = "WITH t AS (SELECT * FROM analytics.customers) SELECT count(*) FROM t"
    assert validate_sql(sql, max_rows=10).tables == ["analytics.customers"]


@pytest.mark.parametrize("query", CERTIFIED_QUERIES, ids=lambda q: q.key)
def test_certified_queries_pass_the_guard(query):
    validate_sql(query.sql, max_rows=200)
