"""Integration tests against a real PostgreSQL + pgvector instance.

Run with:  DATABASE_URL=postgresql+asyncpg://... pytest -m integration
"""

import asyncio
import os
from pathlib import Path

import pytest
from alembic.config import Config
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

from alembic import command
from app.core.config import Settings
from app.main import create_app

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(not os.getenv("DATABASE_URL"), reason="DATABASE_URL not set"),
]

BACKEND_DIR = Path(__file__).resolve().parents[1]


@pytest.fixture(scope="module")
def migrated_db() -> str:
    url = os.environ["DATABASE_URL"]
    cfg = Config(str(BACKEND_DIR / "alembic.ini"))
    cfg.set_main_option("script_location", str(BACKEND_DIR / "alembic"))
    cfg.set_main_option("sqlalchemy.url", url)
    command.downgrade(cfg, "base")
    command.upgrade(cfg, "head")
    return url


async def test_migration_enables_pgvector(migrated_db):
    engine = create_async_engine(migrated_db)
    async with engine.connect() as conn:
        ext = await conn.scalar(text("SELECT extname FROM pg_extension WHERE extname = 'vector'"))
        # Round-trip a vector literal to prove the type actually works.
        dist = await conn.scalar(text("SELECT '[1,2,3]'::vector <-> '[1,2,4]'::vector"))
    await engine.dispose()
    assert ext == "vector"
    assert dist == pytest.approx(1.0)


def test_chat_persists_run_in_postgres(migrated_db):
    settings = Settings(
        _env_file=None, app_env="test", llm_provider="fake", database_url=migrated_db
    )
    with TestClient(create_app(settings)) as client:
        assert client.get("/health/ready").status_code == 200
        resp = client.post("/api/v1/chat", json={"prompt": "integration check"})

    assert resp.status_code == 200
    run_id = resp.json()["run_id"]

    async def fetch():
        engine = create_async_engine(migrated_db)
        async with engine.connect() as conn:
            row = (
                await conn.execute(
                    text("SELECT status, provider, prompt FROM chat_runs WHERE id = :id"),
                    {"id": run_id},
                )
            ).one()
        await engine.dispose()
        return row

    assert tuple(asyncio.run(fetch())) == ("succeeded", "fake", "integration check")
