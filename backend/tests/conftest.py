import os
import uuid
from collections.abc import AsyncIterator, Sequence
from pathlib import Path

import pytest
from alembic.config import Config
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select, text
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import Session

from alembic import command
from app.actions.gateway import ToolResult
from app.analytics.sql import QueryResult
from app.core.config import Settings
from app.db.base import Base
from app.db.models import ActionAudit, AgentAction, AgentRun, ChatRun
from app.llm.base import ChatMessage, LLMResult, StreamDelta
from app.main import create_app
from app.rag.embeddings import HashingEmbedder
from app.rag.retrieval import RetrievedChunk


class StubLLM:
    """Records calls and returns a canned result (or raises a canned error)."""

    provider = "stub"
    model = "stub-model"

    def __init__(self) -> None:
        self.result = LLMResult(
            content="stub answer", model="stub-model", prompt_tokens=10, completion_tokens=2
        )
        self.error: Exception | None = None
        self.calls: list[list[ChatMessage]] = []
        self.json_results: list[str] = []  # returned in order by json_mode calls
        self.closed = False

    async def complete(
        self, messages: Sequence[ChatMessage], *, json_mode: bool = False
    ) -> LLMResult:
        self.calls.append(list(messages))
        if self.error:
            raise self.error
        if json_mode and self.json_results:
            return LLMResult(content=self.json_results.pop(0), model=self.model)
        return self.result

    async def stream(
        self, messages: Sequence[ChatMessage]
    ) -> AsyncIterator[StreamDelta | LLMResult]:
        self.calls.append(list(messages))
        for word in self.result.content.split(" "):
            yield StreamDelta(word + " ")
        if self.error:  # fail mid-stream, after some text was sent
            raise self.error
        yield self.result

    async def aclose(self) -> None:
        self.closed = True


class StubRetriever:
    """Returns canned chunks (or raises) and records the queries it receives."""

    def __init__(self) -> None:
        self.embedder = HashingEmbedder()
        self.chunks: list[RetrievedChunk] = []
        self.error: Exception | None = None
        self.queries: list[tuple[str, list[str]]] = []
        self.options: list[dict] = []  # mode / rerank per search

    async def search(self, session, query, groups, **kwargs) -> list[RetrievedChunk]:
        self.queries.append((query, list(groups)))
        self.options.append(kwargs)
        if self.error:
            raise self.error
        return self.chunks


class StubSQL:
    """Stands in for SQLExecutor: records queries and returns a canned result."""

    def __init__(self) -> None:
        self.result = QueryResult(
            columns=["month", "kyb_tickets"],
            rows=[["2026-08", 9], ["2026-09", 118], ["2026-10", 14]],
            truncated=False,
            elapsed_ms=3,
        )
        self.error: Exception | None = None
        self.queries: list[str] = []

    async def run(self, sql: str) -> QueryResult:
        self.queries.append(sql)
        if self.error:
            raise self.error
        return self.result


class StubTools:
    """A ToolGateway with the tracker's real tool schemas that records every call."""

    server = "tracker-stub"

    def __init__(self, tools) -> None:
        self.tools = tools
        self.calls: list[tuple[str, dict]] = []
        self.fail_with: str | None = None

    async def call(self, name, arguments):
        self.calls.append((name, arguments))
        if name == "search_issues":
            return ToolResult(ok=True, data={"issues": []})
        if self.fail_with:
            return ToolResult(ok=False, error=self.fail_with)
        n = sum(1 for c, _ in self.calls if c == "create_issue")
        return ToolResult(ok=True, data={"key": f"HEL-{n}", "url": f"tracker://helio/HEL-{n}",
                                         "title": arguments["title"]})  # fmt: skip

    def created(self) -> list[dict]:
        return [args for name, args in self.calls if name == "create_issue"]


@pytest.fixture(scope="session")
def tracker_tool_specs(tmp_path_factory):
    """The tracker MCP server's real tool list, fetched once through an in-process client."""
    import asyncio

    from mcp import Client

    from app.actions.gateway import load_tools
    from app.mcp_servers.tracker import LocalTracker, build_server

    async def fetch():
        path = tmp_path_factory.mktemp("tracker") / "t.sqlite3"
        async with Client(build_server(LocalTracker(str(path)))) as client:
            return await load_tools(client)

    return asyncio.run(fetch())


