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

## Scope

This is a portfolio/research project that uses **synthetic data**. Don't load confidential or personal data into it.
