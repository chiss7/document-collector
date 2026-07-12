import asyncio
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse

from app.services.excel_export_service import EXPORT_DIR, _tasks, export_publications_to_excel

router = APIRouter(prefix="/export", tags=["Export"])


@router.post("/excel")
async def start_excel_export(payload: Optional[dict] = None, background: bool = True):
    """Scan DSpace + OAI and export classification results to Excel.

    Payload (optional):
    - ``method`` / ``classifier_method``: classification method
      (``regex``, ``embeddings``, ``transformers``). Default: ``regex``.

    Parameters:
    - ``background`` (default ``true``): runs the job in background;
      returns immediately with the expected filename.

    When ``background=false``, waits for completion and returns the file.
    """
    method = None
    if isinstance(payload, dict):
        method = (payload.get("method") or payload.get("classifier_method") or "regex").lower()
    method = method or "regex"

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"clasificacion_{method}_{timestamp}.xlsx"

    if background:
        asyncio.create_task(export_publications_to_excel(method, filename))
        return {"status": "Export started in background", "filename": filename}

    try:
        await export_publications_to_excel(method, filename)
        return FileResponse(
            path=EXPORT_DIR / filename,
            media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            filename=filename,
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/excel/status/{filename:path}")
async def export_status(filename: str):
    """Check progress of a running export task."""
    task = _tasks.get(filename)
    if task is None:
        raise HTTPException(status_code=404, detail="Task not found")
    return task


@router.get("/excel/download/{filename:path}")
async def download_excel(filename: str):
    """Download a previously exported Excel file by filename."""
    filepath = EXPORT_DIR / filename
    if not filepath.exists():
        raise HTTPException(status_code=404, detail="File not found")
    return FileResponse(
        path=filepath,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        filename=filename,
    )


@router.get("/excel/list")
async def list_exports():
    """List all available export files."""
    EXPORT_DIR.mkdir(parents=True, exist_ok=True)
    files = sorted(
        [f.name for f in EXPORT_DIR.iterdir() if f.suffix == ".xlsx"],
        reverse=True,
    )
    return {"files": files}
