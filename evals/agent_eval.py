# ruff: noqa: E501  (long Markdown table templates in the report)
"""Multi-agent evaluation through the running API.

Usage (backend running with a real model, corpus and analytics data seeded):

    cd backend && .venv/bin/python ../evals/agent_eval.py [--base-url http://localhost:8000]

For each task in datasets/evaluation/agent_tasks.jsonl, measures:
- routing: the plan used every specialist the task needs
- data accuracy: every expected number (from the deterministic analytics data) is in the answer
- document grounding: the answer cites at least one expected document
- citation validity: no invalid [S#]/[T#] markers had to be removed
- safety: injected SQL never reaches non-analytics tables; restricted facts never leak
- latency (p50/p95) and plan size
Writes evals/reports/agents-<date>.md and .json.
"""

import argparse
import json
import re
import statistics
from datetime import date
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parents[1]
TASKS = ROOT / "datasets" / "evaluation" / "agent_tasks.jsonl"
REPORTS = ROOT / "evals" / "reports"


def normalize(text: str) -> str:
    return re.sub(r"\s+", " ", text.replace("**", "").replace("`", "")).lower()


def has_number(answer: str, number: str) -> bool:
    # Whole-number match: "9" must not match inside "19" or "9.5".
    return re.search(rf"(?<![\d.]){re.escape(number)}(?![\d]|\.\d)", answer) is not None


def evaluate(task: dict, run: dict) -> dict:
    answer = normalize(run.get("answer") or "")
    plan_agents = {s["agent"] for s in (run.get("plan") or {}).get("steps", [])}
    cited_docs = {s["doc_key"] for s in run["sources"] if s["index"] in run["citations"]["sources"]}
    checks: dict[str, bool] = {"succeeded": run["status"] == "succeeded"}
    if task["agents"]:
        checks["routing"] = set(task["agents"]) <= plan_agents
    if "max_steps" in task:
        checks["routing"] = len((run.get("plan") or {}).get("steps", [])) <= task["max_steps"]
    if task["numbers"]:
        checks["data_accuracy"] = all(has_number(answer, n) for n in task["numbers"])
    if "data" in task["agents"]:
        checks["cites_data"] = bool(run["citations"]["tables"])
    if task["docs"]:
        checks["doc_grounding"] = bool(cited_docs & set(task["docs"]))
    checks["citations_valid"] = run["invalid_citations"] == 0
    if task.get("forbid_tables"):
        sql = " ".join((t.get("sql") or "") for t in run["tables"]).lower()
        checks["sql_contained"] = not any(f in sql for f in task["forbid_tables"])
    if task.get("restricted_facts"):
        checks["no_leak"] = not any(normalize(f) in answer for f in task["restricted_facts"])
    return {
        "id": task["id"],
        "category": task["category"],
        "question": task["question"],
        "passed": all(checks.values()),
        "checks": checks,
        "plan": sorted(plan_agents),
        "steps": len((run.get("plan") or {}).get("steps", [])),
        "tables": [(t["title"], t.get("origin"), bool(t.get("error"))) for t in run["tables"]],
        "cited_docs": sorted(cited_docs),
        "latency_ms": run["latency_ms"],
        "run_id": run["run_id"],
        "answer": run.get("answer"),
    }


def pct(values: list[bool]) -> str:
    return f"{100 * sum(values) / len(values):.0f}%" if values else "n/a"


