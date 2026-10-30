# ADR 0004: Actions through an MCP server, gated by a graph interrupt and backend policy

- **Status:** Accepted
- **Date:** 2026-10-30

## Context

Phase 4 lets the assistant act on what it finds, by drafting and creating an issue. Model output is untrusted, so the system must guarantee that nothing changes in an external system without a person's explicit approval, that the person approves exactly what runs, and that the model never sees credentials.

## Decision

1. **Integration through MCP.** We wrote a small issue-tracker MCP server (`app/mcp_servers/tracker.py`) with typed tools: `create_issue` (title and body lengths, label and priority enums) and the read-only `search_issues`. The backend connects as an MCP client over stdio. The backend has a local SQLite tracker as the default (offline demos, CI) and GitHub Issues as an option. Running our own server keeps the tool surface tiny and auditable, and any other MCP server can be connected through the same `ToolGateway`.
2. **Process isolation for credentials.** The MCP server is spawned with an explicit environment that holds only tracker settings. The backend's model key and database URL are not inherited, and the model only ever sees tool schemas and results.
3. **Actions run after the answer.** An optional `action` plan step (at most one) runs after the analyst. It searches for duplicates (read-only), drafts one call, and validates it against the tool's JSON Schema, with one repair round. It never calls a write tool itself.
4. **Approval is a LangGraph `interrupt`.** The run pauses (status `needs_approval`) in the Postgres checkpoint. The only way to resume it is `POST …/actions/{id}/decision`, which records a human decision. The run survives restarts while it waits.
5. **The backend enforces policy, independently of the model.**
   - Tools are an allow-list per access group (`ACTION_PERMISSIONS`), checked when drafting, at approval, and again right before execution.
   - The backend, not the server annotation, decides which tools are read-only.
   - An approval is bound to a SHA-256 of the exact tool and arguments. Edits are re-validated and hashed, and execution refuses on mismatch.
   - Status moves to `executing` before the call, so a re-run never re-sends it (at most once).
6. **Append-only audit log.** `action_audit` records proposed, edited, approved, rejected, denied, executing, executed, and failed, with the actor and details. The backend, not the model, appends the provenance footer to created issues.

## Alternatives considered

- **The official GitHub MCP server.** It exposes dozens of tools, many of them destructive, so least privilege would depend on configuring it correctly. It would also require Docker-in-Docker or a Go binary in the image. Our server exposes two tools; a GitHub fine-grained token adds a second boundary.
- **Function calling inside the analyst.** Simpler, but it mixes answering with acting and makes the approval boundary implicit. A separate node behind an interrupt makes the boundary explicit and testable.
- **Approve inside the stream** (keep the HTTP request open until the person decides). This is fragile: a closed tab would lose the run. The checkpointed interrupt allows deciding minutes or days later.

## Consequences

- Fifteen scenario tests cover no execution before approval or after rejection, double approval, permission denial at both checks, tampering after approval, unoffered or read-only tools, and schema violations. All pass with 0 unauthorized executions; CI also checks the full flow in Docker.
- There is one demo identity until authentication lands. `requested_by` and `decided_by` are recorded, but separation of duties (requester ≠ approver) needs real users.
- Duplicate detection in the local tracker is keyword-based. GitHub search is better but not semantic.
