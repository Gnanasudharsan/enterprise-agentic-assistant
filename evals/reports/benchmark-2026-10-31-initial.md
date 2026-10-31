# Benchmark: baseline RAG vs. hybrid + rerank vs. multi-agent — 2026-10-31

32 held-out tasks (`datasets/evaluation/benchmark.jsonl`), asked as a regular employee. Model `gpt-4.1-mini`, embeddings `text-embedding-3-small`, judge `gpt-4.1`. Cost uses $0.40 / $1.60 per 1M input / output tokens and counts every model call (planner, SQL, reranker, analyst); embeddings (~$0.00001 per question) are not counted.

| Metric | `vector-rag` | `hybrid-rerank` | `multi-agent` |
| --- | --- | --- | --- |
| **Task success** | **53%** | **56%** | **78%** |
| Recall@5 (expected documents in the top 5 passages) | 95% | 100% | 86% |
| Evidence recall (expected documents among all passages shown) | 98% | 100% | 86% |
| Citation validity (markers pointing at real evidence) | 100% | 100% | 100% |
| Groundedness (claims supported by the evidence, judge) | 98% | 100% | 100% |
| Fully grounded answers | 94% | 100% | 100% |
| Safety (no restricted facts leaked) | 100% | 100% | 100% |
| Latency p50 / p95 | 1.3 s / 2.0 s | 2.1 s / 2.6 s | 3.1 s / 5.6 s |
| Model calls per task | 1.0 | 2.0 | 3.3 |
| Tokens per task | 1,151 | 2,264 | 3,530 |
| Cost per task | $0.0006 | $0.0011 | $0.0018 |
| Cost per 1,000 tasks | $0.57 | $1.05 | $1.78 |

## Task success by category

| Category | Tasks | `vector-rag` | `hybrid-rerank` | `multi-agent` |
| --- | --- | --- | --- | --- |
| docs | 9 | 100% | 100% | 67% |
| multi-doc | 5 | 80% | 100% | 100% |
| data | 7 | 0% | 0% | 71% |
| cross-source | 7 | 0% | 0% | 71% |
| restricted | 2 | 100% | 100% | 100% |
| unanswerable | 2 | 100% | 100% | 100% |

## Per task

| ID | Category | `vector-rag` | `hybrid-rerank` | `multi-agent` |
| --- | --- | --- | --- | --- |
| B01 | docs | pass | pass | fail: numbers, cites_expected_doc |
| B02 | docs | pass | pass | pass |
| B03 | docs | pass | pass | pass |
| B04 | docs | pass | pass | pass |
| B05 | docs | pass | pass | pass |
| B06 | docs | pass (1 unsupported) | pass | pass |
| B07 | docs | pass | pass | fail: numbers, cites_expected_doc |
| B08 | docs | pass | pass | pass |
| B09 | docs | pass | pass | fail: numbers, cites_expected_doc |
| M01 | multi-doc | pass | pass | pass |
| M02 | multi-doc | pass | pass | pass |
| M03 | multi-doc | pass | pass | pass |
| M04 | multi-doc | pass | pass | pass |
| M05 | multi-doc | fail: numbers | pass | pass |
| D01 | data | fail: numbers, cites_data | fail: numbers, cites_data | pass |
| D02 | data | fail: numbers, cites_data | fail: numbers, cites_data | fail: numbers |
| D03 | data | fail: numbers, cites_data | fail: numbers, cites_data | fail: numbers |
| D04 | data | fail: numbers, cites_data | fail: numbers, cites_data | pass |
| D05 | data | fail: numbers, phrases, cites_data | fail: numbers, phrases, cites_data | pass |
| D06 | data | fail: numbers, cites_data | fail: numbers, cites_data | pass |
| D07 | data | fail: numbers, cites_data | fail: numbers, cites_data | pass |
| X01 | cross-source | fail: numbers, cites_data (1 unsupported) | fail: numbers, cites_data | pass |
| X02 | cross-source | fail: numbers, cites_data | fail: numbers, cites_data | pass |
| X03 | cross-source | fail: numbers, cites_data | fail: numbers, cites_data | fail: numbers |
| X04 | cross-source | fail: numbers, cites_data | fail: numbers, cites_data | pass |
| X05 | cross-source | fail: cites_data | fail: cites_data | pass |
| X06 | cross-source | fail: cites_data | fail: cites_data | pass |
| X07 | cross-source | fail: numbers, cites_data | fail: numbers, cites_expected_doc, cites_data | fail: cites_expected_doc |
| R01 | restricted | pass | pass | pass |
| R02 | restricted | pass | pass | pass |
| U01 | unanswerable | pass | pass | pass |
| U02 | unanswerable | pass | pass | pass |

## Unsupported claims (judge)

**`vector-rag`**: 
- B06: This is part of the quarterly review process managers conduct for their team's access to Confidential and Restricted systems.
- X01: The median Standard-plan onboarding time for September signups did miss the target, but only by less than 0.1 days.

**`hybrid-rerank`**: none

**`multi-agent`**: none

## How to read this

- **Task success** needs every expected number and phrase in the answer, a citation of an expected document, a cited query result for data tasks, no restricted facts, and, for restricted or unanswerable tasks, a clear statement that the information is not available.
- The chat systems cannot query the analytics database, so data and cross-source tasks measure what document retrieval alone can do. A good baseline answer to them says the number is not in the documents, which counts as grounded but not as success.
- The multi-agent system retrieves per research step (up to 6 passages each), so it can show the model more passages than the chat systems' single search; Recall@5 uses its first five.
- Groundedness is judged by a stronger model than the one answering, against exactly the passages and tables the system was given. A judge can be wrong; unsupported claims are listed above for review.
- Best task success: `multi-agent`. One run per task at temperature 0.3; expect a few points of run-to-run variation.
