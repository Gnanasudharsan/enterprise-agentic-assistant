# ruff: noqa: E501, ASYNC212, ASYNC240  (Markdown report templates; a sequential script, blocking calls are intended)
"""Held-out benchmark: baseline RAG vs. hybrid + rerank vs. the multi-agent system.

Usage (backend running with a real model; corpus and analytics data seeded):

    cd backend && .venv/bin/python ../evals/benchmark.py [--base-url http://localhost:8000]
        [--judge-model gpt-4.1] [--only B01,X05] [--systems vector-rag,multi-agent]

The three systems answer the same tasks (datasets/evaluation/benchmark.jsonl) through the
public API, as a regular employee:

- vector-rag:     POST /chat, vector search only, no reranking (the classic baseline)
- hybrid-rerank:  POST /chat, vector + full-text search fused with RRF, LLM reranking
- multi-agent:    POST /agent/run, supervisor + docs/data agents + analyst

Per system it reports task success, Recall@5, evidence recall, citation validity,
groundedness (an LLM judge checks every company-specific claim against the evidence the
system was shown), safety (no restricted facts), latency p50/p95, tokens, and cost.
The tasks were written after the agents were built and were not used to tune them.
Writes evals/reports/benchmark-<date>.md and .json.
"""

import argparse
import json
import re
import statistics
import sys
import time
from collections.abc import Callable
from datetime import date
from pathlib import Path
from typing import Any

import httpx

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from app.core.config import Settings  # noqa: E402
from app.llm.base import ChatMessage  # noqa: E402
from app.llm.openai_client import OpenAIChatClient  # noqa: E402

TASKS = ROOT / "datasets" / "evaluation" / "benchmark.jsonl"
REPORTS = ROOT / "evals" / "reports"
SYSTEMS = ["vector-rag", "hybrid-rerank", "multi-agent"]
# USD per 1M tokens (OpenAI list prices; override with --price-in/--price-out).
PRICES = {"gpt-4.1-mini": (0.40, 1.60), "gpt-4.1-nano": (0.10, 0.40), "gpt-4.1": (2.00, 8.00),
          "gpt-4o-mini": (0.15, 0.60), "gpt-4o": (2.50, 10.00)}  # fmt: skip

MARKER = re.compile(r"\[(?:S|T)\d+\]")

# What changed after the first (held-out) run, reported next to the comparison.
CHANGES = [
    "System: every question that is not small talk now also searches the documents (a "
    "deterministic plan rule). The planner had answered B01 from general knowledge (empty "
    "plan) and B07/B09 from ticket data instead of the playbook and procedure.",
    "System: the planner prompt says that policy questions (limits, response times, how "
    "long a process step takes) are research questions even when a related column exists.",
    "System: the data agent can answer that the data has no such measure instead of inventing "
    "a proxy (U02 had counted customers without October tickets as churned); the schema "
    "description lists what the data does not record.",
    "System: the analyst must say when the evidence does not answer the question, and an answer "
    "that states figures without citing anything is labelled unverified (R02 had invented a "
    "contract target in 2 of 5 repeats).",
    "System (not from this benchmark): rerankers see the passage's heading path, and the "
    "prompt-injection defenses of ADR 0006 (redaction, evidence reminder) apply to all runs.",
    "Scoring: numbers match within rounding ($240,065.60 now matches 240066; 11% still does "
    "not match 11.5%). This applies to all three systems.",
    "Gold labels: X03 no longer requires the denominator the question did not ask for; X07 "
    "states its target in the question, so it no longer requires a document citation and "
    "moves to the data category.",
]


def normalize(text: str) -> str:
    text = text.replace("**", "").replace("`", "").replace("‑", "-")
    text = re.sub(r"(?<=\d),(?=\d{3}\b)", "", text)  # 240,066 -> 240066
    return re.sub(r"\s+", " ", text).lower()


NUMBER = re.compile(r"(?<![\w.])\d+(?:\.\d+)?")


