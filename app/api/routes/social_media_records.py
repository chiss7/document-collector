from fastapi import APIRouter, File, UploadFile, HTTPException

from app.services.social_media_service import import_from_excel

router = APIRouter(prefix="/social-media", tags=["SocialMedia"])


@router.post("/import")
async def import_social_media(file: UploadFile = File(...)):
    if not file:
        raise HTTPException(status_code=400, detail="File is required")
    try:
        inserted = await import_from_excel(file)
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))
    return {"inserted": inserted}
