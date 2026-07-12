import asyncio
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, HTTPException, Query

from app.services.classification_report_service import generate_classification_report

router = APIRouter(prefix="/metrics", tags=["Metrics"])


@router.post("/classification-report")
async def classification_report():
    """Generate confusion matrix and metrics for all classification models.

    Reads ground truth from ``PUBLICACIONES_IA_ETIQUETADAS.xlsx``,
    processes each ``clasificacion_*.xlsx`` file in the exports folder,
    fills the ``relacion_IA`` column with ground truth labels (where empty),
    and returns a JSON report with per-model confusion matrices.
    """
    try:
        result = await generate_classification_report()
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

    return result
