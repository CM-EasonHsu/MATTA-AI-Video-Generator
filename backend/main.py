import asyncio
import base64
import httpx
import logging
import json
import os
import uuid
import io
from datetime import datetime, timezone
from typing import Optional
from cloudevents.http import CloudEvent
import functions_framework

from app import crud, database, gcs, schemas, utils
from app.config import settings

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")
logger = logging.getLogger("VideoGenerationWorker")
logger.setLevel(logging.INFO)

# --- Constants ---
VEO2_INITIATE_ENDPOINT = f"{settings.veo2_api_base_url}/v1/generate"
VEO2_STATUS_ENDPOINT_TEMPLATE = f"{settings.veo2_api_base_url}/v1/jobs/{{job_id}}"
VEO2_HEADERS = {"Authorization": f"Bearer {settings.veo2_api_key}"} if settings.veo2_api_key else {}


async def initiate_veo2_job(client: httpx.AsyncClient, photo_uri: str, prompt: Optional[str]) -> str:
    """Sends request to start Veo2 generation job."""
    logger.info("Initiating Veo2 video generation job...")
    try:
        payload = {"photo_uri": photo_uri}
        if prompt:
            payload["prompt"] = prompt

        # response = await client.post(VEO2_INITIATE_ENDPOINT, json=payload, headers=VEO2_HEADERS, timeout=30.0)
        # response.raise_for_status()

        # if response.status_code == 202:  # Accepted
        #     data = response.json()
        #     job_id = data.get("job_id")
        #     if not job_id:
        #         raise ValueError("Veo2 API did not return a job_id.")
        #     logger.info(f"Veo2 job initiated successfully. Job ID: {job_id}")
        #     return job_id
        # else:
        #     # Should be caught by raise_for_status, but good to be explicit
        #     raise Exception(f"Unexpected status code from Veo2 initiate API: {response.status_code}")

        await asyncio.sleep(3)
        return str(uuid.uuid4())

    except httpx.RequestError as e:
        logger.error(f"HTTP request error initiating Veo2 job: {e}", exc_info=True)
        raise
    except Exception as e:
        logger.error(f"Error initiating Veo2 job: {e}", exc_info=True)
        raise


async def poll_veo2_job(client: httpx.AsyncClient, job_id: str) -> dict:
    """Polls the Veo2 job status endpoint."""
    logger.info(f"Polling Veo2 job status for Job ID: {job_id}")
    status_url = VEO2_STATUS_ENDPOINT_TEMPLATE.format(job_id=job_id)
    attempts = 0
    while attempts < settings.max_polling_attempts:
        attempts += 1
        logger.info(f"Polling attempt {attempts}/{settings.max_polling_attempts} for job {job_id}")
        try:
            # response = await client.get(status_url, headers=VEO2_HEADERS, timeout=20.0)
            # response.raise_for_status()
            # data = response.json()
            # job_status = data.get("status")
            if attempts < 2:
                data = {"status": "RUNNING"}
            else:
                data = {
                    "status": "SUCCEEDED",
                    "output_video_uri": "gs://matta-videogen-storage/generated_videos/sample_video.mp4",
                }
            job_status = data.get("status")

            if job_status == "SUCCEEDED":
                logger.info(f"Veo2 job {job_id} succeeded.")
                video_uri = data.get("output_video_uri")
                if not video_uri:
                    raise ValueError(f"Veo2 job {job_id} succeeded but did not provide output_video_uri.")
                return {"status": "SUCCEEDED", "video_uri": video_uri, "error": None}
            elif job_status == "FAILED":
                error_message = data.get("error_message", "Unknown error")
                logger.error(f"Veo2 job {job_id} failed: {error_message}")
                return {"status": "FAILED", "video_uri": None, "error": error_message}
            elif job_status in ["RUNNING", "PENDING"]:
                logger.info(f"Veo2 job {job_id} status: {job_status}. Waiting...")
                await asyncio.sleep(settings.polling_interval_seconds)
            else:
                logger.warning(f"Veo2 job {job_id} returned unknown status: {job_status}")
                await asyncio.sleep(settings.polling_interval_seconds)

        except httpx.RequestError as e:
            logger.error(f"HTTP error polling job {job_id} (attempt {attempts}): {e}")
            # Consider if retry makes sense on specific HTTP errors (e.g., 503)
            await asyncio.sleep(settings.polling_interval_seconds)  # Wait before retrying
        except Exception as e:
            logger.error(f"Unexpected error polling job {job_id} (attempt {attempts}): {e}", exc_info=True)
            # Decide if this is fatal or worth retrying
            await asyncio.sleep(settings.polling_interval_seconds)

    # Max attempts reached
    logger.error(f"Veo2 job {job_id} polling timed out after {settings.max_polling_attempts} attempts.")
    return {"status": "FAILED", "video_uri": None, "error": "Polling timed out"}


