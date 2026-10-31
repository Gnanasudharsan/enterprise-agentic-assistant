# ruff: noqa: E501  (long Markdown table templates in the report)
"""Retrieval evaluation: compare retrieval configurations on the gold set.

Usage (from backend/, against a scratch database; the corpus is re-ingested per embedder):

    DATABASE_URL=postgresql+asyncpg://... .venv/bin/python ../evals/retrieval_eval.py [--rerank]
        [--cross-encoder [MODEL]]

Configurations: {offline hashing, OpenAI} embeddings x {vector, keyword, hybrid} retrieval,
plus hybrid + LLM reranking with --rerank and hybrid + a local cross-encoder
(default cross-encoder/ms-marco-MiniLM-L-6-v2) with --cross-encoder. OpenAI rows run only
when an API key is set.
Writes evals/reports/retrieval-<date>.md and .json.
"""

import argparse
import asyncio
import json
import re
import statistics
import sys
import time
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from sqlalchemy import select  # noqa: E402

from app.core.config import Settings  # noqa: E402
from app.db.models import Document  # noqa: E402
from app.db.session import build_engine, build_sessionmaker  # noqa: E402
from app.llm.factory import build_llm_client  # noqa: E402
from app.rag.embeddings import Embedder, HashingEmbedder  # noqa: E402
from app.rag.factory import build_embedder  # noqa: E402
from app.rag.ingestion import ingest_directory  # noqa: E402
from app.rag.reranking import LLMReranker  # noqa: E402
from app.rag.retrieval import RetrievedChunk, Retriever  # noqa: E402

GOLD = ROOT / "datasets" / "evaluation" / "retrieval_gold.jsonl"
CORPUS = ROOT / "datasets" / "documents"
REPORTS = ROOT / "evals" / "reports"
EMPLOYEE = ["all-employees"]
K = 5
DEPTH = 10


def normalize(text: str) -> str:
    return re.sub(r"\s+", " ", text.replace("**", "").replace("`", "")).lower()


def matches(chunk: RetrievedChunk, evidence: dict) -> bool:
    """Relevant = right document, and the phrase is in the passage or its heading path."""
    if chunk.doc_key != evidence["doc_key"]:
        return False
    return normalize(evidence["phrase"]) in normalize(f"{chunk.section}\n{chunk.content}")


@dataclass
class QuestionResult:
    id: str
    category: str
    first_relevant_rank: int | None  # 1-based, within DEPTH
    coverage_at_k: float  # share of evidence items found in the top K
    latency_ms: float
    leaked: list[str] = field(default_factory=list)  # restricted doc_keys seen by an employee


@dataclass
class ConfigResult:
    name: str
    embedder: str
    mode: str
    rerank: bool
    questions: list[QuestionResult]

    def _rate(self, pred) -> float:
        return sum(1 for q in self.questions if pred(q)) / len(self.questions)

    @property
    def hit_at_1(self) -> float:
        return self._rate(lambda q: q.first_relevant_rank == 1)

    @property
    def recall_at_k(self) -> float:
        return self._rate(
            lambda q: q.first_relevant_rank is not None and q.first_relevant_rank <= K
        )

    @property
    def mrr(self) -> float:
        return statistics.mean(
            1 / q.first_relevant_rank if q.first_relevant_rank else 0.0 for q in self.questions
        )

    @property
    def coverage(self) -> float:
        return statistics.mean(q.coverage_at_k for q in self.questions)

    @property
    def leaks(self) -> int:
        return sum(len(q.leaked) for q in self.questions)

    def latency(self, pct: float) -> float:
        values = sorted(q.latency_ms for q in self.questions)
        return values[min(len(values) - 1, round(pct * (len(values) - 1)))]

    def by_category(self) -> dict[str, float]:
        cats: dict[str, list[QuestionResult]] = {}
        for q in self.questions:
            cats.setdefault(q.category, []).append(q)
        return {
            c: sum(1 for q in qs if q.first_relevant_rank and q.first_relevant_rank <= K) / len(qs)
            for c, qs in sorted(cats.items())
        }


async def evaluate(
    session,
    retriever: Retriever,
    gold: list[dict],
    restricted_keys: set[str],
    *,
    mode: str,
    rerank: bool,
) -> list[QuestionResult]:
    results = []
    for item in gold:
        groups = item.get("groups", EMPLOYEE)
        started = time.perf_counter()
        hits = await retriever.search(
            session, item["question"], groups, mode=mode, top_k=DEPTH, rerank=rerank
        )
        latency = (time.perf_counter() - started) * 1000

        rank = next(
            (i for i, h in enumerate(hits, 1) if any(matches(h, ev) for ev in item["evidence"])),
            None,
        )
        found = sum(1 for ev in item["evidence"] if any(matches(h, ev) for h in hits[:K]))
        coverage = found / len(item["evidence"]) if item.get("require_all") else float(found > 0)

        # Every question is also asked as a regular employee: restricted docs must never appear.
        employee_hits = (
            hits
            if groups == EMPLOYEE
            else await retriever.search(
                session, item["question"], EMPLOYEE, top_k=DEPTH, rerank=False
            )
        )
        leaked = sorted({h.doc_key for h in employee_hits if h.doc_key in restricted_keys})
        results.append(
            QuestionResult(item["id"], item["category"], rank, coverage, latency, leaked)
        )
    return results


