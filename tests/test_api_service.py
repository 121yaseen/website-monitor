import os
import tempfile

import pytest
from httpx import ASGITransport, AsyncClient

from services.api_service.db import APIDBObject
from services.api_service.main import app


@pytest.fixture
async def client():
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = f.name
    app.state.db = await APIDBObject.get_db_object(db_path)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c
    os.unlink(db_path)


async def test_health(client: AsyncClient) -> None:
    r = await client.get("/health")
    assert r.status_code == 200
    assert r.json() == {"status": "ok", "service": "api_service"}


async def test_list_monitors_empty(client: AsyncClient) -> None:
    r = await client.get("/monitors")
    assert r.status_code == 200
    assert r.json() == []


async def test_add_monitor(client: AsyncClient) -> None:
    r = await client.post("/monitors", json={"url": "https://example.com"})
    assert r.status_code == 201
    body = r.json()
    assert body["url"] == "https://example.com/"
    assert body["is_active"] is True
    assert "id" in body


async def test_add_duplicate_monitor_returns_409(client: AsyncClient) -> None:
    await client.post("/monitors", json={"url": "https://example.com"})
    r = await client.post("/monitors", json={"url": "https://example.com"})
    assert r.status_code == 409


async def test_delete_monitor(client: AsyncClient) -> None:
    r = await client.post("/monitors", json={"url": "https://example.com"})
    mid = r.json()["id"]
    r = await client.delete(f"/monitors/{mid}")
    assert r.status_code == 204
    r = await client.get("/monitors")
    assert r.json() == []


async def test_delete_nonexistent_monitor_returns_404(client: AsyncClient) -> None:
    r = await client.delete("/monitors/nonexistent-id")
    assert r.status_code == 404


async def test_pause_and_resume_monitor(client: AsyncClient) -> None:
    r = await client.post("/monitors", json={"url": "https://example.com"})
    mid = r.json()["id"]

    r = await client.patch(f"/monitors/{mid}/pause")
    assert r.status_code == 200
    assert r.json()["is_active"] is False

    r = await client.patch(f"/monitors/{mid}/pause")
    assert r.json()["is_active"] is True


async def test_pause_nonexistent_monitor_returns_404(client: AsyncClient) -> None:
    r = await client.patch("/monitors/nonexistent-id/pause")
    assert r.status_code == 404


async def test_list_monitors_returns_all(client: AsyncClient) -> None:
    await client.post("/monitors", json={"url": "https://a.com"})
    await client.post("/monitors", json={"url": "https://b.com"})
    r = await client.get("/monitors")
    assert len(r.json()) == 2
