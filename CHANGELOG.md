# Changelog

All notable changes to this project are documented here.
Format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/); versions follow [SemVer](https://semver.org/).

## [Unreleased]

### Changed
- UI redesign in the spirit of Apple's and Google's product UIs:
  - **Type:** system typography (SF Pro on Apple devices, Inter elsewhere) with tight display headlines.
  - **Color:** neutral grays with one interactive blue; the orange sun is now the brand mark only.
  - **Chrome:** a translucent sidebar that follows the theme, and a frosted top bar, composer button, tooltips, and palette.
  - **Shapes:** pill buttons, segmented controls, and composer; borderless tiles for suggestions, sources, and passages.
  - **Motion and depth:** softer shadows and spring motion.
- The hero headline uses an AI gradient and balanced line breaks; mobile shows a shorter greeting.
- README screenshots regenerated.

## [0.6.0] - 2026-10-31 (Phase 6: Deployment & presentation)

### Added
- Production `Dockerfile`: the API serves the built frontend (`STATIC_DIR`, SPA fallback,
  immutable asset caching); CI builds it and smoke-tests the gate, routes, and logs.
- Public-demo protections: `ACCESS_CODE` (constant-time check, rate-limited guesses,
  `GET/POST /api/v1/access`, access screen in the UI), per-client `RATE_LIMIT_REQUESTS`
  with `FORWARDED_HOPS`-aware client addresses, `DAILY_TOKEN_BUDGET` with an offline-model
  fallback (`budget_exhausted` in `/api/v1/info`), and security headers.
- Structured JSON logs (`LOG_FORMAT=json`) for Cloud Logging, linked to traces; one access
  line per request; Cloud Trace export (`TRACING=gcp`, extra `[gcp]`).
- Google Cloud scripts: `deploy/gcp/setup.sh` (project, Cloud SQL, Artifact Registry, Secret
  Manager, least-privilege service account), `deploy.sh`, `monitoring.sh`, `teardown.sh`.
- Architecture diagram, screenshots, demo script (`docs/DEMO.md`), ADR 0007.

### Changed
- Database pool sizes are configurable (`DB_POOL_SIZE`) for small Cloud SQL tiers.

### Fixed
- The checkpointer pool used psycopg's default `min_size=4`, which failed with
  `DB_POOL_SIZE` below 4. It now uses `min_size=1`, and CI starts the image with a pool of 3.
- `setup.sh` retries while newly enabled APIs propagate and never stops at a prompt.

### Deployed
- https://helio-assistant-vpgub2ic6q-uc.a.run.app (Cloud Run + Cloud SQL, us-central1).

## [0.5.0] - 2026-10-31 (Phase 5: Evaluation, reliability & security)

### Added
- Held-out benchmark (32 tasks) and `evals/benchmark.py`: vector RAG vs. hybrid + rerank vs.
  multi-agent through the API, with task success, Recall@5, citation validity, judged
  groundedness, latency, tokens, and cost; the first run and the post-fix run are published.
- Security evaluation (`evals/security_eval.py`): 13 direct and indirect prompt-injection
  attacks (poisoned documents in `datasets/adversarial/`), 9 API-level unauthorized-action
  attempts, integrity checks.
- Defenses: output sanitizing of answers and drafted issues (images removed, links limited to
  `ANSWER_LINK_HOSTS`), redaction of instruction-like paragraphs in passages, escaping of
  evidence delimiters, an evidence reminder after the sources; the UI never renders images
  and sets a CSP for images.
- Per-request usage metering (`MeteredLLM`): `usage.llm_calls` and tokens on `/chat` and
  `/agent/run`, stored on `agent_runs` (migration `0005`); shown in the trace panel.
- OpenTelemetry tracing (`TRACING=otlp|console`): request, graph-node, model-call (with token
  counts), retrieval, SQL, and MCP spans; Jaeger under the Compose `tracing` profile;
  LangSmith variables passed through.
- `/chat` options `retrieval_mode` (`hybrid` / `vector` / `keyword`) and `rerank`.
- Cross-encoder rerankers in the retrieval evaluation (`--cross-encoder`).
- Tests pinning the benchmark's expected numbers to the seed, plus sanitizer, redaction,
  metering, and tracing tests. ADRs 0005 (evaluation protocol) and 0006 (injection defenses).

### Changed
- Every question that is not small talk also searches the documents (plan rule); the planner
  prompt treats policy questions as research questions even when related data exists.
- Rerankers see the passage's heading path, as the embedder does (fixes ranking of passages
  whose identifiers appear only in the title, e.g. INC-198).
- The reranker is always available per request; `RERANKER` sets the default.
- The data agent can answer that the data has no such measure (`unanswerable`, step status
  `no_data`) instead of inventing a proxy metric; the schema description lists what the data
  does not record.
- Answers that state figures without citing any evidence are labelled unverified, and the
  analyst is told to say when the evidence does not answer the question.

## [0.4.0] - 2026-10-30 (Phase 4: MCP & controlled actions)

### Added
- Issue-tracker MCP server (`app.mcp_servers.tracker`): typed `create_issue` and read-only
  `search_issues`; local SQLite backend (default) and GitHub Issues backend.
- MCP client gateway over stdio with an isolated subprocess environment (tracker settings only).
- Action agent: drafts one typed tool call after the answer, with a duplicate search and
  JSON Schema validation (one repair round); offline deterministic drafts.
- Human-in-the-loop approval as a LangGraph interrupt; run status `needs_approval`;
  `POST /api/v1/agent/runs/{id}/actions/{action_id}/decision` (approve, edit, reject).
- Backend policy: per-group tool allow-list, approval for non-read-only tools, approvals bound
  to an argument hash, checks at approval and before execution, at-most-once execution.
- `agent_actions` and append-only `action_audit` tables (migration `0004`);
  `GET /api/v1/tools`, `GET /api/v1/actions`, `GET /api/v1/actions/{id}`.
- UI: approval card (approve / edit / reject, duplicates, audit trail), action agent in the
  timeline, actions panel with the audit log, pending-approval badge.
- 15 unauthorized-action scenario tests, MCP tests, and a Postgres + stdio integration test.
- ADR 0004; security implementation table in SECURITY.md.

### Changed
- CI smoke test also runs an approval flow end to end.
- `alembic check` ignores LangGraph's checkpoint tables.

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