async def ingest(session, embedder: Embedder) -> None:
    results = await ingest_directory(session, CORPUS, embedder)
    changed = sum(r.status != "unchanged" for r in results)
    print(f"  corpus ready for {embedder.model} ({changed} documents (re)embedded)")


def report(
    results: list[ConfigResult], settings: Settings, gold: list[dict], cross_encoders: list[str]
) -> str:
    today = date.today().isoformat()
    lines = [
        f"# Retrieval evaluation — {today}",
        "",
        f"Gold set: `{GOLD.relative_to(ROOT)}` ({len(gold)} questions). "
        f"Corpus: `{CORPUS.relative_to(ROOT)}` (synthetic). Top-{K} for recall, depth {DEPTH} for MRR.",
        "",
        "Restricted questions are asked by a caller who *may* read the evidence; every question is "
        "also asked as a regular employee to count leaks of restricted documents (must be 0).",
        "",
        "| Configuration | Embeddings | Hit@1 | Recall@5 | MRR@10 | Evidence coverage@5 | Leaks | p50 ms | p95 ms |",
        "| --- | --- | --- | --- | --- | --- | --- | --- | --- |",
    ]
    for r in results:
        lines.append(
            f"| {r.name} | `{r.embedder}` | {r.hit_at_1:.0%} | **{r.recall_at_k:.0%}** | "
            f"{r.mrr:.3f} | {r.coverage:.0%} | {r.leaks} | {r.latency(0.5):.0f} | {r.latency(0.95):.0f} |"
        )

    cats = sorted({c for r in results for c in r.by_category()})
    lines += [
        "",
        "## Recall@5 by question category",
        "",
        "| Configuration | " + " | ".join(cats) + " |",
    ]
    lines.append("| --- |" + " --- |" * len(cats))
    for r in results:
        per = r.by_category()
        lines.append(f"| {r.name} | " + " | ".join(f"{per.get(c, 0):.0%}" for c in cats) + " |")

    best = max(results, key=lambda r: (r.recall_at_k, r.mrr))
    misses = [
        q.id for q in best.questions if not q.first_relevant_rank or q.first_relevant_rank > K
    ]
    lines += [
        "",
        "## Notes",
        "",
        f"- Best configuration by Recall@5: **{best.name}** with `{best.embedder}`.",
        f"- Its misses (no relevant passage in the top {K}): {', '.join(misses) or 'none'}.",
        "- **Caveats:** the corpus is small (12 synthetic documents, ~50 passages) and the gold set "
        "was written by the same author as the corpus, so absolute numbers are optimistic. The "
        "comparison *between* configurations is the useful signal. The end-to-end benchmark "
        "(`evals/benchmark.py`) adds held-out tasks written after the system was built.",
        "- `hashing-v1` is an offline lexical embedder used for CI and no-key runs; it is not "
        "a semantic model, so its vector rows are a lower bound.",
        f"- Settings: candidates per channel {settings.retrieval_candidates}, RRF k={settings.rrf_k}, "
        f"chat model for reranking `{settings.llm_model}`.",
        "- Latency is measured in-process against a local Postgres, including embedding the query "
        "(a network call for OpenAI embeddings) and reranking when enabled.",
        "",
        f"Reproduce: `cd backend && DATABASE_URL=... .venv/bin/python ../evals/retrieval_eval.py"
        f"{' --rerank' if any(r.name == 'Hybrid + LLM rerank' for r in results) else ''}"
        + (f" --cross-encoder {','.join(cross_encoders)}" if cross_encoders else "")
        + "`",
    ]
    return "\n".join(lines) + "\n"


class CrossEncoderReranker:
    """A local cross-encoder (sentence-transformers), compared against the LLM reranker.

    Needs `pip install sentence-transformers` (pulls PyTorch); not a backend dependency.
    """

    def __init__(self, model: str) -> None:
        from sentence_transformers import CrossEncoder

        self.model = model
        self._encoder = CrossEncoder(model, max_length=512)

    async def score(self, query: str, passages: list[str]) -> list[float]:
        pairs = [(query, p) for p in passages]
        return [float(s) for s in await asyncio.to_thread(self._encoder.predict, pairs)]


