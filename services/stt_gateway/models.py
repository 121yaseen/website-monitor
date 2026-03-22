from typing import Literal

from pydantic import BaseModel


class SessionStartEvent(BaseModel):
    type: Literal["session.start"]
    session_id: str
    sample_rate: int
    channels: int
    encoding: str


class AudioChunkEvent(BaseModel):
    type: Literal["audio.chunk"]
    session_id: str
    seq: int


class SessionEndEvent(BaseModel):
    type: Literal["session.end"]
    session_id: str


class TranscriptPartialEvent(BaseModel):
    type: Literal["transcript.partial"]
    session_id: str
    utterance_id: str
    text: str


class TranscriptFinalEvent(BaseModel):
    type: Literal["transcript.final"]
    session_id: str
    utterance_id: str
    text: str
    first_audio_ts: float
    first_partial_ts: float | None
    final_ts: float
    last_partial_ts: float | None


class ErrorEvent(BaseModel):
    type: Literal["error"]
    session_id: str | None
    code: str
    message: str


class CompletedUtterance(BaseModel):
    utterance_id: str
    text: str
    first_audio_ts: float
    first_partial_ts: float | None
    final_ts: float


class SessionState(BaseModel):
    session_id: str
    utterance_id: str | None = None
    sample_rate: int
    channels: int
    encoding: str
    chunk_count: int = 0
    total_bytes: int = 0
    first_audio_ts: float | None = None
    first_partial_ts: float | None = None
    final_ts: float | None = None
    last_partial_ts: float | None = None
    committed: bool = True
    utterance_count: int = 0
    completed_utterances: list[CompletedUtterance] = []
    last_chunk_ts: float | None = None
    event_log: list[dict[str, object]] = []
