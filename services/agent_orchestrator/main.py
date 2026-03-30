from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

import structlog
import uvicorn
from fastapi import FastAPI

from services.agent_orchestrator.config import settings
from services.agent_orchestrator.routes.health import router as health_router
from services.agent_orchestrator.routes.metrics import router as metrics_router
from services.agent_orchestrator.routes.ws import router as ws_router

logger = structlog.get_logger("agent_orchestrator.main")


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    logger.info(
        "agent_orchestrator_starting",
        host=settings.host,
        port=settings.port,
        llm_provider=settings.llm_provider,
        tts_provider=settings.tts_provider,
    )
    yield
    logger.info("agent_orchestrator_stopped")


app = FastAPI(
    title="Agent Orchestrator",
    description="Duplex voice agent control plane — STT → LLM → TTS",
    version="0.1.0",
    lifespan=lifespan,
)

app.include_router(ws_router)
app.include_router(health_router)
app.include_router(metrics_router)


if __name__ == "__main__":
    uvicorn.run(
        "services.agent_orchestrator.main:app",
        host=settings.host,
        port=settings.port,
        reload=False,
    )
