# Shared settings for the Google Cloud scripts. Override any of them in the environment.
PROJECT_ID="${PROJECT_ID:-helio-assistant-demo}"
REGION="${REGION:-us-central1}"
SERVICE="${SERVICE:-helio-assistant}"
REPO="${REPO:-helio}"
SQL_INSTANCE="${SQL_INSTANCE:-helio-pg}"
SQL_TIER="${SQL_TIER:-db-f1-micro}"   # smallest shared-core tier (~$9/month with 10 GB)
DB_NAME="${DB_NAME:-assistant}"
DB_USER="${DB_USER:-assistant}"
RUN_SA="${RUN_SA:-helio-run}"
# Daily model budget (tokens). 2M tokens of gpt-4.1-mini is roughly $1.
DAILY_TOKEN_BUDGET="${DAILY_TOKEN_BUDGET:-2000000}"
# Model-calling requests per visitor per hour.
RATE_LIMIT_REQUESTS="${RATE_LIMIT_REQUESTS:-30}"

IMAGE="${REGION}-docker.pkg.dev/${PROJECT_ID}/${REPO}/${SERVICE}"
RUN_SA_EMAIL="${RUN_SA}@${PROJECT_ID}.iam.gserviceaccount.com"
SQL_CONNECTION="${PROJECT_ID}:${REGION}:${SQL_INSTANCE}"
