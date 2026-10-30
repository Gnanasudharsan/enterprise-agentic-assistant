"""Approved actions end to end: Postgres checkpoints + the tracker MCP server over stdio."""

import json
import sqlite3

import pytest
from fastapi.testclient import TestClient

from app.core.config import Settings
from app.main import create_app
from app.rag.embeddings import HashingEmbedder
from app.rag.ingestion import ingest_directory
from tests.conftest import CORPUS_DIR

pytestmark = pytest.mark.integration


def sse(resp) -> list[tuple[str, dict]]:
    events, name = [], None
    for line in resp.iter_lines():
        if line.startswith("event: "):
            name = line[7:]
        elif line.startswith("data: "):
            events.append((name, json.loads(line[6:])))
    return events


async def test_offline_run_pauses_then_creates_issue_after_approval(
    pg_session, migrated_db, tmp_path
):
    await ingest_directory(pg_session, CORPUS_DIR, HashingEmbedder())
    tracker = tmp_path / "tracker.sqlite3"
    settings = Settings(
        _env_file=None,
        llm_provider="fake",
        embedding_provider="hashing",
        database_url=migrated_db,
        agent_checkpointer="postgres",
        tracker_db_path=str(tracker),
    )
    with TestClient(create_app(settings)) as client:
        assert {t["name"] for t in client.get("/api/v1/tools").json()} == {
            "create_issue",
            "search_issues",
        }
        run = client.post(
            "/api/v1/agent/run",
            json={"prompt": "What caused INC-204? Create a follow-up issue for the async queue."},
        ).json()
        assert run["status"] == "needs_approval", run["trace"]
        [action] = run["actions"]
        assert action["status"] == "proposed"
        # The process restarting would not matter: the pause lives in Postgres.
        assert client.get(f"/api/v1/agent/runs/{run['run_id']}").json()["status"] == (
            "needs_approval"
        )
        assert (
            not tracker.exists()
            or not sqlite3.connect(tracker).execute("SELECT count(*) FROM issues").fetchone()[0]
        )

        url = f"/api/v1/agent/runs/{run['run_id']}/actions/{action['id']}/decision"
        with client.stream("POST", url, json={"decision": "approve"}) as resp:
            done = sse(resp)[-1][1]

    assert done["status"] == "succeeded"
    [action] = done["actions"]
    assert action["status"] == "executed" and action["result"]["key"] == "HEL-1"
    [(title, body)] = sqlite3.connect(tracker).execute("SELECT title, body FROM issues").fetchall()
    assert title == action["arguments"]["title"]
    assert "approved by demo-user" in body
