from datetime import UTC, datetime

from pydantic import BaseModel, Field


class EchoRequest(BaseModel):
    message: str
    client_sent_at: datetime
    server_received_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class EchoResponse(BaseModel):
    session_id: str
    message: str
    client_sent_at: datetime
    server_received_at: datetime
    server_sent_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
