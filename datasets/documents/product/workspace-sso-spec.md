---
title: "Product Spec: Workspace Single Sign-On (SSO) and SCIM"
doc_id: PRD-031
doc_type: spec
owner: Product Management
acl: all-employees
version: 1.0
updated: 2026-08-05
---

# Product Spec: Workspace Single Sign-On (SSO) and SCIM

Synthetic document for demonstration. Helio Systems, Inc. is a fictional company.

## Problem

Enterprise customers must manage access centrally. Without SSO, admins create and remove users by hand, which is slow and a security risk when employees leave.

## Goals

- SAML 2.0 and OpenID Connect SSO with the major identity providers.
- SCIM 2.0 user provisioning and deprovisioning.
- Enforce SSO-only login per workspace.

## Non-goals

- Social login for Enterprise workspaces.
- Custom identity provider integrations beyond SAML and OIDC.

## Requirements

1. Admins can configure SSO in under 15 minutes using the setup wizard.
2. SCIM deprovisioning removes access within **5 minutes**.
3. Available on the **Enterprise plan only**.

## Success metrics

- 60% of Enterprise workspaces enable SSO within 90 days of launch.
- 30% fewer access-related support tickets from Enterprise customers.

## Launch plan

Beta with 10 design-partner customers in October 2026, general availability targeted for **Q4 2026**.
