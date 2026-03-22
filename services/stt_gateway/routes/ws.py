import json
from collections.abc import Awaitable, Callable
from datetime import datetime

import structlog
from fastapi import APIRouter
from fastapi.websockets import WebSocket, WebSocketDisconnect
from pydantic import ValidationError

from services.stt_gateway.config import settings
from services.stt_gateway.models import (
    CompletedUtterance,
    ErrorEvent,
    SessionEndEvent,
    SessionStartEvent,
    SessionState,
    TranscriptFinalEvent,
    TranscriptPartialEvent,
)
from services.stt_gateway.providers.azure_speech import AzureSpeechProvider

logger = structlog.get_logger("stt_gateway.routes.ws")

router = APIRouter()


def _make_partial_handler(s: SessionState, ws: WebSocket) -> Callable[[str], Awaitable[None]]:
    async def handle_partial(text: str) -> None:
        if s.committed:
            s.utterance_count += 1
            s.committed = False
            s.utterance_id = f"utt-{s.utterance_count}"
            s.first_partial_ts = datetime.now().timestamp()
            s.first_audio_ts = s.last_chunk_ts
        s.last_partial_ts = datetime.now().timestamp()
        event = TranscriptPartialEvent(
            type="transcript.partial",
            text=text,
            session_id=s.session_id,
            utterance_id=s.utterance_id,
        )
        s.event_log.append(event.model_dump())
        await ws.send_text(event.model_dump_json())

    return handle_partial


def _make_final_handler(s: SessionState, ws: WebSocket) -> Callable[[str], Awaitable[None]]:
    async def handle_final(text: str) -> None:
        if s.committed:
            print("committed is true, skipping the final")
            return
        event = TranscriptFinalEvent(
            type="transcript.final",
            text=text,
            session_id=s.session_id,
            utterance_id=s.utterance_id or "utt-1",
            first_audio_ts=s.first_audio_ts or 0.0,
            first_partial_ts=s.first_partial_ts,
            final_ts=datetime.now().timestamp(),
            last_partial_ts=s.last_partial_ts,
        )
        s.final_ts = event.final_ts
        s.completed_utterances.append(
            CompletedUtterance(
                utterance_id=s.utterance_id,
                text=text,
                first_audio_ts=s.first_audio_ts,
                first_partial_ts=s.first_partial_ts,
                final_ts=event.final_ts,
            )
        )
        s.committed = True
        assert s.first_partial_ts is not None
        assert s.first_audio_ts is not None
        assert s.last_partial_ts is not None
        logger.info(
            "utterance_committed",
            utterance_id=s.utterance_id,
            first_word_latency=s.first_partial_ts - s.first_audio_ts,
            total_utterance_latency=s.final_ts - s.first_audio_ts,
            utterance_duration=s.final_ts - s.first_partial_ts,
            provider_response_delay=s.final_ts - s.last_partial_ts,
        )
        s.event_log.append(event.model_dump())

        await ws.send_text(event.model_dump_json())

    return handle_final


@router.websocket("/ws/audio")
async def audio(websocket: WebSocket) -> None:
    await websocket.accept()
    session: SessionState | None = None
    provider: AzureSpeechProvider | None = None

    try:
        while True:
            message = await websocket.receive()
            if message["type"] == "websocket.disconnect":
                break

            try:
                if "text" in message:
                    data = json.loads(message["text"])
                    message_type = data.get("type")
                    if message_type == "session.start":
                        start_event = SessionStartEvent.model_validate(data)
                        session = SessionState(
                            session_id=start_event.session_id,
                            sample_rate=start_event.sample_rate,
                            channels=start_event.channels,
                            encoding=start_event.encoding,
                        )
                        logger.info(
                            "session_started",
                            session_id=start_event.session_id,
                            sample_rate=start_event.sample_rate,
                            channels=start_event.channels,
                            encoding=start_event.encoding,
                        )
                        session.event_log.append(start_event.model_dump())

                        provider = AzureSpeechProvider(settings.subscription_key, settings.endpoint)
                        provider.on_partial(_make_partial_handler(session, websocket))
                        provider.on_final(_make_final_handler(session, websocket))
                        try:
                            await provider.connect(
                                session.sample_rate, session.channels, session.encoding
                            )
                        except Exception as e:
                            logger.error(
                                "Failed to connect to provider",
                                session_id=session.session_id,
                                error=str(e),
                            )
                            await websocket.send_text(
                                ErrorEvent(
                                    type="error",
                                    session_id=session.session_id,
                                    code="PROVIDER_CONNECTION_FAILED",
                                    message=str(e),
                                ).model_dump_json()
                            )
                            break

                    elif message_type == "session.end":
                        SessionEndEvent.model_validate(data)
                        if provider:
                            await provider.close()
                            provider = None
                        if session:
                            logger.info(
                                "session_ended",
                                session_id=session.session_id,
                                chunk_count=session.chunk_count,
                                total_bytes=session.total_bytes,
                            )
                            session.event_log.append(data)
                        break

                elif "bytes" in message:
                    audio_data = message["bytes"]

                    if session is None:
                        await websocket.send_text(
                            ErrorEvent(
                                type="error",
                                session_id=None,
                                code="NO_SESSION",
                                message="No session started",
                            ).model_dump_json()
                        )
                        continue

                    session.total_bytes += len(audio_data)
                    session.chunk_count += 1
                    session.last_chunk_ts = datetime.now().timestamp()
                    if session.first_audio_ts is None:
                        session.first_audio_ts = datetime.now().timestamp()
                    logger.info(
                        "audio_chunk_received",
                        session_id=session.session_id,
                        seq=session.chunk_count,
                        size=len(audio_data),
                    )
                    if session.chunk_count == 1 or session.chunk_count % 10 == 0:
                        session.event_log.append(
                            {
                                "type": "audio_chunk_received",
                                "session_id": session.session_id,
                                "seq": session.chunk_count,
                                "size": len(audio_data),
                                "timestamp": datetime.now().timestamp(),
                            }
                        )

                    if provider:
                        await provider.send_audio(audio_data)

            except (json.JSONDecodeError, ValidationError) as e:
                await websocket.send_text(
                    ErrorEvent(
                        type="error",
                        session_id=session.session_id if session else None,
                        code="INVALID_MESSAGE",
                        message=str(e),
                    ).model_dump_json()
                )
    except WebSocketDisconnect:
        logger.info(
            "Browser disconnected",
            session_id=session.session_id if session else None,
        )
        if session:
            logger.info(
                "session_ended",
                session_id=session.session_id,
                chunk_count=session.chunk_count,
                total_bytes=session.total_bytes,
                completed_utterances=len(session.completed_utterances),
            )
            session.event_log.append(
                {
                    "type": "session_ended",
                    "session_id": session.session_id,
                    "chunk_count": session.chunk_count,
                    "total_bytes": session.total_bytes,
                    "completed_utterances": len(session.completed_utterances),
                    "timestamp": datetime.now().timestamp(),
                }
            )
    except Exception as e:
        logger.error(
            "Error in WebSocket",
            session_id=session.session_id if session else None,
            error=str(e),
        )
    finally:
        if provider:
            await provider.close()
        if session:
            logger.info("Closing session", session_id=session.session_id)
            logger.info(
                "session_event_log", session_id=session.session_id, events=session.event_log
            )
            session = None
