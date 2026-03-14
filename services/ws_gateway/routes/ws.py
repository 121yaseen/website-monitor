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


class ConnectionManager:
    def __init__(self) -> None:
        self._clients: list[WebSocket] = []

    async def connect(self, websocket: WebSocket) -> None:
        await websocket.accept()
        self._clients.append(websocket)
        logger.info("browser_client_connected", total=len(self._clients))

    def disconnect(self, websocket: WebSocket) -> None:
        self._clients.remove(websocket)
        logger.info("browser_client_disconnected", total=len(self._clients))

    async def broadcast(self, message: str) -> None:
        dead: list[WebSocket] = []
        for client in self._clients:
            try:
                await client.send_text(message)
            except Exception:
                dead.append(client)
        for client in dead:
            self._clients.remove(client)


manager = ConnectionManager()


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
                server_sent_at=datetime.now(UTC),
            )
            await websocket.send_text(response.model_dump_json())
        except WebSocketDisconnect:
            break
        except ValidationError as e:
            await websocket.send_text(json.dumps({"error": str(e)}))
            continue


@router.websocket("/ws/ingest")
async def ingest(websocket: WebSocket) -> None:
    """Probe service connects here to push results; we broadcast to all browser clients."""
    await websocket.accept()
    logger.info("probe_service_connected")
    try:
        while True:
            message = await websocket.receive_text()
            await manager.broadcast(message)
    except WebSocketDisconnect:
        logger.info("probe_service_disconnected")


@router.websocket("/ws/updates")
async def updates(websocket: WebSocket) -> None:
    """Browser clients connect here to receive live probe results."""
    await manager.connect(websocket)
    try:
        while True:
            await websocket.receive_text()  # keep alive; ignore client messages
    except WebSocketDisconnect:
        manager.disconnect(websocket)
