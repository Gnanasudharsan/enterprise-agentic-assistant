"""Analytics data, the read-only SQL executor, and the agent graph on real Postgres."""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

from app.agents.catalog import CERTIFIED_QUERIES
from app.analytics.seed import seed
from app.analytics.sql import SQLExecutionError, SQLExecutor, validate_sql
from app.core.config import Settings
from app.main import create_app
from app.rag.embeddings import HashingEmbedder
from app.rag.ingestion import ingest_directory
from tests.conftest import CORPUS_DIR

pytestmark = pytest.mark.integration


@pytest.fixture
async def analytics_engine(migrated_db):
    engine = create_async_engine(migrated_db)
    async with engine.begin() as conn:
        await seed(conn, force=True)
    yield engine
    await engine.dispose()


async def scalar(engine, sql: str):
    async with engine.connect() as conn:
        return await conn.scalar(text(sql))


async def test_seed_is_deterministic_and_matches_the_documents(analytics_engine):
    async with analytics_engine.begin() as conn:
        assert await seed(conn) is None  # already loaded: idempotent

    # INC-204: 118 kyb-verification tickets in September versus 9 in August.
    kyb = (
        "SELECT count(*) FROM analytics.support_tickets WHERE tag = 'kyb-verification' "
        "AND to_char(created_at, 'YYYY-MM') = '{}'"
    )
    assert await scalar(analytics_engine, kyb.format("2026-09")) == 118
    assert await scalar(analytics_engine, kyb.format("2026-08")) == 9

    # Standard-plan median onboarding: ~2.4 days before September, slower in September.
    median = (
        "SELECT percentile_cont(0.5) WITHIN GROUP (ORDER BY onboarding_business_days) "
        "FROM analytics.customers WHERE plan = 'Standard' "
        "AND to_char(contract_signed_on, 'YYYY-MM') = '{}'"
    )
    august = await scalar(analytics_engine, median.format("2026-08"))
    september = await scalar(analytics_engine, median.format("2026-09"))
    assert august < 3.0 < september


# Expected numbers of the data and cross-source tasks in datasets/evaluation/benchmark.jsonl.
BENCHMARK_FACTS = [
    (
        "SELECT string_agg(region || '=' || n, ',' ORDER BY region) "
        "FROM (SELECT region, count(*) n "
        "FROM analytics.customers GROUP BY 1) r",
        "APAC=37,EMEA=90,NA=168",
    ),
    ("SELECT round(avg(arr_usd)) FROM analytics.customers WHERE plan = 'Enterprise'", 240066),
    ("SELECT count(*) FROM analytics.customers WHERE went_live_on IS NULL", 13),
    (
        "SELECT round(100.0 * avg((result = 'timeout')::int), 1) "
        "FROM analytics.verification_checks "
        "WHERE requested_at >= '2026-09-01' AND requested_at < '2026-10-01'",
        11.5,
    ),
    (
        "SELECT count(*) FROM analytics.support_tickets WHERE tag = 'kyb-verification' AND "
        "priority = 'P2' AND created_at >= '2026-09-01' AND created_at < '2026-10-01'",
        37,
    ),
    (
        "SELECT percentile_cont(0.5) WITHIN GROUP (ORDER BY first_response_minutes) "
        "FROM analytics.support_tickets WHERE priority = 'P1'",
        13,
    ),
    (
        "SELECT count(*) FILTER (WHERE onboarding_business_days <= 10) FROM analytics.customers "
        "WHERE plan = 'Enterprise' AND contract_signed_on >= '2026-09-01' "
        "AND contract_signed_on < '2026-10-01'",
        10,
    ),
    (
        "SELECT round(100.0 * count(*) FILTER (WHERE onboarding_business_days <= 3) / count(*), 1) "
        "FROM analytics.customers WHERE plan = 'Standard' AND contract_signed_on >= '2026-09-01' "
        "AND contract_signed_on < '2026-10-01'",
        25.9,
    ),
]


@pytest.mark.parametrize(("sql", "expected"), BENCHMARK_FACTS)
async def test_benchmark_expectations_match_the_seed(analytics_engine, sql, expected):
    value = await scalar(analytics_engine, sql)
    assert (float(value) if isinstance(expected, int | float) else value) == expected


async def test_reader_role_cannot_escape_the_analytics_schema(analytics_engine):
    executor = SQLExecutor(analytics_engine, timeout_ms=500, max_rows=5)
    # These bypass the validator on purpose: the database must refuse them on its own.
    with pytest.raises(SQLExecutionError, match="permission denied"):
        await executor.run("SELECT * FROM chat_runs")
    with pytest.raises(SQLExecutionError, match="read-only transaction"):
        await executor.run("DELETE FROM analytics.customers")
    with pytest.raises(SQLExecutionError, match="took too long"):
        await executor.run("SELECT pg_sleep(2)")
    assert await scalar(analytics_engine, "SELECT count(*) FROM analytics.customers") > 0

    result = await executor.run("SELECT current_user, customer_id FROM analytics.customers")
    assert result.rows[0][0] == "analytics_reader"
    assert len(result.rows) == 5 and result.truncated
    # The pooled connection is back to the application role afterwards.
    assert await scalar(analytics_engine, "SELECT current_user") != "analytics_reader"


@pytest.mark.parametrize("query", CERTIFIED_QUERIES, ids=lambda q: q.key)
async def test_certified_queries_run(analytics_engine, query):
    executor = SQLExecutor(analytics_engine, timeout_ms=5000, max_rows=200)
    result = await executor.run(validate_sql(query.sql, max_rows=200).sql)
    assert result.rows and not result.truncated


async def test_agent_run_end_to_end_offline(analytics_engine, pg_session, migrated_db):
    await ingest_directory(pg_session, CORPUS_DIR, HashingEmbedder())
    settings = Settings(
        _env_file=None,
        llm_provider="fake",
        embedding_provider="hashing",
        database_url=migrated_db,
        agent_checkpointer="postgres",
    )
    with TestClient(create_app(settings)) as client:
        resp = client.post(
            "/api/v1/agent/run",
            json={"prompt": "How many kyb verification tickets did we get per month?"},
        )
        assert resp.status_code == 200, resp.text
        body = resp.json()
        stored = client.get(f"/api/v1/agent/runs/{body['run_id']}").json()

    assert body["status"] == "succeeded"
    [table] = body["tables"]
    assert table["origin"] == "certified"  # no model connected: the reviewed query is used
    september = next(r for r in table["rows"] if r[0] == "2026-09")
    assert september[1] == 118
    assert body["sources"] and body["citations"]["tables"] == [1]
    assert stored["trace"] == body["trace"]