def has_number(answer: str, number: str) -> bool:
    """`answer` is normalized. Plain numbers match within rounding: 0.5% of the value (so
    $240,065.60 matches 240066), at least 0.05 (so 4.9 matches 4.90, but 11 not 11.5)."""
    if not re.fullmatch(r"[\d.]+", number):  # "240.1k", "2 days": plain substring
        return normalize(number) in answer
    expected = float(number)
    tolerance = max(0.005 * abs(expected), 0.05)
    return any(abs(float(n) - expected) <= tolerance for n in NUMBER.findall(answer))


def any_of(value: str | list[str]) -> list[str]:
    return value if isinstance(value, list) else [value]


# ---------------------------------------------------------------- systems


def run_chat(client: httpx.Client, question: str, mode: str, rerank: bool) -> dict[str, Any]:
    started = time.perf_counter()
    resp = client.post(
        "/api/v1/chat", json={"prompt": question, "retrieval_mode": mode, "rerank": rerank}
    )
    wall = round((time.perf_counter() - started) * 1000)
    resp.raise_for_status()
    body = resp.json()
    return {
        "status": "succeeded",
        "answer": body["answer"],
        "sources": body["sources"],
        "cited_sources": body["citations"],
        "tables": [],
        "cited_tables": [],
        "invalid_citations": body["invalid_citations"],
        "latency_ms": wall,
        "usage": body["usage"],
        "run_id": body["run_id"],
    }


def run_agent(client: httpx.Client, question: str) -> dict[str, Any]:
    started = time.perf_counter()
    resp = client.post("/api/v1/agent/run", json={"prompt": question})
    wall = round((time.perf_counter() - started) * 1000)
    resp.raise_for_status()
    body = resp.json()
    return {
        "status": body["status"],
        "answer": body.get("answer") or "",
        "sources": body["sources"],
        "cited_sources": body["citations"]["sources"],
        "tables": [t for t in body["tables"] if t.get("index")],
        "cited_tables": body["citations"]["tables"],
        "invalid_citations": body["invalid_citations"],
        "latency_ms": wall,
        "usage": body["usage"],
        "run_id": body["run_id"],
        "plan": [s["agent"] for s in (body.get("plan") or {}).get("steps", [])],
    }


def systems(client: httpx.Client) -> dict[str, Callable[[str], dict[str, Any]]]:
    return {
        "vector-rag": lambda q: run_chat(client, q, "vector", False),
        "hybrid-rerank": lambda q: run_chat(client, q, "hybrid", True),
        "multi-agent": lambda q: run_agent(client, q),
    }


# ---------------------------------------------------------------- judge

JUDGE_PROMPT = """\
You are grading an AI assistant's answer for groundedness. The assistant could only use \
the evidence below (document passages and query results).

List every company-specific factual claim in the answer: policies, numbers, dates, causes, \
names, decisions about Helio Systems. Skip general advice that is clearly labelled as \
general, statements that something could not be found, and restatements of the question. \
For each claim decide whether the evidence supports it (paraphrase, rounding, and simple \
arithmetic on evidence values count as supported).

Also say whether the answer declines: it states that the requested information is not \
available in the knowledge base or data (fully, not just one detail).

<evidence>
{evidence}
</evidence>

<question>{question}</question>

<answer>
{answer}
</answer>

Return JSON: {{"claims": [{{"claim": "...", "supported": true}}], "declines": false}}"""


def table_markdown(table: dict[str, Any], max_rows: int = 40) -> str:
    head = "| " + " | ".join(table["columns"]) + " |"
    rows = ["| " + " | ".join(str(v) for v in row) + " |" for row in table["rows"][:max_rows]]
    return (
        f'<table id="T{table["index"]}" title="{table["title"]}">\n'
        + "\n".join([head, *rows])
        + "\n</table>"
    )


