"""
Typed event schema and domain models for the agent orchestrator.

Internal events (orchestrator → client over WebSocket):
  assistant.response.started
  assistant.response.text
  assistant.audio.chunk
  assistant.audio.completed
  assistant.interrupted

Incoming events from STT layer (forwarded by client or bridged directly):
  user.final_transcript
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field
import time
import uuid


# ---------------------------------------------------------------------------
# Session state machine
# ---------------------------------------------------------------------------

SessionStateType = Literal[
    "idle",
    "listening",
    "transcribing",
    "thinking",
    "speaking",
    "interrupted",
    "closed",
]


# ---------------------------------------------------------------------------
# Latency metrics
# ---------------------------------------------------------------------------


class TurnLatencyMetrics(BaseModel):
    model_config = {"arbitrary_types_allowed": True}

    user_first_audio_ts: float | None = None
    user_final_transcript_ts: float | None = None
    llm_request_ts: float | None = None
    llm_response_ts: float | None = None
    tts_request_ts: float | None = None
    tts_first_chunk_ts: float | None = None
    tts_completed_ts: float | None = None

    def stt_latency(self) -> float | None:
        if self.user_first_audio_ts is not None and self.user_final_transcript_ts is not None:
            return self.user_final_transcript_ts - self.user_first_audio_ts
        return None

    def llm_latency(self) -> float | None:
        if self.llm_request_ts is not None and self.llm_response_ts is not None:
            return self.llm_response_ts - self.llm_request_ts
        return None

    def tts_startup_latency(self) -> float | None:
        if self.tts_request_ts is not None and self.tts_first_chunk_ts is not None:
            return self.tts_first_chunk_ts - self.tts_request_ts
        return None

    def total_response_latency(self) -> float | None:
        if self.user_final_transcript_ts is not None and self.tts_first_chunk_ts is not None:
            return self.tts_first_chunk_ts - self.user_final_transcript_ts
        return None

    def total_turn_duration(self) -> float | None:
        if self.user_first_audio_ts is not None and self.tts_completed_ts is not None:
            return self.tts_completed_ts - self.user_first_audio_ts
        return None

    def as_summary(self) -> dict[str, float | None]:
        return {
            "stt_latency": self.stt_latency(),
            "llm_latency": self.llm_latency(),
            "tts_startup_latency": self.tts_startup_latency(),
            "total_response_latency": self.total_response_latency(),
            "total_turn_duration": self.total_turn_duration(),
        }


# ---------------------------------------------------------------------------
# Turn
# ---------------------------------------------------------------------------


class Turn(BaseModel):
    turn_id: str = Field(default_factory=lambda: f"turn-{uuid.uuid4().hex[:8]}")
    speaker: Literal["user", "assistant"]
    text: str
    started_at: float = Field(default_factory=time.time)
    ended_at: float | None = None
    interrupted: bool = False
    latency_metrics: TurnLatencyMetrics | None = None


# ---------------------------------------------------------------------------
# Session memory
# ---------------------------------------------------------------------------


class SessionMemory(BaseModel):
    session_id: str
    system_prompt: str = "You are a helpful voice assistant. Be concise and conversational."
    turns: list[Turn] = Field(default_factory=list)
    max_context_turns: int = 8
    state: SessionStateType = "idle"
    assistant_audio_active: bool = False
    current_turn_id: str | None = None

    def add_turn(self, turn: Turn) -> None:
        self.turns.append(turn)
        self.current_turn_id = turn.turn_id

    def get_context_turns(self) -> list[Turn]:
        """Return the rolling window of recent turns for LLM context."""
        return self.turns[-self.max_context_turns :]

    def mark_interrupted(self) -> None:
        """Mark the current (last) assistant turn as interrupted."""
        for turn in reversed(self.turns):
            if turn.speaker == "assistant" and not turn.interrupted:
                turn.interrupted = True
                turn.ended_at = time.time()
                break

    def transition(self, new_state: SessionStateType) -> None:
        self.state = new_state


# ---------------------------------------------------------------------------
# Internal events (orchestrator ↔ client WebSocket)
# ---------------------------------------------------------------------------


class UserFinalTranscriptEvent(BaseModel):
    type: Literal["user.final_transcript"] = "user.final_transcript"
    session_id: str
    utterance_id: str
    text: str
    first_audio_ts: float | None = None
    final_ts: float = Field(default_factory=time.time)


class AssistantResponseStartedEvent(BaseModel):
    type: Literal["assistant.response.started"] = "assistant.response.started"
    session_id: str
    turn_id: str
    timestamp: float = Field(default_factory=time.time)


class AssistantResponseTextEvent(BaseModel):
    type: Literal["assistant.response.text"] = "assistant.response.text"
    session_id: str
    turn_id: str
    text: str
    timestamp: float = Field(default_factory=time.time)


class AssistantAudioChunkEvent(BaseModel):
    type: Literal["assistant.audio.chunk"] = "assistant.audio.chunk"
    session_id: str
    turn_id: str
    seq: int
    # audio bytes sent separately as binary frame


class AssistantAudioCompletedEvent(BaseModel):
    type: Literal["assistant.audio.completed"] = "assistant.audio.completed"
    session_id: str
    turn_id: str
    timestamp: float = Field(default_factory=time.time)
    latency_summary: dict[str, float | None] = Field(default_factory=dict)


class AssistantInterruptedEvent(BaseModel):
    type: Literal["assistant.interrupted"] = "assistant.interrupted"
    session_id: str
    turn_id: str | None
    timestamp: float = Field(default_factory=time.time)


class OrchestratorErrorEvent(BaseModel):
    type: Literal["error"] = "error"
    session_id: str | None
    code: str
    message: str


# ---------------------------------------------------------------------------
# Client → orchestrator control messages
# ---------------------------------------------------------------------------


class OrchestratorSessionStartEvent(BaseModel):
    type: Literal["session.start"]
    session_id: str
    system_prompt: str | None = None


class OrchestratorSessionEndEvent(BaseModel):
    type: Literal["session.end"]
    session_id: str


class UserBargeInEvent(BaseModel):
    """Signal that the user has started speaking during assistant playback."""
    type: Literal["user.barge_in"] = "user.barge_in"
    session_id: str
    timestamp: float = Field(default_factory=time.time)