async def main(rerank: bool, cross_encoders: list[str]) -> None:
    settings = Settings()
    gold = [json.loads(line) for line in GOLD.read_text().splitlines() if line.strip()]
    engine = build_engine(settings.sqlalchemy_url)
    sessionmaker = build_sessionmaker(engine)

    embedders: list[Embedder] = [HashingEmbedder()]
    if settings.llm_api_key:
        embedders.append(
            build_embedder(settings.model_copy(update={"embedding_provider": "openai"}))
        )
    llm = build_llm_client(settings) if rerank and settings.llm_api_key else None

    results: list[ConfigResult] = []
    try:
        async with sessionmaker() as session:
            for embedder in embedders:
                print(f"Embedder {embedder.model}")
                await ingest(session, embedder)
                rows = await session.execute(select(Document.doc_key, Document.acl))
                restricted = {key for key, acl in rows.all() if "all-employees" not in acl}
                modes = ["vector", "hybrid"] if results else ["keyword", "vector", "hybrid"]
                for mode in modes:
                    retriever = Retriever(
                        embedder,
                        candidates=settings.retrieval_candidates,
                        rrf_k=settings.rrf_k,
                    )
                    qs = await evaluate(
                        session, retriever, gold, restricted, mode=mode, rerank=False
                    )
                    name = {
                        "keyword": "Keyword only (FTS)",
                        "vector": "Vector only",
                        "hybrid": "Hybrid (RRF)",
                    }[mode]
                    results.append(
                        ConfigResult(
                            name, embedder.model if mode != "keyword" else "—", mode, False, qs
                        )
                    )
                    print(
                        f"  {name:<20} recall@5={results[-1].recall_at_k:.0%}  mrr={results[-1].mrr:.3f}"
                    )
                if llm and embedder.model != HashingEmbedder.model:
                    retriever = Retriever(
                        embedder,
                        candidates=settings.retrieval_candidates,
                        rrf_k=settings.rrf_k,
                        reranker=LLMReranker(llm),
                    )
                    qs = await evaluate(
                        session, retriever, gold, restricted, mode="hybrid", rerank=True
                    )
                    results.append(
                        ConfigResult("Hybrid + LLM rerank", embedder.model, "hybrid", True, qs)
                    )
                    print(
                        f"  {'Hybrid + LLM rerank':<20} recall@5={results[-1].recall_at_k:.0%}  mrr={results[-1].mrr:.3f}"
                    )
                for model in cross_encoders if embedder.model != HashingEmbedder.model else []:
                    retriever = Retriever(
                        embedder,
                        candidates=settings.retrieval_candidates,
                        rrf_k=settings.rrf_k,
                        reranker=CrossEncoderReranker(model),
                    )
                    qs = await evaluate(
                        session, retriever, gold, restricted, mode="hybrid", rerank=True
                    )
                    name = f"Hybrid + {model.split('/')[-1]}"
                    results.append(ConfigResult(name, embedder.model, "hybrid", True, qs))
                    print(
                        f"  {name:<20} recall@5={results[-1].recall_at_k:.0%}  mrr={results[-1].mrr:.3f}"
                    )
    finally:
        for e in embedders:
            await e.aclose()
        if llm:
            await llm.aclose()
        await engine.dispose()

    REPORTS.mkdir(parents=True, exist_ok=True)
    stem = REPORTS / f"retrieval-{date.today().isoformat()}"
    stem.with_suffix(".md").write_text(report(results, settings, gold, cross_encoders))
    stem.with_suffix(".json").write_text(
        json.dumps(
            [
                {
                    "name": r.name,
                    "embedder": r.embedder,
                    "mode": r.mode,
                    "rerank": r.rerank,
                    "hit_at_1": r.hit_at_1,
                    "recall_at_5": r.recall_at_k,
                    "mrr_at_10": r.mrr,
                    "evidence_coverage_at_5": r.coverage,
                    "leaks": r.leaks,
                    "latency_p50_ms": r.latency(0.5),
                    "latency_p95_ms": r.latency(0.95),
                    "recall_at_5_by_category": r.by_category(),
                    "questions": [q.__dict__ for q in r.questions],
                }
                for r in results
            ],
            indent=2,
        )
    )
    print(f"Report: {stem.with_suffix('.md').relative_to(ROOT)}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument(
        "--rerank", action="store_true", help="Also evaluate hybrid + LLM reranking"
    )
    parser.add_argument(
        "--cross-encoder",
        metavar="MODELS",
        nargs="?",
        const="cross-encoder/ms-marco-MiniLM-L-6-v2",
        help="Also evaluate hybrid + local cross-encoders, comma-separated Hugging Face ids "
        "(default: ms-marco-MiniLM-L-6-v2; needs sentence-transformers)",
    )
    args = parser.parse_args()
    asyncio.run(main(args.rerank, args.cross_encoder.split(",") if args.cross_encoder else []))
