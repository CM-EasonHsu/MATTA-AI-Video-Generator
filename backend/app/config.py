import os
from pydantic_settings import BaseSettings
import logging

logger = logging.getLogger(__name__)

# Load .env file if it exists (useful for local development)
from dotenv import load_dotenv

load_dotenv()


class Settings(BaseSettings):
    api_key: str

    GOOGLE_CLOUD_PROJECT: str
    GOOGLE_CLOUD_REGION: str
    SERVICE_ACCOUNT_EMAIL: str

    # Cloud SQL specific settings
    DB_USER: str
    DB_PASS: str
    DB_NAME: str
    INSTANCE_CONNECTION_NAME: str  # Format: project:region:instance-id
    # Optional: specify private IP if needed and available
    # IP_TYPE: str = "PRIVATE" # Options: "PUBLIC", "PRIVATE" (defaults to PUBLIC if not set)

    gcs_bucket_name: str
    signed_url_expiration_seconds: int = 3600
    CLOUD_RUN_SERVICE_URL: str
    QUEUE_ID: str

    # VEO2 specific settings
    veo2_model_name: str = "veo-2.0-generate-001"
    veo2_video_duration: int = 5
    veo2_max_retries: int = 2
    veo2_aspect_ratio: str = "16:9"
    veo2_polling_interval: int = 15

    class Config:
        # If using .env file, pydantic-settings will load it automatically
        # You can remove the manual load_dotenv() above if preferred
        env_file = ".env"
        env_file_encoding = "utf-8"
        extra = "ignore"  # Ignore extra fields from environment


settings = Settings()
