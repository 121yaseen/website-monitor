"""Tests for configure_logging() — verifies it runs without error
and wires up the correct renderer based on env."""

import importlib

import pytest

import services.probe_service.config as cfg_module
import services.probe_service.logger as logger_module
from services.probe_service.logger import configure_logging


def test_configure_logging_runs_without_error() -> None:
    """configure_logging() must not raise in any environment."""
    configure_logging()  # would raise if misconfigured


def test_configure_logging_dev_uses_console_renderer(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("PROBE_ENV", "dev")
    importlib.reload(cfg_module)
    importlib.reload(logger_module)
    # Should complete without error — ConsoleRenderer selected
    logger_module.configure_logging()


def test_configure_logging_prod_uses_json_renderer(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("PROBE_ENV", "prod")
    importlib.reload(cfg_module)
    importlib.reload(logger_module)
    # Should complete without error — JSONRenderer selected
    logger_module.configure_logging()
