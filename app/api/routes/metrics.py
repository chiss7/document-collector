from fastapi import APIRouter, UploadFile, File, HTTPException
from app.services.metrics_service import compute_confusion_from_bytes

router = APIRouter(prefix="/metrics", tags=["Metrics"])


@router.post("/confusion")
async def upload_confusion_matrix(file: UploadFile = File(...)):
    """Receive an Excel file and return confusion matrix counts.

    Delegates Excel parsing and DB lookups to `metrics_service`.
    """
    try:
        content = await file.read()
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Could not read uploaded file: {e}")

    try:
        result = await compute_confusion_from_bytes(content, filename=file.filename)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

    return result
