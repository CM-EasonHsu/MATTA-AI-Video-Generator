import logging
import json
import uuid
from fastapi import APIRouter, Depends, HTTPException, status, Body
from typing import List
from app import schemas, crud, gcs, database
from asyncpg import Connection
from google.cloud import pubsub_v1
from google.cloud import tasks_v2
from app.config import settings

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/moderation", tags=["Moderation"])  # Add prefix for all moderation routes


def create_video_generation_task(submission_id: uuid.UUID):
    """
    Creates a Cloud Task to trigger the video generation endpoint for a given submission ID.
    """
    client = tasks_v2.CloudTasksClient()

    # Construct the full path to the queue.
    parent = client.queue_path(settings.GOOGLE_CLOUD_PROJECT, settings.GOOGLE_CLOUD_REGION, settings.QUEUE_ID)

    # Construct the target URL for the FastAPI endpoint.
    # Ensure submission_id is converted to string for the URL.
    target_url = f"{settings.CLOUD_RUN_SERVICE_URL}/generation/{str(submission_id)}"

    # Construct the task body.
    task = tasks_v2.Task(
        http_request=tasks_v2.HttpRequest(
            http_method=tasks_v2.HttpMethod.POST,
            url=target_url,
            oidc_token=tasks_v2.OidcToken(
                service_account_email=settings.SERVICE_ACCOUNT_EMAIL,
                audience=settings.CLOUD_RUN_SERVICE_URL,
            ),
        )
    )

    try:
        logger.info(f"Creating Cloud Task for submission {submission_id} targeting {target_url}")
        response = client.create_task(tasks_v2.CreateTaskRequest(parent=parent, task=task))
        logger.info(f"Successfully created task: {response.name}")
        return response.name
    except Exception as e:
        logger.error(f"Error creating Cloud Task for submission {submission_id}: {e}", exc_info=True)
        raise  # Re-raise the exception for the caller to handle


@router.post(
    "/photo/{submission_id}/action",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Approve or reject a submitted photo",
)
async def moderate_photo(
    submission_id: uuid.UUID, action: schemas.ModerationAction = Body(...), conn: Connection = Depends(database.get_db)
):
    """Updates the submission status based on photo moderation decision."""
    submission = await crud.get_submission_by_id(conn, submission_id)
    if not submission:
        raise HTTPException(status_code=404, detail="Submission not found.")

    if action.decision == schemas.ModerationDecisionEnum.APPROVE:
        new_status = schemas.SubmissionStatusEnum.PHOTO_APPROVED  # Or QUEUED_FOR_GENERATION
        updated = await crud.update_submission_status(conn, submission_id, new_status, set_photo_moderated=True)
        if updated:
            logger.info(f"Photo approved for submission {submission_id}. Triggering video generation (placeholder).")

            try:
                # Create a Cloud Task to trigger the video generation endpoint
                task_name = create_video_generation_task(submission_id)
                logger.info(f"Successfully created Cloud Task {task_name} for submission {submission_id}.")

            except Exception as e:
                logger.exception(f"Failed to create Cloud Task for submission {submission_id}: {e}")
                raise HTTPException(status_code=500, detail="Failed to trigger video generation.")
            pass
        else:
            raise HTTPException(status_code=500, detail="Failed to update submission status.")

    elif action.decision == schemas.ModerationDecisionEnum.REJECT:
        new_status = schemas.SubmissionStatusEnum.PHOTO_REJECTED
        updated = await crud.update_submission_status(conn, submission_id, new_status, set_photo_moderated=True)
        if updated:
            logger.info(f"Photo rejected for submission {submission_id}.")
        else:
            raise HTTPException(status_code=500, detail="Failed to update submission status.")
    else:
        # Should not happen with Enum validation, but good practice
        raise HTTPException(status_code=400, detail="Invalid moderation action.")

    return  # Return 204 No Content on success


@router.post(
    "/video/{submission_id}/action",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Approve or reject a generated video",
)
async def moderate_video(
    submission_id: uuid.UUID, action: schemas.ModerationAction = Body(...), conn: Connection = Depends(database.get_db)
):
    """Updates the submission status based on video moderation decision."""
    submission = await crud.get_submission_by_id(conn, submission_id)
    if not submission:
        raise HTTPException(status_code=404, detail="Submission not found.")

    if submission["status"] != schemas.SubmissionStatusEnum.PENDING_VIDEO_APPROVAL.value:
        raise HTTPException(
            status_code=400, detail=f"Submission is not pending video approval (status: {submission['status']})."
        )

    if action.decision == schemas.ModerationDecisionEnum.APPROVE:
        new_status = schemas.SubmissionStatusEnum.VIDEO_APPROVED
        updated = await crud.update_submission_status(conn, submission_id, new_status, set_video_moderated=True)
        if updated:
            logger.info(f"Video approved for submission {submission_id}. Now accessible to user.")
        else:
            raise HTTPException(status_code=500, detail="Failed to update submission status.")

    elif action.decision == schemas.ModerationDecisionEnum.REJECT:
        new_status = schemas.SubmissionStatusEnum.VIDEO_REJECTED
        updated = await crud.update_submission_status(conn, submission_id, new_status, set_video_moderated=True)
        if updated:
            logger.info(f"Video rejected for submission {submission_id}.")
        else:
            raise HTTPException(status_code=500, detail="Failed to update submission status.")
    else:
        raise HTTPException(status_code=400, detail="Invalid moderation action.")

    return  # Return 204 No Content on success
