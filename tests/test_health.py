"""Unit tests for the /health endpoint.

Uses FastAPI's TestClient (sync) so no real server is started.
"""

from fastapi.testclient import TestClient

from services.probe_service.main import app

# ---------------------------------------------------------------------------
# Fixture: a test client that skips the lifespan (no DB/publisher needed)
# ---------------------------------------------------------------------------


client = TestClient(app, raise_server_exceptions=True)


# ---------------------------------------------------------------------------
# GET /health
# ---------------------------------------------------------------------------


def test_health_returns_200() -> None:
    """GET /health should return HTTP 200."""
    response = client.get("/health")
    assert response.status_code == 200


def test_health_returns_status_ok() -> None:
    """GET /health body should contain status=ok."""
    response = client.get("/health")
    assert response.json()["status"] == "ok"


def test_health_returns_service_name() -> None:
    """GET /health body should identify the service."""
    response = client.get("/health")
    assert response.json()["service"] == "probe_service"


def test_health_response_is_json() -> None:
    """GET /health Content-Type should be application/json."""
    response = client.get("/health")
    assert "application/json" in response.headers["content-type"]


def test_root_returns_404() -> None:
    """GET / is not a registered route and should return 404."""
    response = client.get("/")
    assert response.status_code == 404
