"""
Tests for the agent orchestrator.

Covers:
- Session memory: turn ordering, state retention, rolling context window, session reset.
- TurnLatencyMetrics: computed properties.
- Orchestrator: LLM→TTS pipeline with stub adapters, barge-in handling, interruption state.
- MetricsCollector: record and summary.
- OrchestratorSessionStart/End/Transcript event validation.
"""

from __future__ import annotations

import json
import time
from typing import Any

import pytest

from services.agent_orchestrator.adapters.stub import StubLLMAdapter, StubTTSAdapter
from services.agent_orchestrator.metrics import MetricsCollector
from services.agent_orchestrator.models import (
    OrchestratorSessionStartEvent,
    SessionMemory,
    Turn,
    TurnLatencyMetrics,
    UserFinalTranscriptEvent,
)
from services.agent_orchestrator.orchestrator import Orchestrator

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def make_session(session_id: str = "test-session") -> SessionMemory:
    return SessionMemory(session_id=session_id)


def make_user_turn(text: str = "hello") -> Turn:
    return Turn(speaker="user", text=text, started_at=time.time())


def make_assistant_turn(text: str = "hi there") -> Turn:
    return Turn(speaker="assistant", text=text, started_at=time.time())


def make_transcript_event(
    text: str = "what is the weather",
    session_id: str = "test-session",
) -> UserFinalTranscriptEvent:
    now = time.time()
    return UserFinalTranscriptEvent(
        type="user.final_transcript",
        session_id=session_id,
        utterance_id="utt-1",
        text=text,
        first_audio_ts=now - 0.5,
        final_ts=now,
    )


class FakeWebSocket:
    """Minimal WebSocket stand-in that records sent frames."""

    def __init__(self) -> None:
        self.text_frames: list[str] = []
        self.binary_frames: list[bytes] = []

    async def send_text(self, data: str) -> None:
        self.text_frames.append(data)

    async def send_bytes(self, data: bytes) -> None:
        self.binary_frames.append(data)

    def last_json(self) -> dict[str, Any]:
        result: dict[str, Any] = json.loads(self.text_frames[-1])
        return result

    def all_event_types(self) -> list[str]:
        return [json.loads(f).get("type") for f in self.text_frames]


# ---------------------------------------------------------------------------
# SessionMemory tests
# ---------------------------------------------------------------------------


class TestSessionMemory:
    def test_add_turn_ordering(self) -> None:
        session = make_session()
        t1 = make_user_turn("hello")
        t2 = make_assistant_turn("hi")
        session.add_turn(t1)
        session.add_turn(t2)
        assert len(session.turns) == 2
        assert session.turns[0].speaker == "user"
        assert session.turns[1].speaker == "assistant"

    def test_state_retention(self) -> None:
        session = make_session()
        session.transition("listening")
        assert session.state == "listening"

    def test_state_transitions_to_thinking(self) -> None:
        session = make_session()
        session.transition("thinking")
        assert session.state == "thinking"

    def test_rolling_context_window(self) -> None:
        session = make_session()
        session.max_context_turns = 4
        for i in range(10):
            session.add_turn(make_user_turn(f"msg {i}"))
        context = session.get_context_turns()
        assert len(context) == 4
        assert context[-1].text == "msg 9"

    def test_mark_interrupted(self) -> None:
        session = make_session()
        session.add_turn(make_user_turn("hey"))
        at = make_assistant_turn("sure")
        session.add_turn(at)
        session.mark_interrupted()
        assert session.turns[-1].interrupted is True
        assert session.turns[-1].ended_at is not None

    def test_mark_interrupted_no_assistant_turn(self) -> None:
        """mark_interrupted should be a no-op if there is no assistant turn."""
        session = make_session()
        session.add_turn(make_user_turn("hey"))
        session.mark_interrupted()  # should not raise
        assert session.turns[0].interrupted is False

    def test_session_reset_via_new_instance(self) -> None:
        session = make_session()
        session.add_turn(make_user_turn("hello"))
        session2 = make_session()
        assert len(session2.turns) == 0

    def test_missing_transcript_edge_case(self) -> None:
        session = make_session()
        # Empty text turn should still be accepted
        turn = Turn(speaker="user", text="", started_at=time.time())
        session.add_turn(turn)
        assert session.turns[0].text == ""


