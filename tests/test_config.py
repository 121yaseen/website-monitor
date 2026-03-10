"""Tests for Settings — default values and env-prefix loading."""

import pytest

from services.probe_service.config import Settings


def test_settings_defaults() -> None:
    """Settings constructed with no env vars should have the documented defaults."""
    s = Settings()
    assert s.port == 8003
    assert s.env.lower() == "dev"  # .env may store "DEV" or "dev" — both valid
    assert s.db_connection_string == "probe_results.db"


def test_settings_override_via_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """PROBE_ prefixed env vars must override defaults."""
    monkeypatch.setenv("PROBE_PORT", "9000")
    monkeypatch.setenv("PROBE_ENV", "prod")
    monkeypatch.setenv("PROBE_DB_CONNECTION_STRING", "/tmp/test.db")

    s = Settings()
    assert s.port == 9000
    assert s.env == "prod"
    assert s.db_connection_string == "/tmp/test.db"
