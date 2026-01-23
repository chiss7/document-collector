# app/api/routes/publications.py
from fastapi import APIRouter, Depends
from typing import Optional

from app.services.publication_service import get_all_publications
from app.core.security import get_current_user
from app.schemas.publication import PublicationDTO
from app.schemas.publication_query import PublicationQuery
from app.services.publication_paged_service import get_publications_paged

router = APIRouter(prefix="/publications", tags=["Publications"])


@router.get("")
async def list_publications(limit: Optional[int] = None, offset: int = 0):
    publications = await get_all_publications(limit=limit, offset=offset)
    # Use Pydantic DTOs (from_attributes=True) to serialize ORM objects
    return [PublicationDTO.model_validate(p).model_dump() for p in publications]


@router.post("/paged")
async def list_publications_paged(query: PublicationQuery):
    try:
        result = await get_publications_paged(query)
    except ValueError as e:
        from fastapi import HTTPException

        raise HTTPException(status_code=400, detail=str(e))
    # serialize items
    items = [PublicationDTO.model_validate(p).model_dump() for p in result["items"]]
    return {"items": items, "total": result["total"], "page": result["page"], "size": result["size"]}