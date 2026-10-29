# Changelog

All notable changes to this project are documented here.
Format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/); versions follow [SemVer](https://semver.org/).

## [Unreleased]

## [0.1.0] - 2026-10-29 (Phase 1: Foundation)

### Added
- FastAPI backend with typed settings, `/health`, and `/health/ready`.
- Provider-agnostic LLM client (OpenAI-compatible + offline `fake` provider).
- `POST /api/v1/chat` with prompt validation and 502/504 error mapping.
- PostgreSQL + pgvector, async SQLAlchemy, Alembic migration `0001` (`chat_runs`).
- Persistence of every chat run (status, latency, token usage).
- Backend Dockerfile and `docker-compose.yml` (zero-config startup).
- React + TypeScript frontend skeleton.
- GitHub Actions CI: lint, unit, integration (pgvector), Docker smoke test, frontend build.

### Fixed
- Import `httpx2`, which `openai>=3` depends on, so the production image starts.

## [0.0.1] - 2026-10-29 (Phase 0: Planning)

### Added
- Phase 0: project README, architecture document, roadmap, and ADR 0001.
- Repository conventions: MIT license, `.gitignore`, `.env.example`, `.editorconfig`.
- Contributing guide, security policy, and GitHub issue/PR templates.
