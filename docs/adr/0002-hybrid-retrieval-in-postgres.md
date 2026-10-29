# ADR 0002: Hybrid retrieval inside PostgreSQL, with validated citations

- **Status:** Accepted
- **Date:** 2026-10-29

## Context

Phase 2 needs retrieval that handles both meaning ("why did onboarding slow down?") and exact identifiers (`INC-204`), respects document permissions, and produces citations we can verify. ADR 0001 already chose a single PostgreSQL instance.

## Decision

1. **Both channels in Postgres:** pgvector (HNSW, cosine) for semantic search and a weighted, generated `tsvector` with `websearch_to_tsquery` (terms OR-ed) for keywords. There is no separate search engine.
2. **Reciprocal Rank Fusion** (k = 60) to merge the two rankings. It is score-scale free, so no per-channel calibration is needed.
3. **ACL in the SQL `WHERE` clause** of both channels (`documents.acl && caller_groups`), so restricted passages never leave the database for a caller without access.
4. **Embeddings tagged with their model;** queries only compare against chunks from the same embedding space, and changing the embedder triggers re-embedding on ingestion.
5. **Numbered sources and validated citations:** the model sees passages as `[S1]…[Sn]` and the server removes any marker that does not map to a provided passage, then counts it.
6. **Reranking is optional and LLM-based** (`RERANKER=llm`) instead of a cross-encoder, to avoid shipping a model in the image. It was measured rather than assumed.
7. **No RAG framework.** The pipeline is roughly 600 lines of explicit code, which keeps every step testable and visible in evaluations.

## Consequences

- Measured on the gold set: hybrid reaches 100% Recall@5 against 97% vector-only and 92% keyword-only. Vector-only misses exact identifiers (75% on that category). LLM reranking lifts Hit@1 from 84% to about 95% for about 1 s of extra latency, so it is off by default.
- Retrieval quality depends on Postgres FTS's English configuration; other languages would need their own configuration.
- An LLM reranker adds cost per question and is nondeterministic. A cross-encoder comparison is planned for Phase 5.
