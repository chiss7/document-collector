from typing import Optional
from sqlalchemy.ext.asyncio import AsyncSession
from app.repositories.publication_repository import PublicationRepository
from app.db.session import AsyncSessionLocal


async def get_all_publications(session: Optional[AsyncSession] = None, limit: int | None = None, offset: int = 0):
    """Return list of Publication ORM objects. If no session provided, create one."""
    own = session is None
    if own:
        async with AsyncSessionLocal() as session:
            return await PublicationRepository.findAll(session, limit=limit, offset=offset)
    return await PublicationRepository.findAll(session, limit=limit, offset=offset)
