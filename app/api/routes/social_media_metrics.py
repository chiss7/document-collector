from fastapi import APIRouter
from app.services.social_media_metrics_service import get_social_media_metrics

router = APIRouter(prefix="/social-media", tags=["SocialMediaMetrics"])


@router.get("/metrics")
async def social_media_metrics():
    metrics = await get_social_media_metrics()
    return metrics
