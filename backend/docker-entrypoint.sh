#!/bin/sh
set -e

# Apply database migrations before starting the server.
alembic upgrade head

exec "$@"
