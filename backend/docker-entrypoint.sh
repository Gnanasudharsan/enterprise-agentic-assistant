#!/bin/sh
set -e

# Apply database migrations before starting the server.
alembic upgrade head

# Load the demo knowledge base and analytics data. Idempotent: unchanged documents are
# skipped, and analytics data is only loaded into an empty schema.
if [ "${SEED_DOCUMENTS_ON_STARTUP:-false}" = "true" ]; then
    python -m app.rag.cli ingest "${DOCUMENTS_DIR:-/app/datasets/documents}"
    python -m app.analytics.cli seed
fi

exec "$@"
