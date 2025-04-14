#!/bin/bash

# Exit immediately if a command exits with a non-zero status.
set -e
# Treat unset variables as an error when substituting.
set -u
# Pipelines return the exit status of the last command to exit with a non-zero status,
# or zero if no command exited with a non-zero status.
set -o pipefail

# --- Configuration - CHANGE THESE VALUES ---
# It's recommended to set PROJECT_ID explicitly, although the script tries to fetch it.
# Ensure DB_PASSWORD is set to a strong value before running.
export PROJECT_ID="${PROJECT_ID:-$(gcloud config get-value project)}" # Use existing env var or fetch
export REGION="asia-southeast1"

# Cloud SQL
export SQL_INSTANCE_NAME="videogen-postgres"
export DB_NAME="videogen_db"
export DB_USER="videogen_user"
export DB_PASSWORD="videogen_pw" # <<< CHANGE THIS TO A STRONG PASSWORD

# GCS
export GCS_BUCKET_NAME="matta-videogen-storage"

# Secret Manager
export DB_PASS_SECRET_NAME="videogen-db-password"
export VEO2_API_KEY_SECRET_NAME="videogen-veo2-api-key"

# Cloud Run
export CLOUD_RUN_SERVICE_NAME="videogen-backend-api"

# Pub/Sub
export PUB_SUB_TOPIC_ID="approved-submissions"
export QUEUE_ID="videogen-queue"

# Cloud Function
export CLOUD_FUNCTION_NAME="videogen-worker"

# Service account
export SA_NAME="videogen-sa"

# VEO2 API Key
export VEO2_API_KEY="veo2_api_key"
# --- End Configuration ---

# --- Derived Variables ---
export SA_EMAIL="${SA_NAME}@${PROJECT_ID}.iam.gserviceaccount.com"
# ---

# --- Helper Functions ---

# Function to print messages
log() {
  echo "--------------------------------------------------"
  echo "$1"
  echo "--------------------------------------------------"
}

# Function to check for command existence
check_command() {
  if ! command -v "$1" &> /dev/null; then
    echo "Error: command '$1' not found. Please install it." >&2
    exit 1
  fi
}

# --- Main Script ---

log "Starting GCP Video Generation Infrastructure Deployment"

# --- Prerequisites Check ---
log "Checking prerequisites..."
check_command "gcloud"

if [ -z "${PROJECT_ID}" ]; then
    echo "Error: PROJECT_ID is not set. Please configure it at the top of the script or ensure 'gcloud config get-value project' works." >&2
    exit 1
fi

if [ -z "${DB_PASSWORD}" ]; then
    echo "Error: DB_PASSWORD is not set. Please configure it at the top of the script." >&2
    exit 1
fi

if [ -z "${VEO2_API_KEY}" ]; then
    echo "Error: VEO2_API_KEY is not set. Please configure it at the top of the script." >&2
    exit 1
fi

if [ ! -f "./env.yaml" ]; then
    echo "Warning: ./env.yaml file not found. Cloud Run and Cloud Functions deployments might fail if they require it." >&2
    # Consider adding 'exit 1' here if env.yaml is strictly required for deployment to succeed.
fi

echo "Using Project ID: ${PROJECT_ID}"
echo "Using Region: ${REGION}"
echo "Service Account Email: ${SA_EMAIL}"
echo "Prerequisites seem satisfied."

# --- Enable APIs ---
log "Enabling necessary GCP APIs..."
gcloud services enable \
  sqladmin.googleapis.com \
  secretmanager.googleapis.com \
  run.googleapis.com \
  cloudbuild.googleapis.com \
  pubsub.googleapis.com \
  cloudfunctions.googleapis.com \
  iam.googleapis.com \
  artifactregistry.googleapis.com \
  cloudresourcemanager.googleapis.com \
  eventarc.googleapis.com \
  cloudtasks.googleapis.com
  --project="${PROJECT_ID}"
echo "APIs enabled."

# --- Create GCS Bucket ---
log "Creating GCS bucket ${GCS_BUCKET_NAME}..."
# Use || true to prevent script exit if bucket already exists
if ! gsutil ls -b "gs://${GCS_BUCKET_NAME}" &> /dev/null; then
  gsutil mb -p "${PROJECT_ID}" -l "${REGION}" "gs://${GCS_BUCKET_NAME}"
  echo "GCS bucket ${GCS_BUCKET_NAME} created."
else
  echo "GCS bucket ${GCS_BUCKET_NAME} already exists."
fi