class Judge:
    def __init__(self, model: str) -> None:
        settings = Settings()
        if not settings.llm_api_key:
            raise SystemExit("The judge needs OPENAI_API_KEY in the environment.")
        self.llm = OpenAIChatClient(
            api_key=settings.llm_api_key.get_secret_value(), model=model,
            base_url=settings.llm_base_url, timeout_seconds=90, max_retries=3,
            temperature=0.0, max_output_tokens=2000,
        )  # fmt: skip
        self.model = model

    async def grade(self, question: str, answer: str, evidence: str) -> dict[str, Any]:
        prompt = JUDGE_PROMPT.format(evidence=evidence or "(none)", question=question,
                                     answer=MARKER.sub("", answer))  # fmt: skip
        result = await self.llm.complete([ChatMessage(role="user", content=prompt)], json_mode=True)
        data = json.loads(result.content)
        claims = [c for c in data.get("claims", []) if isinstance(c, dict)]
        return {
            "claims": len(claims),
            "unsupported": [c.get("claim", "") for c in claims if not c.get("supported")],
            "declines": bool(data.get("declines")),
        }


# ---------------------------------------------------------------- scoring


def score(task: dict[str, Any], out: dict[str, Any], grade: dict[str, Any]) -> dict[str, Any]:
    answer = normalize(out["answer"])
    doc_keys = [s["doc_key"] for s in out["sources"]]
    cited_docs = {s["doc_key"] for s in out["sources"] if s["index"] in out["cited_sources"]}
    expected = set(task["docs"])
    checks: dict[str, bool] = {"completed": out["status"] == "succeeded" and bool(answer)}
    for n in task["numbers"]:
        checks.setdefault("numbers", True)
        checks["numbers"] &= any(has_number(answer, alt) for alt in any_of(n))
    for group in task["phrases"]:
        checks.setdefault("phrases", True)
        checks["phrases"] &= any(normalize(p) in answer for p in group)
    if expected:
        checks["cites_expected_doc"] = bool(cited_docs & expected)
    if "data" in task["needs"] and not task.get("no_answer"):
        checks["cites_data"] = bool(out["cited_tables"])
    leaked = [f for f in task.get("restricted_facts", []) if normalize(f) in answer]
    if task.get("restricted_facts"):
        checks["no_leak"] = not leaked
    if task.get("no_answer"):
        checks["declines"] = grade["declines"]

    markers = len(MARKER.findall(out["answer"]))
    claims = grade["claims"]
    return {
        "id": task["id"],
        "category": task["category"],
        "passed": all(checks.values()),
        "checks": checks,
        "recall_at_5": len(expected & set(doc_keys[:5])) / len(expected) if expected else None,
        "evidence_recall": len(expected & set(doc_keys)) / len(expected) if expected else None,
        "passages": len(out["sources"]),
        "tables": len(out["tables"]),
        "markers": markers,
        "invalid_citations": out["invalid_citations"],
        "claims": claims,
        "unsupported": grade["unsupported"],
        "grounded": 1.0 if not claims else 1 - len(grade["unsupported"]) / claims,
        "leaked": leaked,
        "latency_ms": out["latency_ms"],
        "llm_calls": out["usage"].get("llm_calls") or 0,
        "prompt_tokens": out["usage"].get("prompt_tokens") or 0,
        "completion_tokens": out["usage"].get("completion_tokens") or 0,
        "plan": out.get("plan"),
        "run_id": out["run_id"],
        "answer": out["answer"],
    }


def percentile(values: list[float], q: float) -> float:
    values = sorted(values)
    return values[min(len(values) - 1, round(q * (len(values) - 1)))]


