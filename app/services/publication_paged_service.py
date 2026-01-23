from typing import Optional
from app.db.session import AsyncSessionLocal
from app.repositories.publication_repository import PublicationRepository
from app.schemas.publication_query import PublicationQuery


async def get_publications_paged(query: PublicationQuery, session: Optional[object] = None):
    own = session is None
    if own:
        async with AsyncSessionLocal() as s:
            return await PublicationRepository.find_paginated(
                s, filters=query.filters, page=query.page, size=query.size, order_by=query.order_by, order_dir=query.order_dir
            )
    return await PublicationRepository.find_paginated(
        session, filters=query.filters, page=query.page, size=query.size, order_by=query.order_by, order_dir=query.order_dir
    )
