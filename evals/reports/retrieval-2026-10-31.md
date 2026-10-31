# Retrieval evaluation — 2026-10-31

Gold set: `datasets/evaluation/retrieval_gold.jsonl` (37 questions). Corpus: `datasets/documents` (synthetic). Top-5 for recall, depth 10 for MRR.

Restricted questions are asked by a caller who *may* read the evidence; every question is also asked as a regular employee to count leaks of restricted documents (must be 0).

| Configuration | Embeddings | Hit@1 | Recall@5 | MRR@10 | Evidence coverage@5 | Leaks | p50 ms | p95 ms |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| Keyword only (FTS) | `—` | 78% | **92%** | 0.859 | 92% | 0 | 2 | 3 |
| Vector only | `hashing-v1` | 59% | **86%** | 0.721 | 86% | 0 | 2 | 3 |
| Hybrid (RRF) | `hashing-v1` | 65% | **95%** | 0.787 | 95% | 0 | 3 | 3 |
| Vector only | `text-embedding-3-small` | 81% | **97%** | 0.883 | 96% | 0 | 224 | 292 |
| Hybrid (RRF) | `text-embedding-3-small` | 84% | **100%** | 0.901 | 100% | 0 | 214 | 292 |
| Hybrid + LLM rerank | `text-embedding-3-small` | 95% | **100%** | 0.968 | 100% | 0 | 1159 | 1382 |
| Hybrid + ms-marco-MiniLM-L-6-v2 | `text-embedding-3-small` | 89% | **100%** | 0.946 | 100% | 0 | 290 | 405 |
| Hybrid + bge-reranker-base | `text-embedding-3-small` | 92% | **100%** | 0.951 | 99% | 0 | 566 | 662 |

## Recall@5 by question category

| Configuration | cross_doc | factual | identifier | paraphrase | restricted |
| --- | --- | --- | --- | --- | --- |
| Keyword only (FTS) | 100% | 95% | 100% | 67% | 100% |
| Vector only | 100% | 85% | 100% | 67% | 100% |
| Hybrid (RRF) | 100% | 95% | 100% | 83% | 100% |
| Vector only | 100% | 100% | 75% | 100% | 100% |
| Hybrid (RRF) | 100% | 100% | 100% | 100% | 100% |
| Hybrid + LLM rerank | 100% | 100% | 100% | 100% | 100% |
| Hybrid + ms-marco-MiniLM-L-6-v2 | 100% | 100% | 100% | 100% | 100% |
| Hybrid + bge-reranker-base | 100% | 100% | 100% | 100% | 100% |

## Notes

- Best configuration by Recall@5: **Hybrid + LLM rerank** with `text-embedding-3-small`.
- Its misses (no relevant passage in the top 5): none.
- **Caveats:** the corpus is small (12 synthetic documents, ~50 passages) and the gold set was written by the same author as the corpus, so absolute numbers are optimistic. The comparison *between* configurations is the useful signal. The end-to-end benchmark (`evals/benchmark.py`) adds held-out tasks written after the system was built.
- `hashing-v1` is an offline lexical embedder used for CI and no-key runs; it is not a semantic model, so its vector rows are a lower bound.
- Settings: candidates per channel 20, RRF k=60, chat model for reranking `gpt-4.1-mini`.
- Latency is measured in-process against a local Postgres, including embedding the query (a network call for OpenAI embeddings) and reranking when enabled.

Reproduce: `cd backend && DATABASE_URL=... .venv/bin/python ../evals/retrieval_eval.py --rerank --cross-encoder cross-encoder/ms-marco-MiniLM-L-6-v2,BAAI/bge-reranker-base`
