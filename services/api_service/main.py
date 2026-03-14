from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from services.api_service.config import settings
from services.api_service.db import APIDBObject
from services.api_service.routes.health import router as health_router
from services.api_service.routes.monitors import router as monitors_router

STATIC_DIR = Path(__file__).parent / "static"


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    app.state.db = await APIDBObject.get_db_object(settings.db_connection_string)
    yield


app = FastAPI(lifespan=lifespan)
app.include_router(health_router)
app.include_router(monitors_router)
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")


@app.get("/")
async def index() -> FileResponse:
    return FileResponse(str(STATIC_DIR / "index.html"))