async def process_submission(submission_id: uuid.UUID):
    """Main processing logic for a single submission."""
    conn = None
    submission_record = None
    start_time = datetime.now(timezone.utc)
    logger.info(f"Starting processing for submission_id: {submission_id}")

    try:
        conn = await database.get_db_connection()

        # 1. Fetch Submission Details & Check Status (Idempotency)
        submission_record = await crud.get_submission_by_id(conn, submission_id)
        if not submission_record:
            logger.error(f"Submission ID {submission_id} not found in database. Skipping.")
            return

        # Idempotency check: Only process if photo is approved
        current_status = schemas.SubmissionStatusEnum(submission_record["status"])
        if current_status != schemas.SubmissionStatusEnum.PHOTO_APPROVED:
            logger.warning(
                f"Submission {submission_id} has status {current_status}, not PHOTO_APPROVED. Skipping processing."
            )
            # Or handle re-processing logic if needed based on status (e.g., retry FAILED)
            return

        submission_code = submission_record["submission_code"]
        photo_gcs_path = submission_record["uploaded_photo_gcs_path"]
        user_prompt = submission_record["user_prompt"]

        # 2. Update Status to GENERATING_VIDEO
        await crud.update_submission_status(conn, submission_id, schemas.SubmissionStatusEnum.GENERATING_VIDEO)
        logger.info(f"Set status to GENERATING_VIDEO for {submission_id}")

        async with httpx.AsyncClient() as client:  # Create single client for reuse
            # 4. Initiate Veo2 Job
            job_id = await initiate_veo2_job(client, photo_gcs_path, user_prompt)

            # 5. Poll for Veo2 Job Completion
            poll_result = await poll_veo2_job(client, job_id)

            # 6. Handle Result
            if poll_result["status"] == "SUCCEEDED":
                video_gcs_path = poll_result["video_uri"]

                # 6c. Update DB to PENDING_VIDEO_APPROVAL
                await crud.update_submission_status(
                    conn,
                    submission_id,
                    schemas.SubmissionStatusEnum.PENDING_VIDEO_APPROVAL,
                    video_gcs_path=video_gcs_path,
                )
                logger.info(f"Successfully processed submission {submission_id}. Video uploaded to {video_gcs_path}")

            else:  # FAILED or TIMEOUT
                # 6d. Update DB to GENERATION_FAILED
                await crud.update_submission_status(
                    conn,
                    submission_id,
                    schemas.SubmissionStatusEnum.GENERATION_FAILED,
                    error_message=poll_result["error"],
                )
                logger.error(f"Failed to generate video for submission {submission_id}. Error: {poll_result['error']}")

    except Exception as e:
        logger.error(f"Unhandled exception processing submission {submission_id}: {e}", exc_info=True)
        # Attempt to mark as failed if possible
        if conn and submission_id:
            try:
                # Check if submission still exists before updating
                current_sub = await crud.get_submission_by_id(conn, submission_id)
                if current_sub and current_sub["status"] not in [
                    schemas.SubmissionStatusEnum.PENDING_VIDEO_APPROVAL.value,
                    schemas.SubmissionStatusEnum.VIDEO_APPROVED.value,
                    schemas.SubmissionStatusEnum.VIDEO_REJECTED.value,  # Avoid overwriting final states
                ]:
                    await crud.update_submission_status(
                        conn,
                        submission_id,
                        schemas.SubmissionStatusEnum.GENERATION_FAILED,
                        error_message=f"Worker exception: {str(e)}",
                    )
                    logger.info(f"Marked submission {submission_id} as failed due to worker exception.")
                else:
                    logger.warning(
                        f"Skipping failure update for {submission_id} as it's in a terminal state or deleted."
                    )

            except Exception as db_err:
                logger.error(f"Failed to update submission {submission_id} status to FAILED after exception: {db_err}")

    finally:
        if conn:
            await database.release_db_connection(conn)
        end_time = datetime.now(timezone.utc)
        duration = end_time - start_time
        logger.info(f"Finished processing submission {submission_id}. Duration: {duration}")


# --- Cloud Function Entry Point ---
@functions_framework.cloud_event
async def entry_point(event: CloudEvent):
    """
    Cloud Function entry point triggered by Pub/Sub.
    Args:
         event (dict): Event payload. Contains 'data' and 'attributes'.
    """

    submission_id_str = None
    submission_id = None

    try:
        data_str = base64.b64decode(event.data["message"]["data"]).decode()
        logger.info(f"Received Pub/Sub message: {data_str}")
        try:
            payload = json.loads(data_str)
            if isinstance(payload, dict) and "submission_id" in payload:
                submission_id_str = payload["submission_id"]
        except json.JSONDecodeError:
            logger.warning("Pub/Sub data was not valid JSON.")

        if not submission_id_str:
            logger.error("FATAL: 'submission_id' could not be extracted from Pub/Sub message.")
            # Acknowledge the message - can't process, no retry needed.
            return

        # 2. Validate Submission ID format
        try:
            submission_id = uuid.UUID(submission_id_str)
        except ValueError:
            logger.error(f"FATAL: Invalid UUID format for submission_id: '{submission_id_str}'.")
            # Acknowledge the message - invalid format, no retry needed.
            return

        # 3. Run Core Processing Logic
        await process_submission(submission_id)

        logger.info(f"Successfully completed processing for submission ID: {submission_id}")
        # Implicitly acknowledge the Pub/Sub message by returning normally

    except Exception as e:
        logger.error(
            f"Processing failed for submission '{submission_id_str}'. Error Type: {type(e).__name__}. See previous logs for details."
        )
        raise e