# --- Create Cloud SQL Instance ---
log "Creating Cloud SQL instance ${SQL_INSTANCE_NAME}..."
# Check if instance exists first to avoid long wait on 'create' if it already exists
if ! gcloud sql instances describe "${SQL_INSTANCE_NAME}" --project="${PROJECT_ID}" &> /dev/null; then
  gcloud sql instances create "${SQL_INSTANCE_NAME}" \
    --database-version=POSTGRES_17 \
    --tier=db-f1-micro \
    --region="${REGION}" \
    --edition=ENTERPRISE \
    --project="${PROJECT_ID}"
  echo "Cloud SQL instance creation initiated. This may take several minutes."
  # Note: We are not waiting for the instance to be fully RUNNABLE here,
  # subsequent steps might fail if they depend on it immediately.
  # However, `gcloud run deploy` often handles waiting.
else
  echo "Cloud SQL instance ${SQL_INSTANCE_NAME} already exists."
fi

log "Creating database ${DB_NAME}..."
# Use || true to prevent script exit if db already exists
gcloud sql databases create "${DB_NAME}" --instance="${SQL_INSTANCE_NAME}" --project="${PROJECT_ID}" --quiet || true
echo "Database ${DB_NAME} ensured."

log "Creating database user ${DB_USER}..."
# Check if user exists. If so, update password. If not, create.
if gcloud sql users list --instance="${SQL_INSTANCE_NAME}" --project="${PROJECT_ID}" --format="value(name)" | grep -q "^${DB_USER}$"; then
  echo "Database user ${DB_USER} already exists. Setting password..."
  gcloud sql users set-password "${DB_USER}" \
    --instance="${SQL_INSTANCE_NAME}" \
    --password="${DB_PASSWORD}" \
    --project="${PROJECT_ID}" \
    --host=% # Use % for any host, adjust if needed
else
  echo "Creating database user ${DB_USER}..."
  gcloud sql users create "${DB_USER}" \
    --instance="${SQL_INSTANCE_NAME}" \
    --password="${DB_PASSWORD}" \
    --project="${PROJECT_ID}" \
    --host=% # Use % for any host, adjust if needed
fi
echo "Database user ${DB_USER} ensured."


log "Fetching instance connection name..."
# This might fail if the instance isn't ready yet after creation.
# Retry logic could be added here if needed.
export INSTANCE_CONNECTION_NAME=$(gcloud sql instances describe "${SQL_INSTANCE_NAME}" --project="${PROJECT_ID}" --format='value(connectionName)')
if [ -z "${INSTANCE_CONNECTION_NAME}" ]; then
    echo "Error: Failed to get INSTANCE_CONNECTION_NAME. Is the SQL instance ready?" >&2
    exit 1
fi
echo "Instance Connection Name: ${INSTANCE_CONNECTION_NAME}"
echo "Important: Ensure DB_INSTANCE_CONNECTION_NAME in env.yaml matches this value if your application code requires it."


# --- Create Secrets ---
log "Creating secret ${DB_PASS_SECRET_NAME} in Secret Manager..."
# Use || true to prevent script exit if secret already exists
gcloud secrets create "${DB_PASS_SECRET_NAME}" \
    --replication-policy=automatic \
    --project="${PROJECT_ID}" \
    --quiet || true
echo "Secret ${DB_PASS_SECRET_NAME} ensured."

log "Creating secret ${VEO2_API_KEY_SECRET_NAME} in Secret Manager..."
# Use || true to prevent script exit if secret already exists
gcloud secrets create "${VEO2_API_KEY_SECRET_NAME}" \
    --replication-policy=automatic \
    --project="${PROJECT_ID}" \
    --quiet || true
echo "Secret ${VEO2_API_KEY_SECRET_NAME} ensured."

log "Adding database password as secret version..."
# Add the password to the secret
echo -n "${DB_PASSWORD}" | gcloud secrets versions add "${DB_PASS_SECRET_NAME}" --data-file=- --project="${PROJECT_ID}"

# Clear the password variable from the environment immediately after use
unset DB_PASSWORD
echo "Password stored in Secret Manager and variable unset."

log "Adding Veo2 API key as secret version..."
# Add the password to the secret
echo -n "${VEO2_API_KEY}" | gcloud secrets versions add "${VEO2_API_KEY_SECRET_NAME}" --data-file=- --project="${PROJECT_ID}"

# Clear the password variable from the environment immediately after use
unset VEO2_API_KEY
echo "Password stored in Secret Manager and variable unset."


# --- Create Service Account ---
log "Creating Service Account ${SA_NAME}..."
# Use || true to prevent script exit if SA already exists
gcloud iam service-accounts create "${SA_NAME}" \
  --display-name="Video Generator Service Account" \
  --project="${PROJECT_ID}" \
  --quiet || true
echo "Service Account ${SA_EMAIL} ensured."


# --- Grant IAM Permissions ---
log "Granting IAM permissions to ${SA_EMAIL}..."

# Grant Cloud SQL Client role
gcloud projects add-iam-policy-binding "${PROJECT_ID}" \
  --member="serviceAccount:${SA_EMAIL}" \
  --role="roles/cloudsql.client" \
  --condition=None --quiet