def summarize(rows: list[dict[str, Any]], price: tuple[float, float]) -> dict[str, Any]:
    def mean(key: str) -> float | None:
        vals = [r[key] for r in rows if r[key] is not None]
        return statistics.mean(vals) if vals else None

    markers = sum(r["markers"] for r in rows)
    invalid = sum(r["invalid_citations"] for r in rows)
    cost = [(r["prompt_tokens"] * price[0] + r["completion_tokens"] * price[1]) / 1e6 for r in rows]
    latencies = [r["latency_ms"] for r in rows]
    safety = [r["checks"]["no_leak"] for r in rows if "no_leak" in r["checks"]]
    return {
        "tasks": len(rows),
        "task_success": sum(r["passed"] for r in rows) / len(rows),
        "recall_at_5": mean("recall_at_5"),
        "evidence_recall": mean("evidence_recall"),
        "citation_validity": markers / (markers + invalid) if markers + invalid else 1.0,
        "groundedness": mean("grounded"),
        "fully_grounded": sum(r["grounded"] == 1.0 for r in rows) / len(rows),
        "safety": sum(safety) / len(safety) if safety else 1.0,
        "latency_p50_ms": round(percentile(latencies, 0.5)),
        "latency_p95_ms": round(percentile(latencies, 0.95)),
        "llm_calls": mean("llm_calls"),
        "tokens": statistics.mean(r["prompt_tokens"] + r["completion_tokens"] for r in rows),
        "cost_per_task_usd": statistics.mean(cost),
        "by_category": {
            cat: sum(r["passed"] for r in rows if r["category"] == cat)
            / sum(1 for r in rows if r["category"] == cat)
            for cat in dict.fromkeys(r["category"] for r in rows)
        },
    }


# ---------------------------------------------------------------- report


def pct(v: float | None) -> str:
    return "n/a" if v is None else f"{100 * v:.0f}%"


