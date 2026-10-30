# Security Policy

## Reporting a vulnerability

Please **do not** open a public issue for security problems. Report them privately through GitHub's
[private vulnerability reporting](https://docs.github.com/en/code-security/security-advisories/guidance-on-reporting-and-writing-information-about-vulnerabilities/privately-reporting-a-security-vulnerability)
on this repository.

## Design principles

- **Least privilege:** the Data Agent uses a read-only DB role restricted to approved schemas, and tool tokens are scoped to the minimum required.
- **Backend-enforced approvals:** high-impact actions can't execute without a recorded human approval, regardless of LLM output.
- **No secrets in prompts or agent messages.** Credentials stay in server-side configuration.
- **Untrusted retrieved content:** documents and tool outputs are treated as data, never as instructions.
- **SQL guardrails:** statement allow-list (SELECT only), timeouts, row limits, and validation before execution.
- **Auditability:** every proposed, approved, rejected, and executed action is logged.

## How the principles are implemented

| Principle | Implementation | Verified by |
| --- | --- | --- |
| Read-only agent SQL | sqlglot validator + `READ ONLY` transaction as `analytics_reader` (analytics schema only), statement timeout, row cap | `test_sql_guard.py`, `test_integration_analytics.py` (attacks run with the validator bypassed) |
| Approval before any write | Non-read-only tools pause the LangGraph run (`interrupt`); only `POST …/actions/{id}/decision` resumes it | `test_actions.py` (no execution before approval, after rejection, or twice) |
| Backend permission checks | `ACTION_PERMISSIONS` allow-list checked when approving **and** again right before execution; unknown tools denied | `test_actions.py` (403 + `denied` audit event; no proposal for callers without permission) |
| Integrity of approved calls | Approval is bound to a SHA-256 of the exact tool + arguments; execution refuses on mismatch | `test_arguments_changed_after_approval_are_blocked` |
| At-most-once execution | Status moves to `executing` before the call; a re-run after a crash never re-sends it | `execute_action` |
| Credentials isolation | The tracker MCP server is a subprocess that receives only tracker settings (no model key, no DB URL); the model sees tool schemas only | `test_subprocess_gets_only_tracker_settings` |
| Least-privilege tokens | GitHub backend expects a fine-grained token for one repository with only "Issues: read and write" | docs |
| Audit log | Append-only `action_audit`: proposed, edited, approved, rejected, denied, executing, executed, failed (actor + time + detail) | `GET /api/v1/actions` |

## Scope

This is a portfolio/research project that uses **synthetic data**. Don't load confidential or personal data into it.
