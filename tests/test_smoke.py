"""Smoke test – verify the core domain models can be imported and instantiated.

This test does NOT perform any I/O.  Its only job is to catch import errors,
missing dependencies, or badly-broken model definitions as early as possible.
"""

import uuid

from services.probe_service.models import ProbeRequest, ProbeResult


def test_probe_request_defaults() -> None:
    """ProbeRequest should have a UUID auto-generated and sensible defaults."""
    req = ProbeRequest(target_url="https://example.com/", timeout_in_seconds=5)

    assert req.target_url is not None
    assert req.timeout_in_seconds == 5
    # request_id is auto-generated – must be a valid UUID
    assert isinstance(req.request_id, uuid.UUID)


def test_probe_result_defaults_to_failure() -> None:
    """A freshly-created ProbeResult should start in a failed state."""
    req = ProbeRequest(target_url="https://example.com/")
    result = ProbeResult(probe_id="test-id", request=req, success=False)

    assert result.success is False
    assert result.response is None
