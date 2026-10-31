#!/usr/bin/env bash
# Build the production image with Cloud Build and deploy it to Cloud Run.
#
#   ./deploy/gcp/deploy.sh
set -euo pipefail
cd "$(dirname "$0")/../.."
source deploy/gcp/config.sh

TAG="$(git rev-parse --short HEAD)$(git diff --quiet || echo -dirty)"
echo "== Building ${IMAGE}:${TAG}"
gcloud builds submit --project "$PROJECT_ID" --region "$REGION" --tag "${IMAGE}:${TAG}" .

echo "== Deploying ${SERVICE}"
# One instance at most: the rate limiter and the daily budget count in memory, and the
# smallest Cloud SQL tier allows few connections. Scales to zero when idle.
gcloud run deploy "$SERVICE" --project "$PROJECT_ID" --region "$REGION" \
  --image "${IMAGE}:${TAG}" --service-account "$RUN_SA_EMAIL" \
  --add-cloudsql-instances "$SQL_CONNECTION" \
  --set-secrets "OPENAI_API_KEY=openai-api-key:latest,ACCESS_CODE=access-code:latest,DATABASE_URL=database-url:latest" \
  --set-env-vars "^|^GOOGLE_CLOUD_PROJECT=${PROJECT_ID}|TRACING=gcp|RERANKER=llm|SEED_DOCUMENTS_ON_STARTUP=true|DAILY_TOKEN_BUDGET=${DAILY_TOKEN_BUDGET}|RATE_LIMIT_REQUESTS=${RATE_LIMIT_REQUESTS}|RATE_LIMIT_WINDOW_SECONDS=3600|FORWARDED_HOPS=1|DB_POOL_SIZE=3" \
  --min-instances 0 --max-instances 1 --concurrency 40 \
  --cpu 1 --memory 1Gi --cpu-boost --timeout 300 \
  --allow-unauthenticated

URL="$(gcloud run services describe "$SERVICE" --project "$PROJECT_ID" --region "$REGION" --format 'value(status.url)')"
echo "== Smoke test ${URL}"
curl -sf "${URL}/health" && echo
curl -sf "${URL}/health/ready" && echo
test "$(curl -s -o /dev/null -w '%{http_code}' "${URL}/api/v1/info")" = 401 && echo "API requires the access code: ok"
echo "Deployed: ${URL}"
