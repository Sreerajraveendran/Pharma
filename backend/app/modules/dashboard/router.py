from fastapi import APIRouter, Query

from app.modules.dashboard import schemas, service

router = APIRouter()


@router.get("/metrics", response_model=schemas.DashboardMetrics)
async def get_metrics(tz_offset: int = Query(0, ge=-14 * 60, le=14 * 60, description="Viewer's UTC offset in minutes")):
    return await service.get_dashboard_metrics(tz_offset)
