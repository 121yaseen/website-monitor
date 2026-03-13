import json
import uuid
from datetime import UTC, datetime

import structlog
from fastapi import APIRouter
from fastapi.websockets import WebSocket, WebSocketDisconnect
from pydantic import ValidationError

from services.ws_gateway.models import EchoRequest, EchoResponse

logger = structlog.get_logger("ws_gateway.routes.ws")

router = APIRouter()


@router.websocket("/ws/echo")
async def echo(websocket: WebSocket) -> None:
    session_id = str(uuid.uuid4())
    await websocket.accept()
    while True:
        try:
            raw = await websocket.receive_text()
            data = EchoRequest.model_validate_json(raw)
            response = EchoResponse(
                session_id=session_id,
                message=data.message,
                client_sent_at=data.client_sent_at,
                server_received_at=datetime.now(UTC),
            )
            await websocket.send_text(response.model_dump_json())
        except WebSocketDisconnect:
            break
        except ValidationError as e:
            await websocket.send_text(json.dumps({"error": str(e)}))
            continue
