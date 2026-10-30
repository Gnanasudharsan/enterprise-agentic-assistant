"""Controlled actions: nothing runs without a recorded human approval, and the backend
(not the model) enforces permissions and argument integrity. Target: 0 unauthorized
executions across these scenarios."""

import json

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select, update
from sqlalchemy.orm import Session

from app.db.models import ActionAudit, AgentAction
from app.main import create_app
from tests.conftest import make_chunk
from tests.test_agent_graph import sse_events
from tests.test_agent_plan import plan_json

QUESTION = "Summarize INC-204 and create a follow-up issue to add bulk KYB retries."
DRAFT = {
    "tool": "create_issue",
    "arguments": {
        "title": "Add bulk retry for failed KYB verifications",
        "body": "## Context\nINC-204 showed specialists cannot bulk-retry failed checks [S1].",
        "labels": ["verification", "incident-follow-up"],
        "priority": "P2",
    },
    "rationale": "INC-204 lists missing bulk-retry tooling as a contributing factor.",
}


def research_and_action() -> str:
    return plan_json(("research", "INC-204 contributing factors"),
                     ("action", "Create a follow-up issue for bulk KYB retries"))  # fmt: skip


@pytest.fixture
def make_client(settings, llm, retriever, sql, tools):
    def _make(**overrides) -> TestClient:
        app = create_app(settings.model_copy(update=overrides))
        app.state.llm_client = llm
        app.state.retriever = retriever
        app.state.sql_executor = sql
        app.state.tool_gateway = tools
        return TestClient(app)

    return _make


@pytest.fixture
def client(make_client):
    with make_client() as c:
        yield c


@pytest.fixture
def db_rows(db_path):
    def _read(model):
        engine = create_engine(f"sqlite:///{db_path}")
        with Session(engine) as s:
            rows = list(s.scalars(select(model)))
        engine.dispose()
        return rows

    return _read


def start_run(client, llm, retriever, draft=DRAFT) -> dict:
    llm.json_results = [research_and_action(), json.dumps(draft)]
    retriever.chunks = [make_chunk("INC-204", "Contributing factors", "No bulk-retry tooling.")]
    resp = client.post("/api/v1/agent/run", json={"prompt": QUESTION})
    assert resp.status_code == 200, resp.text
    return resp.json()


def decision_url(run: dict) -> str:
    return f"/api/v1/agent/runs/{run['run_id']}/actions/{run['actions'][0]['id']}/decision"


def decide(client, run: dict, **body):
    action_id = run["actions"][0]["id"]
    return client.post(
        f"/api/v1/agent/runs/{run['run_id']}/actions/{action_id}/decision", json=body
    )


def test_run_pauses_with_a_proposal_and_creates_nothing(client, llm, retriever, tools):
    run = start_run(client, llm, retriever)

    assert run["status"] == "needs_approval"
    [action] = run["actions"]
    assert action["status"] == "proposed" and action["tool"] == "create_issue"
    assert action["arguments"]["title"] == DRAFT["arguments"]["title"]
    assert "[S1]" not in action["arguments"]["body"]  # chat markers stripped from the draft
    assert [e["event"] for e in action["audit"]] == ["proposed"]
    assert tools.created() == []  # only the read-only duplicate search ran
    assert [name for name, _ in tools.calls] == ["search_issues"]
    # The analyst was told the action still needs approval.
    assert "not created until they approve" in llm.calls[-2][-2].content


def test_approval_executes_once_with_provenance(client, llm, retriever, tools, db_rows):
    run = start_run(client, llm, retriever)
    with client.stream("POST", decision_url(run), json={"decision": "approve"}) as r:
        assert r.status_code == 200
        events = sse_events(r)

    done = events[-1][1]
    assert done["status"] == "succeeded"
    [action] = done["actions"]
    assert action["status"] == "executed" and action["result"]["key"] == "HEL-1"
    assert action["decided_by"] == "demo-user"
    assert [e["event"] for e in action["audit"]] == [
        "proposed",
        "approved",
        "executing",
        "executed",
    ]
    [created] = tools.created()
    assert created["title"] == DRAFT["arguments"]["title"]
    assert "approved by demo-user" in created["body"]  # added by the backend, not the model
    assert any(name == "action" for name, _ in events)

    again = decide(client, run, decision="approve")
    assert again.status_code == 409
    assert len(tools.created()) == 1


def test_rejection_never_executes(client, llm, retriever, tools):
    run = start_run(client, llm, retriever)
    with client.stream(
        "POST", decision_url(run), json={"decision": "reject", "comment": "Already tracked"}
    ) as r:
        done = sse_events(r)[-1][1]
    assert done["actions"][0]["status"] == "rejected"
    assert tools.created() == []
    assert decide(client, run, decision="approve").status_code == 409


def test_edited_arguments_are_validated_and_audited(client, llm, retriever, tools):
    run = start_run(client, llm, retriever)
    bad = {**DRAFT["arguments"], "labels": ["admin"]}
    resp = decide(client, run, decision="approve", arguments=bad)
    assert resp.status_code == 422 and "labels" in resp.json()["detail"]

    edited = {**run["actions"][0]["arguments"], "title": "Bulk-retry KYB checks from the console"}
    with client.stream(
        "POST", decision_url(run), json={"decision": "approve", "arguments": edited}
    ) as r:
        action = sse_events(r)[-1][1]["actions"][0]
    assert tools.created()[0]["title"] == edited["title"]
    events = [e["event"] for e in action["audit"]]
    assert events[:3] == ["proposed", "edited", "approved"]
    assert action["audit"][1]["detail"]["fields"] == ["title"]


