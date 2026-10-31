#!/usr/bin/env bash
# One-time infrastructure for the Cloud Run deployment. Idempotent: rerunning skips what
# exists. Creates billable resources (mainly the Cloud SQL instance, ~$9/month).
#
#   BILLING_ACCOUNT=XXXXXX-XXXXXX-XXXXXX ./deploy/gcp/setup.sh
#
# Secrets come from the environment and go straight into Secret Manager (never to disk):
#   OPENAI_API_KEY  required
#   ACCESS_CODE     optional; a random code is generated and printed once if unset
set -euo pipefail
cd "$(dirname "$0")"
source ./config.sh

: "${OPENAI_API_KEY:?Set OPENAI_API_KEY in your shell first}"
export CLOUDSDK_CORE_DISABLE_PROMPTS=1  # never stop at a question
exists() { "$@" >/dev/null 2>&1; }
retry() {  # newly enabled APIs take a minute or two to propagate
  for i in 1 2 3 4 5 6 7 8 9 10; do "$@" && return; echo "   (retrying in 20 s)"; sleep 20; done
  "$@"
}
secret() {  # name, value on stdin
  exists gcloud secrets describe "$1" --project "$PROJECT_ID" ||
    gcloud secrets create "$1" --project "$PROJECT_ID" --replication-policy=automatic
  gcloud secrets versions add "$1" --project "$PROJECT_ID" --data-file=- >/dev/null
  gcloud secrets add-iam-policy-binding "$1" --project "$PROJECT_ID" \
    --member "serviceAccount:${RUN_SA_EMAIL}" --role roles/secretmanager.secretAccessor >/dev/null
}

echo "== Project ${PROJECT_ID}"
if ! exists gcloud projects describe "$PROJECT_ID"; then
  : "${BILLING_ACCOUNT:?Set BILLING_ACCOUNT (gcloud billing accounts list) to create the project}"
  gcloud projects create "$PROJECT_ID" --name "Helio Assistant demo"
  gcloud billing projects link "$PROJECT_ID" --billing-account "$BILLING_ACCOUNT"
fi
gcloud services enable --project "$PROJECT_ID" run.googleapis.com sqladmin.googleapis.com \
  artifactregistry.googleapis.com cloudbuild.googleapis.com secretmanager.googleapis.com \
  cloudtrace.googleapis.com monitoring.googleapis.com logging.googleapis.com iam.googleapis.com

echo "== Artifact Registry"
exists gcloud artifacts repositories describe "$REPO" --project "$PROJECT_ID" --location "$REGION" ||
  retry gcloud artifacts repositories create "$REPO" --project "$PROJECT_ID" --location "$REGION" \
    --repository-format docker --description "Helio Assistant images"

echo "== Service account (least privilege: SQL client, its own secrets, traces, logs, metrics)"
exists gcloud iam service-accounts describe "$RUN_SA_EMAIL" --project "$PROJECT_ID" ||
  gcloud iam service-accounts create "$RUN_SA" --project "$PROJECT_ID" --display-name "Helio Assistant runtime"
for role in roles/cloudsql.client roles/cloudtrace.agent roles/logging.logWriter roles/monitoring.metricWriter; do
  gcloud projects add-iam-policy-binding "$PROJECT_ID" --member "serviceAccount:${RUN_SA_EMAIL}" \
    --role "$role" --condition=None >/dev/null
done

echo "== Cloud SQL (PostgreSQL 16 + pgvector) — takes several minutes the first time"
if ! exists gcloud sql instances describe "$SQL_INSTANCE" --project "$PROJECT_ID"; then
  retry gcloud sql instances create "$SQL_INSTANCE" --project "$PROJECT_ID" --region "$REGION" \
    --database-version POSTGRES_16 --edition ENTERPRISE --tier "$SQL_TIER" \
    --storage-size 10 --storage-type SSD --availability-type zonal \
    --backup-start-time 03:00 --retained-backups-count 3
fi
exists gcloud sql databases describe "$DB_NAME" --instance "$SQL_INSTANCE" --project "$PROJECT_ID" ||
  gcloud sql databases create "$DB_NAME" --instance "$SQL_INSTANCE" --project "$PROJECT_ID"
if ! exists gcloud secrets describe database-url --project "$PROJECT_ID"; then
  # A new random password, set on the user and stored only in Secret Manager.
  DB_PASSWORD="$(openssl rand -hex 24)"
  if exists gcloud sql users describe "$DB_USER" --instance "$SQL_INSTANCE" --project "$PROJECT_ID"; then
    gcloud sql users set-password "$DB_USER" --instance "$SQL_INSTANCE" --project "$PROJECT_ID" --password "$DB_PASSWORD"
  else
    gcloud sql users create "$DB_USER" --instance "$SQL_INSTANCE" --project "$PROJECT_ID" --password "$DB_PASSWORD"
  fi
  # Cloud Run mounts the instance as a Unix socket under /cloudsql.
  printf '%s' "postgresql+asyncpg://${DB_USER}:${DB_PASSWORD}@/${DB_NAME}?host=/cloudsql/${SQL_CONNECTION}" | secret database-url
  unset DB_PASSWORD
fi

echo "== Secrets"
printf '%s' "$OPENAI_API_KEY" | secret openai-api-key
if ! exists gcloud secrets describe access-code --project "$PROJECT_ID"; then
  CODE="${ACCESS_CODE:-$(openssl rand -base64 12 | tr -dc 'A-Za-z0-9' | head -c 12)}"
  printf '%s' "$CODE" | secret access-code
  [ -z "${ACCESS_CODE:-}" ] && echo "   Generated access code (shown once; read it later with: gcloud secrets versions access latest --secret access-code): $CODE"
  unset CODE
fi

echo "Done. Next: ./deploy/gcp/deploy.sh"
