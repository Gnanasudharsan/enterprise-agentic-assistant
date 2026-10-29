# ruff: noqa: E501  (long Markdown table templates in the report)
"""End-to-end answer evaluation through the running API (grounding and citations).

Usage (backend running with a real model, corpus seeded, caller = regular employee):

    cd backend && .venv/bin/python ../evals/answer_eval.py [--base-url http://localhost:8000]

Measures, over the retrieval gold set:
- citation validity: share of [S#] markers that point to a provided source
- citation rate: share of answers that cite at least one source
- evidence-grounded rate: share of answers citing a passage that contains gold evidence
- restricted leakage: restricted questions are asked as a regular employee; the answer must
  not contain facts that only exist in the restricted document
Writes evals/reports/answers-<date>.md and .json.
"""

import argparse
import json
import re
import statistics
from datetime import date
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parents[1]
GOLD = ROOT / "datasets" / "evaluation" / "retrieval_gold.jsonl"
REPORTS = ROOT / "evals" / "reports"

# Facts that appear only in restricted documents (HR-007, LDR-014).
RESTRICTED_FACTS = [
    "$195,000",
    "$222,000",
    "$249,000",
    "3.5% of base payroll",
    "15 new Enterprise",
    "Hold headcount flat",
]


def normalize(text: str) -> str:
    return re.sub(r"\s+", " ", text.replace("**", "").replace("`", "")).lower()


def main(base_url: str) -> None:
    gold = [json.loads(line) for line in GOLD.read_text().splitlines() if line.strip()]
    client = httpx.Client(base_url=base_url, timeout=120)
    info = client.get("/api/v1/info").json()
    if info["demo_mode"]:
        raise SystemExit("The backend is in demo mode; connect a real model first.")

    rows = []
    chunk_cache: dict[str, str] = {}
    for item in gold:
        resp = client.post("/api/v1/chat", json={"prompt": item["question"]})
        resp.raise_for_status()
        body = resp.json()
        restricted = item["category"] == "restricted"

        cited_text = []
        for n in body["citations"]:
            source = next(s for s in body["sources"] if s["index"] == n)
            cid = source["chunk_id"]
            if cid not in chunk_cache:
                chunk = client.get(f"/api/v1/chunks/{cid}").json()
                chunk_cache[cid] = normalize(f"{chunk['section']}\n{chunk['content']}")
            cited_text.append((source["doc_key"], chunk_cache[cid]))

        grounded = any(
            doc == ev["doc_key"] and normalize(ev["phrase"]) in text
            for doc, text in cited_text
            for ev in item["evidence"]
        )
        leaked = [f for f in RESTRICTED_FACTS if f.lower() in body["answer"].lower()]
        rows.append(
            {
                "id": item["id"],
                "category": item["category"],
                "retrieval": body["retrieval"],
                "valid_citations": len(re.findall(r"\[S\d+\]", body["answer"])),
                "invalid_citations": body["invalid_citations"],
                "cites_any": bool(body["citations"]),
                "grounded": grounded,
                "restricted": restricted,
                "leaked": leaked,
                "latency_ms": body["latency_ms"],
                "tokens": (body["usage"]["prompt_tokens"] or 0)
                + (body["usage"]["completion_tokens"] or 0),
                "answer": body["answer"],
            }
        )
        print(
            f"  {item['id']:<8} cites={len(body['citations'])} grounded={grounded} leaked={bool(leaked)}"
        )

    answerable = [r for r in rows if not r["restricted"]]
    restricted_rows = [r for r in rows if r["restricted"]]
    markers = sum(r["valid_citations"] + r["invalid_citations"] for r in rows)
    validity = 1 - sum(r["invalid_citations"] for r in rows) / markers if markers else 1.0
    latencies = sorted(r["latency_ms"] for r in rows)
    summary = {
        "date": date.today().isoformat(),
        "model": info["model"],
        "questions": len(rows),
        "citation_validity": validity,
        "citation_rate": statistics.mean(r["cites_any"] for r in answerable),
        "evidence_grounded_rate": statistics.mean(r["grounded"] for r in answerable),
        "restricted_questions": len(restricted_rows),
        "restricted_leaks": sum(bool(r["leaked"]) for r in restricted_rows),
        "latency_p50_ms": latencies[len(latencies) // 2],
        "latency_p95_ms": latencies[min(len(latencies) - 1, round(0.95 * (len(latencies) - 1)))],
        "avg_tokens": statistics.mean(r["tokens"] for r in rows),
    }
    ungrounded = [r["id"] for r in answerable if not r["grounded"]]

    md = f"""# Answer evaluation — {summary["date"]}

End-to-end through `POST /api/v1/chat` (hybrid retrieval, top-6 sources) with `{summary["model"]}`, as a regular employee (`all-employees`). Gold set: `{GOLD.relative_to(ROOT)}`.

| Metric | Result | Definition |
| --- | --- | --- |
| Citation validity | **{validity:.1%}** | [S#] markers that point to a source actually provided ({markers} markers before cleanup) |
| Citation rate | **{summary["citation_rate"]:.0%}** | Answerable questions whose answer cites at least one source |
| Evidence-grounded answers | **{summary["evidence_grounded_rate"]:.0%}** | Answerable questions whose answer cites a passage containing gold evidence |
| Restricted leakage | **{summary["restricted_leaks"]} / {summary["restricted_questions"]}** | Restricted-document facts appearing in answers to a regular employee |
| Latency p50 / p95 | {summary["latency_p50_ms"]} / {summary["latency_p95_ms"]} ms | Server-side, retrieval + generation |
| Avg tokens per answer | {summary["avg_tokens"]:.0f} | Prompt + completion |

Answers without grounded evidence citations: {", ".join(ungrounded) or "none"}.

Citation *support* (does the passage actually justify the sentence?) needs a judge model and is planned for the Phase 5 evaluation suite; this report checks that citations exist and point at the right evidence.

Reproduce: `cd backend && .venv/bin/python ../evals/answer_eval.py` (backend running with a model).
"""
    REPORTS.mkdir(parents=True, exist_ok=True)
    stem = REPORTS / f"answers-{summary['date']}"
    stem.with_suffix(".md").write_text(md)
    stem.with_suffix(".json").write_text(json.dumps({"summary": summary, "rows": rows}, indent=2))
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--base-url", default="http://localhost:8000")
    main(parser.parse_args().base_url)
