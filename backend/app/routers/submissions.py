import logging
import io
import mimetypes
import re

from asyncpg import Connection
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form, status, Query
from typing import Optional

from app import schemas, crud, gcs, utils, database

logger = logging.getLogger(__name__)
router = APIRouter()


def is_valid_email_regex(email):
    pattern = r"^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$"
    return re.match(pattern, email) is not None


@router.post(
    "/submissions/",
    response_model=schemas.SubmissionCreateResponse,
    status_code=status.HTTP_201_CREATED,
    tags=["Submissions"],
    summary="Submit a photo for video generation",
)
async def create_submission(
    photo: UploadFile = File(..., description="Photo file to upload (e.g., JPEG, PNG)"),
    user_name: str = Form(..., description="Name of the user"),
    email: str = Form(None, description="Email address for notifications"),
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
    if content_type not in ["image/jpeg", "image/png", "image/heic"]:
        raise HTTPException(status_code=400, detail=f"Invalid file type: {content_type}. Only JPEG, PNG, HEIC allowed.")

    # Validate email format if provided
    if not is_valid_email_regex(email):
        raise HTTPException(status_code=400, detail="Invalid email format.")

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
        await crud.create_submission(conn, submission_code, photo_gcs_path, user_name, email, user_prompt)

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


@router.get("/submissions/stats/count/", tags=["Submissions"], summary="Count submissions by status")
async def count_submissions_by_status(
    status: schemas.SubmissionStatusEnum = Query(..., description="Filter submissions by this status"),
    conn: Connection = Depends(database.get_db),
):
    """
    Counts the number of submissions filtered by the provided status.
    """
    # Fetch count from the database using the new CRUD function
    count = await crud.count_submissions_by_status(conn, [status])

    if count is None:
        raise HTTPException(status_code=404, detail="No submissions found for this status.")

    return {"status": status.value, "count": count}


@router.get(
    "/submissions/",
    response_model=list[schemas.SubmissionDetail],
    tags=["Submissions"],
    summary="List submissions by status",
)
async def list_submissions_by_status(
    status: schemas.SubmissionStatusEnum = Query(
        ..., description="Filter submissions by this status"
    ),  # Use Query for query param
    conn: Connection = Depends(database.get_db),
    skip: int = Query(0, ge=0, description="Number of records to skip for pagination"),
    limit: int = Query(10, ge=1, le=50, description="Maximum number of records to return"),
    desc: Optional[bool] = Query(False, description="Sort results in descending order (latest first)"),
):
    """
    Retrieves a list of submissions filtered by the provided status.
    Includes pagination using skip and limit parameters.
    If a submission's video is approved, it includes a signed URL to view it.
    """
    db_submissions = await crud.get_submissions_by_status(conn, [status], skip, limit, desc)

    response_list: list[schemas.SubmissionDetail] = []
    for sub in db_submissions:
        photo_url = await gcs.generate_signed_url(sub["uploaded_photo_gcs_path"])
        video_url = None
        if sub["generated_video_gcs_path"]:
            video_url = await gcs.generate_signed_url(sub["generated_video_gcs_path"])
            if not video_url:
                logger.warning(
                    f"Could not generate signed URL for approved video: {sub['generated_video_gcs_path']} (Submission: {sub['submission_code']})"
                )

        # Construct the response object for each submission
        response_list.append(
            schemas.SubmissionDetail(
                id=sub["id"],
                submission_code=sub["submission_code"],
                status=schemas.SubmissionStatusEnum(sub["status"]),
                user_name=sub["user_name"],
                email=sub["email"],
                user_prompt=sub["user_prompt"],
                photo_url=photo_url,
                video_url=video_url,
                error_message=sub["error_message"],
                comment=sub["comment"],
                created_at=sub["created_at"],
                updated_at=sub["updated_at"],
            )
        )

    return response_list


@router.get(
    "/submissions/{submission_code}",
    response_model=schemas.SubmissionDetail,
    tags=["Submissions"],
    summary="Check the status of a submission",
)
async def get_submission(submission_code: str, conn: Connection = Depends(database.get_db)):
    """
    Retrieves the submission by its code.
    """
    sub = await crud.get_submission_by_code(conn, submission_code)
    if not sub:
        raise HTTPException(status_code=404, detail="Submission not found.")

    photo_url = await gcs.generate_signed_url(sub["uploaded_photo_gcs_path"])
    video_url = None
    if sub["generated_video_gcs_path"]:
        video_url = await gcs.generate_signed_url(sub["generated_video_gcs_path"])
        if not video_url:
            logger.warning(
                f"Could not generate signed URL for approved video: {sub['generated_video_gcs_path']} (Submission: {sub['submission_code']})"
            )

    return schemas.SubmissionDetail(
        id=sub["id"],
        submission_code=sub["submission_code"],
        status=schemas.SubmissionStatusEnum(sub["status"]),
        user_name=sub["user_name"],
        email=sub["email"],
        user_prompt=sub["user_prompt"],
        photo_url=photo_url,
        video_url=video_url,
        error_message=sub["error_message"],
        comment=sub["comment"],
        created_at=sub["created_at"],
        updated_at=sub["updated_at"],
    )
