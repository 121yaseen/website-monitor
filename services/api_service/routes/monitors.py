import json
import uuid
from datetime import datetime
from typing import cast

import httpx
import websockets
from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import JSONResponse

from services.api_service.models import MonitorCreate, MonitorWithStatus

router = APIRouter(prefix="/monitors")

WS_INGEST_URL = "ws://localhost:8000/ws/ingest"


@router.get("")
async def list_monitors(request: Request) -> list[MonitorWithStatus]:
    return cast(list[MonitorWithStatus], await request.app.state.db.list_monitors())


@router.post("", status_code=201)
async def add_monitor(request: Request, body: MonitorCreate) -> JSONResponse:
    url = str(body.url)
    try:
        monitor = await request.app.state.db.add_monitor(url)
    except Exception as e:
        if "UNIQUE constraint failed" in str(e):
            raise HTTPException(
                status_code=409, detail="Monitor for this URL already exists"
            ) from None
        raise HTTPException(status_code=500, detail=str(e)) from e
    return JSONResponse(monitor.model_dump(mode="json"), status_code=201)


@router.delete("/{monitor_id}", status_code=204)
async def delete_monitor(request: Request, monitor_id: str) -> None:
    deleted = await request.app.state.db.delete_monitor(monitor_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Monitor not found")


@router.patch("/{monitor_id}/pause")
async def toggle_pause(request: Request, monitor_id: str) -> JSONResponse:
    monitor = await request.app.state.db.toggle_pause(monitor_id)
    if monitor is None:
        raise HTTPException(status_code=404, detail="Monitor not found")
    return JSONResponse(monitor.model_dump(mode="json"))


@router.post("/{monitor_id}/check")
async def force_check(request: Request, monitor_id: str) -> JSONResponse:
    url = await request.app.state.db.get_monitor_url(monitor_id)
    if url is None:
        raise HTTPException(status_code=404, detail="Monitor not found")

    probe_id = str(uuid.uuid4())
    timestamp = datetime.now()
    status_code: int | None = None
    latency: float = 0.0
    error: str | None = None
    status = "unhealthy"

    try:
        async with httpx.AsyncClient(follow_redirects=True) as client:
            resp = await client.get(url, timeout=10)
            latency = resp.elapsed.total_seconds()
            status_code = resp.status_code
            status = "healthy" if resp.status_code < 400 else "unhealthy"
    except Exception as exc:
        latency = (datetime.now() - timestamp).total_seconds()
        error = str(exc)

    timestamp = datetime.now()
    await request.app.state.db.save_probe_result(
        probe_id=probe_id,
        url=url,
        status=status,
        status_code=status_code,
        latency=latency,
        error=error,
        timestamp=timestamp,
    )

    result = {
        "target_url": url,
        "status": status,
        "status_code": status_code,
        "latency": latency,
        "error": error,
        "timestamp": timestamp.isoformat(),
    }

    # Best-effort broadcast to all browser clients via the WS gateway
    try:
        async with websockets.connect(WS_INGEST_URL, open_timeout=2) as ws:
            await ws.send(json.dumps(result))
    except Exception:
        pass  # Gateway not reachable; caller still gets the result via HTTP

    return JSONResponse(result)