# ---------------------------------------------------------------------------
# TurnLatencyMetrics tests
# ---------------------------------------------------------------------------


class TestTurnLatencyMetrics:
    def test_stt_latency(self) -> None:
        m = TurnLatencyMetrics(user_first_audio_ts=100.0, user_final_transcript_ts=100.4)
        assert m.stt_latency() == pytest.approx(0.4)

    def test_llm_latency(self) -> None:
        m = TurnLatencyMetrics(llm_request_ts=100.0, llm_response_ts=100.8)
        assert m.llm_latency() == pytest.approx(0.8)

    def test_tts_startup_latency(self) -> None:
        m = TurnLatencyMetrics(tts_request_ts=100.0, tts_first_chunk_ts=100.2)
        assert m.tts_startup_latency() == pytest.approx(0.2)

    def test_total_response_latency(self) -> None:
        m = TurnLatencyMetrics(user_final_transcript_ts=100.0, tts_first_chunk_ts=101.5)
        assert m.total_response_latency() == pytest.approx(1.5)

    def test_returns_none_when_timestamps_missing(self) -> None:
        m = TurnLatencyMetrics()
        assert m.stt_latency() is None
        assert m.llm_latency() is None
        assert m.tts_startup_latency() is None
        assert m.total_response_latency() is None

    def test_as_summary_keys(self) -> None:
        m = TurnLatencyMetrics()
        summary = m.as_summary()
        assert "stt_latency" in summary
        assert "llm_latency" in summary
        assert "tts_startup_latency" in summary
        assert "total_response_latency" in summary
        assert "total_turn_duration" in summary


# ---------------------------------------------------------------------------
# Orchestrator tests (using stub adapters + FakeWebSocket)
# ---------------------------------------------------------------------------


class TestOrchestrator:
    def _make_orch(
        self, response: str = "I'm fine, thanks!"
    ) -> tuple[Orchestrator, SessionMemory, FakeWebSocket]:
        session = make_session()
        session.transition("listening")
        ws = FakeWebSocket()
        orch = Orchestrator(
            session=session,
            llm=StubLLMAdapter(response=response),
            tts=StubTTSAdapter(),
            ws=ws,  # type: ignore[arg-type]
        )
        return orch, session, ws

    @pytest.mark.asyncio
    async def test_full_pipeline_runs(self) -> None:
        orch, session, ws = self._make_orch()
        evt = make_transcript_event()
        await orch.handle_transcript(evt)

        # Wait for the pipeline task to finish
        if orch._pipeline_task:
            await orch._pipeline_task

        types = ws.all_event_types()
        assert "assistant.response.started" in types
        assert "assistant.response.text" in types
        assert "assistant.audio.completed" in types
        assert session.state == "listening"

    @pytest.mark.asyncio
    async def test_user_turn_added_to_history(self) -> None:
        orch, session, ws = self._make_orch()
        await orch.handle_transcript(make_transcript_event("what time is it"))
        if orch._pipeline_task:
            await orch._pipeline_task
        user_turns = [t for t in session.turns if t.speaker == "user"]
        assert len(user_turns) == 1
        assert user_turns[0].text == "what time is it"

    @pytest.mark.asyncio
    async def test_assistant_turn_added_to_history(self) -> None:
        orch, session, ws = self._make_orch("It is noon.")
        await orch.handle_transcript(make_transcript_event())
        if orch._pipeline_task:
            await orch._pipeline_task
        assistant_turns = [t for t in session.turns if t.speaker == "assistant"]
        assert len(assistant_turns) == 1
        assert assistant_turns[0].text == "It is noon."

    @pytest.mark.asyncio
    async def test_multi_turn_context(self) -> None:
        orch, session, ws = self._make_orch()
        for i in range(3):
            evt = make_transcript_event(f"question {i}")
            await orch.handle_transcript(evt)
            if orch._pipeline_task:
                await orch._pipeline_task

        # 3 user + 3 assistant = 6 turns
        assert len(session.turns) == 6

    @pytest.mark.asyncio
    async def test_barge_in_during_speaking(self) -> None:
        orch, session, _ = self._make_orch()
        # Force state to speaking to simulate mid-TTS barge-in
        session.transition("speaking")
        session.add_turn(make_assistant_turn("I'm speaking right now…"))
        session.assistant_audio_active = True

        await orch.handle_barge_in()

        assert session.state == "listening"
        assert session.assistant_audio_active is False
        interrupted = [t for t in session.turns if t.interrupted]
        assert len(interrupted) == 1

    @pytest.mark.asyncio
    async def test_barge_in_ignored_when_listening(self) -> None:
        orch, session, ws = self._make_orch()
        session.transition("listening")
        await orch.handle_barge_in()  # should be no-op
        assert session.state == "listening"
        # No interrupted event emitted
        types = ws.all_event_types()
        assert "assistant.interrupted" not in types

    @pytest.mark.asyncio
    async def test_close_transitions_to_closed(self) -> None:
        orch, session, _ = self._make_orch()
        await orch.close()
        assert session.state == "closed"

    @pytest.mark.asyncio
    async def test_audio_chunks_sent_as_binary(self) -> None:
        orch, _, ws = self._make_orch()
        await orch.handle_transcript(make_transcript_event())
        if orch._pipeline_task:
            await orch._pipeline_task
        # StubTTSAdapter emits 3 chunks
        assert len(ws.binary_frames) == 3

    @pytest.mark.asyncio
    async def test_latency_summary_in_completed_event(self) -> None:
        orch, _, ws = self._make_orch()
        await orch.handle_transcript(make_transcript_event())
        if orch._pipeline_task:
            await orch._pipeline_task
        completed_frames = [
            json.loads(f)
            for f in ws.text_frames
            if json.loads(f).get("type") == "assistant.audio.completed"
        ]
        assert len(completed_frames) == 1
        summary = completed_frames[0]["latency_summary"]
        assert "llm_latency" in summary
        assert "tts_startup_latency" in summary


