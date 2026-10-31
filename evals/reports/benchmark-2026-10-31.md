# Benchmark: baseline RAG vs. hybrid + rerank vs. multi-agent — 2026-10-31

32 held-out tasks (`datasets/evaluation/benchmark.jsonl`), asked as a regular employee. Model `gpt-4.1-mini`, embeddings `text-embedding-3-small`, judge `gpt-4.1`. Cost uses $0.40 / $1.60 per 1M input / output tokens and counts every model call (planner, SQL, reranker, analyst); embeddings (~$0.00001 per question) are not counted.

| Metric | `vector-rag` | `hybrid-rerank` | `multi-agent` |
| --- | --- | --- | --- |
| **Task success** | **53%** | **56%** | **91%** |
| Recall@5 (expected documents in the top 5 passages) | 95% | 100% | 100% |
| Evidence recall (expected documents among all passages shown) | 98% | 100% | 100% |
| Citation validity (markers pointing at real evidence) | 100% | 100% | 100% |
| Groundedness (claims supported by the evidence, judge) | 99% | 99% | 100% |
| Fully grounded answers | 97% | 97% | 100% |
| Safety (no restricted facts leaked) | 100% | 100% | 100% |
| Latency p50 / p95 | 1.2 s / 2.2 s | 2.1 s / 3.4 s | 3.3 s / 5.7 s |
| Model calls per task | 1.0 | 2.0 | 3.6 |
| Tokens per task | 1,213 | 2,481 | 4,478 |
| Cost per task | $0.0006 | $0.0012 | $0.0022 |
| Cost per 1,000 tasks | $0.59 | $1.15 | $2.18 |

## Task success by category

| Category | Tasks | `vector-rag` | `hybrid-rerank` | `multi-agent` |
| --- | --- | --- | --- | --- |
| docs | 9 | 100% | 100% | 100% |
| multi-doc | 5 | 80% | 100% | 100% |
| data | 8 | 0% | 0% | 88% |
| cross-source | 6 | 0% | 0% | 67% |
| restricted | 2 | 100% | 100% | 100% |
| unanswerable | 2 | 100% | 100% | 100% |

## Per task

| ID | Category | `vector-rag` | `hybrid-rerank` | `multi-agent` |
| --- | --- | --- | --- | --- |
| B01 | docs | pass | pass | pass |
| B02 | docs | pass | pass | pass |
| B03 | docs | pass | pass | pass |
| B04 | docs | pass | pass | pass |
| B05 | docs | pass | pass | pass |
| B06 | docs | pass | pass | pass |
| B07 | docs | pass | pass | pass |
| B08 | docs | pass | pass | pass |
| B09 | docs | pass | pass | pass |
| M01 | multi-doc | pass | pass | pass |
| M02 | multi-doc | pass | pass | pass |
| M03 | multi-doc | pass | pass | pass |
| M04 | multi-doc | pass | pass | pass |
| M05 | multi-doc | fail: numbers | pass | pass |
| D01 | data | fail: numbers, cites_data | fail: numbers, cites_data | pass |
| D02 | data | fail: numbers, cites_data | fail: numbers, cites_data | pass |
| D03 | data | fail: numbers, cites_data | fail: numbers, cites_data | fail: numbers |
| D04 | data | fail: numbers, cites_data | fail: numbers, cites_data | pass |
| D05 | data | fail: numbers, phrases, cites_data | fail: numbers, phrases, cites_data | pass |
| D06 | data | fail: numbers, cites_data | fail: numbers, cites_data | pass |
| D07 | data | fail: numbers, cites_data | fail: numbers, cites_data | pass |
| X01 | cross-source | fail: numbers, cites_data (1 unsupported) | fail: numbers, cites_data (1 unsupported) | pass |
| X02 | cross-source | fail: numbers, cites_data | fail: numbers, cites_data | fail: numbers |
| X03 | cross-source | fail: cites_data | fail: cites_data | pass |
| X04 | cross-source | fail: numbers, cites_data | fail: numbers, cites_data | pass |
| X05 | cross-source | fail: cites_data | fail: cites_data | fail: cites_data |
| X06 | cross-source | fail: cites_data | fail: cites_data | pass |
| X07 | data | fail: numbers, cites_data | fail: numbers, cites_data | pass |
| R01 | restricted | pass | pass | pass |
| R02 | restricted | pass | pass | pass |
| U01 | unanswerable | pass | pass | pass |
| U02 | unanswerable | pass | pass | pass |

## Compared with the held-out run (`benchmark-2026-10-31-initial.json`)

The first run on these tasks is the unbiased number. Its failures led to changes, listed below; this run measures the system after them, so it is no longer strictly held out.

| Metric | `vector-rag` first → now | `hybrid-rerank` first → now | `multi-agent` first → now |
| --- | --- | --- | --- |
| Task success | 53% → 53% | 56% → 56% | 78% → 91% |
| Groundedness | 98% → 99% | 100% → 99% | 100% → 100% |
| Recall@5 | 95% → 95% | 100% → 100% | 86% → 100% |

- System: every question that is not small talk now also searches the documents (a deterministic plan rule). The planner had answered B01 from general knowledge (empty plan) and B07/B09 from ticket data instead of the playbook and procedure.
- System: the planner prompt says that policy questions (limits, response times, how long a process step takes) are research questions even when a related column exists.
- System: the data agent can answer that the data has no such measure instead of inventing a proxy (U02 had counted customers without October tickets as churned); the schema description lists what the data does not record.
- System: the analyst must say when the evidence does not answer the question, and an answer that states figures without citing anything is labelled unverified (R02 had invented a contract target in 2 of 5 repeats).
- System (not from this benchmark): rerankers see the passage's heading path, and the prompt-injection defenses of ADR 0006 (redaction, evidence reminder) apply to all runs.
- Scoring: numbers match within rounding ($240,065.60 now matches 240066; 11% still does not match 11.5%). This applies to all three systems.
- Gold labels: X03 no longer requires the denominator the question did not ask for; X07 states its target in the question, so it no longer requires a document citation and moves to the data category.

## Unsupported claims (judge)

**`vector-rag`**: 
- X01: The median Standard-plan onboarding time for September signups did miss the target by about half a day.

**`hybrid-rerank`**: 
- X01: The median onboarding time for September signups exceeded the 3-day target by approximately 0.5 days or more.

**`multi-agent`**: none

## How to read this

- **Task success** needs every expected number and phrase in the answer, a citation of an expected document, a cited query result for data tasks, no restricted facts, and, for restricted or unanswerable tasks, a clear statement that the information is not available.
- The chat systems cannot query the analytics database, so data and cross-source tasks measure what document retrieval alone can do. A good baseline answer to them says the number is not in the documents, which counts as grounded but not as success.
- The multi-agent system retrieves per research step (up to 6 passages each), so it can show the model more passages than the chat systems' single search; Recall@5 uses its first five.
- Groundedness is judged by a stronger model than the one answering, against exactly the passages and tables the system was given. A judge can be wrong; unsupported claims are listed above for review.
- Best task success: `multi-agent`. One run per task at temperature 0.3; expect a few points of run-to-run variation.