# Grant Secret Accessor role for the specific secret
gcloud secrets add-iam-policy-binding "${DB_PASS_SECRET_NAME}" \
  --member="serviceAccount:${SA_EMAIL}" \
  --role="roles/secretmanager.secretAccessor" \
  --project="${PROJECT_ID}" \
  --condition=None --quiet

gcloud secrets add-iam-policy-binding "${VEO2_API_KEY_SECRET_NAME}" \
  --member="serviceAccount:${SA_EMAIL}" \
  --role="roles/secretmanager.secretAccessor" \
  --project="${PROJECT_ID}" \
  --condition=None --quiet

# Grant Storage Object User role
gcloud projects add-iam-policy-binding "${PROJECT_ID}" \
  --member="serviceAccount:${SA_EMAIL}" \
  --role="roles/storage.objectUser" \
  --condition=None --quiet

# Grant Cloud Run Invoker role
gcloud projects add-iam-policy-binding "${PROJECT_ID}" \
  --member="serviceAccount:${SA_EMAIL}" \
  --role="roles/run.invoker" \
  --condition=None --quiet

# Grant Service Account Token Creator role (often needed for SA impersonation or inter-service auth)
gcloud iam service-accounts add-iam-policy-binding \
    "${SA_EMAIL}" \
    --member="serviceAccount:${SA_EMAIL}" \
    --role="roles/iam.serviceAccountTokenCreator" \
    --project="${PROJECT_ID}" \
    --quiet


echo "Core IAM permissions granted."


# --- Create Cloud Tasks queue ---
gcloud tasks queues create "${QUEUE_ID}" --project="${PROJECT_ID}" --location="${REGION}" --quiet || true
echo "Cloud Tasks queue ${QUEUE_ID} ensured."


# --- Deploy Cloud Run Service (Backend API) ---
log "Deploying Cloud Run service ${CLOUD_RUN_SERVICE_NAME}..."
# Deployment implicitly uses Cloud Build
gcloud run deploy "${CLOUD_RUN_SERVICE_NAME}" \
  --source=./backend \
  --region="${REGION}" \
  --service-account="${SA_EMAIL}" \
  --allow-unauthenticated `# Adjust if authentication is needed` \
  --add-cloudsql-instances="${INSTANCE_CONNECTION_NAME}" \
  --set-secrets="DB_PASS=${DB_PASS_SECRET_NAME}:latest" \
  --env-vars-file=env.yaml \
  --memory=1Gi \
  --cpu=1 \
  --min-instances=1 \
  --max-instances=10 \
  --project="${PROJECT_ID}" \
  --quiet # Add --quiet for less verbose output during deployment

BACKEND_URL=$(gcloud run services describe "${CLOUD_RUN_SERVICE_NAME}" --region="${REGION}" --project="${PROJECT_ID}" --format='value(status.url)')
echo "Cloud Run service deployed. URL: ${BACKEND_URL}"


log "Deployment script finished successfully!"
echo "Backend API URL: ${BACKEND_URL}"


# --- Deploy Cloud Run Service (Streamlit Submission) ---
log "Deploying Cloud Run service streamlit-submission..."
# Deployment implicitly uses Cloud Build
gcloud run deploy streamlit-submission \
  --source=./streamlit_submission \
  --region="${REGION}" \
  --service-account="${SA_EMAIL}" \
  --allow-unauthenticated `# Adjust if authentication is needed` \
  --set-env-vars="BACKEND_API_URL=${BACKEND_URL}" \
  --port=8501 \
  --memory=1Gi \
  --cpu=1 \
  --min-instances=1 \
  --max-instances=10 \
  --project="${PROJECT_ID}" \
  --quiet # Add --quiet for less verbose output during deployment

SUBMISSION_URL=$(gcloud run services describe streamlit-submission --region="${REGION}" --project="${PROJECT_ID}" --format='value(status.url)')
echo "Cloud Run service deployed. URL: ${SUBMISSION_URL}"

# --- Deploy Cloud Run Service (Streamlit Moderation) ---
log "Deploying Cloud Run service streamlit-moderation..."
# Deployment implicitly uses Cloud Build
gcloud run deploy streamlit-moderation \
  --source=./streamlit_moderation \
  --region="${REGION}" \
  --service-account="${SA_EMAIL}" \
  --allow-unauthenticated `# Adjust if authentication is needed` \
  --set-env-vars="BACKEND_API_URL=${BACKEND_URL}" \
  --port=8501 \
  --memory=1Gi \
  --cpu=1 \
  --min-instances=1 \
  --max-instances=10 \
  --project="${PROJECT_ID}" \
  --quiet # Add --quiet for less verbose output during deployment

MODERATION_URL=$(gcloud run services describe streamlit-moderation --region="${REGION}" --project="${PROJECT_ID}" --format='value(status.url)')
echo "Cloud Run service deployed. URL: ${MODERATION_URL}"