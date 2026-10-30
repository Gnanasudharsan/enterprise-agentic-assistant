# ADR 0003: A small LangGraph plan-and-execute graph, and two-layer SQL safety

- **Status:** Accepted
- **Date:** 2026-10-30

## Context

Phase 3 must answer questions that need both documents and measurements ("why did onboarding slow down, and by how much?"). The model has to plan the work, run SQL over company data, and combine both kinds of evidence in one cited answer. Model-written SQL is untrusted input, and long multi-step runs fail part-way more often than single calls.

## Decision

1. **Plan-and-execute, not a free-running agent loop.** The supervisor emits one JSON plan (validated by Pydantic: step ids, agent names, at most 3 steps per agent, dependencies only from data steps to research steps). The graph executes it in at most two parallel waves and then writes the answer. Runs have a bounded number of LLM calls and are easy to trace and test.
2. **Repair, then rules, then fallback.** An invalid plan goes back to the model once with the validation error. Deterministic rules run on every plan; for example, a question about a target or policy always gets a research step. If no valid plan exists (provider error, offline mode), a keyword plan is used and the trace says so.
3. **Dependencies instead of a separate "context" agent.** A data step can declare `depends_on: ["s1"]`. It then runs after the research step and receives its top passages, e.g. the incident dates it needs for a `WHERE` clause. This was added after the evaluation showed the data agent guessing dates.
4. **Two independent SQL safety layers.** A sqlglot validator (one SELECT, allow-listed tables and functions, enforced LIMIT) and a least-privilege executor (READ ONLY transaction, `SET LOCAL ROLE analytics_reader`, statement timeout, row cap, rollback). Either layer alone blocks writes and reads outside the analytics schema; integration tests run attacks with the validator bypassed.
5. **Self-correction with a reviewed fallback.** Rejected or failing SQL goes back to the model with the error, up to 3 attempts. A small catalog of reviewed queries then serves as fallback and as few-shot examples. Fallbacks are labeled in the trace and the UI.
6. **Numbered evidence for both kinds of sources.** Passages are `[S#]`, query results are `[T#]`. The same server-side check removes markers that point to nothing.
7. **Postgres checkpoints keyed by run id.** State is plain JSON, so every step is checkpointed; failed runs resume without repeating work. The `agent_runs` row holds the plan, trace, evidence, and answer for auditing.

## Alternatives considered

- **ReAct-style tool loop** (the model calls search/SQL tools freely). More flexible, but harder to bound, trace, and evaluate. Plan-and-execute covers the target questions; a loop can be added as one node later.
- **A dedicated login role for agent SQL.** Stronger isolation (the session user itself is unprivileged), but needs a second credential to provision. `SET LOCAL ROLE` from the app role is used for now; the executor already accepts any engine, so a separate URL is a small change for production.
- **LLM-computed numbers.** Rejected: all figures come from SQL results, and the analyst is told to show how any derived number was obtained.

## Consequences

- A typical cross-source question costs 3 LLM calls (plan, SQL, answer); p50 latency is about 3.7 s and p95 about 11 s on `gpt-4.1-mini`.
- The plan is only as good as the supervisor's understanding of the schema; the schema description (with conventions such as "monthly onboarding metrics use the signing-month cohort") is part of the prompt and must be kept in sync with the tables.
- The evaluation set is small and was used during development; Phase 5 adds a held-out benchmark and the baseline-vs-agentic comparison.
