import asyncio
import json
import logging
import uuid
from typing import List, Optional

import httpx
from asyncpg import Connection
from fastapi import (APIRouter, Body, Depends, HTTPException, Request,
                     Response, status)

from app import crud, database, schemas
from app.config import \
    settings  # Assuming settings contains Veo2 details, polling config, etc.

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/generation", tags=["Generation"])


# --- Constants ---
VEO2_INITIATE_ENDPOINT = f"{settings.veo2_api_base_url}/v1/generate"
VEO2_PROMPT_ENDPOINT = f"{settings.veo2_api_base_url}/v1/prompt"
VEO2_STATUS_ENDPOINT_TEMPLATE = f"{settings.veo2_api_base_url}/v1/jobs/{{job_id}}"
VEO2_HEADERS = {"Authorization": f"Bearer {settings.veo2_api_key}"} if settings.veo2_api_key else {}


async def initiate_veo2_job(client: httpx.AsyncClient, photo_uri: str, prompt: Optional[str]) -> str:
    """Sends request to start Veo2 generation job. Raises exceptions on failure."""
    logger.info(f"Initiating Veo2 video generation job for photo: {photo_uri}...")
    try:
        payload = {"photo_uri": photo_uri}
        if prompt:
            payload["prompt"] = prompt

        # --- Start: Real API call (uncomment when ready) ---
        # response = await client.post(
        #     VEO2_INITIATE_ENDPOINT,
        #     json=payload,
        #     headers=VEO2_HEADERS,
        #     timeout=settings.veo2_initiate_timeout_seconds # Use config
        # )
        # response.raise_for_status() # Raises HTTPStatusError for 4xx/5xx

        # if response.status_code == 202:  # Accepted
        #     data = response.json()
        #     job_id = data.get("job_id")
        #     if not job_id:
        #         # Treat missing job_id as an error
        #         raise ValueError("Veo2 API accepted the request but did not return a job_id.")
        #     logger.info(f"Veo2 job initiated successfully. Job ID: {job_id}")
        #     return job_id
        # else:
        #     # Should be caught by raise_for_status, but good to be explicit
        #     # This path might not be reachable if raise_for_status() works as expected
        #     raise Exception(f"Unexpected status code from Veo2 initiate API: {response.status_code}")
        # --- End: Real API call ---

        # --- Start: Mock API call (remove when using real API) ---
        await asyncio.sleep(1)  # Simulate network delay
        mock_job_id = str(uuid.uuid4())
        logger.info(f"Mock Veo2 job initiated successfully. Job ID: {mock_job_id}")
        return mock_job_id
        # --- End: Mock API call ---

    except httpx.HTTPStatusError as e:
        # Specific error from the API (e.g., 4xx bad request, 5xx server error)
        logger.error(
            f"Veo2 API returned an error during job initiation: {e.response.status_code} - {e.response.text}",
            exc_info=True,
        )
        # Re-raise to be caught by the main handler
        raise
    except httpx.RequestError as e:
        # Network errors, timeouts during the request
        logger.error(f"HTTP request error initiating Veo2 job: {e}", exc_info=True)
        # Re-raise to be caught by the main handler
        raise
    except Exception as e:
        # Other unexpected errors (e.g., ValueError from missing job_id)
        logger.error(f"Unexpected error initiating Veo2 job: {e}", exc_info=True)
        # Re-raise to be caught by the main handler
        raise


