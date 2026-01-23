from typing import List, Set
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.models.excluded_publication import ExcludedPublication


class ExcludedPublicationRepository:
    """Repository for simple operations on the `excluded_publication` table."""

    @staticmethod
    async def get_all_urls(session: AsyncSession) -> Set[str]:
        stmt = select(ExcludedPublication.url)
        res = await session.execute(stmt)
        return set(res.scalars().all())

    @staticmethod
    async def saveAll(session: AsyncSession, excluded: List[ExcludedPublication]) -> Set[str]:
        """Insert excluded publications in bulk, avoiding duplicates by `url`.

        Returns number of rows inserted.
        """
        if not excluded:
            return set()

        urls = [e.url for e in excluded if getattr(e, "url", None)]
        if not urls:
            return 0

        stmt = select(ExcludedPublication.url).where(ExcludedPublication.url.in_(urls))
        res = await session.execute(stmt)
        existing = set(res.scalars().all())

        to_insert = [e for e in excluded if e.url not in existing]
        if not to_insert:
            return set()

        inserted_urls: Set[str] = set()
        started_tx = False
        if not session.in_transaction():
            started_tx = True
            async with session.begin():
                session.add_all(to_insert)
            # after commit, all to_insert have been persisted
            inserted_urls = {e.url for e in to_insert}
        else:
            session.add_all(to_insert)
            try:
                await session.flush()
                inserted_urls = {e.url for e in to_insert}
            except Exception:
                # if flush fails and we started a tx earlier, rollback
                if started_tx and session.in_transaction():
                    try:
                        await session.rollback()
                    except Exception:
                        pass
                raise

        return inserted_urls
