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
