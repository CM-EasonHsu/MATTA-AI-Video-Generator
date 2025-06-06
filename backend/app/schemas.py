import uuid
from pydantic import BaseModel, Field, HttpUrl
from typing import Optional, List
from enum import Enum
from datetime import datetime


class SubmissionStatusEnum(str, Enum):
    PENDING_PHOTO_APPROVAL = "PENDING_PHOTO_APPROVAL"
    PHOTO_REJECTED = "PHOTO_REJECTED"
    PHOTO_APPROVED = "PHOTO_APPROVED"
    GENERATING_VIDEO = "GENERATING_VIDEO"
    GENERATION_FAILED = "GENERATION_FAILED"
    PENDING_GENERATION_RETRY = "PENDING_GENERATION_RETRY"
    PENDING_VIDEO_APPROVAL = "PENDING_VIDEO_APPROVAL"
    VIDEO_REJECTED = "VIDEO_REJECTED"
    VIDEO_APPROVED = "VIDEO_APPROVED"


class SubmissionBase(BaseModel):
    user_prompt: Optional[str] = None


class SubmissionCreateResponse(BaseModel):
    submission_code: str
    status: SubmissionStatusEnum
    message: str = "Submission received successfully."


class SubmissionDetail(BaseModel):
    id: uuid.UUID
    submission_code: str
    status: SubmissionStatusEnum
    user_name: Optional[str] = None
    email: Optional[str] = None
    user_prompt: Optional[str] = None
    photo_url: Optional[str] = None  # Signed URL
    video_url: Optional[str] = None  # Signed URL
    error_message: Optional[str] = None
    comment: Optional[str] = None
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True  # Compatibility with ORM models / Row objects


class ModerationDecisionEnum(str, Enum):
    APPROVE = "approve"
    REJECT = "reject"


class ModerationAction(BaseModel):
    decision: ModerationDecisionEnum
    reason: Optional[str] = Field(None, description="Reason for the moderation decision")


class RetryRequest(BaseModel):
    prompt: str


class VideoPromptRequest(BaseModel):
    """
    Request model for generating a video prompt using Veo2.
    """

    photo_uri: str = Field(..., description="GCS URI of the photo to generate a prompt for")
    description: Optional[str] = Field(None, description="Optional description to guide prompt generation")


class VideoPromptResponse(BaseModel):
    """
    Response model for the generated video prompt.
    """

    prompt: str = Field(..., description="The generated video prompt")
    suggestions: List[str] = Field(
        default_factory=list, description="Optional list of suggestions to improve the prompt"
    )
