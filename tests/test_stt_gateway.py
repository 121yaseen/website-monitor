"""Tests for the STT gateway WebSocket endpoint.

Uses a FakeProvider to avoid any Azure dependency.
"""

import json
from collections.abc import Awaitable, Callable
from unittest.mock import patch

from fastapi.testclient import TestClient

from services.stt_gateway.main import app
from services.stt_gateway.providers.base import STTProvider

SESSION_START = {
    "type": "session.start",
    "session_id": "test-session",
    "sample_rate": 16000,
    "channels": 1,
    "encoding": "pcm",
}

SESSION_END = {"type": "session.end", "session_id": "test-session"}

AUDIO_CHUNK = b"\x00\x01" * 160  # 320 bytes of fake PCM


# ---------------------------------------------------------------------------
# Fake providers
# ---------------------------------------------------------------------------


class FakeProvider(STTProvider):
    """A no-op provider that accepts audio without emitting events."""

    def __init__(self, *_args: object, **_kwargs: object) -> None:
        self._on_partial_cb: Callable[[str], Awaitable[None]] | None = None
        self._on_final_cb: Callable[[str], Awaitable[None]] | None = None
        self.connected = False
        self.closed = False
        self.chunks: list[bytes] = []

    async def connect(self, sample_rate: int, channels: int, encoding: str) -> None:
        self.connected = True

    async def send_audio(self, chunk: bytes) -> None:
        self.chunks.append(chunk)

    async def close(self) -> None:
        self.closed = True

    def on_partial(self, callback: Callable[[str], Awaitable[None]]) -> None:
        self._on_partial_cb = callback

    def on_final(self, callback: Callable[[str], Awaitable[None]]) -> None:
        self._on_final_cb = callback


class FailingProvider(FakeProvider):
    """Raises on connect()."""

    async def connect(self, sample_rate: int, channels: int, encoding: str) -> None:
        raise RuntimeError("provider exploded")


class EmittingProvider(FakeProvider):
    """Emits a partial then a final for every audio chunk received."""

    def __init__(self, *args: object, **kwargs: object) -> None:
        super().__init__(*args, **kwargs)
        self._chunk_count = 0

    async def send_audio(self, chunk: bytes) -> None:
        self.chunks.append(chunk)
        self._chunk_count += 1
        if self._on_partial_cb:
            await self._on_partial_cb(f"partial-{self._chunk_count}")
        if self._on_final_cb:
            await self._on_final_cb(f"final-{self._chunk_count}")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

PROVIDER_PATH = "services.stt_gateway.routes.ws.AzureSpeechProvider"


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def test_happy_path_session() -> None:
    with patch(PROVIDER_PATH, FakeProvider):
        client = TestClient(app)
        with client.websocket_connect("/ws/audio") as ws:
            ws.send_json(SESSION_START)
            ws.send_bytes(AUDIO_CHUNK)
            ws.send_bytes(AUDIO_CHUNK)
            ws.send_json(SESSION_END)
    # No assertion exception → connection closed cleanly.


def test_audio_before_session_start() -> None:
    with patch(PROVIDER_PATH, FakeProvider):
        client = TestClient(app)
        with client.websocket_connect("/ws/audio") as ws:
            ws.send_bytes(AUDIO_CHUNK)
            resp = json.loads(ws.receive_text())
    assert resp["type"] == "error"
    assert resp["code"] == "NO_SESSION"


def test_provider_connect_failure() -> None:
    with patch(PROVIDER_PATH, FailingProvider):
        client = TestClient(app)
        with client.websocket_connect("/ws/audio") as ws:
            ws.send_json(SESSION_START)
            resp = json.loads(ws.receive_text())
    assert resp["type"] == "error"
    assert resp["code"] == "PROVIDER_CONNECTION_FAILED"
    assert "provider exploded" in resp["message"]


def test_partial_and_final_flow() -> None:
    with patch(PROVIDER_PATH, EmittingProvider):
        client = TestClient(app)
        with client.websocket_connect("/ws/audio") as ws:
            ws.send_json(SESSION_START)
            ws.send_bytes(AUDIO_CHUNK)

            partial = json.loads(ws.receive_text())
            final = json.loads(ws.receive_text())

            ws.send_json(SESSION_END)

    assert partial["type"] == "transcript.partial"
    assert partial["text"] == "partial-1"
    assert partial["utterance_id"] == "utt-1"
    assert partial["session_id"] == "test-session"

    assert final["type"] == "transcript.final"
    assert final["text"] == "final-1"
    assert final["utterance_id"] == "utt-1"
    assert final["session_id"] == "test-session"
    assert isinstance(final["first_audio_ts"], float)
    assert isinstance(final["final_ts"], float)


def test_client_disconnect_without_session_end() -> None:
    """Server should not crash when client disconnects abruptly."""
    with patch(PROVIDER_PATH, FakeProvider):
        client = TestClient(app)
        with client.websocket_connect("/ws/audio") as ws:
            ws.send_json(SESSION_START)
            ws.send_bytes(AUDIO_CHUNK)
            # exit context manager without sending session.end → triggers disconnect
    # If we get here the server didn't crash.


def test_multiple_utterances() -> None:
    with patch(PROVIDER_PATH, EmittingProvider):
        client = TestClient(app)
        with client.websocket_connect("/ws/audio") as ws:
            ws.send_json(SESSION_START)

            # First utterance
            ws.send_bytes(AUDIO_CHUNK)
            p1 = json.loads(ws.receive_text())
            f1 = json.loads(ws.receive_text())

            # Second utterance (provider emits new partial+final on next chunk)
            ws.send_bytes(AUDIO_CHUNK)
            p2 = json.loads(ws.receive_text())
            f2 = json.loads(ws.receive_text())

            ws.send_json(SESSION_END)

    assert p1["utterance_id"] == "utt-1"
    assert f1["utterance_id"] == "utt-1"
    assert p2["utterance_id"] == "utt-2"
    assert f2["utterance_id"] == "utt-2"

    # first_audio_ts should reset for the second utterance
    assert f2["first_audio_ts"] != f1["first_audio_ts"]


def test_invalid_json_message() -> None:
    with patch(PROVIDER_PATH, FakeProvider):
        client = TestClient(app)
        with client.websocket_connect("/ws/audio") as ws:
            ws.send_text("this is not json {{{")
            resp = json.loads(ws.receive_text())
    assert resp["type"] == "error"
    assert resp["code"] == "INVALID_MESSAGE"
