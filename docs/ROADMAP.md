# Roadmap & Progress Checklist

Each phase ends with a **working, tested deliverable**. A box is checked only after the feature is implemented **and** verified by a test or a reproducible demo.

Legend: ✅ done · ⏳ in progress · ⬜ planned

---

## Phase 0 — Planning & repository setup ✅

- [x] Project README with architecture and honest status
- [x] Architecture document and first ADR
- [x] Roadmap with per-phase acceptance criteria
- [x] Repo conventions: license, `.gitignore`, `.env.example`, contributing, security policy
- [x] GitHub issue and PR templates

## Phase 1 — Foundation ✅

**Deliverable:** A user submits a prompt and gets a model-generated answer through our own application.

- [x] `backend/` FastAPI app with `/health` (liveness) and `/health/ready` (DB readiness)
- [x] Typed settings (`pydantic-settings`) loaded from `.env`, validated at startup
- [x] Provider-agnostic LLM client: OpenAI-compatible + offline `fake` provider; timeout and error mapping (504/502)
- [x] `POST /api/v1/chat` endpoint with Pydantic request/response models
- [x] PostgreSQL + pgvector via `docker-compose.yml`
- [x] Async SQLAlchemy + Alembic migrations (`chat_runs` table; `vector` extension enabled)
- [x] Every run persisted (succeeded and failed) with latency and token usage
- [x] Dockerfile for the backend (non-root, healthcheck, migrations on start)
- [x] pytest suite with a stubbed LLM (unit) plus integration tests against real pgvector
- [x] GitHub Actions CI: ruff, unit tests, integration tests, Docker smoke test, frontend build
- [x] Minimal frontend (React + TS) that calls `/chat`

**Acceptance (verified):** `docker compose up` → `/health/ready` returns 200 → `POST /api/v1/chat` returns an answer with a `run_id` stored in Postgres → `pytest` is green locally and in CI.

## Phase 2 — Reliable hybrid RAG ⏳

**Deliverable:** Ask questions about uploaded documents and get answers with verifiable source passages.

- [ ] Document ingestion (Markdown, PDF, DOCX) with text cleaning
- [ ] Chunking that keeps metadata (doc id, section, page, version, ACL)
- [ ] Embeddings stored in pgvector
- [ ] PostgreSQL full-text search (keyword channel)
- [ ] Hybrid fusion (Reciprocal Rank Fusion)
- [ ] Cross-encoder reranking
- [ ] Permission filtering before generation
- [ ] Answers with citations to stable passage IDs, and a check that each cited ID exists
- [ ] Synthetic company corpus v1 + gold retrieval labels
- [ ] Recall@5 measured on the gold set

## Phase 3 — LangGraph multi-agent orchestration ⬜

**Deliverable:** A complex question automatically triggers coordinated document retrieval and SQL analysis.

- [ ] Graph state schema and builder
- [ ] Supervisor with a Pydantic-validated plan
- [ ] Research, Data, and Analysis agents as graph nodes
- [ ] Read-only SQL role, schema allow-list, statement timeout, row limit, query validator
- [ ] Synthetic structured dataset (`customers`, `onboarding_events`, `support_tickets`, …)
- [ ] Bounded retries and error recovery
- [ ] PostgreSQL checkpointing (resume interrupted runs)
- [ ] Execution trace exposed through the API

## Phase 4 — MCP & controlled actions ⬜

**Deliverable:** The assistant drafts a task, requests approval, and creates it only after authorization.

- [ ] Typed tool schemas
- [ ] One real integration (e.g. GitHub Issues) through an MCP adapter
- [ ] Action preview and human-in-the-loop approval (graph interrupt)
- [ ] Backend-enforced permission check, independent of the LLM
- [ ] Audit log of proposed, approved, rejected, and executed actions
- [ ] Least-privilege token scopes, with no credentials in prompts

## Phase 5 — Evaluation, reliability & security ⬜

**Deliverable:** Repeatable evaluation reports comparing baseline RAG with the agentic system.

- [ ] Benchmark dataset of cross-source tasks with known answers
- [ ] Metrics: Recall@5, citation validity, groundedness, task success, latency (p50/p95), cost
- [ ] Three-way comparison: vector RAG vs. hybrid + rerank vs. multi-agent
- [ ] Prompt-injection test suite
- [ ] Unauthorized-action test suite (target: 0 successes)
- [ ] Tracing (LangSmith / OpenTelemetry)

## Phase 6 — Deployment & presentation ⬜

**Deliverable:** A deployed, reproducible application that reviewers can inspect.

- [ ] Docker images and Cloud Run deployment
- [ ] Health checks and monitoring
- [ ] Complete UI: conversation, citations, trace, approvals
- [ ] Published evaluation results
- [ ] Architecture diagrams and demo video
