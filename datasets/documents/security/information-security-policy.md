---
title: Information Security Policy
doc_id: SEC-001
doc_type: policy
owner: Security
acl: all-employees
version: 5.2
updated: 2026-05-20
---

# Information Security Policy

Synthetic document for demonstration. Helio Systems, Inc. is a fictional company.

## Authentication

Multi-factor authentication (MFA) is **mandatory for every internal system**. Hardware security keys are required for production access and for administrators of the identity provider. Passwords must be at least 14 characters and stored only in the company password manager.

## Data classification

| Class | Examples | Handling |
| --- | --- | --- |
| Public | Marketing site, published docs | No restrictions |
| Internal | Handbook, roadmaps, most documents | Employees only |
| Confidential | Customer data, contracts, financials | Need-to-know; encrypted at rest and in transit |
| Restricted | Compensation, security keys, M&A plans | Named individuals only; access logged |

Customer data must never be copied to personal devices, personal cloud storage, or unapproved AI tools.

## Devices

Company laptops must have full-disk encryption, automatic screen lock after 5 minutes, and the endpoint protection agent installed. Lost or stolen devices must be reported to Security **within 1 hour**.

## Access reviews

Managers review their team's access to Confidential and Restricted systems **every quarter**. Access is removed within 24 hours of a role change or departure.

## Reporting security incidents

Report any suspected security incident (phishing, leaked credentials, unexpected access) in the #security-incidents channel or to security@helio.example **within 1 hour of discovery**. Do not investigate on your own or delete evidence.

## Third-party software

New SaaS tools and libraries that process Internal or higher data require a security review before purchase. Reviews take up to 10 business days; vendors handling customer data also need a signed data processing agreement.
