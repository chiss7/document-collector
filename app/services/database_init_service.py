"""
Service for initializing database tables on application startup.
Verifies that all necessary tables are created, and creates them if they don't exist.
"""

import logging
from sqlalchemy.ext.asyncio import AsyncEngine
from sqlalchemy import inspect, text
from app.db.base import Base
from app.db.session import engine

logger = logging.getLogger(__name__)


async def init_database() -> None:
    """
    Initialize the database by creating all tables defined in the models.
    This function is called during application startup.
    
    If tables already exist, they are not recreated.
    If tables don't exist, they are created.
    """
    try:
        # Create all tables (only creates tables that don't exist)
        async with engine.begin() as conn:
            # Use sync inspection via run_sync to avoid async IO in wrong context
            def _get_table_names(sync_conn):
                return inspect(sync_conn).get_table_names()

            existing_tables = await conn.run_sync(_get_table_names)
            
            # List of expected tables
            expected_tables = {
                "publications",
                "subjects",
                "publication_subjects",
                "contributors",
                "social_media_records",
                "excluded_publication"
            }
            
            missing_tables = expected_tables - set(existing_tables)
            
            if missing_tables:
                logger.info(f"Creating missing tables: {missing_tables}")
                await conn.run_sync(Base.metadata.create_all)
                logger.info(f"Successfully created {len(missing_tables)} table(s)")
            else:
                logger.info("All required tables already exist")
            
            # Log all existing tables
            all_tables = set(existing_tables)
            logger.debug(f"Current database tables: {all_tables}")
            
    except Exception as e:
        logger.error(f"Error initializing database: {str(e)}", exc_info=True)
        raise


async def verify_database_connection() -> bool:
    """
    Verify that the database connection is working.
    
    Returns:
        bool: True if connection is successful, False otherwise
    """
    try:
        async with engine.begin() as conn:
            await conn.execute(text("SELECT 1"))
        logger.info("Database connection verified successfully")
        return True
    except Exception as e:
        logger.error(f"Database connection failed: {str(e)}", exc_info=True)
        return False
