import logging
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form, status, Query
from app import schemas, crud, gcs, utils, database
from asyncpg import Connection
import io
import mimetypes  # For getting content type
from typing import Optional

logger = logging.getLogger(__name__)
router = APIRouter()


@router.post(
    "/submissions/",
    response_model=schemas.SubmissionCreateResponse,
    status_code=status.HTTP_201_CREATED,
    tags=["Submissions"],
    summary="Submit a photo for video generation",
)
async def create_submission(
    photo: UploadFile = File(..., description="Photo file to upload (e.g., JPEG, PNG)"),
    user_prompt: Optional[str] = Form(None, description="Optional text prompt for video generation"),
    conn: Connection = Depends(database.get_db),
):
    """
    Handles user photo uploads:
    - Generates a unique submission code.
    - Uploads the photo to GCS under 'pending_photos/'.
    - Creates a database record with status PENDING_PHOTO_APPROVAL.
    - Returns the submission code.
    """
    if not photo:
        raise HTTPException(status_code=400, detail="No photo file provided.")

    # Validate content type (basic check)
    content_type = photo.content_type
    if content_type not in ["image/jpeg", "image/png", "image/gif", "image/webp"]:
        raise HTTPException(
            status_code=400, detail=f"Invalid file type: {content_type}. Only JPEG, PNG, GIF, WEBP allowed."
        )

    submission_code = utils.generate_submission_code()
    file_extension = utils.get_file_extension(photo.filename, content_type)
    destination_blob_name = f"pending_photos/{submission_code}{file_extension}"

    try:
        # Read file content into memory (for small files) or stream if large
        file_content = await photo.read()
        file_stream = io.BytesIO(file_content)

        # Upload to GCS
        photo_gcs_path = await gcs.upload_to_gcs(file_stream, destination_blob_name, content_type)

        # Create DB record (use await with async crud function)
        await crud.create_submission(conn, submission_code, photo_gcs_path, user_prompt)

        return schemas.SubmissionCreateResponse(
            submission_code=submission_code, status=schemas.SubmissionStatusEnum.PENDING_PHOTO_APPROVAL
        )

    except HTTPException as http_exc:
        # Re-raise HTTP exceptions directly
        raise http_exc
    except Exception as e:
        logger.error(f"Error creating submission {submission_code}: {e}", exc_info=True)
        # Consider cleanup: deleting GCS file if DB insert fails?
        raise HTTPException(status_code=500, detail=f"Internal server error during submission: {e}")
    finally:
        await photo.close()  # Ensure file handle is closed


@router.get(
    "/submissions/",
    response_model=list[schemas.SubmissionStatusResponse],  # Returns a list
    tags=["Submissions"],
    summary="List submissions by status",
)
async def list_submissions_by_status(
    status: schemas.SubmissionStatusEnum = Query(
        ..., description="Filter submissions by this status"
    ),  # Use Query for query param
    conn: Connection = Depends(database.get_db),
    skip: int = Query(0, ge=0, description="Number of records to skip for pagination"),
    limit: int = Query(100, ge=1, le=1000, description="Maximum number of records to return"),
):
    """
    Retrieves a list of submissions filtered by the provided status.
    Includes pagination using skip and limit parameters.
    If a submission's video is approved, it includes a signed URL to view it.
    """
    # Fetch submissions from the database using the new CRUD function
    # Pass status.value to get the string representation for the DB query
    db_submissions = await crud.get_submissions_by_status(conn, [status], skip, limit)

    response_list: list[schemas.SubmissionStatusResponse] = []
    for submission in db_submissions:
        video_url = None
        # Generate signed URL only if the status matches VIDEO_APPROVED
        # Check using the string value fetched from DB before casting
        if submission["status"] == schemas.SubmissionStatusEnum.VIDEO_APPROVED.value:
            if submission["generated_video_gcs_path"]:
                video_url = await gcs.generate_signed_url(submission["generated_video_gcs_path"])
                if not video_url:
                    logger.warning(
                        f"Could not generate signed URL for approved video: {submission['generated_video_gcs_path']} (Submission: {submission['submission_code']})"
                    )
            else:
                logger.warning(f"Approved video GCS path is missing for submission: {submission['submission_code']}")

        # Construct the response object for each submission
        response_list.append(
            schemas.SubmissionStatusResponse(
                submission_code=submission["submission_code"],
                status=schemas.SubmissionStatusEnum(submission["status"]),  # Cast DB string to Enum
                video_url=video_url,
                error_message=submission["error_message"],
                created_at=submission["created_at"],
                updated_at=submission["updated_at"],
            )
        )

    return response_list


@router.get(
    "/submissions/{submission_code}/status",
    response_model=schemas.SubmissionStatusResponse,
    tags=["Submissions"],
    summary="Check the status of a submission",
)
async def get_submission_status(submission_code: str, conn: Connection = Depends(database.get_db)):
    """
    Retrieves the status of a submission by its code.
    If the video is approved, it includes a signed URL to view it.
    """
    submission = await crud.get_submission_by_code(conn, submission_code)
    if not submission:
        raise HTTPException(status_code=404, detail="Submission not found.")

    video_url = None
    if submission["status"] == schemas.SubmissionStatusEnum.VIDEO_APPROVED.value:
        video_url = await gcs.generate_signed_url(submission["generated_video_gcs_path"])
        if not video_url:
            # Log warning but don't fail the request, just indicate URL is unavailable
            logger.warning(
                f"Could not generate signed URL for approved video: {submission['generated_video_gcs_path']}"
            )

    return schemas.SubmissionStatusResponse(
        submission_code=submission["submission_code"],
        status=schemas.SubmissionStatusEnum(submission["status"]),  # Cast to Enum
        video_url=video_url,
        error_message=submission["error_message"],
        created_at=submission["created_at"],
        updated_at=submission["updated_at"],
    )
