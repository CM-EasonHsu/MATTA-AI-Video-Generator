import shortuuid
import os
import mimetypes

from typing import Optional


def generate_submission_code() -> str:
    """Generates a unique, short submission code."""
    # shortuuid generates URL-safe base57 codes by default
    return shortuuid.uuid()[:10]  # Adjust length as needed


def get_file_extension(filename: str, content_type: Optional[str] = None) -> str:
    """Gets a safe file extension from filename or content type."""
    # Prefer extension from filename if available
    if filename and "." in filename:
        ext = os.path.splitext(filename)[1].lower()
        # Basic validation (add more mimetypes if needed)
        if ext in [".jpg", ".jpeg", ".png", ".gif", ".webp"]:
            return ext

    # Fallback to guessing from content type
    if content_type:
        guessed_ext = mimetypes.guess_extension(content_type)
        if guessed_ext:
            # Map common types if necessary (e.g., .jpe for .jpg)
            map = {".jpe": ".jpg"}
            return map.get(guessed_ext, guessed_ext).lower()

    # Default fallback (or raise error)
    return ".jpg"  # Defaulting to jpg, consider if this is safe enough
