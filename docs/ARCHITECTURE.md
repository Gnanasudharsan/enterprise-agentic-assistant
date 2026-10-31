# Architecture

> This is the **target architecture**. Components are built phase by phase; see [ROADMAP.md](ROADMAP.md) for what exists today.

## 1. Request lifecycle

```mermaid
sequenceDiagram
    actor U as User
    participant FE as Frontend
    participant API as FastAPI
    participant G as LangGraph Supervisor
    participant R as Research Agent
    participant D as Data Agent
    participant AN as Analysis Agent
    participant AC as Action Agent
    participant V as Validator/Composer

    U->>FE: Ask a business question
    FE->>API: POST /api/v1/runs
    API->>G: Start run (auth context, thread id)
    G->>G: Build validated plan
    par Evidence gathering
        G->>R: Retrieve documents
        R-->>G: Passages + source IDs
    and
        G->>D: Analyze structured data
        D-->>G: Query + result table
    end
    G->>AN: Synthesize evidence
    AN-->>G: Findings + confidence + gaps
    opt Action proposed
        G->>AC: Draft action
        AC-->>G: Typed action (approval_required)
        G-->>API: INTERRUPT: awaiting approval
        API-->>FE: Show action preview
        U->>FE: Approve / Reject
        FE->>API: POST /api/v1/runs/{id}/approval
        API->>G: Resume with decision
    end
    G->>V: Verify citations, compose answer
    V-->>API: Answer + citations + trace + action status
    API-->>FE: Stream response
```

## 2. Components

| Component | Responsibility | Key constraints |
| --- | --- | --- |
| **Frontend** | Conversation, citation previews, execution trace, approval panel | Never holds tool credentials |
| **FastAPI backend** | Auth, validation, streaming, run management | Enforces permissions and approvals itself |
| **Supervisor** | Interprets intent, decomposes tasks, routes, stops | Plan validated by a Pydantic schema; bounded iterations |
| **Research Agent** | Hybrid retrieval + reranking + citations | Permission filter applied before generation |
| **Data Agent** | Text-to-SQL over approved schemas | Read-only role, allow-list, timeout, row limit |
| **Analysis Agent** | Combines evidence, flags gaps and contradictions | Correlation ≠ causation; explicit confidence |
| **Action Agent** | Proposes typed tool calls via MCP adapters | Cannot execute without recorded approval |
| **Validator / Composer** | Checks every citation maps to a stored passage | Unverifiable claims are labeled, not hidden |

## 3. Retrieval pipeline (Phase 2, implemented)

```
Upload / seed ─▶ Parse (md, txt, pdf, docx) + front matter (doc_id, title, acl, version)
              ─▶ Heading-aware chunks (heading path, ≤220 words, sentence overlap)
              ─▶ Embed "heading path + text" (text-embedding-3-small | offline hashing)
              ─▶ documents + chunks (generated weighted tsvector, vector(1536))

Question ─▶ (+ previous question for short follow-ups)
         ─▶ ┬─ pgvector cosine top-20   WHERE acl && caller_groups AND same embedding model ─┐
            └─ FTS ts_rank top-20       WHERE acl && caller_groups ─────────────────────────┴▶ RRF (k=60)
         ─▶ [optional LLM rerank] ─▶ top-6 numbered sources [S1..S6]
         ─▶ grounded prompt ─▶ answer ─▶ citation check (drop markers to unknown sources)
         ─▶ response: answer + sources + validated citations; run audit row
```

See [ADR 0002](adr/0002-hybrid-retrieval-in-postgres.md) for the reasoning and measured trade-offs.

## 4. Multi-agent graph (Phase 3, implemented)

```mermaid
flowchart LR
    S["Supervisor<br/>Pydantic plan · repair · rules · fallback"] -->|wave 1: Send per step| R["Docs agent<br/>hybrid retrieval, ACL"]
    S -->|wave 1| D["Data agent<br/>SQL → guard → read-only run"]
    R --> C{{"Coordinator"}}
    D --> C
    C -->|"wave 2: steps with depends_on<br/>(+ research findings)"| D
    C -->|all steps done| A["Analyst<br/>[S#] + [T#] answer, citation check"]
    S -->|no steps| A
    A --> E((END))
```

- **State** is plain JSON (question, history, caller groups, plan, research results, tables, trace), so LangGraph's **Postgres checkpointer** stores it after every step. The run id is the thread id; `POST /agent/runs/{id}/resume` continues a failed run without repeating completed steps.
- **Retries:** transient DB errors retry with backoff (node retry policy); the analyst retries once on model errors and resets streamed text. Logical failures are handled in the node: plan repair (once), SQL repair (up to 3 attempts with the error), then a reviewed query, then a reported failure that the analyst must acknowledge.
- **Trace:** every node returns an event (status `succeeded` / `fallback` / `failed`, start time, duration, summary, detail such as SQL, attempts, or plan rules), persisted on `agent_runs` and shown as a waterfall in the UI.

### SQL safety layers

```
model SQL ─▶ validate_sql (sqlglot, postgres dialect)
             • one statement · SELECT/UNION only · no INTO / FOR UPDATE / data-modifying CTEs
             • tables ∈ analytics.{customers, onboarding_events, verification_checks, support_tickets}
             • functions ∈ allow-list (aggregates, window, date, math, text)
             • LIMIT ≤ SQL_MAX_ROWS enforced
          ─▶ SQLExecutor: SET TRANSACTION READ ONLY · SET LOCAL ROLE analytics_reader
             · SET LOCAL statement_timeout · fetchmany(max_rows + 1) · always ROLLBACK
```

