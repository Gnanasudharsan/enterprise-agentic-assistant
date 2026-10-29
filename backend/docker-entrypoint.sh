#!/bin/sh
set -e

# Apply database migrations before starting the server.
alembic upgrade head

# Load the demo knowledge base. Idempotent: unchanged documents are skipped.
if [ "${SEED_DOCUMENTS_ON_STARTUP:-false}" = "true" ]; then
    python -m app.rag.cli ingest "${DOCUMENTS_DIR:-/app/datasets/documents}"
fi

exec "$@"
