# Synthetic enterprise corpus: Helio Systems (fictional)

Everything in this folder is **synthetic**. It was written for this project and describes a fictional B2B SaaS company, *Helio Systems, Inc.*, which sells a workspace collaboration platform. Any resemblance to real companies, people, products, or incidents is coincidental.

The documents link to each other on purpose (a September 2026 customer-onboarding slowdown appears in the procedure, an incident report, an ADR, and the support playbook), so cross-document questions have known answers for evaluation.

Each file starts with front matter:

| Field | Meaning |
| --- | --- |
| `title` | Human-readable title |
| `doc_id` | Stable identifier used in citations |
| `doc_type` | policy, procedure, incident, adr, playbook, spec, plan |
| `owner` | Owning team |
| `acl` | Comma-separated groups allowed to read it (`all-employees`, `hr-confidential`, `leadership`, …) |
| `version`, `updated` | Document version and last update date |

`README.md` files are not ingested.