async def poll_veo2_job(client: httpx.AsyncClient, job_id: str) -> dict:
    """
    Polls the Veo2 job status endpoint until completion or timeout.
    Returns a dict: {"status": "SUCCEEDED"|"FAILED", "video_uri": str|None, "error": str|None}
    """
    logger.info(f"Polling Veo2 job status for Job ID: {job_id}")
    status_url = VEO2_STATUS_ENDPOINT_TEMPLATE.format(job_id=job_id)
    attempts = 0
    max_attempts = settings.max_polling_attempts  # From config
    poll_interval = settings.polling_interval_seconds  # From config

    while attempts < max_attempts:
        attempts += 1
        logger.info(f"Polling attempt {attempts}/{max_attempts} for job {job_id}")
        try:
            # --- Start: Real API call (uncomment when ready) ---
            # response = await client.get(
            #     status_url,
            #     headers=VEO2_HEADERS,
            #     timeout=settings.veo2_poll_timeout_seconds # Use config
            # )
            # response.raise_for_status()
            # data = response.json()
            # --- End: Real API call ---

            # --- Start: Mock API call (remove when using real API) ---
            await asyncio.sleep(2)  # Simulate network delay + processing time
            if attempts < 3:  # Simulate running state for a couple of attempts
                data = {"status": "RUNNING"}
            elif attempts < max_attempts:  # Simulate success before timeout
                data = {
                    "status": "SUCCEEDED",
                    "output_video_uri": "gs://matta-videogen-storage/generated_videos/sample_video.mp4",
                }
            else:  # Simulate reaching max attempts without success (timeout)
                # This case is handled by the loop condition, but shows the final state
                pass  # Will fall through to timeout logic below loop
            # --- End: Mock API call ---

            job_status = data.get("status")

            if job_status == "SUCCEEDED":
                logger.info(f"Veo2 job {job_id} succeeded.")
                video_uri = data.get("output_video_uri")
                if not video_uri:
                    logger.error(f"Veo2 job {job_id} succeeded but missing 'output_video_uri'.")
                    # Treat missing URI as failure for this job
                    return {"status": "FAILED", "video_uri": None, "error": "Job succeeded but output URI was missing."}
                return {"status": "SUCCEEDED", "video_uri": video_uri, "error": None}

            elif job_status == "FAILED":
                error_message = data.get("error_message", "Unknown error from Veo2 API")
                logger.error(f"Veo2 job {job_id} failed: {error_message}")
                return {"status": "FAILED", "video_uri": None, "error": error_message}

            elif job_status in ["RUNNING", "PENDING"]:
                logger.info(f"Veo2 job {job_id} status: {job_status}. Waiting {poll_interval}s...")
                await asyncio.sleep(poll_interval)

            else:
                # Unknown status - treat as potentially transient, continue polling
                logger.warning(f"Veo2 job {job_id} returned unknown status: '{job_status}'. Continuing poll.")
                await asyncio.sleep(poll_interval)

        except httpx.HTTPStatusError as e:
            # Non-2xx status from Veo2 status API. Could be transient (5xx) or permanent (4xx).
            # We'll log and continue polling unless it's clearly a final state (e.g., 404 Not Found might mean job expired)
            logger.warning(
                f"HTTP status error polling job {job_id} (attempt {attempts}): {e.response.status_code}. Retrying poll."
            )
            # Optional: Check for specific codes (e.g., 404) to potentially fail faster.
            # if e.response.status_code == 404:
            #    return {"status": "FAILED", "video_uri": None, "error": f"Polling failed: Job {job_id} not found (404)."}
            await asyncio.sleep(poll_interval)  # Wait before retrying poll

        except httpx.RequestError as e:
            # Network errors, timeouts during polling request
            logger.warning(f"HTTP request error polling job {job_id} (attempt {attempts}): {e}. Retrying poll.")
            await asyncio.sleep(poll_interval)  # Wait before retrying poll

        except Exception as e:
            # Unexpected errors during polling logic
            logger.error(f"Unexpected error polling job {job_id} (attempt {attempts}): {e}", exc_info=True)
            # Continue polling, hoping it's temporary
            await asyncio.sleep(poll_interval)

    # Loop finished without success
    logger.error(f"Veo2 job {job_id} polling timed out after {max_attempts} attempts.")
    return {"status": "FAILED", "video_uri": None, "error": f"Polling timed out after {max_attempts} attempts"}


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
    task_retry_count = request.headers.get("X-CloudTasks-TaskRetryCount")
    if task_retry_count:
        logger.info(f"Received task for submission {submission_id}, task retry count: {task_retry_count}")
    else:
        logger.info(f"Received task for submission {submission_id} (first attempt)")

    # --- 1. Fetch Submission Details & Idempotency Check ---
    try:
        submission_record = await crud.get_submission_by_id(conn, submission_id)
    except Exception as e:
        # If DB connection fails, it's a server-side issue. Signal retry.
        logger.error(f"Database error fetching submission {submission_id}: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="Database error fetching submission."
        )

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
    submission_code = submission_record["submission_code"]
    photo_gcs_path = submission_record["uploaded_photo_gcs_path"]
    user_prompt = submission_record["user_prompt"]
    veo2_job_id = submission_record.get("veo2_job_id")  # Get potential existing job ID

    # Idempotency Check: Only start processing if the status is PHOTO_APPROVED.
    if current_status != schemas.SubmissionStatusEnum.PHOTO_APPROVED:
        # If it's already generating, completed, or failed in a terminal way,
        # assume a previous task attempt handled it or is handling it.
        # Acknowledge the task by returning 2xx.
        logger.warning(
            f"Submission {submission_id} has status {current_status}. Expected PHOTO_APPROVED. "
            f"Acknowledging task as likely already processed or in progress by another attempt."
        )
        return Response(
            status_code=status.HTTP_200_OK,
            content=json.dumps({"message": f"Submission status is {current_status}, processing skipped."}),
            media_type="application/json",
        )

    # --- 2. Update Status to GENERATING_VIDEO ---
    try:
        await crud.update_submission_status(conn, submission_id, schemas.SubmissionStatusEnum.GENERATING_VIDEO)
        logger.info(f"Set status to GENERATING_VIDEO for {submission_id}")
    except Exception as e:
        logger.error(f"Database error updating status to GENERATING_VIDEO for {submission_id}: {e}", exc_info=True)
        # Signal retry
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="Database error updating status.")

    # --- 3. Main Generation Logic ---
    veo2_job_id = None  # Initialize
    try:
        async with httpx.AsyncClient() as client:
            # --- 4. Initiate Veo2 Job ---
            # Note: If initiate_veo2_job fails, it raises an exception
            veo2_job_id = await initiate_veo2_job(client, photo_gcs_path, user_prompt)

            # --- 4b. Store Veo2 Job ID (Optional but Recommended) ---
            # Persisting the job_id allows resuming polling if the task fails *after* initiation
            # but before polling completes. You'd need to adjust the idempotency check
            # at the start to look for GENERATING_VIDEO status *and* a veo2_job_id, then skip initiation.
            # For simplicity here, we don't implement resume logic, but storing is good practice.
            # try:
            #     await crud.update_submission_veo2_job_id(
            #         conn, submission_id, veo2_job_id
            #     )  # Assumes this DB function exists
            #     logger.info(f"Stored Veo2 Job ID {veo2_job_id} for submission {submission_id}")
            # except Exception as e:
            #     # Log the error but proceed; the main failure point is the video generation itself.
            #     # If this fails consistently, it might warrant a 5xx, but could also make retries harder.
            #     logger.warning(f"Database error storing Veo2 Job ID for {submission_id}: {e}", exc_info=True)
            #     # Decide: raise HTTPException(503)? Or just log and continue? Let's log and continue for now.

            # --- 5. Poll for Veo2 Job Completion ---
            poll_result = await poll_veo2_job(client, veo2_job_id)

            # --- 6. Handle Result ---
            if poll_result["status"] == "SUCCEEDED":
                video_gcs_path = poll_result["video_uri"]
                # Update DB to PENDING_VIDEO_APPROVAL
                await crud.update_submission_status(
                    conn,
                    submission_id,
                    schemas.SubmissionStatusEnum.PENDING_VIDEO_APPROVAL,
                    video_gcs_path=video_gcs_path,
                    # Optionally clear veo2_job_id here if no longer needed
                )
                logger.info(f"Successfully processed submission {submission_id}. Video URI: {video_gcs_path}")
                # Return 2xx to signal success to Cloud Tasks
                return Response(
                    status_code=status.HTTP_200_OK,
                    content=json.dumps({"message": "Processing successful"}),
                    media_type="application/json",
                )

            else:  # FAILED or TIMEOUT from polling
                # This is a terminal failure of the *underlying Veo2 job*.
                # Update DB to GENERATION_FAILED.
                # We should return 2xx to Cloud Tasks because retrying the *entire* FastAPI task
                # won't fix the already failed/timed-out Veo2 job.
                error_msg = poll_result["error"]
                await crud.update_submission_status(
                    conn,
                    submission_id,
                    schemas.SubmissionStatusEnum.GENERATION_FAILED,
                    error_message=error_msg,
                    # Optionally clear veo2_job_id
                )
                logger.error(f"Video generation failed for submission {submission_id}. Error: {error_msg}")
                # Return 2xx to signal handled failure (stop Cloud Tasks retries)
                return Response(
                    status_code=status.HTTP_200_OK,
                    content=json.dumps({"message": f"Video generation failed: {error_msg}"}),
                    media_type="application/json",
                )

    except httpx.HTTPStatusError as e:
        # Failure during Veo2 *initiation* due to API error (4xx/5xx)
        logger.error(f"Veo2 API error during initiation for {submission_id}: {e}", exc_info=True)
        error_detail = f"Veo2 initiation API error: {e.response.status_code}"
        # Update DB to reflect failure (optional, could leave as GENERATING_VIDEO for retry)
        try:
            await crud.update_submission_status(
                conn,
                submission_id,
                schemas.SubmissionStatusEnum.GENERATION_FAILED,
                error_message=error_detail,
                veo2_job_id=veo2_job_id,
            )
        except Exception as db_err:
            logger.error(
                f"Failed to update status to FAILED after Veo2 initiation error for {submission_id}: {db_err}",
                exc_info=True,
            )
        # Raise 5xx to trigger Cloud Tasks retry - maybe the Veo2 API issue is transient
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=error_detail)

    except httpx.RequestError as e:
        # Failure during Veo2 *initiation* due to network/timeout
        logger.error(f"Network error during Veo2 initiation for {submission_id}: {e}", exc_info=True)
        error_detail = f"Network error during Veo2 initiation: {e}"
        # Update DB to reflect failure (optional)
        try:
            await crud.update_submission_status(
                conn,
                submission_id,
                schemas.SubmissionStatusEnum.GENERATION_FAILED,
                error_message=error_detail,
                veo2_job_id=veo2_job_id,
            )
        except Exception as db_err:
            logger.error(
                f"Failed to update status to FAILED after Veo2 initiation network error for {submission_id}: {db_err}",
                exc_info=True,
            )
        # Raise 5xx to trigger Cloud Tasks retry - network issues are often transient
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=error_detail)

    except Exception as e:
        # Catch all other unexpected errors during the main logic (e.g., DB update failures within the try block)
        logger.error(f"Unexpected error processing submission {submission_id}: {e}", exc_info=True)
        error_detail = f"Unexpected server error: {e}"
        # Attempt to update DB to failed state
        try:
            await crud.update_submission_status(
                conn,
                submission_id,
                schemas.SubmissionStatusEnum.GENERATION_FAILED,
                error_message=error_detail,
                veo2_job_id=veo2_job_id,
            )
        except Exception as db_err:
            logger.error(
                f"Failed to update status to FAILED after unexpected error for {submission_id}: {db_err}", exc_info=True
            )
        # Raise 500 to trigger Cloud Tasks retry
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=error_detail)

    # If the code somehow reaches here without returning/raising (shouldn't happen with current logic),
    # treat it as an internal error.
    logger.error(f"Reached unexpected end of function for submission {submission_id}")
    raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Unexpected end of processing.")


