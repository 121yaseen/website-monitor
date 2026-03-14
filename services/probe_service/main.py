import asyncio
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

import structlog
from fastapi import FastAPI

from services.probe_service.config import settings
from services.probe_service.db import DBObject
from services.probe_service.logger import configure_logging
from services.probe_service.models import ProbeRequest
from services.probe_service.prober import probe
from services.probe_service.publisher import Publisher
from services.probe_service.routes.health import router as health_router

configure_logging()

logger = structlog.get_logger("probe_service")


async def probe_loop(app: FastAPI) -> None:
    while True:
        monitors = await app.state.db.get_active_monitors()
        if not monitors:
            logger.info("no_active_monitors")
        for _monitor_id, url in monitors:
            request = ProbeRequest(target_url=url, timeout_in_seconds=10)  # type: ignore[arg-type]
            result = await probe(request)
            await app.state.db.save_result(result)
            if result.response is not None:
                app.state.publisher.publish(result.response)
        await asyncio.sleep(settings.probe_interval)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    app.state.db = await DBObject.get_db_object(settings.db_connection_string)
    app.state.publisher = Publisher()
    await app.state.publisher.start()
    probe_task = asyncio.create_task(probe_loop(app))
    logger.info("probe_task_started", task=probe_task)

    yield

    logger.info("service_stopping")
    try:
        probe_task.cancel()
        await probe_task
    except asyncio.CancelledError:
        pass
    await app.state.publisher.stop()
    logger.info("service_stopped")


app = FastAPI(lifespan=lifespan)
app.include_router(health_router)
