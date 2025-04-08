# AI Video Generation Application

This repository contains the Streamlit frontend, backend API and worker function for an AI video generation application, designed to be deployed on Google Cloud Platform (GCP).

## Architecture

The application utilizes the following GCP services:

* **Cloud Run:** Hosts the two Streamlit services and the backend API service.
* **Cloud SQL (PostgreSQL):** Provides the relational database for storing application data.
* **Secret Manager:** Securely stores the database password.
* **Pub/Sub:** Used as a message queue to trigger the video generation worker when a submission is approved.
* **Cloud Run Functions:** Hosts the video generation worker, triggered by Pub/Sub messages.
* **IAM:** Manages permissions using a dedicated Service Account.
* **Cloud Build:** Used implicitly by Cloud Run and Cloud Run Functions for building container images from source.

## Prerequisites

1.  **Google Cloud SDK:** Ensure you have `gcloud` [installed and configured](https://cloud.google.com/sdk/docs/install).
2.  **GCP Project:** Have a Google Cloud project created and selected in your `gcloud` configuration (`gcloud config set project YOUR_PROJECT_ID`).
3.  **Permissions:** Ensure the user or service account running the deployment script has sufficient permissions to create and manage the resources listed above (e.g., Project Owner, Editor, or specific roles like Cloud SQL Admin, Cloud Run Admin, Pub/Sub Admin, Cloud Functions Developer, Service Account Admin, Secret Manager Admin, IAM Role Administrator).
4.  **Environment Configuration (`env.yaml`):** The deployment script references an `env.yaml` file for setting environment variables for both the Cloud Run service and the Cloud Function. Make sure the values specificed in `env.yaml` is correct and consistent with the values specified in `deploy.sh`.

## Configuration

Before running the deployment script, you **must** configure the variables at the top of the script.

1.  **Open the deployment script** (e.g., save the provided steps into a file named `deploy.sh`).
2.  **Modify the values** under the `# --- Configuration - CHANGE THESE VALUES ---` section.

## Deployment

1.  **Make the script executable:**
    ```bash
    chmod +x deploy.sh
    ```
2.  **Run the script:**
    ```bash
    ./deploy.sh
    ```

The script will perform the following actions:

* Enable necessary GCP APIs.
* Create a Cloud Storage bucket.
* Create a Cloud SQL (PostgreSQL) instance, database, and user.
* Store the database password securely in Secret Manager.
* Create a dedicated Service Account.
* Grant the Service Account necessary IAM roles.
* Create a Pub/Sub topic.
* Deploy the backend API service to Cloud Run using source code from the `./backend` directory, connecting it to Cloud SQL and Secret Manager.
* Deploy the worker function to Cloud Functions (Gen 2) using source code from the `./backend` directory, triggering it from the Pub/Sub topic, and connecting it to Cloud SQL and Secret Manager.
* Update the Cloud Function's underlying Cloud Run service to add the Cloud SQL connection.
* Deploy both Streamlit application to Cloud Run using source code from the `./streamlit_submission` and `streamlit_moderation` directories respectively.