from pydantic import BaseModel, HttpUrl, Field
from typing import Literal
from datetime import datetime
import uuid

class ProbeRequest(BaseModel):
    request_id: str = Field(default_factory=uuid.uuid4)
    target_url: HttpUrl
    timeout_in_seconds: int = Field(default=10, gt=0, lt=60)

class ProbeResponse(BaseModel):
    target_url: HttpUrl
    status_code:int | None = Field(default=None, ge=100, le=599)
    status: Literal["healthy", "unhealthy"]
    latency: float = Field(ge=0)
    error: str | None = None
    timestamp: datetime = Field(default_factory=datetime.now)

class ProbeResult(BaseModel):
    probe_id: str
    request: ProbeRequest
    response: ProbeResponse | None = None
    success: bool
    