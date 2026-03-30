"""
Agent orchestrator core.

Responsibilities:
- Maintain session state machine (idle → listening → transcribing → thinking → speaking → …)
- On user.final_transcript: add user turn, call LLM, call TTS, stream audio to client.
- On user.barge_in: cancel TTS, mark turn interrupted, return to listening.
- Capture all latency timestamps per turn.
- Emit structured internal events to the client WebSocket.
"""

from __future__ import annotations

import asyncio
import time
from collections.abc import AsyncGenerator
from typing import Any

import structlog
from fastapi.websockets import WebSocket

from services.agent_orchestrator.adapters.llm_base import LLMAdapter
from services.agent_orchestrator.adapters.tts_base import TTSAdapter
from services.agent_orchestrator.metrics import collector
from services.agent_orchestrator.models import (
    AssistantAudioChunkEvent,
    AssistantAudioCompletedEvent,
    AssistantInterruptedEvent,
    AssistantResponseStartedEvent,
    AssistantResponseTextEvent,
    OrchestratorErrorEvent,
    SessionMemory,
    Turn,
    TurnLatencyMetrics,
    UserFinalTranscriptEvent,
)

logger = structlog.get_logger("agent_orchestrator.orchestrator")


class Orchestrator:
    """
    One Orchestrator instance per client WebSocket session.

    The caller is responsible for:
    1. Calling handle_transcript() when a user turn finalises.
    2. Calling handle_barge_in()  when user speech starts during playback.
    3. Calling close()            when the session ends.
    """

    def __init__(
        self,
        session: SessionMemory,
        llm: LLMAdapter,
        tts: TTSAdapter,
        ws: WebSocket,
    ) -> None:
        self._session = session
        self._llm = llm
        self._tts = tts
        self._ws = ws

        # The asyncio Task running the current LLM→TTS pipeline
        self._pipeline_task: asyncio.Task[None] | None = None

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def handle_transcript(self, event: UserFinalTranscriptEvent) -> None:
        """Called when STT finalises a user utterance."""
        log = logger.bind(session_id=self._session.session_id, utterance_id=event.utterance_id)
        log.info("transcript_received", text=event.text)

        # Build latency tracker
        metrics = TurnLatencyMetrics(
            user_first_audio_ts=event.first_audio_ts,
            user_final_transcript_ts=event.final_ts,
        )

        # Create and store user turn
        user_turn = Turn(
            speaker="user",
            text=event.text,
            started_at=event.first_audio_ts or event.final_ts,
            ended_at=event.final_ts,
            latency_metrics=metrics,
        )
        self._session.add_turn(user_turn)
        self._session.transition("thinking")

        # If an old pipeline is somehow still running, cancel it first
        if self._pipeline_task and not self._pipeline_task.done():
            log.warning("pipeline_already_running_cancelling")
            self._pipeline_task.cancel()
            try:
                await self._pipeline_task
            except asyncio.CancelledError:
                pass

        self._pipeline_task = asyncio.create_task(
            self._run_pipeline(metrics),
            name=f"pipeline-{user_turn.turn_id}",
        )

    async def handle_barge_in(self) -> None:
        """Called when user speech is detected while assistant audio is playing."""
        log = logger.bind(session_id=self._session.session_id, state=self._session.state)

        if self._session.state not in ("speaking", "thinking"):
            log.debug("barge_in_ignored_wrong_state")
            return

        log.info("barge_in_detected")
        interrupted_turn_id = self._session.current_turn_id

        # Cancel TTS
        await self._tts.cancel()

        # Cancel pipeline task
        if self._pipeline_task and not self._pipeline_task.done():
            self._pipeline_task.cancel()
            try:
                await self._pipeline_task
            except asyncio.CancelledError:
                pass

        # Mark assistant turn as interrupted in history
        self._session.mark_interrupted()
        self._session.assistant_audio_active = False
        self._session.transition("interrupted")

        # Emit event to client
        await self._send_json(
            AssistantInterruptedEvent(
                session_id=self._session.session_id,
                turn_id=interrupted_turn_id,
            ).model_dump()
        )

        log.info("barge_in_handled", interrupted_turn_id=interrupted_turn_id)
        self._session.transition("listening")

    async def close(self) -> None:
        """Tear down the session cleanly."""
        if self._pipeline_task and not self._pipeline_task.done():
            self._pipeline_task.cancel()
            try:
                await self._pipeline_task
            except asyncio.CancelledError:
                pass
        await self._tts.cancel()
        self._session.transition("closed")
        logger.info("session_closed", session_id=self._session.session_id)

    # ------------------------------------------------------------------
    # Internal pipeline: LLM → TTS → stream audio
    # ------------------------------------------------------------------

    async def _run_pipeline(self, metrics: TurnLatencyMetrics) -> None:
        session_id = self._session.session_id
        log = logger.bind(session_id=session_id)

        try:
            # ── 1. LLM ─────────────────────────────────────────────────
            self._session.transition("thinking")
            context_turns = self._session.get_context_turns()
            # Exclude the very last user turn (already included) – context is the window
            log.info("llm_call_start", context_turns=len(context_turns))

            metrics.llm_request_ts = time.time()
            assistant_text = await self._llm.complete(self._session.system_prompt, context_turns)
            metrics.llm_response_ts = time.time()
            log.info(
                "llm_response_received",
                chars=len(assistant_text),
                llm_latency=metrics.llm_latency(),
            )

            # Create assistant turn and add to history
            assistant_turn = Turn(
                speaker="assistant",
                text=assistant_text,
                started_at=time.time(),
                latency_metrics=metrics,
            )
            self._session.add_turn(assistant_turn)

            # Emit response.started
            await self._send_json(
                AssistantResponseStartedEvent(
                    session_id=session_id,
                    turn_id=assistant_turn.turn_id,
                ).model_dump()
            )

            # Emit response.text
            await self._send_json(
                AssistantResponseTextEvent(
                    session_id=session_id,
                    turn_id=assistant_turn.turn_id,
                    text=assistant_text,
                ).model_dump()
            )

            # ── 2. TTS ─────────────────────────────────────────────────
            self._session.transition("speaking")
            self._session.assistant_audio_active = True
            log.info("tts_start")
            metrics.tts_request_ts = time.time()

            seq = 0
            async for chunk in self._tts_stream_or_cancel(assistant_text):
                if seq == 0:
                    metrics.tts_first_chunk_ts = time.time()
                    log.info("tts_first_chunk", tts_startup_latency=metrics.tts_startup_latency())

                # Send control JSON
                await self._send_json(
                    AssistantAudioChunkEvent(
                        session_id=session_id,
                        turn_id=assistant_turn.turn_id,
                        seq=seq,
                    ).model_dump()
                )
                # Send binary audio
                await self._ws.send_bytes(chunk)
                seq += 1

            metrics.tts_completed_ts = time.time()
            assistant_turn.ended_at = metrics.tts_completed_ts

            log.info(
                "tts_completed",
                chunks=seq,
                total_response_latency=metrics.total_response_latency(),
                total_turn_duration=metrics.total_turn_duration(),
            )

            self._session.assistant_audio_active = False

            # ── Record latency into shared metrics collector ────────────
            collector.record(assistant_turn.turn_id, metrics)

            # Emit audio.completed with latency summary
            await self._send_json(
                AssistantAudioCompletedEvent(
                    session_id=session_id,
                    turn_id=assistant_turn.turn_id,
                    latency_summary=metrics.as_summary(),
                ).model_dump()
            )

            self._session.transition("listening")

        except asyncio.CancelledError:
            log.info("pipeline_cancelled")
            self._session.assistant_audio_active = False
            raise
        except Exception as exc:
            log.error("pipeline_error", error=str(exc))
            self._session.assistant_audio_active = False
            self._session.transition("listening")
            await self._send_json(
                OrchestratorErrorEvent(
                    session_id=session_id,
                    code="PIPELINE_ERROR",
                    message=str(exc),
                ).model_dump()
            )

    async def _tts_stream_or_cancel(self, text: str) -> AsyncGenerator[bytes, None]:
        """Wrapper so asyncio.CancelledError propagates correctly through the TTS generator."""
        async for chunk in self._tts.synthesize(text):
            yield chunk

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    async def _send_json(self, data: dict[str, Any]) -> None:
        import json

        try:
            await self._ws.send_text(json.dumps(data))
        except Exception as exc:
            logger.warning("ws_send_error", error=str(exc))
