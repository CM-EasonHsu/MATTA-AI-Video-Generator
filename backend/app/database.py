import asyncpg
import asyncio
from app.config import settings
import logging
from google.cloud.sql.connector import Connector, IPTypes, create_async_connector

logger = logging.getLogger(__name__)

pool: asyncpg.Pool | None = None
connector: Connector | None = None


async def connect_db():
    """Initializes the database connection pool using Cloud SQL Python Connector."""
    global pool, connector
    if pool is not None:
        logger.info("Database connection pool already initialized.")
        return

    logger.info("Initializing database connection pool via Cloud SQL Connector...")

    try:
        # Determine IP type preference (optional, defaults to PUBLIC)
        ip_type = IPTypes.PRIVATE if getattr(settings, "IP_TYPE", "PUBLIC").upper() == "PRIVATE" else IPTypes.PUBLIC
        if ip_type == IPTypes.PRIVATE:
            logger.info("Attempting to connect using Private IP.")
        else:
            logger.info("Attempting to connect using Public IP (default).")

        # Create Connector instance
        connector = await create_async_connector()

        # Define connection factory for asyncpg.create_pool
        async def getconn(instance_connection_name, **kwargs) -> asyncpg.Connection:
            return await connector.connect_async(
                instance_connection_name,  # Cloud SQL instance connection name
                "asyncpg",  # DB driver
                user=settings.DB_USER,
                password=settings.DB_PASS,
                db=settings.DB_NAME,
                **kwargs,
            )

        # Create the asyncpg connection pool using the connector
        pool = await asyncpg.create_pool(settings.INSTANCE_CONNECTION_NAME, connect=getconn, min_size=1, max_size=5)

        logger.info("Database connection pool initialized successfully via Cloud SQL Connector.")

    except Exception as e:
        logger.error(f"Failed to initialize database connection pool: {e}", exc_info=True)
        pool = None  # Ensure pool is None if connection fails
        if connector:
            await connector.close_async()
            connector = None
        raise  # Re-raise the exception to prevent app startup if DB fails


async def get_db_connection() -> asyncpg.Connection:
    """Gets a connection from the pool."""
    global pool
    if pool is None:
        raise RuntimeError("Database pool not initialized or connection lost. Check logs.")
    try:
        conn = await pool.acquire()
        return conn
    except Exception as e:
        logger.error(f"Error acquiring database connection from pool: {e}")
        raise


async def release_db_connection(conn: asyncpg.Connection):
    """Releases a connection back to the pool."""
    global pool
    if pool is None:
        logger.warning("Attempted to release connection but pool is None (already closed or never initialized).")
        return  # Pool already closed or never initialized
    try:
        # Release the connection back to the asyncpg pool
        await pool.release(conn)
    except Exception as e:
        # Log error but don't raise, as the app might be shutting down
        logger.error(f"Error releasing database connection to pool: {e}")


async def close_db():
    """Closes the database connection pool and the Cloud SQL Connector."""
    global pool, connector
    if pool:
        logger.info("Closing database connection pool...")
        try:
            # Close the asyncpg pool first
            await pool.close()
            logger.info("Database connection pool closed.")
        except Exception as e:
            logger.error(f"Error closing database pool: {e}", exc_info=True)
        finally:
            pool = None  # Ensure pool is marked as closed

    if connector:
        logger.info("Closing Cloud SQL Connector...")
        try:
            # Close the connector instance
            await connector.close_async()  # Use close_async for the async connector
            logger.info("Cloud SQL Connector closed.")
        except Exception as e:
            logger.error(f"Error closing Cloud SQL Connector: {e}", exc_info=True)
        finally:
            connector = None  # Ensure connector is marked as closed


# Dependency for FastAPI endpoints
async def get_db():
    """FastAPI dependency to get a DB connection."""
    conn = None  # Initialize conn to None
    try:
        conn = await get_db_connection()
        yield conn
    except Exception as e:
        logger.error(f"Error in get_db dependency during yield: {e}", exc_info=True)
        # Depending on your error handling strategy, you might want to raise an HTTPException here
        # from fastapi import HTTPException
        # raise HTTPException(status_code=503, detail="Database connection error")
        raise  # Re-raise the original exception if not handling via HTTPException
    finally:
        if conn:
            await release_db_connection(conn)