`analytics_reader` is `NOLOGIN` with `USAGE` on the analytics schema and `SELECT` on its tables only. Privileges are checked when a statement starts, so a statement can't widen its own access, and the rollback reverts any session setting. See [ADR 0003](adr/0003-multi-agent-graph-and-safe-sql.md).

### Controlled actions (Phase 4, implemented)

```mermaid
sequenceDiagram
    participant G as LangGraph run
    participant AA as Action agent
    participant DB as Postgres (actions, audit, checkpoints)
    participant API as FastAPI
    participant U as User
    participant MCP as Tracker MCP server (subprocess)

    G->>AA: answer + evidence (plan has an action step)
    AA->>MCP: search_issues (read-only, no approval)
    AA->>AA: draft create_issue · validate against the tool's JSON Schema
    AA->>DB: agent_actions(status=proposed) · audit "proposed"
    G-->>API: interrupt → run status needs_approval
    API-->>U: approval card (approve / edit / reject)
    U->>API: POST …/actions/{id}/decision
    API->>API: permission check · validate edits · hash arguments
    API->>DB: status=approved · audit "approved"
    API->>G: Command(resume=decision)
    G->>DB: re-check status, hash, permission · status=executing
    G->>MCP: create_issue(arguments + provenance footer)
    MCP-->>G: issue key / URL
    G->>DB: status=executed · audit "executed"
```

The model can only produce a *draft*. Approval, permission, integrity, and execution are all backend code paths, and the only route from a draft to a tool call is the decision endpoint. See [ADR 0004](adr/0004-mcp-actions-behind-approval.md).

### Observability and evaluation (Phase 5, implemented)

Every request is one OpenTelemetry trace (`TRACING=otlp`, Jaeger bundled under the Compose `tracing` profile):

```
POST /api/v1/agent/run                           FastAPI instrumentation
├─ agent.supervisor ── chat gpt-4.1-mini         gen_ai.* attributes, input/output tokens
├─ agent.research ──── retrieval.search ── chat  (reranker)
├─ agent.data ──────── chat (SQL) ── sql.execute db.response.returned_rows
├─ agent.coordinator
├─ agent.analyst ───── chat (streamed answer)
└─ agent.propose_action ── mcp.call_tool search_issues ── chat (draft)
```

Spans carry ids, sizes, timings, and token counts, never prompts, answers, or rows. An approval pause is recorded as `agent.interrupted`, not as an error. LangSmith can trace the same graph independently (`LANGSMITH_TRACING=true`).

`MeteredLLM` wraps the model client and adds every call's tokens to the current request's meter (a context variable shared by concurrent graph nodes). `/chat` and `/agent/run` return `usage` (`llm_calls`, tokens), which is stored per run, and the benchmark prices it.

Evaluation suites (`evals/`):

| Suite | What it measures | Report |
| --- | --- | --- |
| `retrieval_eval.py` | Hit@1, Recall@5, MRR, ACL leaks for keyword / vector / hybrid / LLM and cross-encoder reranking | `retrieval-*.md` |
| `benchmark.py` | 32 held-out tasks × 3 systems: task success, recall, citation validity, judged groundedness, latency, cost | `benchmark-*.md` |
| `security_eval.py` | Direct and indirect prompt injection, API-level unauthorized actions, integrity | `security-*.md` |
| `agent_eval.py`, `answer_eval.py` | Regression suites from Phases 2–3 | `agents-*.md`, `answers-*.md` |

## 5. Data model

| Table | Purpose |
| --- | --- |
| `documents` | Source document metadata, version, ACL, content hash, embedding model *(implemented)* |
| `chunks` | Chunk text, heading path, generated `tsvector`, `vector(1536)`, FK to document *(implemented)* |
| `chat_runs` | One row per run: status, latency, tokens, retrieved chunks, validated citations *(implemented)* |
| `agent_runs` | One row per multi-agent run: plan, trace, sources, tables (SQL + rows), citations, latency, model calls and tokens *(implemented)* |
| `checkpoint*` | LangGraph state after every step, created by `AsyncPostgresSaver.setup()` *(implemented)* |
| `analytics.*` | `customers`, `onboarding_events`, `verification_checks`, `support_tickets` (synthetic, read via `analytics_reader`) *(implemented)* |
| `agent_actions` | Proposed tool calls: tool, arguments + approved hash, status, decided by, result *(implemented)* |
| `action_audit` | Append-only log of proposals, edits, decisions, denials, and executions *(implemented)* |

## 6. Trust boundaries

1. **User ↔ backend:** authenticated; every request carries a user and role context.
2. **LLM ↔ tools:** the LLM only *proposes* tool calls. The backend validates arguments against the tool schema, checks permissions at approval and execution, binds approvals to an argument hash, and runs each approved call at most once.
3. **Data Agent ↔ database:** model SQL is validated, then executed read-only as `analytics_reader`, which can only see the analytics schema.
4. **Retrieved content ↔ LLM:** retrieved text is untrusted. Plans are made before retrieval, so a document cannot add steps. Instruction-like paragraphs are redacted and delimiter tags are escaped before passages reach a prompt. Output is sanitized (no images, no links to unlisted hosts) whether or not the model was fooled ([ADR 0006](adr/0006-prompt-injection-defense-in-depth.md)).
5. **Backend ↔ tool servers:** each MCP server is a separate process holding only its own credentials.

## 7. Decisions

Significant decisions are recorded as ADRs in [`adr/`](adr/).
