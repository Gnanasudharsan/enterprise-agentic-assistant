# Changelog

All notable changes to this project are documented here.
Format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/); versions follow [SemVer](https://semver.org/).

## [Unreleased]

## [0.3.0] - 2026-10-30 (Phase 3: Multi-agent orchestration)

### Added
- LangGraph graph: supervisor (Pydantic plan, repair, plan rules, keyword fallback) → docs and
  data agents in parallel waves (data steps can depend on research findings) → analyst.
- `analytics` schema with deterministic synthetic data (customers, onboarding events,
  verification checks, support tickets) consistent with the document corpus; seeded on startup.
- Safe SQL: sqlglot validator (tables, functions, single read-only SELECT, LIMIT) and a
  read-only executor as the `analytics_reader` role with timeout and row cap.
- SQL self-correction (3 attempts) and a catalog of reviewed queries as fallback/examples.
- `[T#]` data citations validated alongside `[S#]`; chart hints for query results.
- Postgres checkpointing; `agent_runs` table with plan, trace, evidence, and answer.
- `POST /api/v1/agent/run`, `/agent/stream` (SSE), `GET /agent/runs`, `GET /agent/runs/{id}`,
  `POST /agent/runs/{id}/resume`.
- UI: Agent / Docs / General modes, live agent timeline, data cards (chart, table, SQL),
  data citations, trace panel with a timing waterfall, resume after failure.
- Agent evaluation (10 tasks) and report; `app.analytics.cli seed|query`.
- ADR 0003.

### Changed
- `LLMClient.complete` accepts `json_mode` (JSON object responses, temperature 0).
- Citation checking generalized to multiple marker prefixes.
- CI smoke test also checks an offline multi-agent run that cites data.

## [0.2.0] - 2026-10-29 (Phase 2: Hybrid RAG)

### Added
- Synthetic Helio Systems corpus (12 documents, 2 access-restricted).
- Ingestion pipeline: Markdown/text/PDF/DOCX parsing, heading-aware chunking, OpenAI or
  offline embeddings, idempotent re-ingestion (`python -m app.rag.cli ingest`).
- `documents` and `chunks` tables (migration `0002`): pgvector HNSW + weighted full-text GIN.
- Hybrid retrieval (vector + keyword, RRF), SQL-level ACL filtering, optional LLM reranker.
- Grounded chat with numbered sources and validated `[S#]` citations; `sources` SSE event.
- `POST /api/v1/search`, `GET/POST /api/v1/documents`, `GET /api/v1/chunks/{id}`.
- UI: citation chips, source cards and preview panel, knowledge-base browser with upload,
  company-docs toggle.
- Evaluation: 37-question gold set, retrieval and answer evaluation harnesses and reports.

### Changed
- Docker seeds the corpus on startup; CI smoke test asserts a correctly cited answer.
- System prompt reflects knowledge-base access.

## [0.1.1] - 2026-10-29

### Added
- Streaming answers over Server-Sent Events (`POST /api/v1/chat/stream`).
- Multi-turn conversation memory (`history` in chat requests; last 20 messages sent).
- `GET /api/v1/info` (provider, model, demo mode).
- Redesigned UI: sidebar with recent conversations, suggestion cards, Markdown rendering
  (tables, code, lists), streaming cursor, stop/regenerate/copy, demo-mode banner,
  light/dark themes, mobile layout.

### Changed
- `LLM_PROVIDER=auto` is the default: uses the real model when `LLM_API_KEY` or
  `OPENAI_API_KEY` is set. Default model is `gpt-4.1-mini`.
- Structured system prompt: direct-first Markdown answers, honest about lacking
  access to internal documents.
- The demo provider explains how to connect a model instead of echoing the prompt.

## [0.1.0] - 2026-10-29 (Phase 1: Foundation)

### Added
- FastAPI backend with typed settings, `/health`, and `/health/ready`.
- Provider-agnostic LLM client (OpenAI-compatible + offline `fake` provider).
- `POST /api/v1/chat` with prompt validation and 502/504 error mapping.
- PostgreSQL + pgvector, async SQLAlchemy, Alembic migration `0001` (`chat_runs`).
- Persistence of every chat run (status, latency, token usage).
- Backend Dockerfile and `docker-compose.yml` (zero-config startup).
- React + TypeScript frontend skeleton.
- GitHub Actions CI: lint, unit, integration (pgvector), Docker smoke test, frontend build.

### Fixed
- Import `httpx2`, which `openai>=3` depends on, so the production image starts.

## [0.0.1] - 2026-10-29 (Phase 0: Planning)

### Added
- Phase 0: project README, architecture document, roadmap, and ADR 0001.
- Repository conventions: MIT license, `.gitignore`, `.env.example`, `.editorconfig`.
- Contributing guide, security policy, and GitHub issue/PR templates.
