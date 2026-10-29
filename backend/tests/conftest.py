import os
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
from app.core.config import Settings
from app.db.base import Base
from app.db.models import ChatRun
from app.llm.base import ChatMessage, LLMResult, StreamDelta
from app.main import create_app


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
        self.closed = False

    async def complete(self, messages: Sequence[ChatMessage]) -> LLMResult:
        self.calls.append(list(messages))
        if self.error:
            raise self.error
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
    Base.metadata.create_all(engine, tables=[ChatRun.__table__])
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
def app(settings: Settings, llm: StubLLM) -> FastAPI:
    app = create_app(settings)
    app.state.llm_client = llm
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
        await conn.execute(text("TRUNCATE documents, chunks, chat_runs CASCADE"))
    async with AsyncSession(engine, expire_on_commit=False) as session:
        yield session
    await engine.dispose()
