import logging
import json
import uuid
from fastapi import APIRouter, Depends, HTTPException, status, Body
from typing import List
from app import schemas, crud, gcs, database
from asyncpg import Connection
from google.cloud import pubsub_v1
from app.config import settings

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/moderation", tags=["Moderation"])  # Add prefix for all moderation routes


@router.get(
    "/pending_photos", response_model=List[schemas.SubmissionDetail], summary="List submissions awaiting photo approval"
)
async def get_pending_photo_submissions(conn: Connection = Depends(database.get_db)):
    """Retrieves all submissions with status PENDING_PHOTO_APPROVAL."""
    submissions_db = await crud.get_submissions_by_status(conn, [schemas.SubmissionStatusEnum.PENDING_PHOTO_APPROVAL])
    result = []
    for sub in submissions_db:
        photo_url = await gcs.generate_signed_url(sub["uploaded_photo_gcs_path"])
        result.append(
            schemas.SubmissionDetail(
                id=sub["id"],
                submission_code=sub["submission_code"],
                status=schemas.SubmissionStatusEnum(sub["status"]),
                user_prompt=sub["user_prompt"],
                photo_url=photo_url,
                video_url=None,  # No video yet
                error_message=sub["error_message"],
                created_at=sub["created_at"],
                updated_at=sub["updated_at"],
            )
        )
    return result


@router.post(
    "/photos/{submission_id}/action",
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

    if submission["status"] != schemas.SubmissionStatusEnum.PENDING_PHOTO_APPROVAL.value:
        raise HTTPException(
            status_code=400, detail=f"Submission is not pending photo approval (status: {submission['status']})."
        )

    if action.decision == schemas.ModerationDecisionEnum.APPROVE:
        new_status = schemas.SubmissionStatusEnum.PHOTO_APPROVED  # Or QUEUED_FOR_GENERATION
        updated = await crud.update_submission_status(conn, submission_id, new_status, set_photo_moderated=True)
        if updated:
            logger.info(f"Photo approved for submission {submission_id}. Triggering video generation (placeholder).")
            # Example: await trigger_video_generation_task(submission_id)
            try:
                # Create client per request (Simpler, but less performant. See note above)
                publisher = pubsub_v1.PublisherClient()
                topic_path = publisher.topic_path(settings.GOOGLE_CLOUD_PROJECT, settings.pub_sub_topic_id)

                # Prepare the message data (must be bytes)
                message_data = json.dumps({"submission_id": str(submission_id)}).encode("utf-8")

                # Publish the message. publish() returns a Future.
                future = publisher.publish(topic_path, data=message_data)

                # Optional: Wait for the publish acknowledgment (blocks).
                # You might remove .result() for higher throughput if you don't
                # need immediate confirmation within this request lifecycle.
                # Add a timeout to prevent indefinite blocking.
                publish_result = future.result(timeout=60)
                logger.info(
                    f"Successfully published message {publish_result} for submission {submission_id} to {topic_path}"
                )

            except Exception as e:
                logger.exception(f"Failed to publish Pub/Sub message for submission {submission_id}: {e}")
                # Raising 500 because a critical next step failed
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


@router.get(
    "/pending_videos",
    response_model=List[schemas.SubmissionDetail],
    summary="List submissions awaiting generated video approval",
)
async def get_pending_video_submissions(conn: Connection = Depends(database.get_db)):
    """Retrieves all submissions with status PENDING_VIDEO_APPROVAL."""
    submissions_db = await crud.get_submissions_by_status(conn, [schemas.SubmissionStatusEnum.PENDING_VIDEO_APPROVAL])
    result = []
    for sub in submissions_db:
        # Need both photo and video for context
        photo_url = await gcs.generate_signed_url(sub["uploaded_photo_gcs_path"])
        video_url = await gcs.generate_signed_url(sub["generated_video_gcs_path"])
        result.append(
            schemas.SubmissionDetail(
                id=sub["id"],
                submission_code=sub["submission_code"],
                status=schemas.SubmissionStatusEnum(sub["status"]),
                user_prompt=sub["user_prompt"],
                photo_url=photo_url,
                video_url=video_url,
                error_message=sub["error_message"],
                created_at=sub["created_at"],
                updated_at=sub["updated_at"],
            )
        )
    return result


@router.post(
    "/videos/{submission_id}/action",
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
