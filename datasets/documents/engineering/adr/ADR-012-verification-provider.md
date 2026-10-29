---
title: "ADR-012: External KYB verification provider and integration design"
doc_id: ADR-012
doc_type: adr
owner: Platform Engineering
acl: all-employees
version: 1.2
updated: 2026-09-26
---

# ADR-012: External KYB verification provider and integration design

Synthetic document for demonstration. Helio Systems, Inc. is a fictional company.

- **Status:** Accepted (amended 2026-09-26 after INC-204)
- **Date:** 2026-07-28

## Context

Enterprise and financial-services prospects require us to verify the legal identity of business customers (know-your-business, KYB) before they get a workspace. Compliance asked for verification to be in place by September 2026.

## Options considered

1. **Build in-house** on top of public company registries: full control, but 4 to 6 months of work and ongoing maintenance for each country.
2. **VeriTrust (external provider):** coverage of 40+ countries, per-check pricing, REST API, results in seconds for about 90% of businesses.
3. **Manual review only:** no engineering cost, but would add 1 to 2 days to every onboarding.

## Decision

Use **VeriTrust**, integrated **synchronously** in the provisioning flow: provisioning calls the verification API and waits for the result before creating the workspace. The synchronous design was chosen to ship by the September compliance deadline.

## Consequences

- Positive: compliance requirement met on time; no country-specific registry integrations to maintain.
- Negative: provisioning now depends on VeriTrust's latency and availability. Timeouts or outages block onboarding directly.

## Amendment after INC-204 (2026-09-26)

The synchronous design amplified the impact of INC-204. We will move verification to an **asynchronous job queue** with automatic resumption of provisioning, targeted for Q4 2026. Until then, the client uses a 15-second timeout with exponential backoff.
