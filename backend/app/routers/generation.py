import asyncio
import json
import logging
import mimetypes
import uuid

from google import genai
from google.genai import types
from typing import List, Optional

import httpx
from asyncpg import Connection
from fastapi import APIRouter, Body, Depends, HTTPException, Request, Response, status

from app import crud, database, schemas
from app.config import settings  # Assuming settings contains Veo2 details, polling config, etc.

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/generation", tags=["Generation"])


# --- Constants ---
VEO2_MODEL_NAME = settings.veo2_model_name
VEO2_MAX_RETRIES = settings.veo2_max_retries
VEO2_ASPECT_RATIO = settings.veo2_aspect_ratio
VEO2_OUTPUT_GCS_URI = f"gs://{settings.gcs_bucket_name}/generated_videos"
VEO2_VIDEO_DURATION = settings.veo2_video_duration
VEO2_POLLING_INTERVAL = settings.veo2_polling_interval


async def veo2_generate_video(photo_uri: str, prompt: Optional[str] = None) -> str:
    """Sends request to start Veo2 generation. Raises exceptions on failure."""
    photo_mime_type = mimetypes.guess_type(photo_uri)[0]
    logger.info(
        f"Initiating Veo2 video generation job for photo: {photo_uri}, mime type: {photo_mime_type}, prompt: {prompt}"
    )
    try:
        client = genai.Client(vertexai=True, project=settings.GOOGLE_CLOUD_PROJECT, location="us-central1")

        operation = client.models.generate_videos(
            model=VEO2_MODEL_NAME,
            prompt=prompt,
            image=types.Image(
                gcs_uri=photo_uri,
                mime_type=photo_mime_type,
            ),
            config=types.GenerateVideosConfig(
                aspect_ratio=VEO2_ASPECT_RATIO,
                output_gcs_uri=VEO2_OUTPUT_GCS_URI,
                number_of_videos=1,
                duration_seconds=VEO2_VIDEO_DURATION,
                person_generation="allow_adult",
                enhance_prompt=True,
            ),
        )

        logger.info(f"Veo2 job started: {operation.name}")

        while not operation.done:
            await asyncio.sleep(VEO2_POLLING_INTERVAL)
            operation = client.operations.get(operation)
            logger.info(operation)

        if operation.error:
            return {"status": "FAILED", "error": operation.error["message"]}

        elif operation.response:
            logger.info(f"Veo2 job succeeded: {operation.response}")
            return {"status": "SUCCEEDED", "video_uri": operation.result.generated_videos[0].video.uri}

    except Exception as e:
        logger.error(f"Veo2 job failed: {e}", exc_info=True)
        return {"status": "FAILED", "error": str(e)}


@router.post(
    "/{submission_id}",
    summary="Trigger video generation for a submission (Cloud Task Target)",
)
async def generate_video(
    submission_id: uuid.UUID,
    request: Request,  # Inject request to access headers
    conn: Connection = Depends(database.get_db),
):
    """
    Processes a video generation request triggered by Cloud Tasks.
    Handles idempotency and signals success/failure back to Cloud Tasks.
    - Returns 2xx on success or non-retryable handled error (e.g., already processed, not found).
    - Raises HTTPException with 5xx on retryable failures.
    """
    task_retry_count = request.headers.get("X-CloudTasks-TaskRetryCount", 0)
    task_retry_count = int(task_retry_count) if task_retry_count.isdigit() else 0
    final_attempt = task_retry_count >= VEO2_MAX_RETRIES
    logger.info(f"Received task for submission {submission_id}, task retry count: {task_retry_count}")

    try:
        # --- 1. Fetch Submission Details & Idempotency Check ---
        submission_record = await crud.get_submission_by_id(conn, submission_id)
        if not submission_record:
            # Submission not found. This isn't an error we can recover from by retrying.
            # Log it and return 2xx to ACK the task and prevent retries.
            logger.error(f"Submission ID {submission_id} not found. Acknowledging task.")
            # Return 200 OK or 204 No Content. 200 allows a potential response body if needed later.
            return Response(
                status_code=status.HTTP_200_OK,
                content=json.dumps({"message": "Submission not found, task acknowledged."}),
                media_type="application/json",
            )

        current_status = schemas.SubmissionStatusEnum(submission_record["status"])
        photo_gcs_path = submission_record["uploaded_photo_gcs_path"]
        user_prompt = submission_record["user_prompt"]

        # Idempotency Check: Only start processing if the status is PHOTO_APPROVED.
        if current_status not in (
            schemas.SubmissionStatusEnum.PHOTO_APPROVED,
            schemas.SubmissionStatusEnum.PENDING_GENERATION_RETRY,
        ):
            return Response(
                status_code=status.HTTP_200_OK,
                content=json.dumps({"message": f"Submission status is {current_status}, processing skipped."}),
                media_type="application/json",
            )

        # --- 2. Update Status to GENERATING_VIDEO ---
        await crud.update_submission_status(conn, submission_id, schemas.SubmissionStatusEnum.GENERATING_VIDEO)
        logger.info(f"Set status to GENERATING_VIDEO for {submission_id}")

        # --- 3. Generate video using Veo2 ---
        veo2_result = await veo2_generate_video(photo_gcs_path, user_prompt)

        if veo2_result["status"] == "SUCCEEDED":
            video_gcs_path = veo2_result["video_uri"]

            # Update DB to PENDING_VIDEO_APPROVAL
            await crud.update_submission_status(
                conn,
                submission_id,
                schemas.SubmissionStatusEnum.PENDING_VIDEO_APPROVAL,
                video_gcs_path=video_gcs_path,
            )
            logger.info(f"Successfully processed submission {submission_id}. Video URI: {video_gcs_path}")

            # Return 2xx to signal success to Cloud Tasks
            return Response(
                status_code=status.HTTP_200_OK,
                content=json.dumps({"message": "Processing successful"}),
                media_type="application/json",
            )

        else:
            error_msg = veo2_result["error"]
            logger.error(f"Video generation failed for submission {submission_id}. Error: {error_msg}")
            if final_attempt:
                # Update DB to GENERATION_FAILED
                await crud.update_submission_status(
                    conn, submission_id, schemas.SubmissionStatusEnum.GENERATION_FAILED, error_message=error_msg
                )
                # Return 2xx to signal handled failure (stop Cloud Tasks retries)
                return Response(
                    status_code=status.HTTP_200_OK,
                    content=json.dumps({"message": f"Video generation failed: {error_msg}"}),
                    media_type="application/json",
                )
            else:
                # Update DB to PENDING_GENERATION_RETRY
                await crud.update_submission_status(
                    conn, submission_id, schemas.SubmissionStatusEnum.PENDING_GENERATION_RETRY, error_message=error_msg
                )
                return Response(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    content=json.dumps({"message": f"Video generation failed: {error_msg}"}),
                    media_type="application/json",
                )

    except Exception as e:
        try:
            # Update DB to PENDING_GENERATION_RETRY
            await crud.update_submission_status(
                conn, submission_id, schemas.SubmissionStatusEnum.PENDING_GENERATION_RETRY, error_message=error_msg
            )
        except Exception as db_error:
            logger.error(f"Failed to update submission status in DB: {db_error}", exc_info=True)

        finally:
            # Raise 500 to trigger Cloud Tasks retry
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Unexpected server error: {e}"
            )