def test_caller_without_permission_cannot_approve(client, llm, retriever, tools, db_rows):
    run = start_run(client, llm, retriever)
    client.app.state.agent_service.policy = client.app.state.agent_service.policy.__class__(
        {"create_issue": frozenset({"engineering"})}
    )
    resp = decide(client, run, decision="approve")
    assert resp.status_code == 403
    assert tools.created() == []
    denied = [a for a in db_rows(ActionAudit) if a.event == "denied"]
    assert len(denied) == 1 and denied[0].actor == "demo-user"
    assert db_rows(AgentAction)[0].status == "proposed"


def test_no_proposal_when_the_caller_lacks_permission(make_client, llm, retriever, tools, db_rows):
    with make_client(action_permissions={"create_issue": ["engineering"]}) as client:
        llm.json_results = [research_and_action(), json.dumps(DRAFT)]
        run = client.post("/api/v1/agent/run", json={"prompt": QUESTION}).json()
    assert run["status"] == "succeeded" and run["actions"] == []
    action_event = next(e for e in run["trace"] if e["node"] == "action")
    assert action_event["status"] == "failed" and "permission" in action_event["summary"]
    assert [a.event for a in db_rows(ActionAudit)] == ["denied"]
    assert tools.calls == []


def test_arguments_changed_after_approval_are_blocked(client, llm, retriever, tools, db_path):
    run = start_run(client, llm, retriever)
    service = client.app.state.agent_service
    original = service.continue_after_decision

    def tamper_then_continue(run_id, value):
        engine = create_engine(f"sqlite:///{db_path}")
        with Session(engine) as s:  # e.g. a compromised process editing the stored call
            tampered = {**DRAFT["arguments"], "title": "Grant admin to everyone"}
            s.execute(update(AgentAction).values(arguments=tampered))
            s.commit()
        engine.dispose()
        return original(run_id, value)

    service.continue_after_decision = tamper_then_continue
    with client.stream("POST", decision_url(run), json={"decision": "approve"}) as r:
        action = sse_events(r)[-1][1]["actions"][0]
    assert tools.created() == []
    assert action["status"] == "failed" and "changed after approval" in action["error"]
    assert action["audit"][-1]["event"] == "denied"


@pytest.mark.parametrize(
    "bad_draft",
    [
        {**DRAFT, "tool": "delete_repository"},  # not a tool the caller was offered
        {**DRAFT, "tool": "search_issues"},  # read-only tools are not "actions"
        {**DRAFT, "arguments": {**DRAFT["arguments"], "labels": ["admin"]}},  # schema
        {**DRAFT, "arguments": {"title": "x"}},  # schema
    ],
)
def test_invalid_drafts_are_never_proposed(client, llm, retriever, tools, bad_draft):
    llm.json_results = [research_and_action(), json.dumps(bad_draft), json.dumps(bad_draft)]
    run = client.post("/api/v1/agent/run", json={"prompt": QUESTION}).json()
    assert run["status"] == "succeeded" and run["actions"] == []
    assert tools.created() == []
    action_event = next(e for e in run["trace"] if e["node"] == "action")
    assert action_event["status"] == "failed" and len(action_event["detail"]["problems"]) == 2


def test_failed_tool_call_is_recorded(client, llm, retriever, tools):
    tools.fail_with = "GitHub returned 403"
    run = start_run(client, llm, retriever)
    with client.stream("POST", decision_url(run), json={"decision": "approve"}) as r:
        action = sse_events(r)[-1][1]["actions"][0]
    assert action["status"] == "failed" and action["error"] == "GitHub returned 403"
    assert action["audit"][-1]["event"] == "failed"


def test_paused_run_cannot_be_resumed_without_a_decision(client, llm, retriever):
    run = start_run(client, llm, retriever)
    assert client.post(f"/api/v1/agent/runs/{run['run_id']}/resume").status_code == 409


def test_action_steps_are_refused_when_actions_are_off(settings, llm, retriever, sql):
    app = create_app(settings)  # actions_enabled=False: no tool gateway at all
    app.state.llm_client, app.state.retriever, app.state.sql_executor = llm, retriever, sql
    llm.json_results = [research_and_action(), research_and_action()]
    with TestClient(app) as client:
        run = client.post("/api/v1/agent/run", json={"prompt": QUESTION}).json()
        assert client.get("/api/v1/tools").json() == []
    supervisor = run["trace"][0]
    assert supervisor["status"] == "fallback"
    assert "not available" in supervisor["detail"]["problems"][0]
    assert all(s["agent"] != "action" for s in run["plan"]["steps"]) and run["actions"] == []


def test_tools_and_actions_endpoints(client, llm, retriever):
    tools_out = {t["name"]: t for t in client.get("/api/v1/tools").json()}
    assert tools_out["create_issue"]["requires_approval"] is True
    assert tools_out["search_issues"]["requires_approval"] is False
    assert tools_out["create_issue"]["permitted"] is True

    run = start_run(client, llm, retriever)
    [listed] = client.get("/api/v1/actions", params={"status": "proposed"}).json()
    assert listed["run_id"] == run["run_id"]
    assert client.get(f"/api/v1/actions/{listed['id']}").json()["audit"][0]["event"] == "proposed"
