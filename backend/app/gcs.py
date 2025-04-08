import logging
import google.auth
from google.cloud import storage
from google.cloud.exceptions import NotFound
from app.config import settings
from datetime import timedelta
from typing import Optional
import io

logger = logging.getLogger(__name__)

# Initialize GCS client (reuse across functions)
# Handles credentials automatically based on environment
try:
    storage_client = storage.Client()
    # Verify connection by getting the bucket (optional but good practice)
    bucket = storage_client.bucket(settings.gcs_bucket_name)
    logger.info(f"GCS Client initialized for bucket: {settings.gcs_bucket_name}")
except Exception as e:
    logger.error(f"Failed to initialize GCS Client or access bucket {settings.gcs_bucket_name}: {e}")
    storage_client = None  # Indicate failure
    # Depending on policy, you might want to raise an error here to stop startup


async def upload_to_gcs(file: io.BytesIO, destination_blob_name: str, content_type: str) -> str:
    """Uploads a file object to GCS."""
    if not storage_client:
        raise RuntimeError("GCS Client not initialized.")

    try:
        bucket = storage_client.bucket(settings.gcs_bucket_name)
        blob = bucket.blob(destination_blob_name)

        # Reset stream position just in case
        file.seek(0)

        # Using upload_from_file for efficient streaming
        blob.upload_from_file(file, content_type=content_type)

        logger.info(f"File uploaded to gs://{settings.gcs_bucket_name}/{destination_blob_name}")
        # Return the full GCS path (gs:// URI format)
        return f"gs://{settings.gcs_bucket_name}/{destination_blob_name}"
    except Exception as e:
        logger.error(f"Failed to upload file to GCS: {e}", exc_info=True)
        raise


async def generate_signed_url(blob_name: str) -> Optional[str]:
    """Generates a V4 signed URL for downloading a blob."""
    if not storage_client:
        logger.error("Cannot generate signed URL: GCS Client not initialized.")
        return None
    if not blob_name:
        logger.warning("Cannot generate signed URL: blob_name is empty.")
        return None

    # Ensure blob_name doesn't include gs:// prefix for the blob() method
    if blob_name.startswith(f"gs://{settings.gcs_bucket_name}/"):
        blob_name = blob_name[len(f"gs://{settings.gcs_bucket_name}/") :]

    try:
        credentials, project = google.auth.default()
        request = google.auth.transport.requests.Request()
        credentials.refresh(request)
        bucket = storage_client.bucket(settings.gcs_bucket_name)
        blob = bucket.blob(blob_name)

        # Check if the blob actually exists before generating URL (optional)
        # Note: This adds an extra API call
        # if not blob.exists():
        #     logger.warning(f"Blob {blob_name} not found in bucket {settings.gcs_bucket_name}. Cannot generate signed URL.")
        #     return None

        url = blob.generate_signed_url(
            version="v4",
            expiration=timedelta(seconds=settings.signed_url_expiration_seconds),
            method="GET",
            service_account_email=settings.SERVICE_ACCOUNT_EMAIL,
            access_token=credentials.token,
        )
        logger.debug(f"Generated signed URL for {blob_name}")
        return url
    except NotFound:
        logger.warning(f"Blob {blob_name} not found in bucket {settings.gcs_bucket_name} when generating signed URL.")
        return None
    except Exception as e:
        logger.error(f"Failed to generate signed URL for {blob_name}: {e}", exc_info=True)
        return None  # Return None on failure


async def download_blob_to_bytes(blob_name: str) -> Optional[bytes]:
    """Downloads a blob from GCS into memory as bytes."""
    if not storage_client:
        logger.error("Cannot download blob: GCS Client not initialized.")
        return None
    if not blob_name:
        logger.warning("Cannot download blob: blob_name is empty.")
        return None

    # Ensure blob_name doesn't include gs:// prefix
    if blob_name.startswith(f"gs://{settings.gcs_bucket_name}/"):
        blob_name = blob_name[len(f"gs://{settings.gcs_bucket_name}/") :]

    try:
        bucket = storage_client.bucket(settings.gcs_bucket_name)
        blob = bucket.blob(blob_name)

        logger.info(f"Attempting to download blob: {blob_name}")
        content = await asyncio.to_thread(blob.download_as_bytes)  # Run blocking call in thread
        logger.info(f"Successfully downloaded blob: {blob_name} ({len(content)} bytes)")
        return content
    except NotFound:
        logger.error(f"Blob {blob_name} not found in bucket {settings.gcs_bucket_name} during download.")
        return None
    except Exception as e:
        logger.error(f"Failed to download blob {blob_name}: {e}", exc_info=True)
        return None
