import uuid
import asyncpg
from typing import List, Optional
from app.schemas import SubmissionStatusEnum
from datetime import datetime, timezone
import logging

logger = logging.getLogger(__name__)


async def create_submission(
    conn: asyncpg.Connection,
    code: str,
    photo_gcs_path: str,
    prompt: Optional[str] = None,
) -> uuid.UUID:
    """Creates a new submission record."""
    try:
        query = """
            INSERT INTO submissions (submission_code, uploaded_photo_gcs_path, user_prompt, status)
            VALUES ($1, $2, $3, $4)
            RETURNING id;
        """
        result = await conn.fetchrow(
            query,
            code,
            photo_gcs_path,
            prompt,
            SubmissionStatusEnum.PENDING_PHOTO_APPROVAL.value,
        )
        if result:
            logger.info(f"Created submission with code {code}, ID: {result['id']}")
            return result["id"]
        else:
            raise Exception("Failed to retrieve ID after submission creation.")
    except Exception as e:
        logger.error(f"Error creating submission for code {code}: {e}", exc_info=True)
        raise


async def get_submission_by_code(conn: asyncpg.Connection, code: str) -> Optional[asyncpg.Record]:
    """Fetches a submission by its user-facing code."""
    try:
        query = "SELECT * FROM submissions WHERE submission_code = $1;"
        return await conn.fetchrow(query, code)
    except Exception as e:
        logger.error(f"Error fetching submission by code {code}: {e}", exc_info=True)
        raise


async def get_submission_by_id(conn: asyncpg.Connection, submission_id: uuid.UUID) -> Optional[asyncpg.Record]:
    """Fetches a submission by its internal UUID."""
    try:
        query = "SELECT * FROM submissions WHERE id = $1;"
        return await conn.fetchrow(query, submission_id)
    except Exception as e:
        logger.error(f"Error fetching submission by ID {submission_id}: {e}", exc_info=True)
        raise


async def get_submissions_by_status(
    conn: asyncpg.Connection, statuses: List[SubmissionStatusEnum]
) -> List[asyncpg.Record]:
    """Fetches submissions matching a list of statuses."""
    try:
        # Convert enum values to strings for the query
        status_values = [s.value for s in statuses]
        # Use ANY($1::submission_status[]) for array comparison
        query = """
            SELECT * FROM submissions
            WHERE status = ANY($1::submission_status[])
            ORDER BY created_at ASC;
        """
        return await conn.fetch(query, status_values)
    except Exception as e:
        logger.error(f"Error fetching submissions by status {statuses}: {e}", exc_info=True)
        raise


async def update_submission_status(
    conn: asyncpg.Connection,
    submission_id: uuid.UUID,
    new_status: SubmissionStatusEnum,
    video_gcs_path: Optional[str] = None,
    error_message: Optional[str] = None,
    set_photo_moderated: bool = False,
    set_video_moderated: bool = False,
) -> bool:
    """Updates the status and optionally other fields of a submission."""
    try:
        fields_to_update = {
            "status": new_status.value,
            "error_message": error_message,
            "updated_at": datetime.now(timezone.utc),  # Explicitly set here, DB trigger also works
        }
        if video_gcs_path is not None:
            fields_to_update["generated_video_gcs_path"] = video_gcs_path
        if set_photo_moderated:
            fields_to_update["photo_moderated_at"] = datetime.now(timezone.utc)
        if set_video_moderated:
            fields_to_update["video_moderated_at"] = datetime.now(timezone.utc)

        # Build the SET part of the query dynamically
        set_clauses = []
        values = []
        i = 1
        for key, value in fields_to_update.items():
            set_clauses.append(f"{key} = ${i}")
            values.append(value)
            i += 1

        # Add the submission ID for the WHERE clause
        values.append(submission_id)
        where_clause_index = len(values)

        query = f"""
            UPDATE submissions
            SET {', '.join(set_clauses)}
            WHERE id = ${where_clause_index};
        """

        result = await conn.execute(query, *values)
        # Check if any row was updated
        updated = result == "UPDATE 1"
        if updated:
            logger.info(f"Updated submission {submission_id} to status {new_status.value}")
        else:
            logger.warning(
                f"Attempted to update submission {submission_id} but no rows were affected (might not exist?)."
            )
        return updated
    except Exception as e:
        logger.error(f"Error updating submission {submission_id} status to {new_status.value}: {e}", exc_info=True)
        raise
