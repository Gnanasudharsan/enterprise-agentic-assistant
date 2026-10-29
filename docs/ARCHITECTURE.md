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

## 4. Data model (initial sketch)

| Table | Purpose |
| --- | --- |
| `documents` | Source document metadata, version, ACL, content hash, embedding model *(implemented)* |
| `chunks` | Chunk text, heading path, generated `tsvector`, `vector(1536)`, FK to document *(implemented)* |
| `chat_runs` | One row per run: status, latency, tokens, retrieved chunks, validated citations *(implemented)* |
| `run_steps` | Agent/tool steps for the execution trace |
| `actions` | Proposed actions, approval decision, executor result (audit log) |
| `checkpoints` | LangGraph state persistence |
| *demo schema* | `customers`, `onboarding_events`, `support_tickets`, `issues`, `operational_metrics` (synthetic) |

## 5. Trust boundaries

1. **User ↔ backend:** authenticated; every request carries a user and role context.
2. **LLM ↔ tools:** the LLM only *proposes* tool calls. The backend validates arguments, checks permissions, and requires approval for high-impact actions.
3. **Data Agent ↔ database:** a dedicated read-only role limited to the demo schema.
4. **Retrieved content ↔ LLM:** retrieved text is treated as untrusted data, which is why prompt-injection tests are part of the eval suite.

## 6. Decisions

Significant decisions are recorded as ADRs in [`adr/`](adr/).
