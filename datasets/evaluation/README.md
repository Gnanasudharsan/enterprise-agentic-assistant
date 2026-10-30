# Evaluation datasets

## `retrieval_gold.jsonl`

Questions about the synthetic Helio Systems corpus with the evidence a correct retrieval must surface. One JSON object per line:

| Field | Meaning |
| --- | --- |
| `id`, `category` | `factual`, `paraphrase` (wording differs from the source), `identifier` (exact IDs like INC-204), `cross_doc` (evidence spread over documents), `restricted` (access-controlled documents) |
| `question` | The user question |
| `evidence` | `{doc_key, phrase}` items. A retrieved passage is relevant if it belongs to `doc_key` and contains `phrase` in its text or heading path (case-insensitive, Markdown emphasis ignored). Phrases are used instead of chunk IDs so the gold set survives re-chunking. |
| `require_all` | If true, *all* evidence items are needed for a complete answer (also reported as evidence coverage) |
| `groups` | For `restricted` questions: the groups that *may* read the evidence. The harness checks both that these callers find it and that a regular employee never retrieves it. |

A unit test (`backend/tests/test_eval_gold.py`) checks that every phrase exists in its document, so the gold set cannot silently drift from the corpus.

## `agent_tasks.jsonl`

Tasks for the multi-agent evaluation (`evals/agent_eval.py`), run through `POST /api/v1/agent/run`:

| Field | Meaning |
| --- | --- |
| `id`, `category` | `cross-source`, `data`, `documents`, `safety`, `conversational` |
| `question` | The user question |
| `agents` | Specialists the plan must include (`research`, `data`) |
| `docs` | The answer must cite at least one of these documents (if non-empty) |
| `numbers` | Values from the deterministic analytics data that must appear in the answer (whole-number match, so `9` does not match `19`) |
| `forbid_tables` | Safety: no executed SQL may reference these |
| `restricted_facts` | Safety: facts only in restricted documents; a regular employee's answer must not contain them |
| `max_steps` | Conversational: the plan may have at most this many steps |

The analytics data is generated with a fixed seed, so expected numbers are stable; `backend/tests/test_integration_analytics.py` pins the key ones (118 / 9 tickets, the onboarding medians).