async def generate_veo2_prompt(client: httpx.AsyncClient, photo_uri: str, description: Optional[str] = None) -> dict:
    """
    Generates a video prompt using Veo2's prompt generation API.

    Args:
        client: An httpx.AsyncClient instance
        photo_uri: The GCS URI of the photo to generate a prompt for
        description: Optional description to guide prompt generation

    Returns:
        dict: The generated prompt data from Veo2

    Raises:
        httpx.HTTPStatusError: For API errors (4xx/5xx)
        httpx.RequestError: For network/timeout errors
        Exception: For other unexpected errors
    """
    logger.info(f"Generating Veo2 video prompt for photo: {photo_uri}...")
    try:
        payload = {"photo_uri": photo_uri}
        if description:
            payload["description"] = description

        # --- Start: Real API call (uncomment when ready) ---
        # response = await client.post(
        #     VEO2_PROMPT_ENDPOINT,
        #     json=payload,
        #     headers=VEO2_HEADERS,
        #     timeout=settings.veo2_prompt_timeout_seconds  # Use config
        # )
        # response.raise_for_status()  # Raises HTTPStatusError for 4xx/5xx
        # prompt_data = response.json()
        # logger.info(f"Successfully generated Veo2 prompt for photo: {photo_uri}")
        # return prompt_data
        # --- End: Real API call ---

        # --- Start: Mock API call (remove when using real API) ---
        await asyncio.sleep(1)  # Simulate network delay
        mock_prompt_data = {
            "prompt": "A beautiful scene with dynamic movement and vibrant colors",
            "suggestions": [
                "Add more motion to the scene",
                "Focus on the central subject",
                "Enhance the lighting effects"
            ]
        }
        logger.info(f"Mock Veo2 prompt generated successfully for photo: {photo_uri}")
        return mock_prompt_data
        # --- End: Mock API call ---

    except httpx.HTTPStatusError as e:
        logger.error(
            f"Veo2 API returned an error during prompt generation: {e.response.status_code} - {e.response.text}",
            exc_info=True,
        )
        raise
    except httpx.RequestError as e:
        logger.error(f"HTTP request error during Veo2 prompt generation: {e}", exc_info=True)
        raise
    except Exception as e:
        logger.error(f"Unexpected error during Veo2 prompt generation: {e}", exc_info=True)
        raise


