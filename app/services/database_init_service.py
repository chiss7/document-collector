import asyncio
import logging

from sqlalchemy import text
from alembic.config import Config
from alembic import command

from app.db.session import engine

logger = logging.getLogger(__name__)


def _run_alembic_upgrade() -> None:
    """Run pending Alembic migrations synchronously."""
    alembic_cfg = Config("alembic.ini")
    command.upgrade(alembic_cfg, "head")


async def init_database() -> None:
    """
    Initialize the database by applying all Alembic migrations.
    Tables are created only if they don't exist (handled by the migration).
    """
    try:
        loop = asyncio.get_event_loop()
        await loop.run_in_executor(None, _run_alembic_upgrade)
        logger.info("Database is up to date with all migrations")
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
