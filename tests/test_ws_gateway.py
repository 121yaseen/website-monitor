"""Tests for the ws_gateway service — WebSocket echo endpoint and health route."""

from datetime import datetime

from fastapi.testclient import TestClient

from services.ws_gateway.main import app

client = TestClient(app, raise_server_exceptions=True)


# ---------------------------------------------------------------------------
# Health
# ---------------------------------------------------------------------------


def test_health_returns_200() -> None:
    response = client.get("/health")
    assert response.status_code == 200


def test_health_identifies_ws_gateway() -> None:
    response = client.get("/health")
    assert response.json()["service"] == "ws_gateway"


# ---------------------------------------------------------------------------
# Happy path
# ---------------------------------------------------------------------------


def test_echo_returns_sent_message() -> None:
    with client.websocket_connect("/ws/echo") as ws:
        ws.send_json({"message": "hello", "client_sent_at": datetime.now().isoformat()})
        data = ws.receive_json()
    assert data["message"] == "hello"


def test_echo_response_has_server_received_at() -> None:
    with client.websocket_connect("/ws/echo") as ws:
        ws.send_json({"message": "ping", "client_sent_at": datetime.now().isoformat()})
        data = ws.receive_json()
    assert "server_received_at" in data
    assert data["server_received_at"] is not None


def test_echo_response_echoes_client_sent_at() -> None:
    sent_at = datetime.now().isoformat()
    with client.websocket_connect("/ws/echo") as ws:
        ws.send_json({"message": "ping", "client_sent_at": sent_at})
        data = ws.receive_json()
    assert data["client_sent_at"] == sent_at


def test_echo_response_has_session_id() -> None:
    with client.websocket_connect("/ws/echo") as ws:
        ws.send_json({"message": "ping", "client_sent_at": datetime.now().isoformat()})
        data = ws.receive_json()
    assert "session_id" in data
    assert len(data["session_id"]) > 0


# ---------------------------------------------------------------------------
# session_id consistency
# ---------------------------------------------------------------------------


def test_session_id_is_consistent_within_a_connection() -> None:
    with client.websocket_connect("/ws/echo") as ws:
        ws.send_json({"message": "first", "client_sent_at": datetime.now().isoformat()})
        r1 = ws.receive_json()
        ws.send_json({"message": "second", "client_sent_at": datetime.now().isoformat()})
        r2 = ws.receive_json()
    assert r1["session_id"] == r2["session_id"]


def test_session_id_differs_across_connections() -> None:
    with client.websocket_connect("/ws/echo") as ws:
        ws.send_json({"message": "a", "client_sent_at": datetime.now().isoformat()})
        r1 = ws.receive_json()

    with client.websocket_connect("/ws/echo") as ws:
        ws.send_json({"message": "b", "client_sent_at": datetime.now().isoformat()})
        r2 = ws.receive_json()

    assert r1["session_id"] != r2["session_id"]


# ---------------------------------------------------------------------------
# Bad payloads — connection must stay open
# ---------------------------------------------------------------------------


def test_bad_json_returns_error_without_closing_connection() -> None:
    with client.websocket_connect("/ws/echo") as ws:
        ws.send_text("not json at all")
        error = ws.receive_json()
        # Connection still open — can send a valid message afterwards
        ws.send_json({"message": "ok", "client_sent_at": datetime.now().isoformat()})
        ok = ws.receive_json()
    assert "error" in error
    assert "message" in ok


def test_missing_required_field_returns_error() -> None:
    with client.websocket_connect("/ws/echo") as ws:
        ws.send_json({"message": "no timestamp here"})  # missing client_sent_at
        data = ws.receive_json()
    assert "error" in data


def test_empty_object_returns_error() -> None:
    with client.websocket_connect("/ws/echo") as ws:
        ws.send_json({})
        data = ws.receive_json()
    assert "error" in data