@router.post(
    "/prompt",
    summary="Generate a video prompt using Veo2",
    response_model=schemas.VideoPromptResponse,
)
async def generate_video_prompt(
    request_data: schemas.VideoPromptRequest = Body(...),
):
    """
    Generates a video prompt using Veo2's prompt generation API.
    This is a synchronous endpoint that returns the generated prompt directly.

    Args:
        request_data: The request data containing the photo URI and optional description

    Returns:
        schemas.VideoPromptResponse: The generated prompt data

    Raises:
        HTTPException: For various error conditions
    """
    photo_uri = request_data.photo_uri
    description = request_data.description

    logger.info(f"Received request to generate video prompt for photo: {photo_uri}")

    try:
        async with httpx.AsyncClient() as client:
            prompt_data = await generate_veo2_prompt(client, photo_uri, description)

            return schemas.VideoPromptResponse(
                prompt=prompt_data.get("prompt", ""),
                suggestions=prompt_data.get("suggestions", []),
            )

    except httpx.HTTPStatusError as e:
        error_detail = f"Veo2 API error: {e.response.status_code} - {e.response.text}"
        logger.error(error_detail)
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=error_detail,
        )

    except httpx.RequestError as e:
        error_detail = f"Network error communicating with Veo2: {e}"
        logger.error(error_detail)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=error_detail,
        )

    except Exception as e:
        error_detail = f"Unexpected error generating video prompt: {e}"
        logger.error(error_detail, exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=error_detail,
        )
