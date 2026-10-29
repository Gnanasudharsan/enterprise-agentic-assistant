---
title: Support Escalation Playbook
doc_id: SUP-003
doc_type: playbook
owner: Customer Support
acl: all-employees
version: 3.4
updated: 2026-09-12
---

# Support Escalation Playbook

Synthetic document for demonstration. Helio Systems, Inc. is a fictional company.

## Priority levels

| Priority | Definition | First response | Update cadence |
| --- | --- | --- | --- |
| P1 | Platform down or data loss for many customers | 15 minutes | Every 30 minutes |
| P2 | Major feature broken or blocking for several customers | 1 hour | Every 2 hours |
| P3 | Feature degraded with a workaround | 4 business hours | Daily |
| P4 | Question or cosmetic issue | 1 business day | As needed |

## When to escalate to engineering

Escalate to the on-call engineer of the owning team when:

- a P1 or P2 ticket is opened, or
- **more than 10 tickets with the same tag** are opened within 48 hours (a "ticket cluster"), even if each one is P3.

Ticket clusters are a leading indicator of an incident. During INC-204 in September 2026, the `kyb-verification` cluster was the first signal of the problem.

## How to escalate

1. Page the owning team's on-call through the paging tool with the ticket links.
2. Post a summary in #support-escalations: affected customers, first occurrence, example error.
3. Keep customers updated at the cadence for the ticket's priority, even when there is no news.

## Onboarding-related tickets

Tickets about blocked onboarding (verification, provisioning, data import) are at least **P3**, and **P2 when a customer's go-live date is at risk**. Tag them with the stage, for example `kyb-verification` or `data-import`.
