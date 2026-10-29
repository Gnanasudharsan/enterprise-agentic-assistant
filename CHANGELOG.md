# Changelog

All notable changes to this project are documented here.
Format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/); versions follow [SemVer](https://semver.org/).

## [Unreleased]

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
