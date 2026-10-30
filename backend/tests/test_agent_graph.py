"""The multi-agent graph through the API, with stub model, retriever, and SQL executor."""

import json

from app.analytics.sql import SQLExecutionError
from app.llm.base import LLMError, LLMResult
from tests.conftest import make_chunk
from tests.test_agent_plan import plan_json

QUESTION = "Why did onboarding slow down in September, and how many tickets did we get?"
GOOD_SQL = json.dumps(
    {
        "title": "KYB tickets by month",
        "sql": "SELECT to_char(created_at, 'YYYY-MM') AS month, count(*) AS kyb_tickets "
        "FROM analytics.support_tickets WHERE tag = 'kyb-verification' GROUP BY 1 ORDER BY 1",
    }
)


def both_steps() -> str:
    return plan_json(("research", "INC-204 onboarding delays"), ("data", "KYB tickets by month"))


def sse_events(resp) -> list[tuple[str, dict]]:
    events, name = [], None
    for line in resp.iter_lines():
        if line.startswith("event: "):
            name = line[7:]
        elif line.startswith("data: "):
            events.append((name, json.loads(line[6:])))
    return events


def test_plan_runs_research_and_data_then_cites_both(client, llm, retriever, sql):
    llm.json_results = [both_steps(), GOOD_SQL]
    retriever.chunks = [make_chunk("INC-204", "Summary", "Verification timed out.")]
    llm.result = LLMResult(
        content="Tickets rose to 118 [T1] during INC-204 [S1]. Unsupported [S9].",
        model="stub-model",
    )

    resp = client.post("/api/v1/agent/run", json={"prompt": QUESTION})

    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["status"] == "succeeded"
    assert body["answer"] == "Tickets rose to 118 [T1] during INC-204 [S1]. Unsupported."
    assert body["citations"] == {"sources": [1], "tables": [1]}
    assert body["invalid_citations"] == 1
    assert [s["doc_key"] for s in body["sources"]] == ["INC-204"]

    [table] = body["tables"]
    assert table["index"] == 1 and table["origin"] == "generated"
    assert table["sql"].endswith("LIMIT 200")
    assert table["rows"] == [["2026-08", 9], ["2026-09", 118], ["2026-10", 14]]
    assert table["chart"]["x"] == "month"
    assert sql.queries == [table["sql"]]

    # The caller's groups reach retrieval; the search uses the planned query.
    assert retriever.queries == [("INC-204 onboarding delays", ["all-employees"])]
    # The analyst saw both kinds of evidence.
    evidence = llm.calls[-1][-2].content
    assert '<source id="S1"' in evidence and '<table id="T1"' in evidence

    nodes = [e["node"] for e in body["trace"]]
    assert nodes[0] == "supervisor" and nodes[-1] == "analyst"
    assert sorted(nodes[1:3]) == ["data", "research"]
    assert all(e["status"] == "succeeded" for e in body["trace"])


def test_run_is_persisted_with_trace(client, llm):
    llm.json_results = [both_steps(), GOOD_SQL]
    run_id = client.post("/api/v1/agent/run", json={"prompt": QUESTION}).json()["run_id"]

    stored = client.get(f"/api/v1/agent/runs/{run_id}").json()
    assert stored["status"] == "succeeded"
    assert stored["plan"]["steps"][1]["agent"] == "data"
    assert len(stored["trace"]) == 4
    [summary] = client.get("/api/v1/agent/runs").json()
    assert summary["run_id"] == run_id and summary["steps"] == 2


def test_invalid_plan_is_repaired_once(client, llm):
    llm.json_results = ["not json at all", plan_json(("research", "PTO carry over"))]
    body = client.post("/api/v1/agent/run", json={"prompt": "PTO carry-over?"}).json()

    supervisor = body["trace"][0]
    assert supervisor["status"] == "succeeded"
    assert supervisor["detail"]["attempts"] == 2
    assert "not valid JSON" in supervisor["detail"]["problems"][0]
    # The second planner call was shown its own invalid output and the error.
    repair = llm.calls[1]
    assert repair[-2].content == "not json at all"
    assert "invalid" in repair[-1].content


def test_planner_falls_back_to_keyword_plan(client, llm):
    llm.json_results = ["{}", "{}"]
    body = client.post("/api/v1/agent/run", json={"prompt": "How many tickets in September?"})
    body = body.json()
    assert body["trace"][0]["status"] == "fallback"
    assert [s["agent"] for s in body["plan"]["steps"]] == ["research", "data"]


def test_bad_sql_is_sent_back_with_the_error(client, llm, sql):
    bad = json.dumps({"title": "runs", "sql": "SELECT * FROM chat_runs"})
    llm.json_results = [plan_json(("data", "KYB tickets by month")), bad, GOOD_SQL]
    body = client.post("/api/v1/agent/run", json={"prompt": QUESTION}).json()

    [table] = body["tables"]
    assert table["origin"] == "generated"
    assert len(table["attempts"]) == 1
    assert "chat_runs is not allowed" in table["attempts"][0]["error"]
    assert len(sql.queries) == 1  # the rejected query never reached the database
    assert "chat_runs is not allowed" in llm.calls[2][-1].content


def test_sql_falls_back_to_certified_query(client, llm, sql, settings):
    bad = json.dumps({"sql": "DELETE FROM analytics.customers"})
    llm.json_results = [plan_json(("data", "kyb verification tickets by month")),
                        *[bad] * settings.agent_max_sql_attempts]  # fmt: skip
    body = client.post("/api/v1/agent/run", json={"prompt": QUESTION}).json()

    [table] = body["tables"]
    assert table["origin"] == "certified"
    assert table["title"] == "Onboarding-related support tickets by month and tag"
    assert len(table["attempts"]) == settings.agent_max_sql_attempts
    data_event = next(e for e in body["trace"] if e["node"] == "data")
    assert data_event["status"] == "fallback"


