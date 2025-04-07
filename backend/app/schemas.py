import uuid
from pydantic import BaseModel, Field
from typing import Optional, List
from enum import Enum
from datetime import datetime


class SubmissionStatusEnum(str, Enum):
    PENDING_PHOTO_APPROVAL = "PENDING_PHOTO_APPROVAL"
    PHOTO_REJECTED = "PHOTO_REJECTED"
    PHOTO_APPROVED = "PHOTO_APPROVED"
    QUEUED_FOR_GENERATION = "QUEUED_FOR_GENERATION"  # Added for clarity
    GENERATING_VIDEO = "GENERATING_VIDEO"
    GENERATION_FAILED = "GENERATION_FAILED"
    PENDING_VIDEO_APPROVAL = "PENDING_VIDEO_APPROVAL"
    VIDEO_REJECTED = "VIDEO_REJECTED"
    VIDEO_APPROVED = "VIDEO_APPROVED"


class SubmissionBase(BaseModel):
    user_prompt: Optional[str] = None


class SubmissionCreateResponse(BaseModel):
    submission_code: str
    status: SubmissionStatusEnum
    message: str = "Submission received successfully."


class SubmissionStatusResponse(BaseModel):
    submission_code: str
    status: SubmissionStatusEnum
    video_url: Optional[str] = None  # Signed URL if approved
    error_message: Optional[str] = None
    created_at: datetime
    updated_at: datetime


# For Moderator views
class SubmissionDetail(BaseModel):
    id: uuid.UUID
    submission_code: str
    status: SubmissionStatusEnum
    user_prompt: Optional[str] = None
    photo_url: Optional[str] = None  # Signed URL
    video_url: Optional[str] = None  # Signed URL
    error_message: Optional[str] = None
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True  # Compatibility with ORM models / Row objects


class ModerationDecisionEnum(str, Enum):
    APPROVE = "approve"
    REJECT = "reject"


class ModerationAction(BaseModel):
    decision: ModerationDecisionEnum
