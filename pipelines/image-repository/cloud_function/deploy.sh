#!/bin/bash
# Deploy Image Sync Cloud Function and Cloud Scheduler Job
# Usage: ./deploy.sh [environment]
# Example: ./deploy.sh production

set -e

ENVIRONMENT=${1:-dev}
PROJECT_ID="${GCP_PROJECT_ID:-emailpilot-438321}"
REGION="us-central1"
FUNCTION_NAME="image-sync-pipeline-${ENVIRONMENT}"
SERVICE_ACCOUNT="rag-microservice-user@${PROJECT_ID}.iam.gserviceaccount.com"

echo "=============================================="
echo "Deploying Image Sync Pipeline"
echo "=============================================="
echo "Environment: ${ENVIRONMENT}"
echo "Project: ${PROJECT_ID}"
echo "Region: ${REGION}"
echo "Function: ${FUNCTION_NAME}"
echo "=============================================="

# Check if gcloud is authenticated
if ! gcloud auth list 2>&1 | grep -q 'ACTIVE'; then
    echo "ERROR: Not authenticated with gcloud. Run 'gcloud auth login' first."
    exit 1
fi

# Set project
gcloud config set project ${PROJECT_ID}

# Deploy Cloud Function (Gen 2)
echo ""
echo "Deploying Cloud Function..."
gcloud functions deploy ${FUNCTION_NAME} \
    --gen2 \
    --runtime=python311 \
    --region=${REGION} \
    --source=. \
    --entry-point=sync_images \
    --trigger-http \
    --timeout=540s \
    --memory=2GB \
    --max-instances=1 \
    --service-account=${SERVICE_ACCOUNT} \
    --set-env-vars="GCP_PROJECT_ID=${PROJECT_ID},VERTEX_DATA_STORE_ID=emailpilot-rag_1765205761919,GCP_LOCATION=us,IMAGE_SYNC_INCREMENTAL=true,IMAGE_SYNC_BATCH_SIZE=50" \
    --no-allow-unauthenticated

# Get function URL
FUNCTION_URL=$(gcloud functions describe ${FUNCTION_NAME} --region=${REGION} --format='value(serviceConfig.uri)')

echo ""
echo "Function deployed: ${FUNCTION_URL}"

# Create or update Cloud Scheduler job (daily at 6 AM)
SCHEDULER_NAME="${FUNCTION_NAME}-daily"

echo ""
echo "Creating/updating Cloud Scheduler job..."

# Delete existing job if it exists
gcloud scheduler jobs delete ${SCHEDULER_NAME} \
    --location=${REGION} \
    --quiet 2>/dev/null || true

# Create new scheduler job
gcloud scheduler jobs create http ${SCHEDULER_NAME} \
    --location=${REGION} \
    --schedule="0 6 * * *" \
    --time-zone="America/Los_Angeles" \
    --uri="${FUNCTION_URL}" \
    --http-method=POST \
    --headers="Content-Type=application/json" \
    --message-body='{}' \
    --oidc-service-account-email=${SERVICE_ACCOUNT} \
    --oidc-token-audience="${FUNCTION_URL}" \
    --attempt-deadline=540s \
    --description="Daily image sync from Google Drive to Vertex AI"

echo ""
echo "=============================================="
echo "Deployment Complete!"
echo "=============================================="
echo ""
echo "Cloud Function: ${FUNCTION_URL}"
echo "Scheduler Job: ${SCHEDULER_NAME}"
echo "Schedule: Daily at 6:00 AM Pacific"
echo ""
echo "To trigger manually:"
echo "  curl -X POST ${FUNCTION_URL} \\"
echo "    -H 'Authorization: Bearer \$(gcloud auth print-identity-token)' \\"
echo "    -H 'Content-Type: application/json' \\"
echo "    -d '{}'"
echo ""
echo "To sync a specific client:"
echo "  curl -X POST ${FUNCTION_URL} \\"
echo "    -H 'Authorization: Bearer \$(gcloud auth print-identity-token)' \\"
echo "    -H 'Content-Type: application/json' \\"
echo "    -d '{\"client_id\": \"your-client-slug\"}'"
echo ""
