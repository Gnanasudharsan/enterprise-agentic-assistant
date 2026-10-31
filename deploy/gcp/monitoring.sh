#!/usr/bin/env bash
# Uptime check on /health/ready, plus an email alert when it fails (optional).
#
#   ALERT_EMAIL=you@example.com ./deploy/gcp/monitoring.sh
set -euo pipefail
cd "$(dirname "$0")"
source ./config.sh

URL="$(gcloud run services describe "$SERVICE" --project "$PROJECT_ID" --region "$REGION" --format 'value(status.url)')"
HOST="${URL#https://}"
gcloud monitoring uptime create "${SERVICE}-ready" --project "$PROJECT_ID" \
  --resource-type uptime-url --resource-labels "host=${HOST},project_id=${PROJECT_ID}" \
  --path /health/ready --protocol https --period 15 --timeout 10

if [ -n "${ALERT_EMAIL:-}" ]; then
  CHANNEL="$(gcloud beta monitoring channels create --project "$PROJECT_ID" \
    --display-name "Helio alerts" --type email --channel-labels "email_address=${ALERT_EMAIL}" \
    --format 'value(name)')"
  POLICY="$(mktemp)"
  cat > "$POLICY" <<JSON
{
  "displayName": "${SERVICE} is down",
  "combiner": "OR",
  "conditions": [{
    "displayName": "Uptime check failing",
    "conditionThreshold": {
      "filter": "metric.type=\"monitoring.googleapis.com/uptime_check/check_passed\" AND resource.type=\"uptime_url\" AND resource.label.host=\"${HOST}\"",
      "comparison": "COMPARISON_GT", "thresholdValue": 1, "duration": "300s",
      "aggregations": [{"alignmentPeriod": "1200s", "perSeriesAligner": "ALIGN_NEXT_OLDER",
                        "crossSeriesReducer": "REDUCE_COUNT_FALSE", "groupByFields": ["resource.label.*"]}],
      "trigger": {"count": 1}
    }
  }],
  "notificationChannels": ["${CHANNEL}"]
}
JSON
  gcloud alpha monitoring policies create --project "$PROJECT_ID" --policy-from-file "$POLICY"
  rm -f "$POLICY"
fi
