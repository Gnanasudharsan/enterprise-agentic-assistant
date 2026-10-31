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

## Phase 3 — LangGraph multi-agent orchestration ✅

**Deliverable:** A complex question automatically triggers coordinated document retrieval and SQL analysis.

- [x] Graph state schema (plain JSON, checkpointable) and builder: supervisor → specialists in parallel waves → coordinator → analyst
- [x] Supervisor with a Pydantic-validated plan: one repair round with the validation error, deterministic plan rules, keyword fallback
- [x] Research (docs), Data, and Analysis agents as graph nodes; data steps can depend on research steps and receive their findings
- [x] Read-only SQL: `analytics_reader` role, table and function allow-lists, statement timeout, row limit, sqlglot validator; database-level refusals tested without the validator
- [x] Synthetic structured dataset: `customers`, `onboarding_events`, `verification_checks`, `support_tickets`, consistent with the document corpus
- [x] Bounded retries and error recovery: node retry policies, SQL self-correction (3 attempts), reviewed-query fallback, failed steps reported in the answer
- [x] PostgreSQL checkpointing; `POST /agent/runs/{id}/resume` continues a failed run from its last completed step
- [x] Execution trace exposed through the API (`GET /agent/runs/{id}`) and the UI (timeline + waterfall)
- [x] Agent evaluation: 10 tasks, 100% task success, 100% data accuracy, 0 safety failures

**Acceptance (verified):** asking "Why did onboarding slow down in September?" plans research + data, cites the incident report and a query result in one answer, shows the SQL and chart, and the run's trace is retrievable; a run whose analyst fails resumes without re-planning or re-querying (tested).

## Phase 4 — MCP & controlled actions ✅

**Deliverable:** The assistant drafts a task, requests approval, and creates it only after authorization.

- [x] Typed tool schemas: the tracker MCP server declares `create_issue` / `search_issues` with JSON Schema (enums, lengths, limits) and read-only annotations; drafts are validated client-side (jsonschema) and server-side
- [x] One real integration through MCP: an issue-tracker MCP server over stdio, with a local SQLite backend (default, offline) and a GitHub Issues backend
- [x] Action preview and human-in-the-loop approval: the action agent drafts after the answer, the graph `interrupt`s, and the UI approves / edits / rejects; the decision resumes the checkpointed run
- [x] Backend-enforced permission check, independent of the LLM: allow-listed tools per access group, checked at proposal, at approval, and before execution; approvals bound to an argument hash; at-most-once execution
- [x] Audit log of proposed, edited, approved, rejected, denied, executing, executed, and failed actions (`action_audit`, `GET /api/v1/actions`, actions panel)
- [x] Least-privilege token scopes, with no credentials in prompts: the MCP subprocess receives only tracker settings; GitHub uses a fine-grained single-repo token with issue access only
- [x] Unauthorized-action test suite: 15 scenarios, 0 unauthorized executions

**Acceptance (verified):** "What caused INC-204? Create a follow-up issue…" answers with citations, drafts an issue (with a duplicate check), pauses as `needs_approval`, creates the issue only after approval (offline in CI via the local tracker), and records the full audit trail; a second approval is refused.

## Phase 5 — Evaluation, reliability & security ✅

**Deliverable:** Repeatable evaluation reports comparing baseline RAG with the agentic system.

- [x] Held-out benchmark: 32 tasks (single- and multi-document, data, cross-source, restricted, unanswerable) with answers computed from the seeded data; expectations pinned by tests
- [x] Metrics: task success, Recall@5, evidence recall, citation validity, judged groundedness (`gpt-4.1` judge), safety, latency p50/p95, model calls, tokens, and cost per task (metered per request)
- [x] Three-way comparison through the production API: vector RAG vs. hybrid + LLM rerank vs. multi-agent; the first (held-out) run and the post-fix run are both published
- [x] Prompt-injection suite: 13 direct and indirect attacks (poisoned documents ingested for the run) against chat and agents, 20 runs; defense in depth (output sanitizing, injection redaction, delimiter escaping, evidence reminder, CSP)
- [x] Unauthorized-action suite: 9 live API attempts plus the 15 unit scenarios; **0 unauthorized executions**
- [x] Tracing: OpenTelemetry spans for requests, graph nodes, model calls (with tokens), retrieval, SQL, and MCP calls; Jaeger via Compose profile; LangSmith optional
- [x] Cross-encoder comparison (carried over from Phase 2): `ms-marco-MiniLM-L-6-v2` and `bge-reranker-base` vs. the LLM reranker; found and fixed rerankers missing the heading path

**Acceptance (verified):** `evals/benchmark.py` reproduces the three-way report, `evals/security_eval.py` the security report, and every report records its model, judge, prices, and date.

## Phase 6 — Deployment & presentation ⬜

**Deliverable:** A deployed, reproducible application that reviewers can inspect.

- [ ] Docker images and Cloud Run deployment
- [ ] Health checks and monitoring
- [ ] Complete UI: conversation, citations, trace, approvals
- [ ] Published evaluation results
- [ ] Architecture diagrams and demo video
