from datetime import datetime

from pydantic import BaseModel


class EchoRequest(BaseModel):
    message: str
    client_sent_at: datetime


class EchoResponse(BaseModel):
    session_id: str
    message: str
    client_sent_at: datetime
    server_received_at: datetime