# ---------------------------------------------------------------------------
# MetricsCollector tests
# ---------------------------------------------------------------------------


class TestMetricsCollector:
    def test_record_and_summary(self) -> None:
        coll = MetricsCollector()
        m = TurnLatencyMetrics(
            user_first_audio_ts=0.0,
            user_final_transcript_ts=0.3,
            llm_request_ts=0.3,
            llm_response_ts=1.0,
            tts_request_ts=1.0,
            tts_first_chunk_ts=1.2,
            tts_completed_ts=2.0,
        )
        coll.record("turn-1", m)
        summary = coll.summary()
        assert summary["stt_latency"]["p50"] == pytest.approx(0.3)
        assert summary["llm_latency"]["p50"] == pytest.approx(0.7)

    def test_empty_summary_returns_nones(self) -> None:
        coll = MetricsCollector()
        summary = coll.summary()
        for stage_data in summary.values():
            assert stage_data["p50"] is None
            assert stage_data["p95"] is None

    def test_p95_with_multiple_records(self) -> None:
        coll = MetricsCollector()
        for i in range(1, 11):  # 10 records, LLM latency 0.1..1.0
            m = TurnLatencyMetrics(llm_request_ts=0.0, llm_response_ts=float(i) * 0.1)
            coll.record(f"turn-{i}", m)
        summary = coll.summary()
        # p50 of 10 values [0.1..1.0] → 0.55
        assert summary["llm_latency"]["p50"] == pytest.approx(0.55)
        # p95 of 10 values [0.1..1.0] → 0.955 (linear interpolation at idx=8.55)
        assert summary["llm_latency"]["p95"] == pytest.approx(0.955, rel=1e-3)


# ---------------------------------------------------------------------------
# Event model validation tests
# ---------------------------------------------------------------------------


class TestEventModels:
    def test_session_start_event(self) -> None:
        evt = OrchestratorSessionStartEvent.model_validate(
            {"type": "session.start", "session_id": "abc"}
        )
        assert evt.session_id == "abc"
        assert evt.system_prompt is None

    def test_transcript_event_missing_text(self) -> None:
        from pydantic import ValidationError

        with pytest.raises(ValidationError):
            UserFinalTranscriptEvent.model_validate(
                {
                    "type": "user.final_transcript",
                    "session_id": "x",
                    "utterance_id": "u1",
                    # text is missing
                }
            )

    def test_transcript_event_full(self) -> None:
        now = time.time()
        evt = UserFinalTranscriptEvent.model_validate(
            {
                "type": "user.final_transcript",
                "session_id": "s1",
                "utterance_id": "utt-1",
                "text": "hello world",
                "first_audio_ts": now - 1,
                "final_ts": now,
            }
        )
        assert evt.text == "hello world"
