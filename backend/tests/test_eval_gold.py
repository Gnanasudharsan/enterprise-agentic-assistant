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
