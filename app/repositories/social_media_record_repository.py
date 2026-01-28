from typing import List
import logging
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.exc import IntegrityError

from app.models.social_media_record import SocialMediaRecord


logger = logging.getLogger(__name__)
if not logging.getLogger().hasHandlers():
    logging.basicConfig(level=logging.INFO)


class SocialMediaRecordRepository:
    @staticmethod
    async def saveAll(session: AsyncSession, records: List[SocialMediaRecord], chunk_size: int = 500) -> int:
        logger.info("Starting saveAll: total records=%d", len(records))
        if not records:
            return 0

        if not all(isinstance(r, SocialMediaRecord) for r in records):
            raise TypeError("`records` must be a list of SocialMediaRecord instances")

        total = 0
        for i in range(0, len(records), chunk_size):
            chunk = records[i : i + chunk_size]
            if not chunk:
                continue
            logger.info("Attempting to save chunk %d (size=%d)", i // chunk_size + 1, len(chunk))
            try:
                # use a transaction if none active
                started_tx = False
                if not session.in_transaction():
                    started_tx = True
                    async with session.begin():
                        session.add_all(chunk)
                else:
                    session.add_all(chunk)
                    await session.flush()
                total += len(chunk)
                logger.info("Successfully inserted chunk %d (inserted=%d)", i // chunk_size + 1, len(chunk))
            except IntegrityError as ie:
                logger.warning("IntegrityError on chunk %d: %s", i // chunk_size + 1, str(ie))
                # Some primary key conflicts; fallback to single inserts
                try:
                    if session.in_transaction() and started_tx:
                        await session.rollback()
                except Exception:
                    logger.exception("Rollback failed after IntegrityError for chunk %d", i // chunk_size + 1)

                for idx, rec in enumerate(chunk, start=1):
                    try:
                        started_single = False
                        logger.debug("Inserting record %d of chunk %d: id=%s", idx, i // chunk_size + 1, getattr(rec, "id", None))
                        if not session.in_transaction():
                            started_single = True
                            async with session.begin():
                                session.add(rec)
                        else:
                            session.add(rec)
                            await session.flush()
                        total += 1
                    except IntegrityError:
                        try:
                            if session.in_transaction() and started_single:
                                await session.rollback()
                        except Exception:
                            logger.exception("Rollback failed for single insert id=%s", getattr(rec, "id", None))
                        logger.info("Skipped duplicate record id=%s", getattr(rec, "id", None))
                        # ignore duplicate primary key
                    except Exception as e:
                        try:
                            if session.in_transaction() and started_single:
                                await session.rollback()
                        except Exception:
                            logger.exception("Rollback failed after error inserting id=%s", getattr(rec, "id", None))
                        logger.exception("Failed to insert record id=%s: %s", getattr(rec, "id", None), str(e))
                        # continue with other records

        logger.info("Finished saveAll: total inserted=%d", total)
        return total
