import os
from pydantic_settings import BaseSettings
import logging

logger = logging.getLogger(__name__)

# Load .env file if it exists (useful for local development)
from dotenv import load_dotenv

load_dotenv()


class Settings(BaseSettings):
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
    pub_sub_topic_id: str
    CLOUD_RUN_SERVICE_URL: str
    QUEUE_ID: str

    # Worker specific settings
    veo2_api_base_url: str = "https://veo2.googleapis.com"  # Default hypothetical
    veo2_api_key: str = None
    polling_interval_seconds: int = 15
    max_polling_attempts: int = 80

    class Config:
        # If using .env file, pydantic-settings will load it automatically
        # You can remove the manual load_dotenv() above if preferred
        env_file = ".env"
        env_file_encoding = "utf-8"
        extra = "ignore"  # Ignore extra fields from environment


settings = Settings()

# Add a check for the API key
if not settings.veo2_api_key:
    logger.warning("VEO2_API_KEY is not set. Veo2 API calls will likely fail.")
    # You might want to raise an error if the key is essential for the worker


# Ensure credentials are set if running locally without implicit auth
# if not os.getenv("GOOGLE_APPLICATION_CREDENTIALS") and not os.getenv("FUNCTIONS_SIGNATURE_TYPE"): # FUNCTIONS_SIGNATURE_TYPE implies Cloud Functions env
#     # In a real app, you might raise an error or handle based on environment
#     print("Warning: GOOGLE_APPLICATION_CREDENTIALS not set. GCS operations might fail if not in a GCP environment.")
