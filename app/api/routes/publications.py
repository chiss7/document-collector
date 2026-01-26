# app/api/routes/publications.py
from fastapi import APIRouter, Depends, Request, Form, File, UploadFile
from typing import Optional
import json

from app.services.publication_service import get_all_publications
from app.core.security import get_current_user
from app.schemas.publication import PublicationDTO
from app.schemas.publication_query import PublicationQuery
from app.services.publication_paged_service import get_publications_paged
from app.schemas.publication import PublicationCreateDTO
from app.services.publication_service import create_publication

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


@router.post("")
async def create_single_publication(request: Request, payload_json: str | None = Form(None), pdf_file: UploadFile | None = File(None)):
    """Accepts either a JSON body or a multipart form with a `payload_json` field (JSON string) and optional `pdf_file`."""
    try:
        if payload_json:
            print(payload_json)
            payload = PublicationCreateDTO.model_validate_json(payload_json)
        else:
            body = await request.json()
            payload = PublicationCreateDTO.model_validate(body)

        pub_id = await create_publication(payload, pdf_file=pdf_file)
    except Exception as e:
        from fastapi import HTTPException

        raise HTTPException(status_code=400, detail=str(e))
    return {"id": pub_id}