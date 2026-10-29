---
title: Customer Onboarding Procedure
doc_id: CS-004
doc_type: procedure
owner: Customer Success
acl: all-employees
version: 2.0
updated: 2026-09-01
---

# Customer Onboarding Procedure

Synthetic document for demonstration. Helio Systems, Inc. is a fictional company.

## Purpose and target

This procedure covers every new paying customer from contract signature to go-live. The target is to complete onboarding within **3 business days** for Standard plans and **10 business days** for Enterprise plans.

## Stages

1. **Kickoff (day 0):** the onboarding specialist sends the welcome email and schedules the kickoff call within 1 business day of contract signature.
2. **Identity verification (KYB):** since version 2.0 of this procedure (effective **2026-09-01**), every new business customer must pass a know-your-business (KYB) check through our verification provider before a workspace is provisioned. See ADR-012 for the decision record.
3. **Workspace provisioning:** automated once verification passes.
4. **Data import:** customers upload users and projects via CSV or the migration API.
5. **Admin training:** a 45-minute live session for workspace administrators.
6. **Go-live:** the customer is marked live in the CRM and handed over to their account manager.

## What changed in version 2.0

Before September 2026, workspaces were provisioned immediately and verification happened afterwards, in the background. Version 2.0 makes verification a **blocking step**, to meet new compliance requirements from enterprise and financial-services customers. Expected impact: about half a day added to median onboarding time.

## Verification failures and escalation

- If the verification provider returns "manual review", the onboarding specialist collects documents from the customer and the Compliance team decides within 2 business days.
- If verification is blocked by a technical error, open a support ticket tagged `kyb-verification` and follow the escalation rules in SUP-003.
- Any onboarding exceeding its target by more than 2 business days must be flagged in the weekly Customer Success review.

## Metrics

Customer Success tracks median and 90th-percentile onboarding time per month, the share of customers onboarded within target, and the number of onboarding-related support tickets.
