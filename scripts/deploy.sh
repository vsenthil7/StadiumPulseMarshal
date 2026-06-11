#!/usr/bin/env bash
# Build + deploy StadiumPulse Marshal to Cloud Run.
# Usage: PROJECT_ID=my-proj REGION=europe-west2 ./scripts/deploy.sh [TAG]
set -euo pipefail

PROJECT_ID="${PROJECT_ID:?set PROJECT_ID}"
REGION="${REGION:-europe-west2}"
TAG="${1:-$(git rev-parse --short HEAD 2>/dev/null || echo latest)}"
IMAGE="gcr.io/${PROJECT_ID}/stadiumpulse-marshal:${TAG}"
SERVICE="stadiumpulse-marshal"

if [ "${TAG}" = "dryrun" ]; then
  echo "Would deploy to Cloud Run: service=${SERVICE} region=${REGION} image=gcr.io/${PROJECT_ID}/stadiumpulse-marshal:<tag>"
  echo "Secrets bound from Secret Manager: DT_API_TOKEN GOOGLE_API_KEY PAGERDUTY_ROUTING_KEY OPSGENIE_API_KEY JWT_SECRET"
  exit 0
fi

echo ">> Building ${IMAGE}"
docker build -t "${IMAGE}" .
echo ">> Pushing ${IMAGE}"
docker push "${IMAGE}"

echo ">> Deploying ${SERVICE} to Cloud Run (${REGION})"
gcloud run deploy "${SERVICE}" \
  --image "${IMAGE}" \
  --region "${REGION}" \
  --platform managed \
  --allow-unauthenticated \
  --port 8080 \
  --cpu 1 --memory 512Mi \
  --set-env-vars "USE_MOCKS=false,GOOGLE_CLOUD_PROJECT=${PROJECT_ID},GOOGLE_CLOUD_LOCATION=${REGION}" \
  --set-secrets "DT_API_TOKEN=DT_API_TOKEN:latest,GOOGLE_API_KEY=GOOGLE_API_KEY:latest,PAGERDUTY_ROUTING_KEY=PAGERDUTY_ROUTING_KEY:latest,OPSGENIE_API_KEY=OPSGENIE_API_KEY:latest,JWT_SECRET=JWT_SECRET:latest"

echo ">> Deployed ${SERVICE}:${TAG}"
