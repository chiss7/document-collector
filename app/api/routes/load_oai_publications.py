from fastapi import APIRouter, HTTPException
from typing import Optional
import asyncio

from app.db.session import AsyncSessionLocal
from app.services.oai_service import fetch_and_save_oai_publications
from sqlalchemy import select, func
from app.models.publication import Publication
from app.models.excluded_publication import ExcludedPublication

router = APIRouter(prefix="/load", tags=["Load Publications"])


async def run_fetch_and_save(payload: Optional[dict] = None):
    async with AsyncSessionLocal() as session:
        method = None
        from_date = None
        if isinstance(payload, dict):
            method = (payload.get("method") or payload.get("classifier_method") or "regex").lower()
            from_date = payload.get("from_date")
        async with session.begin():
            return await fetch_and_save_oai_publications(
                session,
                classifier_method=method or "regex",
                from_date=from_date,
            )


@router.post("/oai")
async def start_oai_loading(payload: Optional[dict] = None, background: bool = True):
    """Start loading OAI journal publications.

    - ``payload.method`` / ``payload.classifier_method``: classification method
      (``regex``, ``embeddings``, ``transformers``). Default: ``regex``.
    - ``payload.from_date``: optional ISO date string (``YYYY-MM-DD``) to
      restrict harvesting to records from that date onward.
    - If ``background=True`` (default) the job runs in the background and the
      endpoint returns immediately.
    - If ``background=False`` the job runs synchronously and returns the count
      of new IA publications saved.
    """
    if background:
        asyncio.create_task(run_fetch_and_save(payload))
        return {"status": "Loading OAI publications started in background"}

    try:
        saved = await run_fetch_and_save(payload)
        return {"status": "ok", "saved": saved}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/oai/status")
async def load_oai_status():
    async with AsyncSessionLocal() as session:
        stmt1 = select(func.count(Publication.id))
        stmt2 = select(func.count(ExcludedPublication.id))
        res1 = await session.execute(stmt1)
        res2 = await session.execute(stmt2)
        pubs = int(res1.scalar_one())
        excs = int(res2.scalar_one())
        return {"publications": pubs, "excluded_publications": excs}
