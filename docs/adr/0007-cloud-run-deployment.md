# ADR 0007: One Cloud Run service with Cloud SQL, bounded for a public demo

- **Status:** Accepted
- **Date:** 2026-10-31

## Context

The project needs a public URL that reviewers can try, built from the same code that the evaluations measured. Every question spends real model credits, so the demo must cap its own cost. It also has to survive idle periods cheaply and be reproducible from scripts.

## Decision

1. **One container.** A multi-stage `Dockerfile` builds the frontend and serves it from FastAPI (`STATIC_DIR`). The API is on the same origin, which means no CORS and one deployable. Fingerprinted assets are cached as immutable, and every other path falls back to `index.html`.
2. **Cloud Run, scale to zero, at most one instance.** Idle costs nothing. One instance keeps the in-memory rate limiter and daily budget exact, and stays within the connection limit of the smallest Cloud SQL tier.
3. **Cloud SQL for PostgreSQL 16, with pgvector, over the Unix-socket connector.** It runs the same database and migrations as local development and CI. Its connection URL lives in Secret Manager.
4. **Three cost and abuse limits, all enforced by the backend:**
   - An **access code**, compared in constant time, with guesses rate limited.
   - **Per-client rate limits** on the endpoints that call the model. The client address is read from `X-Forwarded-For` according to `FORWARDED_HOPS`, because the left-most entries are client-controlled.
   - A **daily token budget.** When it is spent, `BudgetedLLM` routes to the offline model, so the demo degrades instead of failing. The count is restored from the day's recorded runs at startup.
5. **Least privilege.** A dedicated runtime service account holds only the Cloud SQL client role, access to its own three secrets, and permission to write traces, logs, and metrics. Secrets reach Secret Manager from the shell on stdin and are never written to disk.
6. **Observability.** Logs are structured JSON, using Cloud Logging's `severity` and `httpRequest` fields and linked to their trace. Cloud Trace receives the OpenTelemetry spans (`TRACING=gcp`), and an uptime check watches `/health/ready`.

## Alternatives considered

- **Neon or Supabase (free Postgres with pgvector).** $0, but they need an account outside the GCP project and they add a third-party data processor. The scripts work with any `DATABASE_URL`, so switching only means changing one secret.
- **Identity-Aware Proxy instead of an access code.** IAP is stronger, but every reviewer would need a Google account added to the project. A shareable code fits a portfolio demo; IAP is the upgrade path once real users exist.
- **Separate frontend hosting (Cloud Storage + CDN).** Splitting the frontend adds a second deployable and a CORS configuration for no benefit at this scale.

## Consequences

- Cold starts take a few seconds, plus the first-start seeding (once per database).
- The local issue tracker resets when the instance is replaced; the audit log does not.
- Horizontal scaling would need the limiter and the budget moved to the database or Redis.
