# app/api/routes/load_publications.py
from fastapi import APIRouter, HTTPException
from typing import Optional
import asyncio

from app.db.session import AsyncSessionLocal
from app.services.dspace_service import fetch_and_save_ia_publications
from sqlalchemy import select, func
from app.models.publication import Publication
from app.models.excluded_publication import ExcludedPublication

router = APIRouter(prefix="/load", tags=["Load Publications"])


async def run_fetch_and_save():
  async with AsyncSessionLocal() as session:
    # Begin an explicit transaction for the whole run so commits are
    # applied at the end and visible to other sessions.
    async with session.begin():
      return await fetch_and_save_ia_publications(session)


@router.post("")
async def start_loading(payload: Optional[dict] = None, background: bool = False):
    """Start loading publications.

    - If `background` is true (default) the job is scheduled and the endpoint
      returns immediately with a started message.
    - If `background` is false the endpoint runs the job synchronously and
      returns `{"status": "ok", "saved": N}` or raises HTTP 500 on error.
    """
    if background:
        # schedule in current event loop
        asyncio.create_task(run_fetch_and_save())
        return {"status": "Loading publications started in background"}

    try:
        saved = await run_fetch_and_save()
        return {"status": "ok", "saved": saved}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/status")
async def load_status():
    async with AsyncSessionLocal() as session:
      stmt1 = select(func.count(Publication.id))
      stmt2 = select(func.count(ExcludedPublication.id))
      res1 = await session.execute(stmt1)
      res2 = await session.execute(stmt2)
      pubs = int(res1.scalar_one())
      excs = int(res2.scalar_one())
      return {"publications": pubs, "excluded_publications": excs}
