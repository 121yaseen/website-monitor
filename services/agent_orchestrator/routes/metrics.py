from fastapi import APIRouter
from pydantic import BaseModel

from services.agent_orchestrator.metrics import collector

router = APIRouter()


class MetricsSummaryResponse(BaseModel):
    summary: dict[str, dict[str, float | None | int]]


@router.get("/metrics", response_model=MetricsSummaryResponse)
async def get_metrics() -> MetricsSummaryResponse:
    """Return p50/p95 latency summary for all recorded turns."""
    return MetricsSummaryResponse(summary=collector.summary())
