import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, HttpUrl


class MonitorCreate(BaseModel):
    url: HttpUrl


class Monitor(BaseModel):
    id: str
    url: str
    is_active: bool
    created_at: datetime


class LatestResult(BaseModel):
    status: Literal["healthy", "unhealthy"] | None = None
    status_code: int | None = None
    latency: float | None = None
    error: str | None = None
    checked_at: datetime | None = None


class MonitorWithStatus(BaseModel):
    id: str
    url: str
    is_active: bool
    created_at: datetime
    latest: LatestResult | None = None
    history: list[LatestResult] = []


def new_monitor_id() -> str:
    return str(uuid.uuid4())
