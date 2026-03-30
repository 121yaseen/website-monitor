"""
WebSocket route for the agent orchestrator.

Message flow
────────────
Client → orchestrator (JSON text frames):
  { "type": "session.start", "session_id": "...", "system_prompt": "..." }
  { "type": "user.final_transcript", "session_id": "...", "utterance_id": "...",
    "text": "...", "first_audio_ts": 1234.56, "final_ts": 1234.78 }
  { "type": "user.barge_in", "session_id": "..." }
  { "type": "session.end", "session_id": "..." }

Orchestrator → client (JSON text + binary audio):
  { "type": "assistant.response.started", ... }
  { "type": "assistant.response.text", ..., "text": "..." }
  { "type": "assistant.audio.chunk", ..., "seq": N }  ← followed by binary frame
  <binary bytes>                                        ← MP3 audio chunk
  { "type": "assistant.audio.completed", ..., "latency_summary": {...} }
  { "type": "assistant.interrupted", ... }
  { "type": "error", ... }
"""

from __future__ import annotations

import json

import structlog
from fastapi import APIRouter
from fastapi.websockets import WebSocket, WebSocketDisconnect
from pydantic import ValidationError

from services.agent_orchestrator.adapters import (
    AzureTTSAdapter,
    OpenAILLMAdapter,
    StubLLMAdapter,
    StubTTSAdapter,
)
from services.agent_orchestrator.config import settings
from services.agent_orchestrator.metrics import collector
from services.agent_orchestrator.models import (
    OrchestratorErrorEvent,
    OrchestratorSessionEndEvent,
    OrchestratorSessionStartEvent,
    SessionMemory,
    UserBargeInEvent,
    UserFinalTranscriptEvent,
)
from services.agent_orchestrator.orchestrator import Orchestrator

logger = structlog.get_logger("agent_orchestrator.routes.ws")

router = APIRouter()


def _build_llm() -> OpenAILLMAdapter | StubLLMAdapter:
    if settings.openai_api_key:
        return OpenAILLMAdapter(
            api_key=settings.openai_api_key,
            base_url=settings.openai_base_url,
            model=settings.openai_model,
            is_azure=settings.llm_is_azure,
        )
    logger.warning("no_openai_key_using_stub")
    return StubLLMAdapter()


def _build_tts() -> AzureTTSAdapter | StubTTSAdapter:
    if settings.azure_tts_key:
        return AzureTTSAdapter(
            subscription_key=settings.azure_tts_key,
            region=settings.azure_tts_region,
            voice=settings.azure_tts_voice,
        )
    logger.warning("no_azure_tts_key_using_stub")
    return StubTTSAdapter()


@router.websocket("/ws/agent")
async def agent_ws(websocket: WebSocket) -> None:
    await websocket.accept()
    session: SessionMemory | None = None
    orch: Orchestrator | None = None

    try:
        while True:
            message = await websocket.receive()

            if message["type"] == "websocket.disconnect":
                break

            if "text" not in message:
                continue

            try:
                data = json.loads(message["text"])
                msg_type = data.get("type")

                # ── session.start ────────────────────────────────────
                if msg_type == "session.start":
                    evt = OrchestratorSessionStartEvent.model_validate(data)
                    session = SessionMemory(
                        session_id=evt.session_id,
                        system_prompt=evt.system_prompt or settings.system_prompt,
                        max_context_turns=settings.max_context_turns,
                    )
                    session.transition("listening")
                    orch = Orchestrator(
                        session=session,
                        llm=_build_llm(),
                        tts=_build_tts(),
                        ws=websocket,
                    )
                    logger.info("session_started", session_id=evt.session_id)

                # ── user.final_transcript ────────────────────────────
                elif msg_type == "user.final_transcript":
                    if orch is None or session is None:
                        await websocket.send_text(
                            OrchestratorErrorEvent(
                                session_id=None,
                                code="NO_SESSION",
                                message="Send session.start first",
                            ).model_dump_json()
                        )
                        continue
                    evt_transcript = UserFinalTranscriptEvent.model_validate(data)
                    session.transition("transcribing")
                    await orch.handle_transcript(evt_transcript)

                # ── user.barge_in ────────────────────────────────────
                elif msg_type == "user.barge_in":
                    if orch is not None:
                        UserBargeInEvent.model_validate(data)
                        await orch.handle_barge_in()

                # ── session.end ──────────────────────────────────────
                elif msg_type == "session.end":
                    OrchestratorSessionEndEvent.model_validate(data)
                    if orch:
                        await orch.close()

                    # Dump per-session metrics
                    if session:
                        logger.info(
                            "session_metrics",
                            session_id=session.session_id,
                            summary=collector.summary(),
                        )
                    break

                else:
                    logger.warning("unknown_message_type", msg_type=msg_type)

            except (json.JSONDecodeError, ValidationError) as exc:
                await websocket.send_text(
                    OrchestratorErrorEvent(
                        session_id=session.session_id if session else None,
                        code="INVALID_MESSAGE",
                        message=str(exc),
                    ).model_dump_json()
                )

    except WebSocketDisconnect:
        logger.info("client_disconnected", session_id=session.session_id if session else None)
    except Exception as exc:
        logger.error("ws_error", error=str(exc))
    finally:
        if orch:
            await orch.close()
        if session:
            logger.info("session_closed_finally", session_id=session.session_id)
