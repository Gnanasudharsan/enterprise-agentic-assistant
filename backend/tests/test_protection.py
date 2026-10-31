"""Deployment protections: access code, rate limits, budget, static frontend, logs."""

import json
import logging

import pytest
from fastapi.testclient import TestClient
from pydantic import SecretStr

from app.core.logs import JsonFormatter
from app.core.protection import SlidingWindowLimiter, client_ip
from app.llm.budget import BudgetedLLM, DailyBudget
from app.main import create_app
from tests.conftest import StubLLM


def make_client(settings, llm, retriever, sql, **overrides) -> TestClient:
    app = create_app(settings.model_copy(update=overrides))
    app.state.llm_client = llm
    app.state.retriever = retriever
    app.state.sql_executor = sql
    return TestClient(app)


@pytest.fixture
def protected(settings, llm, retriever, sql):
    with make_client(settings, llm, retriever, sql, access_code=SecretStr("open-sesame"),
                     rate_limit_requests=2, rate_limit_window_seconds=60) as c:  # fmt: skip
        yield c


def test_api_needs_the_access_code(protected):
    assert protected.post("/api/v1/chat", json={"prompt": "hi"}).status_code == 401
    assert protected.get("/api/v1/info").status_code == 401
    ok = protected.get("/api/v1/info", headers={"X-Access-Code": "open-sesame"})
    assert ok.status_code == 200
    # Liveness, readiness, and the code check stay open.
    assert protected.get("/health").status_code == 200
    assert protected.get("/api/v1/access").json() == {"required": True, "granted": False}
    granted = protected.get("/api/v1/access", headers={"X-Access-Code": "open-sesame"})
    assert granted.json() == {"required": True, "granted": True}


def test_code_attempts_are_rate_limited(protected):
    assert protected.post("/api/v1/access", json={"code": "open-sesame"}).status_code == 204
    codes = [protected.post("/api/v1/access", json={"code": f"guess{i}"}).status_code
             for i in range(12)]  # fmt: skip
    assert codes[:9] == [401] * 9 and codes[-1] == 429


def test_model_endpoints_are_rate_limited_per_client(protected):
    headers = {"X-Access-Code": "open-sesame"}
    codes = [protected.post("/api/v1/chat", json={"prompt": "PTO?"}, headers=headers).status_code
             for _ in range(3)]  # fmt: skip
    assert codes == [200, 200, 429]
    limited = protected.post("/api/v1/chat", json={"prompt": "PTO?"}, headers=headers)
    assert int(limited.headers["Retry-After"]) > 0
    # Reads are not limited.
    assert protected.get("/api/v1/agent/runs", headers=headers).status_code == 200


def test_without_settings_nothing_is_gated(client):
    assert client.get("/api/v1/access").json() == {"required": False, "granted": True}
    resp = client.get("/api/v1/info")
    assert resp.status_code == 200
    assert resp.headers["X-Content-Type-Options"] == "nosniff"
    assert resp.headers["X-Frame-Options"] == "DENY"


def test_client_ip_trusts_only_the_proxy_hops():
    class Req:
        def __init__(self, xff):
            self.headers = {"x-forwarded-for": xff}
            self.client = type("C", (), {"host": "10.0.0.1"})()

    forged = Req("6.6.6.6, 203.0.113.7")  # the client prepended a fake address
    assert client_ip(forged, 1) == "203.0.113.7"
    assert client_ip(forged, 0) == "10.0.0.1"
    assert client_ip(Req(""), 1) == "10.0.0.1"


def test_sliding_window():
    limiter = SlidingWindowLimiter(2, 10)
    assert limiter.hit("a", 0) is None and limiter.hit("a", 1) is None
    assert limiter.hit("a", 2) == pytest.approx(8)
    assert limiter.hit("b", 2) is None
    assert limiter.hit("a", 10.5) is None  # the first hit expired


async def test_budget_switches_to_the_offline_model():
    real, fake = StubLLM(), StubLLM()
    fake.provider, fake.model = "fake", "fake-model"
    budget = DailyBudget(limit_tokens=20)
    llm = BudgetedLLM(real, fake, budget)

    await llm.complete([])  # 12 tokens
    assert llm.provider == "stub" and not budget.exhausted
    await llm.complete([])  # 24 tokens: over the budget
    assert budget.exhausted and llm.provider == "fake" and llm.model == "fake-model"
    await llm.complete([])
    assert len(real.calls) == 2 and len(fake.calls) == 1
    assert budget.used == 24  # offline calls cost nothing

    budget.day = "2000-01-01"  # a new UTC day resets it
    assert not budget.exhausted and budget.used == 0


async def test_budget_counts_streamed_answers():
    budget = DailyBudget(limit_tokens=5)
    llm = BudgetedLLM(StubLLM(), StubLLM(), budget)
    [item async for item in llm.stream([])]
    assert budget.used == 12 and budget.exhausted


def test_frontend_is_served_with_spa_fallback(settings, llm, retriever, sql, tmp_path):
    (tmp_path / "assets").mkdir()
    (tmp_path / "index.html").write_text("<html>app</html>")
    (tmp_path / "assets" / "app-123.js").write_text("console.log(1)")
    (tmp_path.parent / "secret.txt").write_text("nope")
    with make_client(settings, llm, retriever, sql, static_dir=str(tmp_path)) as c:
        asset = c.get("/assets/app-123.js")
        assert asset.text == "console.log(1)" and "immutable" in asset.headers["Cache-Control"]
        assert c.get("/conversations/42").text == "<html>app</html>"  # client-side route
        assert c.get("/").headers["Cache-Control"] == "no-cache"
        assert "nope" not in c.get("/../secret.txt").text
        assert "nope" not in c.get("/%2e%2e/secret.txt").text
        assert c.get("/api/v1/nope").status_code == 404  # API paths never fall back
        assert c.get("/api/v1/info").json()["version"]


def test_json_logs_are_cloud_logging_entries():
    record = logging.LogRecord("app.x", logging.WARNING, __file__, 1, "Hello %s", ("you",), None)
    record.fields = {"httpRequest": {"status": 200}}
    entry = json.loads(JsonFormatter("proj").format(record))
    assert entry["severity"] == "WARNING" and entry["message"] == "Hello you"
    assert entry["httpRequest"] == {"status": 200}


def test_budget_is_loaded_from_todays_runs(settings, retriever, sql, chat_runs):
    # A real-looking client so the budget wraps it; it never gets called here.
    real = StubLLM()
    with make_client(settings, real, retriever, sql) as c:
        c.post("/api/v1/chat", json={"prompt": "PTO?"})  # 12 tokens recorded
    budget = DailyBudget(limit_tokens=100)
    import asyncio

    from app.db.session import build_engine, build_sessionmaker

    engine = build_engine(settings.sqlalchemy_url)
    asyncio.run(budget.load(build_sessionmaker(engine)))
    asyncio.run(engine.dispose())
    assert budget.used == 12
