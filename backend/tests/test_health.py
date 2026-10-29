from fastapi.testclient import TestClient

from app import __version__
from app.main import create_app


def test_health_returns_ok(client):
    resp = client.get("/health")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok", "version": __version__, "env": "test"}


def test_ready_when_database_reachable(client):
    resp = client.get("/health/ready")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok", "database": "up"}


def test_ready_returns_503_when_database_down(settings, llm, tmp_path):
    bad = settings.model_copy(
        update={"database_url": f"sqlite+aiosqlite:///{tmp_path}/missing-dir/x.db"}
    )
    app = create_app(bad)
    app.state.llm_client = llm
    with TestClient(app) as c:
        resp = c.get("/health/ready")
    assert resp.status_code == 503
    assert resp.json()["database"] == "down"