@pytest.fixture
def tools(tracker_tool_specs) -> StubTools:
    return StubTools(tracker_tool_specs)


def make_chunk(doc_key: str, section: str, content: str) -> RetrievedChunk:
    return RetrievedChunk(
        chunk_id=uuid.uuid4(),
        doc_key=doc_key,
        title=doc_key,
        section=section,
        content=content,
        source_path=f"{doc_key}.md",
        doc_type="policy",
        score=0.03,
    )


@pytest.fixture(autouse=True)
def _isolate_env(monkeypatch):
    """Keep the developer's real credentials (e.g. OPENAI_API_KEY) out of tests."""
    for var in ("OPENAI_API_KEY", "LLM_API_KEY", "LLM_PROVIDER"):
        monkeypatch.delenv(var, raising=False)


@pytest.fixture
def db_path(tmp_path):
    """A throwaway SQLite database with the schema created (unit tests only).

    Postgres-specific behavior (pgvector, migrations) is covered by integration tests.
    """
    path = tmp_path / "test.db"
    engine = create_engine(f"sqlite:///{path}")
    # Only tables that work on SQLite; knowledge-base tables need Postgres (integration tests).
    Base.metadata.create_all(
        engine, tables=[t.__table__ for t in (ChatRun, AgentRun, AgentAction, ActionAudit)]
    )
    engine.dispose()
    return path


@pytest.fixture
def settings(db_path) -> Settings:
    # _env_file=None keeps a developer's local .env from leaking into tests.
    return Settings(
        _env_file=None,
        app_env="test",
        llm_provider="fake",
        database_url=f"sqlite+aiosqlite:///{db_path}",
        agent_checkpointer="memory",
        actions_enabled=False,  # tests that need tools install a StubTools gateway
    )


@pytest.fixture
def chat_runs(db_path):
    """Returns a function that reads all persisted chat runs."""

    def _read() -> list[ChatRun]:
        engine = create_engine(f"sqlite:///{db_path}")
        with Session(engine) as session:
            rows = list(session.scalars(select(ChatRun).order_by(ChatRun.created_at)))
        engine.dispose()
        return rows

    return _read


@pytest.fixture
def llm() -> StubLLM:
    return StubLLM()


@pytest.fixture
def retriever() -> StubRetriever:
    return StubRetriever()


@pytest.fixture
def sql() -> StubSQL:
    return StubSQL()


@pytest.fixture
def app(settings: Settings, llm: StubLLM, retriever: StubRetriever, sql: StubSQL) -> FastAPI:
    app = create_app(settings)
    app.state.llm_client = llm
    app.state.retriever = retriever
    app.state.sql_executor = sql
    return app


@pytest.fixture
def client(app: FastAPI):
    with TestClient(app) as c:
        yield c


# ---------- PostgreSQL integration fixtures (pytest -m integration) ----------

BACKEND_DIR = Path(__file__).resolve().parents[1]
CORPUS_DIR = BACKEND_DIR.parent / "datasets" / "documents"


@pytest.fixture(scope="session")
def migrated_db() -> str:
    """A real Postgres + pgvector database, migrated from scratch to head."""
    url = os.getenv("DATABASE_URL")
    if not url:
        pytest.skip("DATABASE_URL not set")
    cfg = Config(str(BACKEND_DIR / "alembic.ini"))
    cfg.set_main_option("script_location", str(BACKEND_DIR / "alembic"))
    cfg.set_main_option("sqlalchemy.url", url)
    command.downgrade(cfg, "base")
    command.upgrade(cfg, "head")
    return url


@pytest.fixture
async def pg_session(migrated_db) -> AsyncIterator[AsyncSession]:
    """An async session on an empty knowledge base."""
    engine = create_async_engine(migrated_db)
    async with engine.begin() as conn:
        await conn.execute(
            text(
                "TRUNCATE documents, chunks, chat_runs, agent_runs, agent_actions, action_audit "
                "CASCADE"
            )
        )
    async with AsyncSession(engine, expire_on_commit=False) as session:
        yield session
    await engine.dispose()
