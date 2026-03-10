"""Tests for Pydantic models — validation rules, defaults, and constraints."""

import uuid

import pytest
from pydantic import ValidationError

from services.probe_service.models import ProbeRequest, ProbeResponse, ProbeResult

# ---------------------------------------------------------------------------
# ProbeRequest
# ---------------------------------------------------------------------------


def test_probe_request_auto_generates_uuid() -> None:
    req = ProbeRequest(target_url="https://example.com/")
    assert isinstance(req.request_id, uuid.UUID)


def test_probe_request_two_instances_have_different_ids() -> None:
    r1 = ProbeRequest(target_url="https://example.com/")
    r2 = ProbeRequest(target_url="https://example.com/")
    assert r1.request_id != r2.request_id


def test_probe_request_default_timeout() -> None:
    req = ProbeRequest(target_url="https://example.com/")
    assert req.timeout_in_seconds == 10


def test_probe_request_rejects_timeout_zero() -> None:
    with pytest.raises(ValidationError):
        ProbeRequest(target_url="https://example.com/", timeout_in_seconds=0)


def test_probe_request_rejects_timeout_too_large() -> None:
    # lt=60 means 60 is also invalid
    with pytest.raises(ValidationError):
        ProbeRequest(target_url="https://example.com/", timeout_in_seconds=60)


def test_probe_request_rejects_invalid_url() -> None:
    with pytest.raises(ValidationError):
        ProbeRequest(target_url="not-a-url")


# ---------------------------------------------------------------------------
# ProbeResponse
# ---------------------------------------------------------------------------


def test_probe_response_healthy() -> None:
    r = ProbeResponse(
        target_url="https://example.com/",
        status_code=200,
        status="healthy",
        latency=0.123,
    )
    assert r.status == "healthy"
    assert r.error is None


def test_probe_response_rejects_invalid_status_literal() -> None:
    with pytest.raises(ValidationError):
        ProbeResponse(
            target_url="https://example.com/",
            status_code=200,
            status="ok",  # only "healthy" | "unhealthy" allowed
            latency=0.1,
        )


def test_probe_response_rejects_negative_latency() -> None:
    with pytest.raises(ValidationError):
        ProbeResponse(
            target_url="https://example.com/",
            status_code=200,
            status="healthy",
            latency=-1.0,
        )


def test_probe_response_rejects_status_code_out_of_range() -> None:
    with pytest.raises(ValidationError):
        ProbeResponse(
            target_url="https://example.com/",
            status_code=99,  # ge=100 required
            status="unhealthy",
            latency=0.0,
        )


# ---------------------------------------------------------------------------
# ProbeResult
# ---------------------------------------------------------------------------


def test_probe_result_success_with_response() -> None:
    req = ProbeRequest(target_url="https://example.com/")
    resp = ProbeResponse(
        target_url="https://example.com/",
        status_code=200,
        status="healthy",
        latency=0.05,
    )
    result = ProbeResult(probe_id="abc", request=req, response=resp, success=True)

    assert result.success is True
    assert result.response is not None
    assert result.response.status_code == 200
