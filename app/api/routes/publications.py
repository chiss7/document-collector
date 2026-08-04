# app/api/routes/publications.py
from fastapi import APIRouter, Depends, Request, Form, File, UploadFile, HTTPException
from typing import Optional
import json

from app.services.publication_service import get_all_publications, create_publication, update_publication, delete_publication, get_filter_options, get_ai_publication_stats
from app.core.security import get_current_user
from app.schemas.publication import PublicationDTO, PublicationCreateDTO, PublicationUpdateDTO, FilterOptionsResponse, AIPublicationStatsResponse
from app.schemas.publication_query import PublicationQuery
from app.schemas.response import GenericResponse
from app.services.publication_paged_service import get_publications_paged

router = APIRouter(prefix="/publications", tags=["Publications"])


@router.get("/filter-options", response_model=FilterOptionsResponse)
async def list_filter_options():
    return await get_filter_options()


@router.get("/ai-stats", response_model=AIPublicationStatsResponse)
async def list_ai_publication_stats():
    return await get_ai_publication_stats()


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
        raise HTTPException(status_code=400, detail=str(e))
    # serialize items
    items = [PublicationDTO.model_validate(p).model_dump() for p in result["items"]]
    return {"items": items, "total": result["total"], "page": result["page"], "size": result["size"]}


@router.post("")
async def create_single_publication(request: Request, file: UploadFile = File(...), payload_json: str | None = Form(None), current_user: dict = Depends(get_current_user)):
    """Accepts either a JSON body or a multipart form with a `payload_json` field (JSON string) and required `pdf_file`."""
    try:
        if payload_json:
            print(payload_json)
            payload = PublicationCreateDTO.model_validate_json(payload_json)
        else:
            body = await request.json()
            payload = PublicationCreateDTO.model_validate(body)

        pub_id = await create_publication(payload, pdf_file=file)
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))
    return GenericResponse(data={"id": pub_id})


@router.put("/{publication_id}")
async def update_single_publication(
    publication_id: int,
    request: Request,
    file: UploadFile = File(None),
    payload_json: str | None = Form(None),
    current_user: dict = Depends(get_current_user),
):
    """Update a publication by ID.

    Only allowed if entity_type is 'AcademicPublication' or 'Publication'
    and classified_at is null.
    """
    print(f"[PUB-UPDATE] received id={publication_id} payload_json={bool(payload_json)}", flush=True)
    try:
        if payload_json:
            payload = PublicationUpdateDTO.model_validate_json(payload_json)
        else:
            body = await request.json()
            payload = PublicationUpdateDTO.model_validate(body)

        pub = await update_publication(publication_id, payload, pdf_file=file)
    except ValueError as e:
        print(f"[PUB-UPDATE] error: {e}", flush=True)
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        print(f"[PUB-UPDATE] error: {e}", flush=True)
        raise HTTPException(status_code=400, detail=str(e))

    print(f"[PUB-UPDATE] success id={pub.id}", flush=True)
    return {"success": True, "id": pub.id}


@router.delete("/{publication_id}")
async def delete_single_publication(
    publication_id: int,
    current_user: dict = Depends(get_current_user),
):
    """Delete a publication by ID.

    Only allowed if entity_type is 'AcademicPublication' or 'Publication'
    and classified_at is null.
    """
    print(f"[PUB-DELETE] received id={publication_id}", flush=True)
    try:
        deleted_id = await delete_publication(publication_id)
    except ValueError as e:
        print(f"[PUB-DELETE] error: {e}", flush=True)
        raise HTTPException(status_code=400, detail=str(e))

    print(f"[PUB-DELETE] success id={deleted_id}", flush=True)
    return {"success": True, "id": deleted_id}