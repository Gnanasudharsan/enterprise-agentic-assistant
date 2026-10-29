# ADR 0001: Initial stack and scope

- **Status:** Accepted
- **Date:** 2026-10-29

## Context

The project combines LLM reasoning, multi-agent orchestration, RAG, backend engineering, and LLMOps. The risk is building a complicated set of agents that looks impressive but can't be tested. We need a stack that is small, reproducible, and production-shaped.

## Decision

- **Language/backend:** Python 3.11+, FastAPI, Pydantic.
- **Storage:** a single PostgreSQL instance with `pgvector` for vectors, full-text search for keywords, and LangGraph checkpoints.
- **Orchestration:** LangGraph (explicit state, nodes, edges, interrupts for approval).
- **LLM:** any OpenAI-compatible API, configured through environment variables.
- **Frontend:** React + TypeScript.
- **Deployment:** Docker locally, then GCP Cloud Run.
- **Not on day one:** Kubernetes, Redis, Kafka, or multiple cloud services.
- **Build order:** a single reliable RAG workflow first, then hybrid retrieval, evaluation, SQL, agents, and actions.

## Consequences

- One database simplifies ops, permissions, and joins between metadata and vectors.
- Scaling past a single Postgres node is deferred. That is acceptable for a portfolio-scale corpus.
- Every phase must ship tests, so progress claims can be verified.
