import logging
import uvicorn

from fastapi import FastAPI, Depends, Request, status, HTTPException, Security
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from fastapi.security.api_key import APIKeyHeader
from starlette.status import HTTP_403_FORBIDDEN

from app.routers import submissions, moderation, generation
from app.database import connect_db, close_db
from app.config import settings

# Configure logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)


API_KEY = settings.api_key
API_KEY_NAME = "X-API-Key"
api_key_header = APIKeyHeader(name=API_KEY_NAME, auto_error=False)


def get_api_key(api_key: str = Security(api_key_header)):
    if api_key == API_KEY:
        return api_key
    raise HTTPException(status_code=HTTP_403_FORBIDDEN, detail="Could not validate API KEY")


app = FastAPI(
    title="AI Video Generator Backend",
    description="API service to handle photo submissions, video generation tracking, and moderation.",
    version="0.1.0",
    dependencies=[Depends(get_api_key)],
)


# --- Event Handlers ---
@app.on_event("startup")
async def startup_event():
    logger.info("Application startup...")
    try:
        await connect_db()  # Initialize DB pool
        # Initialize GCS Client (already done in gcs.py, just log)
        if settings.gcs_bucket_name:  # Check if bucket name is configured
            logger.info(f"GCS Bucket configured: {settings.gcs_bucket_name}")
        else:
            logger.error("GCS_BUCKET_NAME is not configured!")
            # Optionally raise an error to prevent startup if GCS is critical
            # raise RuntimeError("GCS_BUCKET_NAME must be set")
    except Exception as e:
        logger.error(f"FATAL: Application startup failed: {e}", exc_info=True)
        # Depending on deployment, might need to exit explicitly
        # sys.exit(1)


@app.on_event("shutdown")
async def shutdown_event():
    logger.info("Application shutdown...")
    await close_db()  # Close DB pool gracefully
    logger.info("Application shutdown complete.")


# --- Exception Handlers ---
@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    # Log the details of the validation error
    logger.warning(f"Validation error for request {request.url}: {exc.errors()}")
    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        content={"detail": exc.errors()},
    )


# Could add more generic exception handlers if needed

# --- Routers ---
app.include_router(submissions.router)
app.include_router(moderation.router)
app.include_router(generation.router)


@app.get("/", tags=["Health Check"])
async def read_root():
    """Health check endpoint."""
    return {"status": "ok"}


# --- Main execution block for local running ---
if __name__ == "__main__":
    uvicorn.run("app.api:app", host="0.0.0.0", port=8080, reload=True)
