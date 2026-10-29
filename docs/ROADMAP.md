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

## Phase 2 — Reliable hybrid RAG ✅

**Deliverable:** Ask questions about uploaded documents and get answers with verifiable source passages.

- [x] Document ingestion (Markdown, PDF, DOCX, text) with text cleaning and front-matter metadata
- [x] Heading-aware chunking that keeps metadata (doc key, heading path, chunk index, version, ACL)
- [x] Embeddings stored in pgvector (HNSW, cosine); offline hashing embedder for CI and no-key runs
- [x] PostgreSQL full-text search (keyword channel, weighted generated `tsvector`)
- [x] Hybrid fusion (Reciprocal Rank Fusion)
- [x] Second-stage reranking: **LLM listwise reranker** (optional, `RERANKER=llm`). A cross-encoder was planned; the LLM judge avoids a model download and was measured instead (Hit@1 84% → ~95%). A cross-encoder comparison moves to Phase 5.
- [x] Permission filtering inside the retrieval SQL, before generation
- [x] Answers with `[S#]` citations validated against the provided passages; invalid markers removed and counted
- [x] Synthetic company corpus v1 (12 documents, 2 restricted) + 37-question gold set
- [x] Recall@5 measured: **100%** hybrid (vs. 97% vector-only, 92% keyword-only); 0 ACL leaks
- [x] Documents API (list, upload, passage lookup) and UI (citations, source panel, knowledge-base browser)

**Acceptance (verified):** `docker compose up` seeds the corpus → a cross-document question returns a grounded answer whose citations open the exact passages → retrieval and answer evaluations are reproducible (`evals/`) and CI checks a correctly cited answer.

## Phase 3 — LangGraph multi-agent orchestration ⏳

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
