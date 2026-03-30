"""Azure Cognitive Services TTS adapter using the REST synthesis endpoint."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncGenerator

import httpx
import structlog

from services.agent_orchestrator.adapters.tts_base import TTSAdapter

logger = structlog.get_logger("agent_orchestrator.adapters.azure_tts")

_SSML_TEMPLATE = """<speak version='1.0' xml:lang='en-US'>
  <voice name='{voice}'>{text}</voice>
</speak>"""


class AzureTTSAdapter(TTSAdapter):
    """
    Streams MP3 audio from the Azure TTS REST endpoint.
    Uses chunked streaming so the first bytes arrive before synthesis is complete.
    """

    def __init__(self, subscription_key: str, region: str, voice: str) -> None:
        self._key = subscription_key
        self._region = region
        self._voice = voice
        self._cancel_event = asyncio.Event()

    async def synthesize(self, text: str) -> AsyncGenerator[bytes, None]:
        self._cancel_event.clear()
        endpoint = f"https://{self._region}.tts.speech.microsoft.com/cognitiveservices/v1"
        ssml = _SSML_TEMPLATE.format(voice=self._voice, text=text)
        headers = {
            "Ocp-Apim-Subscription-Key": self._key,
            "Content-Type": "application/ssml+xml",
            "X-Microsoft-OutputFormat": "audio-16khz-128kbitrate-mono-mp3",
            "User-Agent": "voice-agent-v0",
        }
        logger.info("tts_request", chars=len(text), voice=self._voice)
        async with httpx.AsyncClient(timeout=30.0) as client:
            async with client.stream(
                "POST", endpoint, headers=headers, content=ssml.encode()
            ) as resp:
                resp.raise_for_status()
                first_chunk = True
                async for chunk in resp.aiter_bytes(chunk_size=4096):
                    if self._cancel_event.is_set():
                        logger.info("tts_cancelled_mid_stream")
                        return
                    if first_chunk:
                        logger.info("tts_first_chunk")
                        first_chunk = False
                    yield chunk
        logger.info("tts_completed")

    async def cancel(self) -> None:
        self._cancel_event.set()
        logger.info("tts_cancel_requested")
