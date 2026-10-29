# Contributing

## Workflow

1. Open or pick an issue (use the templates).
2. Create a branch: `feat/<short-name>`, `fix/<short-name>`, or `docs/<short-name>`.
3. Keep PRs small and focused on one roadmap item.
4. Make sure tests pass and add tests for new behavior.
5. Update `CHANGELOG.md` under **[Unreleased]** and tick the item in `docs/ROADMAP.md` once it's verified.

## Commit messages

Use [Conventional Commits](https://www.conventionalcommits.org/):

```
feat(rag): add reciprocal rank fusion for hybrid retrieval
fix(api): return 422 on empty prompt
docs: update roadmap for phase 1
test(data-agent): reject non-SELECT statements
```

## Code standards (from Phase 1)

- Python: `ruff` for lint and format, type hints everywhere, `pytest` for tests.
- Never commit secrets. Configuration goes through `.env` (see `.env.example`).
- LLM calls are mocked in unit tests. Evaluations that hit real models live in `evals/`.

## Honesty rule

Only mark a roadmap item done, or publish a metric, after it has been **implemented and verified** by a test or a reproducible evaluation.
