"""The retrieval gold set must stay consistent with the corpus it describes."""

import json
import re
from pathlib import Path

from app.rag.parsing import parse_document

ROOT = Path(__file__).resolve().parents[2]
GOLD = ROOT / "datasets" / "evaluation" / "retrieval_gold.jsonl"
CORPUS = ROOT / "datasets" / "documents"


def normalize(text: str) -> str:
    return re.sub(r"\s+", " ", text.replace("**", "").replace("`", "")).lower()


def test_every_gold_phrase_exists_in_its_document():
    docs = {}
    for path in CORPUS.rglob("*.md"):
        if path.name != "README.md":
            doc = parse_document(path.name, path.read_bytes())
            docs[doc.doc_key] = normalize(doc.body)

    items = [json.loads(line) for line in GOLD.read_text().splitlines() if line.strip()]
    assert len(items) >= 30
    assert len({i["id"] for i in items}) == len(items)
    for item in items:
        for ev in item["evidence"]:
            assert ev["doc_key"] in docs, item["id"]
            assert normalize(ev["phrase"]) in docs[ev["doc_key"]], (item["id"], ev["phrase"])


def test_benchmark_and_injection_tasks_reference_real_documents():
    keys = set()
    for root in (CORPUS, ROOT / "datasets" / "adversarial"):
        for path in root.rglob("*.md"):
            if path.name != "README.md":
                keys.add(parse_document(path.name, path.read_bytes()).doc_key)

    bench = [
        json.loads(line) for line in (GOLD.parent / "benchmark.jsonl").read_text().splitlines()
    ]
    assert len(bench) >= 30 and len({t["id"] for t in bench}) == len(bench)
    for task in bench:
        assert set(task["docs"]) <= keys, task["id"]
        assert set(task["needs"]) <= {"docs", "data"} and task["needs"], task["id"]
        assert task["numbers"] or task["phrases"] or task.get("no_answer"), task["id"]

    attacks = [
        json.loads(line)
        for line in (GOLD.parent / "injection_tasks.jsonl").read_text().splitlines()
    ]
    for attack in attacks:
        assert attack.get("doc") is None or attack["doc"] in keys, attack["id"]
        assert set(attack["systems"]) <= {"chat", "agent"}, attack["id"]