def test_failed_data_step_is_reported_not_fatal(client, llm, sql):
    sql.error = SQLExecutionError("relation does not exist")
    no_match = json.dumps({"sql": "SELECT count(*) FROM analytics.customers"})
    llm.json_results = [plan_json(("data", "revenue per seat")), *[no_match] * 3]
    body = client.post("/api/v1/agent/run", json={"prompt": "Revenue per seat?"}).json()

    assert body["status"] == "succeeded"
    [table] = body["tables"]
    assert table["index"] is None
    assert "relation does not exist" in table["error"]
    assert "<failed_query" in llm.calls[-1][-2].content


def test_no_steps_answers_directly(client, llm, retriever, sql):
    llm.json_results = [json.dumps({"reasoning": "chit-chat", "steps": []})]
    body = client.post("/api/v1/agent/run", json={"prompt": "Thanks!"}).json()

    assert body["answer"] == "stub answer"
    assert retriever.queries == [] and sql.queries == []
    assert [e["node"] for e in body["trace"]] == ["supervisor", "analyst"]


def test_stream_emits_progress_then_done(client, llm, retriever):
    llm.json_results = [both_steps(), GOOD_SQL]
    retriever.chunks = [make_chunk("INC-204", "Summary", "Verification timed out.")]
    with client.stream("POST", "/api/v1/agent/stream", json={"prompt": QUESTION}) as resp:
        assert resp.headers["content-type"].startswith("text/event-stream")
        events = sse_events(resp)

    names = [n for n, _ in events]
    assert names[0] == "run" and names[-1] == "done"
    for expected in ("plan", "step", "sql", "evidence", "answer_reset", "delta"):
        assert expected in names
    assert names.index("plan") < names.index("evidence") < names.index("delta")
    text = "".join(d["text"] for n, d in events if n == "delta")
    assert text.strip() == "stub answer"
    evidence = dict(events)["evidence"]
    assert evidence["tables"][0]["index"] == 1 and evidence["sources"][0]["index"] == 1


def test_failed_run_resumes_from_checkpoint(client, llm, sql, retriever):
    llm.json_results = [both_steps(), GOOD_SQL]
    retriever.chunks = [make_chunk("INC-204", "Summary", "Verification timed out.")]
    healthy_stream = llm.stream
    outages = {"left": 2}  # both analyst attempts (the node retries once) fail

    def flaky_stream(messages):
        if outages["left"]:
            outages["left"] -= 1
            raise LLMError("provider down")
        return healthy_stream(messages)

    llm.stream = flaky_stream
    with client.stream("POST", "/api/v1/agent/stream", json={"prompt": QUESTION}) as resp:
        events = sse_events(resp)
    name, error = events[-1]
    assert name == "error" and error["resumable"] is True
    run_id = error["run_id"]

    failed = client.get(f"/api/v1/agent/runs/{run_id}").json()
    assert failed["status"] == "failed" and failed["error_type"] == "LLMError"
    assert {e["node"] for e in failed["trace"]} == {"supervisor", "research", "data"}

    calls_before = len(llm.calls)
    with client.stream("POST", f"/api/v1/agent/runs/{run_id}/resume") as resp:
        events = sse_events(resp)
    assert events[0] == ("run", {"run_id": run_id, "resumed": True, "pending": ["analyst"]})
    done = events[-1][1]
    assert done["status"] == "succeeded" and done["answer"] == "stub answer"
    # Only the analyst ran again: no new plan, no repeated SQL.
    assert len(llm.calls) == calls_before + 1
    assert len(sql.queries) == 1
    assert [e["node"] for e in done["trace"]].count("supervisor") == 1


def test_unknown_runs_return_404(client):
    missing = "00000000-0000-0000-0000-000000000000"
    assert client.get(f"/api/v1/agent/runs/{missing}").status_code == 404
    assert client.post(f"/api/v1/agent/runs/{missing}/resume").status_code == 404


def test_rejects_blank_prompt(client, llm):
    assert client.post("/api/v1/agent/run", json={"prompt": "  "}).status_code == 422
    assert llm.calls == []


def test_dependent_data_step_waits_for_research_and_sees_its_findings(client, llm, retriever):
    plan = json.loads(plan_json(("research", "INC-204 dates"), ("data", "timeouts during INC-204")))
    plan["steps"][1]["depends_on"] = ["s1"]
    llm.json_results = [json.dumps(plan), GOOD_SQL]
    retriever.chunks = [make_chunk("INC-204", "Summary", "Between 2026-09-08 and 2026-09-19 ...")]

    body = client.post("/api/v1/agent/run", json={"prompt": QUESTION}).json()

    assert body["status"] == "succeeded"
    nodes = [e["node"] for e in body["trace"]]
    assert nodes == ["supervisor", "research", "data", "analyst"]  # two waves, in order
    sql_request = llm.calls[1][-1].content
    assert "<findings>" in sql_request and "2026-09-08" in sql_request
    data_event = body["trace"][2]
    assert data_event["detail"]["used_findings"] is True


def test_plan_rejects_invalid_dependencies(client, llm):
    plan = json.loads(plan_json(("data", "tickets"), ("research", "INC-204")))
    plan["steps"][1]["depends_on"] = ["s1"]  # research may not wait for data
    llm.json_results = [json.dumps(plan), json.dumps(plan)]
    body = client.post("/api/v1/agent/run", json={"prompt": "tickets?"}).json()
    supervisor = body["trace"][0]
    assert supervisor["status"] == "fallback"
    assert "only data steps can depend" in supervisor["detail"]["problems"][0]
