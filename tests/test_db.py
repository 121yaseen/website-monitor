"""Tests for DBObject — uses a temp-file SQLite DB so no permanent files are created."""

import pathlib

import pytest

from services.probe_service.db import DBObject
from services.probe_service.models import ProbeRequest, ProbeResponse, ProbeResult

# ---------------------------------------------------------------------------
# Fixture: a fresh temp-file DB for each test
# Each test gets its own isolated file via pytest's tmp_path fixture.
# We can't use ":memory:" because every aiosqlite.connect(":memory:") call
# opens a *separate* in-memory database — meaning init_db and save_result
# would be talking to different databases.
# ---------------------------------------------------------------------------


@pytest.fixture
async def db(tmp_path: pathlib.Path) -> DBObject:
    db_path = str(tmp_path / "test.db")
    return await DBObject.get_db_object(db_path)


# ---------------------------------------------------------------------------
# save_result
# ---------------------------------------------------------------------------


async def test_save_result_raises_when_response_is_none(db: DBObject) -> None:
    req = ProbeRequest(target_url="https://example.com/")
    result = ProbeResult(probe_id="pid-1", request=req, success=False, response=None)

    with pytest.raises(ValueError, match="no response"):
        await db.save_result(result)


async def test_save_and_retrieve_healthy_result(db: DBObject) -> None:
    req = ProbeRequest(target_url="https://example.com/")
    resp = ProbeResponse(
        target_url="https://example.com/",
        status_code=200,
        status="healthy",
        latency=0.042,
    )
    result = ProbeResult(probe_id="pid-2", request=req, response=resp, success=True)

    await db.save_result(result)
    retrieved = await db.get_results("pid-2")

    assert len(retrieved) == 1
    assert retrieved[0].status_code == 200
    assert retrieved[0].status == "healthy"
    assert retrieved[0].latency == pytest.approx(0.042)
    assert retrieved[0].error is None


async def test_save_and_retrieve_unhealthy_result(db: DBObject) -> None:
    req = ProbeRequest(target_url="https://example.com/")
    resp = ProbeResponse(
        target_url="https://example.com/",
        status_code=503,
        status="unhealthy",
        latency=1.5,
        error="Service Unavailable",
    )
    result = ProbeResult(probe_id="pid-3", request=req, response=resp, success=False)

    await db.save_result(result)
    retrieved = await db.get_results("pid-3")

    assert retrieved[0].status == "unhealthy"
    assert retrieved[0].error == "Service Unavailable"
    assert retrieved[0].status_code == 503


# ---------------------------------------------------------------------------
# get_results
# ---------------------------------------------------------------------------


async def test_get_results_returns_empty_for_unknown_probe_id(db: DBObject) -> None:
    results = await db.get_results("does-not-exist")
    assert results == []