def main(base_url: str) -> None:
    tasks = [json.loads(line) for line in TASKS.read_text().splitlines() if line.strip()]
    client = httpx.Client(base_url=base_url, timeout=180)
    info = client.get("/api/v1/info").json()
    if info["demo_mode"]:
        raise SystemExit("The backend is in demo mode; connect a real model first.")

    rows = []
    for task in tasks:
        resp = client.post("/api/v1/agent/run", json={"prompt": task["question"]})
        resp.raise_for_status()
        row = evaluate(task, resp.json())
        rows.append(row)
        status = (
            "PASS"
            if row["passed"]
            else "FAIL " + ",".join(k for k, v in row["checks"].items() if not v)
        )
        print(f"{task['id']} {status:<30} {row['latency_ms']:>6} ms  plan={row['plan']}")

    def metric(name: str) -> list[bool]:
        return [r["checks"][name] for r in rows if name in r["checks"]]

    latencies = sorted(r["latency_ms"] for r in rows)
    p95 = latencies[min(len(latencies) - 1, round(0.95 * (len(latencies) - 1)))]
    summary = {
        "date": date.today().isoformat(),
        "model": info["model"],
        "embedding_model": info["embedding_model"],
        "tasks": len(rows),
        "task_success": pct([r["passed"] for r in rows]),
        "routing": pct(metric("routing")),
        "data_accuracy": pct(metric("data_accuracy")),
        "doc_grounding": pct(metric("doc_grounding")),
        "citations_valid": pct(metric("citations_valid")),
        "safety": pct(metric("sql_contained") + metric("no_leak")),
        "latency_p50_ms": round(statistics.median(latencies)),
        "latency_p95_ms": p95,
        "avg_steps": round(statistics.mean(r["steps"] for r in rows), 2),
        "certified_fallbacks": sum(1 for r in rows for t in r["tables"] if t[1] == "certified"),
    }

    REPORTS.mkdir(exist_ok=True)
    stem = REPORTS / f"agents-{summary['date']}"
    stem.with_suffix(".json").write_text(json.dumps({"summary": summary, "rows": rows}, indent=2))
    lines = [
        f"# Multi-agent evaluation — {summary['date']}",
        "",
        f"Model `{summary['model']}`, embeddings `{summary['embedding_model']}`, "
        f"{summary['tasks']} tasks from `datasets/evaluation/agent_tasks.jsonl`, asked as a "
        "regular employee (`all-employees`).",
        "",
        "| Metric | Result |",
        "| --- | --- |",
        f"| Task success (all checks pass) | **{summary['task_success']}** |",
        f"| Routing (plan used the needed specialists) | {summary['routing']} |",
        f"| Data accuracy (expected numbers in the answer) | {summary['data_accuracy']} |",
        f"| Document grounding (cites an expected document) | {summary['doc_grounding']} |",
        f"| Citation validity (no invalid markers) | {summary['citations_valid']} |",
        f"| Safety (SQL contained, no restricted leaks) | {summary['safety']} |",
        f"| Latency p50 / p95 | {summary['latency_p50_ms']:,} ms / {summary['latency_p95_ms']:,} ms |",
        f"| Average plan size | {summary['avg_steps']} steps |",
        f"| Reviewed-query fallbacks | {summary['certified_fallbacks']} |",
        "",
        "These tasks were used while developing the agents, so read this as a regression "
        "suite, not an unbiased benchmark. Phase 5 adds a larger held-out benchmark and "
        "compares baseline RAG with the multi-agent system.",
        "",
        "## Tasks",
        "",
        "| ID | Category | Result | Plan | Data | Cited documents | Latency |",
        "| --- | --- | --- | --- | --- | --- | --- |",
    ]
    for r in rows:
        failed = [k for k, v in r["checks"].items() if not v]
        result = "pass" if r["passed"] else "fail: " + ", ".join(failed)
        data = "; ".join(f"{t[0]} ({'failed' if t[2] else t[1]})" for t in r["tables"]) or "—"
        lines.append(
            f"| {r['id']} | {r['category']} | {result} | {', '.join(r['plan']) or 'none'} | "
            f"{data} | {', '.join(r['cited_docs']) or '—'} | {r['latency_ms']:,} ms |"
        )
    stem.with_suffix(".md").write_text("\n".join(lines) + "\n")
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", default="http://localhost:8000")
    main(parser.parse_args().base_url)
