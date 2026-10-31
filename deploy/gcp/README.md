# Deploying to Google Cloud Run

One Cloud Run service runs the API and serves the built frontend; Cloud SQL (PostgreSQL 16 + pgvector) holds documents, analytics data, checkpoints, and the audit log. Secrets live in Secret Manager. Design and trade-offs: [ADR 0007](../../docs/adr/0007-cloud-run-deployment.md).

## What it costs

| Resource | Setting | Approximate cost |
| --- | --- | --- |
| Cloud SQL | `db-f1-micro`, 10 GB SSD, zonal, 3 backups | ~$9–11 / month (always on) |
| Cloud Run | 1 vCPU, 1 GiB, min 0 / max 1 instance | usually within the free tier for a demo |
| Artifact Registry, Secret Manager, Cloud Build | a few images, 3 secrets | cents |
| OpenAI | capped by `DAILY_TOKEN_BUDGET` (default 2M tokens ≈ $1 / day) | ≤ ~$30 / month at the cap |

Set a monthly spend limit on the OpenAI project as a second cap. `./teardown.sh` removes the service and the database (the main cost); `./teardown.sh --project` deletes everything.

## Steps

You need `gcloud` logged in (`gcloud auth login`), a billing account (`gcloud billing accounts list`), and your OpenAI key in the shell.

```bash
BILLING_ACCOUNT=XXXXXX-XXXXXX-XXXXXX ./deploy/gcp/setup.sh
```

This creates the project (`PROJECT_ID`, default `helio-assistant-demo`), enables the APIs, and sets up:
- an image repository;
- a runtime service account (Cloud SQL client, its own secrets, traces, logs, metrics);
- the Cloud SQL instance, its database, and a user with a random password;
- three secrets: the model key, the access code, and the database URL.

If `ACCESS_CODE` is unset, it generates the access code and prints it once.

```bash
./deploy/gcp/deploy.sh
```

This builds the image with Cloud Build, deploys it, and checks that `/health` and `/health/ready` respond and that the API refuses requests without the code. The first start runs the migrations and seeds the corpus and analytics data, which takes about a minute.

```bash
ALERT_EMAIL=you@example.com ./deploy/gcp/monitoring.sh
```

This adds an uptime check on `/health/ready`, plus an email alert if you set `ALERT_EMAIL`.

Read the access code again later:

```bash
gcloud secrets versions access latest --secret access-code --project helio-assistant-demo
```

## Notes

- **One instance on purpose.** The rate limiter and the daily budget count in memory, and the smallest Cloud SQL tier allows about 25 connections.
- **The local issue tracker resets.** Its SQLite file lives on the container's disk, so drafted and approved issues reset when the instance is replaced. The audit log in Cloud SQL keeps everything. For lasting issues, deploy with `TRACKER_BACKEND=github`, using a fine-grained token stored as a secret.
- **Traces and logs.** Traces go to Cloud Trace (`TRACING=gcp`). Logs are JSON lines linked to their trace in Cloud Logging.
