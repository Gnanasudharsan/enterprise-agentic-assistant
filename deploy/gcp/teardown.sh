#!/usr/bin/env bash
# Stop the costs. Deletes the Cloud Run service and the Cloud SQL instance (its data is
# lost; it is all synthetic and re-seeded on the next deploy). Pass --project to delete
# the whole project instead.
set -euo pipefail
cd "$(dirname "$0")"
source ./config.sh

if [ "${1:-}" = "--project" ]; then
  gcloud projects delete "$PROJECT_ID"
  exit
fi
gcloud run services delete "$SERVICE" --project "$PROJECT_ID" --region "$REGION" --quiet || true
gcloud sql instances delete "$SQL_INSTANCE" --project "$PROJECT_ID" --quiet || true
gcloud secrets delete database-url --project "$PROJECT_ID" --quiet || true
echo "Deleted the service and the database. Images and secrets cost cents; --project removes everything."