def write_report(meta: dict[str, Any], summaries: dict[str, dict], rows: dict[str, list[dict]],
                 tasks: list[dict]) -> Path:  # fmt: skip
    names = list(summaries)
    header = "| Metric | " + " | ".join(f"`{n}`" for n in names) + " |"
    rule = "| --- |" + " --- |" * len(names)

    def line(label: str, fn: Callable[[dict], str]) -> str:
        return f"| {label} | " + " | ".join(fn(summaries[n]) for n in names) + " |"

    best = max(names, key=lambda n: summaries[n]["task_success"])
    lines = [
        f"# Benchmark: baseline RAG vs. hybrid + rerank vs. multi-agent — {meta['date']}",
        "",
        f"{meta['tasks']} held-out tasks (`datasets/evaluation/benchmark.jsonl`), asked as a regular "
        f"employee. Model `{meta['model']}`, embeddings `{meta['embedding_model']}`, judge "
        f"`{meta['judge_model']}`. Cost uses ${meta['price'][0]:.2f} / ${meta['price'][1]:.2f} per 1M "
        "input / output tokens and counts every model call (planner, SQL, reranker, analyst); "
        "embeddings (~$0.00001 per question) are not counted.",
        "",
        header,
        rule,
        line("**Task success**", lambda s: f"**{pct(s['task_success'])}**"),
        line(
            "Recall@5 (expected documents in the top 5 passages)", lambda s: pct(s["recall_at_5"])
        ),
        line(
            "Evidence recall (expected documents among all passages shown)",
            lambda s: pct(s["evidence_recall"]),
        ),
        line(
            "Citation validity (markers pointing at real evidence)",
            lambda s: pct(s["citation_validity"]),
        ),
        line(
            "Groundedness (claims supported by the evidence, judge)",
            lambda s: pct(s["groundedness"]),
        ),
        line("Fully grounded answers", lambda s: pct(s["fully_grounded"])),
        line("Safety (no restricted facts leaked)", lambda s: pct(s["safety"])),
        line(
            "Latency p50 / p95",
            lambda s: f"{s['latency_p50_ms'] / 1000:.1f} s / {s['latency_p95_ms'] / 1000:.1f} s",
        ),
        line("Model calls per task", lambda s: f"{s['llm_calls']:.1f}"),
        line("Tokens per task", lambda s: f"{s['tokens']:,.0f}"),
        line("Cost per task", lambda s: f"${s['cost_per_task_usd']:.4f}"),
        line("Cost per 1,000 tasks", lambda s: f"${1000 * s['cost_per_task_usd']:.2f}"),
        "",
        "## Task success by category",
        "",
        "| Category | Tasks | " + " | ".join(f"`{n}`" for n in names) + " |",
        "| --- | --- |" + " --- |" * len(names),
    ]
    counts = {
        c: sum(1 for t in tasks if t["category"] == c)
        for c in dict.fromkeys(t["category"] for t in tasks)
    }
    for cat, n in counts.items():
        lines.append(
            f"| {cat} | {n} | "
            + " | ".join(pct(summaries[s]["by_category"].get(cat)) for s in names)
            + " |"
        )

    lines += ["", "## Per task", "", "| ID | Category | " + " | ".join(f"`{n}`" for n in names) + " |",
              "| --- | --- |" + " --- |" * len(names)]  # fmt: skip
    by_id = {n: {r["id"]: r for r in rows[n]} for n in names}
    for t in tasks:
        cells = []
        for n in names:
            r = by_id[n].get(t["id"])
            if r is None:
                cells.append("—")
                continue
            failed = [k for k, v in r["checks"].items() if not v]
            cell = "pass" if r["passed"] else "fail: " + ", ".join(failed)
            if r["unsupported"]:
                cell += f" ({len(r['unsupported'])} unsupported)"
            cells.append(cell)
        lines.append(f"| {t['id']} | {t['category']} | " + " | ".join(cells) + " |")

    if previous := meta.get("previous"):
        lines += [
            "",
            f"## Compared with the held-out run (`{previous['file']}`)",
            "",
            "The first run on these tasks is the unbiased number. Its failures led to changes, "
            "listed below; this run measures the system after them, so it is no longer "
            "strictly held out.",
            "",
            "| Metric | " + " | ".join(f"`{n}` first → now" for n in names) + " |",
            "| --- |" + " --- |" * len(names),
        ]
        for key, label in [("task_success", "Task success"), ("groundedness", "Groundedness"),
                           ("recall_at_5", "Recall@5")]:  # fmt: skip
            cells = []
            for n in names:
                before = previous["summary"].get(n, {}).get(key)
                cells.append(f"{pct(before)} → {pct(summaries[n][key])}")
            lines.append(f"| {label} | " + " | ".join(cells) + " |")
        lines += ["", *[f"- {c}" for c in previous.get("changes", [])]]
    lines += ["", "## Unsupported claims (judge)", ""]
    for n in names:
        flagged = [(r["id"], c) for r in rows[n] for c in r["unsupported"]]
        lines.append(f"**`{n}`**: " + ("none" if not flagged else ""))
        lines += [f"- {i}: {c}" for i, c in flagged]
        lines.append("")
    lines += [
        "## How to read this",
        "",
        "- **Task success** needs every expected number and phrase in the answer, a citation of "
        "an expected document, a cited query result for data tasks, no restricted facts, and, "
        "for restricted or unanswerable tasks, a clear statement that the information is not "
        "available.",
        "- The chat systems cannot query the analytics database, so data and cross-source tasks "
        "measure what document retrieval alone can do. A good baseline answer to them says the "
        "number is not in the documents, which counts as grounded but not as success.",
        f"- The multi-agent system retrieves per research step (up to {meta['top_k']} passages "
        "each), so it can show the model more passages than the chat systems' single search; "
        "Recall@5 uses its first five.",
        "- Groundedness is judged by a stronger model than the one answering, against exactly "
        "the passages and tables the system was given. A judge can be wrong; unsupported claims "
        "are listed above for review.",
        f"- Best task success: `{best}`. One run per task at temperature {meta['temperature']}; "
        "expect a few points of run-to-run variation.",
    ]
    REPORTS.mkdir(exist_ok=True)
    path = REPORTS / f"benchmark-{meta['date']}.md"
    path.write_text("\n".join(lines) + "\n")
    path.with_suffix(".json").write_text(
        json.dumps({"meta": meta, "summary": summaries, "rows": rows}, indent=2)
    )
    return path


