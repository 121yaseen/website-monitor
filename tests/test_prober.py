"""Unit tests for probe() – the core HTTP-probe function.

httpx calls are intercepted with `respx` so no real network traffic is made.
"""

import httpx
import respx

from services.probe_service.models import ProbeRequest
from services.probe_service.prober import probe


@respx.mock
async def test_probe_healthy_url() -> None:
    """probe() should mark the result successful on a 200 response."""
    target = "https://example.com/"

    # Intercept the outgoing GET and return a synthetic 200
    respx.get(target).mock(return_value=httpx.Response(200))

    request = ProbeRequest(target_url=target, timeout_in_seconds=5)
    result = await probe(request)

    assert result.success is True
    assert result.response is not None
    assert result.response.status == "healthy"
    assert result.response.status_code == 200
    assert result.response.error is None


@respx.mock
async def test_probe_unhealthy_url_returns_failure() -> None:
    """probe() should mark the result as unhealthy on a 500 response."""
    target = "https://example.com/"

    respx.get(target).mock(return_value=httpx.Response(500))

    request = ProbeRequest(target_url=target, timeout_in_seconds=5)
    result = await probe(request)

    assert result.success is False
    assert result.response is not None
    assert result.response.status == "unhealthy"
    assert result.response.status_code == 500


@respx.mock
async def test_probe_network_error_returns_failure() -> None:
    """probe() should handle a connection error gracefully."""
    target = "https://example.com/"

    respx.get(target).mock(side_effect=httpx.ConnectError("connection refused"))

    request = ProbeRequest(target_url=target, timeout_in_seconds=5)
    result = await probe(request)

    assert result.success is False
    assert result.response is not None
    assert result.response.status == "unhealthy"
    assert result.response.error is not None
