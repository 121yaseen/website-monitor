from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from services.ws_gateway.routes.health import router as health_router
from services.ws_gateway.routes.ws import router as ws_router


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    yield


app = FastAPI(lifespan=lifespan)
app.include_router(ws_router)
app.include_router(health_router)
