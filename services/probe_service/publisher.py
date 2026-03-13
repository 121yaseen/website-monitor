import asyncio

import structlog
import websockets

from services.probe_service.config import settings
from services.probe_service.models import ProbeResponse

logger = structlog.get_logger("probe_service.publisher")


class Publisher:
    _queue: asyncio.Queue[str]
    _task: asyncio.Task[None] | None
    retry_count: int

    def publish(self, response: ProbeResponse) -> None:
        self._queue.put_nowait(response.model_dump_json())

    async def _connect_loop(self) -> None:
        while True:
            try:
                async with websockets.connect(settings.websocket_url) as ws:
                    self.retry_count = 0
                    await self._send_loop(ws)
            except Exception as e:
                logger.error("ws_connect_failed", error=str(e), retry_count=self.retry_count)
                await asyncio.sleep(10 + self.retry_count**2)
                self.retry_count += 1

    async def _send_loop(self, ws: websockets.ClientConnection) -> None:
        try:
            while True:
                message = await self._queue.get()
                await ws.send(message)
                self._queue.task_done()
        except Exception as e:
            logger.error("ws_send_failed", error=str(e))
            raise

    async def start(self) -> None:
        self._task = asyncio.create_task(self._connect_loop())

    async def stop(self) -> None:
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass

    def __init__(self) -> None:
        self._queue: asyncio.Queue[str] = asyncio.Queue()
        self._task: asyncio.Task[None] | None = None
        self.retry_count: int = 0
