# ADR 0005: Evaluation protocol — held-out benchmark, three systems, judged groundedness, metered cost

- **Status:** Accepted
- **Date:** 2026-10-31

## Context

Phases 2–4 were measured on gold sets written while the system was being built (37 retrieval questions, 10 agent tasks). Those are regression suites: they show that changes don't break known cases, but they overstate quality, because failures on them were fixed. Phase 5 has to say how much the multi-agent system actually adds over plain RAG, and at what latency and cost.

## Decision

1. **A held-out benchmark, written after the system was built.** `datasets/evaluation/benchmark.jsonl` has 32 tasks: single-document (9), multi-document (5), data (7), cross-source (7), restricted (2), and unanswerable (2). Expected numbers come from SQL over the deterministic analytics data, and expected documents from the corpus.
   - The **first run is the reported held-out result** ([initial report](../../evals/reports/benchmark-2026-10-31-initial.md)).
   - Changes made because of it are listed in the next report, which shows first-run and current numbers side by side and says it is no longer strictly held out.
2. **Three systems, same API, same tasks.**
   - `vector-rag`: `/chat` with `retrieval_mode=vector`, no reranking.
   - `hybrid-rerank`: `/chat` with hybrid retrieval and the LLM reranker.
   - `multi-agent`: `/agent/run`.

   The request options exist so the baselines run through the production code path, not a re-implementation.
3. **Task success is checked deterministically.** Every expected number (within rounding: 0.5% of the value, at least 0.05) and phrase must be present. A task must also cite an expected document, data tasks must cite a query result, nothing restricted may appear, and restricted or unanswerable tasks must decline.
4. **Groundedness is judged by a stronger model** (`gpt-4.1` judging `gpt-4.1-mini`). The judge sees exactly the passages and tables the system was given. It lists each company-specific claim, marks it as supported or not, and reports whether the answer declines. Unsupported claims are printed in the report for human review.
5. **Cost is metered, not estimated.** A `MeteredLLM` wrapper counts tokens for every model call in a request (planner, SQL repair, reranker, analyst, action draft) through a context variable shared by concurrent graph nodes. Usage is returned by `/chat` and `/agent/run` and stored on `agent_runs`. The report prices it with list prices. Embeddings are excluded (about $0.00001 per question).
6. **Security has its own suite** (`evals/security_eval.py`). It runs direct and indirect prompt injections and API-level unauthorized-action attempts against the live system. Integrity is checked before and after: analytics row counts and executed issues. See ADR 0006.

## Alternatives considered

- **RAGAS / DeepEval metrics.** Their faithfulness metrics are LLM judges as well. A short, explicit prompt that we can read and that outputs the unsupported claims is easier to audit, and it adds no dependency.
- **Exact-match answers.** Too brittle for free text. Deterministic number and phrase checks plus a judge give both precision and coverage.
- **Mocking the baselines in-process.** That would compare against code the product doesn't run.

## Consequences

- With 32 tasks and one run per system, a single task is about 3 points. Differences of a few points are noise; the category breakdown carries the signal.
- The tasks share an author with the corpus, and the corpus is small (12 documents), so absolute numbers remain optimistic. The *relative* comparison is what this benchmark supports.
- One run per task hides flaky behaviour. When a task flips between runs, it is repeated 5 to 10 times before and after a fix. For example, R02 invented a figure in 2 of 5 repeats and U02 invented a churn proxy in 5 of 5; both went to 10 of 10 after the fixes.
- A failed check is only as good as its gold label. Two labels were wrong in the first run (X03, X07) and were corrected openly in the report.