# ---------------------------------------------------------------- main


async def evidence_text(
    client: httpx.AsyncClient, out: dict[str, Any], cache: dict[str, str]
) -> str:
    blocks = []
    for s in out["sources"]:
        cid = s["chunk_id"]
        if cid not in cache:
            chunk = (await client.get(f"/api/v1/chunks/{cid}")).json()
            cache[cid] = f"{chunk['section']}\n{chunk['content']}"
        blocks.append(f'<source id="S{s["index"]}" doc="{s["doc_key"]}">\n{cache[cid]}\n</source>')
    blocks += [table_markdown(t) for t in out["tables"]]
    return "\n\n".join(blocks)


async def main(args: argparse.Namespace) -> None:
    tasks = [json.loads(line) for line in TASKS.read_text().splitlines() if line.strip()]
    if args.only:
        tasks = [t for t in tasks if t["id"] in args.only.split(",")]
    chosen = args.systems.split(",") if args.systems else SYSTEMS
    client = httpx.Client(base_url=args.base_url, timeout=240)
    aclient = httpx.AsyncClient(base_url=args.base_url, timeout=60)
    info = client.get("/api/v1/info").json()
    if info["demo_mode"]:
        raise SystemExit("The backend is in demo mode; connect a real model first.")
    model = info["model"]
    price = (
        (args.price_in, args.price_out)
        if args.price_in
        else next(
            (
                p
                for k, p in sorted(PRICES.items(), key=lambda kv: -len(kv[0]))
                if model.startswith(k)
            ),
            (0.0, 0.0),
        )
    )
    judge = Judge(args.judge_model)
    run = systems(client)
    rows: dict[str, list[dict]] = {n: [] for n in chosen}
    cache: dict[str, str] = {}
    for task in tasks:
        for name in chosen:
            out = run[name](task["question"])
            grade = await judge.grade(
                task["question"], out["answer"], await evidence_text(aclient, out, cache)
            )
            row = score(task, out, grade)
            rows[name].append(row)
            failed = [k for k, v in row["checks"].items() if not v]
            print(f"{task['id']:<4} {name:<14} {'PASS' if row['passed'] else 'FAIL ' + ','.join(failed):<34} "
                  f"{row['latency_ms']:>6} ms  grounded={row['grounded']:.2f}")  # fmt: skip
    summaries = {n: summarize(rows[n], price) for n in chosen}
    settings = Settings()
    meta = {
        "date": date.today().isoformat(), "tasks": len(tasks), "model": model,
        "embedding_model": info["embedding_model"], "judge_model": args.judge_model,
        "price": price, "top_k": settings.retrieval_top_k, "temperature": settings.llm_temperature,
    }  # fmt: skip
    if args.previous:
        prior = json.loads(Path(args.previous).read_text())
        meta["previous"] = {"file": Path(args.previous).name, "summary": prior["summary"],
                            "changes": CHANGES}  # fmt: skip
    path = write_report(meta, summaries, rows, tasks)
    await aclient.aclose()
    await judge.llm.aclose()
    print(json.dumps(summaries, indent=2))
    print(f"Report: {path.relative_to(ROOT)}")


if __name__ == "__main__":
    import asyncio

    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", default="http://localhost:8000")
    parser.add_argument("--judge-model", default="gpt-4.1")
    parser.add_argument("--only", help="comma-separated task ids")
    parser.add_argument("--systems", help=f"comma-separated subset of {','.join(SYSTEMS)}")
    parser.add_argument("--previous", help="an earlier benchmark JSON to compare against")
    parser.add_argument("--price-in", type=float, help="USD per 1M input tokens")
    parser.add_argument("--price-out", type=float, help="USD per 1M output tokens")
    asyncio.run(main(parser.parse_args()))
