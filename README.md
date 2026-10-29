# Agentic Enterprise Research & Workflow Assistant

> A multi-agent AI assistant that answers business questions by searching enterprise documents, analyzing structured data, and running authorized workflows. Every answer cites its sources, and every action needs human approval.

![Status](https://img.shields.io/badge/status-in%20development-yellow)
[![CI](https://github.com/Gnanasudharsan/enterprise-agentic-assistant/actions/workflows/ci.yml/badge.svg)](https://github.com/Gnanasudharsan/enterprise-agentic-assistant/actions/workflows/ci.yml)
![Phase](https://img.shields.io/badge/phase-1%20%E2%80%94%20foundation-blue)
![Python](https://img.shields.io/badge/python-3.11%2B-blue)
![License](https://img.shields.io/badge/license-MIT-green)

> **Project status:** Under active development. This README describes the **target design**. See [Roadmap & Progress](#roadmap--progress) for what is implemented and verified today. Evaluation numbers below are **targets, not results**. I only publish measured results after running reproducible evaluations.

---

## Table of Contents

- [Why this project](#why-this-project)
- [What it does](#what-it-does)
- [Architecture](#architecture)
- [The agents](#the-agents)
- [Tech stack](#tech-stack)
- [Roadmap & Progress](#roadmap--progress)
- [Evaluation plan](#evaluation-plan)
- [Dataset](#dataset)
- [Repository structure](#repository-structure)
- [Getting started](#getting-started)
- [Security principles](#security-principles)
- [Documentation](#documentation)
- [License](#license)

---

## Why this project

Company knowledge is spread across HR policies, engineering docs, incident reports, support tickets, and operational databases. Consider a question like:

> *"Why did our customer onboarding time increase in September, what engineering issues contributed to it, and what actions should we take?"*

- A **chatbot** can't answer it, because the evidence lives in documents and databases it has no access to.
- A **basic RAG bot** retrieves a few passages but can't compare metrics, link evidence across sources, or take follow-up action.

This assistant handles the whole workflow:

1. Breaks the question into research tasks.
2. Searches documents (procedures, incident reports) with hybrid retrieval.
3. Runs read-only SQL to compare periods and spot trends.
4. Links the document evidence to the data evidence.
5. Writes a grounded answer with citations and states its uncertainty explicitly.
6. Proposes an action, such as a follow-up ticket.
7. **Waits for human approval** before running any high-impact action.

## What it does

| Capability | Description |
| --- | --- |
| 🔎 **Grounded research** | Hybrid (semantic + keyword) retrieval with reranking. Citations point to real, stored passages. |
| 📊 **Data analysis** | Validated, read-only SQL. Calculations run deterministically in SQL or Python, not by the LLM. |
| 🧠 **Evidence synthesis** | Combines document and data findings, and separates correlation from causation. |
| 🛠️ **Controlled actions** | Typed tool calls through MCP adapters. The backend enforces approval and permissions. |
| 🧾 **Auditability** | Shows which sources were used, which tools ran, where approval was required, and what couldn't be verified. |
| 📏 **Measured quality** | Reproducible evaluations for retrieval, citations, task success, safety, latency, and cost. |

## Architecture

```mermaid
flowchart TD
    UI["Web Interface<br/>Conversation · Citations · Execution trace · Approvals"]
    API["FastAPI Backend<br/>Auth · Validation · Streaming · Run management"]
    SUP["LangGraph Supervisor / Planner<br/>Interpret · Decompose · Delegate · Shared state"]

    R["Research Agent<br/>Hybrid RAG + citations"]
    D["Data Agent<br/>Read-only SQL + analysis"]
    A["Analysis Agent<br/>Evidence synthesis + validation"]
    ACT["Action Agent<br/>MCP tools + approval requests"]

    V["Evidence Validator + Response Composer<br/>Verify sources · Flag uncertainty · Assemble answer"]
    OUT["Grounded answer + citations + auditable actions"]

    UI --> API --> SUP
    SUP --> R & D & A & ACT
    R & D & A & ACT --> V --> OUT

    subgraph Shared Infrastructure
        PG[("PostgreSQL + pgvector")]
        POL["Policy + permissions"]
        OBS["Tracing + evaluation"]
    end
```

LangGraph models the workflow as nodes and edges over a shared state. That gives explicit control over what runs, what gets retried, and where execution must **pause for human approval**.

More detail: [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md)

## The agents

<details>
<summary><b>1. Supervisor / Planner</b>: decomposes the request and routes it</summary>

Produces a structured plan that is validated against a Pydantic schema. The LLM's JSON is never trusted blindly. The supervisor also decides when there's enough evidence, when to retry, and when to stop.

```json
{
  "intent": "research_analyze_propose_action",
  "tasks": [
    {"agent": "research", "task": "Find Q3 support incidents"},
    {"agent": "data",     "task": "Calculate delay trends"},
    {"agent": "analysis", "task": "Compare evidence and explain causes"},
    {"agent": "action",   "task": "Draft a ticket for approval"}
  ]
}
```
</details>

<details>
<summary><b>2. Research / RAG Agent</b>: hybrid retrieval with real citations</summary>

`Upload → Extract → Chunk (+metadata) → Embed → Store → Hybrid search → Rerank + permission filter → Passages with stable source IDs`

Semantic search finds conceptually related content. Keyword search catches exact identifiers like `INC-204` or policy names. The two result sets are fused and then reranked by a cross-encoder.
</details>

<details>
<summary><b>3. Data Agent</b>: safe, read-only SQL</summary>

Read-only database role, allow-listed schemas, query validation, statement timeouts, and row limits. Numbers are computed deterministically in SQL or Python.
</details>

<details>
<summary><b>4. Evidence Analysis Agent</b>: honest synthesis</summary>

Combines document and data findings. Flags missing or contradictory evidence and **never presents correlation as causation**.
</details>

<details>
<summary><b>5. Action Agent</b>: controlled tool executor</summary>

Proposes typed actions (e.g. `create_issue`). Nothing runs until the user approves it, and the backend enforces permissions independently of the LLM. Credentials never pass through prompts.
</details>

## Tech stack

| Layer | Technology |
| --- | --- |
| LLM | OpenAI-compatible API (OpenAI / Gemini) |
| Orchestration | LangGraph |
| RAG framework | LangChain |
| Vector + relational DB | PostgreSQL + pgvector |
| Keyword retrieval | PostgreSQL full-text search |
| Reranking | Cross-encoder |
| Backend | FastAPI + Pydantic |
| Frontend | React + TypeScript |
| Tool integration | MCP + explicit adapters |
| Checkpoints | PostgreSQL |
| Observability | LangSmith / OpenTelemetry |
| Testing | pytest + evaluation datasets |
| Deployment | Docker + GCP Cloud Run |

The infrastructure is deliberately minimal: one backend, one PostgreSQL instance, one frontend. Kubernetes, Kafka, and Redis aren't needed to prove the core system works.

## Roadmap & Progress

Each phase ends with a working, **tested** deliverable. Full checklist: [`docs/ROADMAP.md`](docs/ROADMAP.md)

| Phase | Goal | Deliverable | Status |
| --- | --- | --- | --- |
| 0 | Project planning & repository setup | README, architecture, roadmap, repo conventions | ✅ Done |
| 1 | Foundation | Prompt in → LLM answer out, through our own FastAPI app + Postgres + Docker | ✅ Done |
| 2 | Reliable hybrid RAG | Questions over uploaded docs, answered with verifiable source passages | ⏳ Next |
| 3 | LangGraph multi-agent orchestration | Complex questions trigger coordinated retrieval + SQL analysis | ⬜ Planned |
| 4 | MCP & controlled actions | Drafted task → approval → created only after authorization | ⬜ Planned |
| 5 | Evaluation, reliability & security | Reproducible reports: baseline RAG vs. hybrid vs. agentic | ⬜ Planned |
| 6 | Deployment & presentation | Deployed on Cloud Run with docs, diagrams, eval results, demo | ⬜ Planned |

Changes are logged in [`CHANGELOG.md`](CHANGELOG.md).

## Evaluation plan

These are **proposed acceptance criteria**. They are targets, not achieved results.

| Metric | Target | Definition |
| --- | --- | --- |
| Retrieval Recall@5 | ≥ 85% | Gold evidence appears in the top 5 retrieved chunks |
| Citation validity | ≥ 95% | Cited passages exist and support the claim |
| Task completion | ≥ 80% | End-to-end tasks meet predefined correctness criteria |
| Unauthorized actions | 0 | No restricted or unapproved action executes |
| p95 latency | Baseline TBD | 95th-percentile response time per task class |
| Cost per task | Baseline TBD | Model + retrieval cost for representative queries |

Three configurations will be compared: **(1)** basic vector RAG, **(2)** hybrid RAG + reranking, **(3)** full multi-agent system. The comparison shows which gains come from better retrieval and which come from orchestration.

## Dataset

The system uses a **fictional software company** built from public documentation plus **clearly labeled synthetic records**. No confidential data is used.

- **Unstructured:** product docs, policies, onboarding procedures, incident reports, support notes (Markdown/PDF/DOCX)
- **Structured:** PostgreSQL tables such as `customers`, `onboarding_events`, `support_tickets`, `issues`, and `operational_metrics`

Because the dataset is built for this project, cross-source questions have **known answers**. That makes evaluation reproducible, and actions can be demonstrated safely.

## Repository structure

Target layout. Directories are filled in as each phase lands.

```
enterprise-agentic-assistant/
├── backend/
│   ├── app/
│   │   ├── api/            # FastAPI routers + dependencies
│   │   ├── core/           # typed settings
│   │   ├── llm/            # provider-agnostic LLM clients
│   │   ├── schemas/        # Pydantic request/response models
│   │   ├── agents/         # supervisor, research, data, analysis, action
│   │   ├── rag/            # ingestion, chunking, embeddings, retrieval, reranking
│   │   ├── graph/          # LangGraph state, builder, routing
│   │   ├── tools/          # MCP adapters & typed tools
│   │   ├── security/       # authn/z, SQL guardrails, approval policy
│   │   ├── db/             # SQLAlchemy models, sessions
│   │   └── main.py
│   ├── alembic/            # database migrations
│   ├── tests/              # unit + integration tests
│   └── Dockerfile
├── frontend/               # React + TypeScript UI
├── datasets/
│   ├── documents/          # unstructured corpus
│   ├── structured/         # SQL seed data
│   └── evaluation/         # gold Q&A + evidence labels
├── evals/                  # evaluation harness & reports
├── docs/                   # architecture, roadmap, decisions
├── .github/workflows/      # CI
├── docker-compose.yml
├── .env.example
└── README.md
```

## Getting started

What works today (Phase 1): a FastAPI backend that answers prompts through a pluggable LLM client, records every run in PostgreSQL + pgvector, and serves a minimal React UI.

### Prerequisites

- Docker (with Compose v2.24+)
- Node.js 20.19+ (for the frontend)
- Python 3.11+ (only for running backend tests or the backend outside Docker)

### 1. Start the backend and database

```bash
git clone https://github.com/Gnanasudharsan/enterprise-agentic-assistant.git
cd enterprise-agentic-assistant
docker compose up --build
```

This works with **zero configuration**. With no `.env`, the backend uses the offline `fake` LLM provider, which gives deterministic answers without an API key. Database migrations run automatically on startup.

To use a real model, create `.env` from the example and set your key:

```bash
cp .env.example .env
# then edit .env:  LLM_PROVIDER=openai  and  LLM_API_KEY=sk-...
docker compose up --build
```

Any OpenAI-compatible endpoint works through `LLM_BASE_URL` and `LLM_MODEL`.

### 2. Try the API

```bash
curl localhost:8000/health/ready
```

```bash
curl -X POST localhost:8000/api/v1/chat -H 'content-type: application/json' -d '{"prompt": "What should a new employee do in their first week?"}'
```

Interactive API docs: <http://localhost:8000/docs>

| Endpoint | Description |
| --- | --- |
| `GET /health` | Liveness (process is up) |
| `GET /health/ready` | Readiness (database reachable), `503` otherwise |
| `POST /api/v1/chat` | `{"prompt": "..."}` → answer, provider, model, latency, token usage, `run_id` |

### 3. Run the frontend

```bash
cd frontend && npm install && npm run dev
```

Open <http://localhost:5173>. The dev server proxies `/api` and `/health` to the backend on port 8000.

### Running tests

```bash
cd backend && python3 -m venv .venv && .venv/bin/pip install -e ".[dev]"
```

```bash
cd backend && .venv/bin/pytest
```

Integration tests need a running Postgres + pgvector, for example the compose database on host port 5433:

```bash
cd backend && DATABASE_URL=postgresql+asyncpg://assistant:change-me@localhost:5433/assistant .venv/bin/pytest -m integration
```

CI runs lint, unit tests, integration tests against pgvector, a Docker Compose smoke test, and the frontend build on every push.

## Security principles

- **Least privilege everywhere:** a read-only DB role for agent SQL, and scoped tokens for each tool.
- **Approval enforced by the backend, not by the LLM.** High-impact actions pause the graph until a human approves.
- **No secrets in prompts.** Credentials live in server-side config, never in agent messages.
- **Permission-aware retrieval.** Access control is applied before passages reach the model.
- **Prompt-injection and unauthorized-action tests** are part of the evaluation suite.

See [`SECURITY.md`](SECURITY.md).

## Documentation

- [Architecture](docs/ARCHITECTURE.md)
- [Roadmap & checklist](docs/ROADMAP.md)
- [Architecture Decision Records](docs/adr/)
- [Contributing](CONTRIBUTING.md)
- [Changelog](CHANGELOG.md)

## License

[MIT](LICENSE) © 2026 Gnanasudharsan Ashokumar
