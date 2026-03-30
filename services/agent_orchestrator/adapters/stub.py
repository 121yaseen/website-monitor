# Stub adapters for testing without live credentials
from __future__ import annotations

from collections.abc import AsyncGenerator

import structlog

from services.agent_orchestrator.adapters.llm_base import LLMAdapter
from services.agent_orchestrator.adapters.tts_base import TTSAdapter
from services.agent_orchestrator.models import Turn

logger = structlog.get_logger("agent_orchestrator.adapters.stub")


class StubLLMAdapter(LLMAdapter):
    """Returns a fixed response for testing."""

    def __init__(self, response: str = "Hello! I heard you. How can I help?") -> None:
        self._response = response

    async def complete(self, system_prompt: str, turns: list[Turn]) -> str:
        logger.info("stub_llm_complete", turn_count=len(turns))
        return self._response

    async def stream(self, system_prompt: str, turns: list[Turn]) -> AsyncGenerator[str, None]:
        for word in self._response.split():
            yield word + " "


class StubTTSAdapter(TTSAdapter):
    """Yields silent audio bytes for testing without a real TTS provider."""

    _SILENT_WAV_HEADER = b"RIFF" + b"\x00" * 40  # minimal placeholder

    async def synthesize(self, text: str) -> AsyncGenerator[bytes, None]:
        logger.info("stub_tts_synthesize", chars=len(text))
        # Emit a couple of fake chunks to exercise the streaming path
        for _ in range(3):
            yield self._SILENT_WAV_HEADER

    async def cancel(self) -> None:
        logger.info("stub_tts_cancelled")
