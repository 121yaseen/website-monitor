import structlog
from fastapi import APIRouter
from fastapi.websockets import WebSocket, WebSocketDisconnect
from datetime import datetime
import json
from pydantic import ValidationError

from services.stt_gateway.models import (
    SessionState, SessionStartEvent, SessionEndEvent, ErrorEvent,
    TranscriptPartialEvent, TranscriptFinalEvent,
)
from services.stt_gateway.config import settings
from services.stt_gateway.providers.azure_speech import AzureSpeechProvider

logger = structlog.get_logger("stt_gateway.routes.ws")

router = APIRouter()


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
                        validated = SessionStartEvent.model_validate(data)
                        session = SessionState(
                            session_id=validated.session_id,
                            sample_rate=validated.sample_rate,
                            channels=validated.channels,
                            encoding=validated.encoding,
                        )
                        logger.info("session_started", session_id=validated.session_id,
                            sample_rate=validated.sample_rate, channels=validated.channels,
                            encoding=validated.encoding)

                        provider = AzureSpeechProvider(settings.subscription_key, settings.endpoint)

                        async def handle_partial(text: str) -> None:
                            event = TranscriptPartialEvent(
                                type="transcript.partial",
                                text=text,
                                session_id=session.session_id,
                                utterance_id=session.utterance_id or "utt-1",
                            )
                            await websocket.send_text(event.model_dump_json())

                        async def handle_final(text: str) -> None:
                            event = TranscriptFinalEvent(
                                type="transcript.final",
                                text=text,
                                session_id=session.session_id,
                                utterance_id=session.utterance_id or "utt-1",
                                first_audio_ts=session.first_audio_ts or 0.0,
                                first_partial_ts=session.first_partial_ts,
                                final_ts=datetime.now().timestamp(),
                            )
                            await websocket.send_text(event.model_dump_json())

                        provider.on_partial(handle_partial)
                        provider.on_final(handle_final)
                        await provider.connect(session.sample_rate, session.channels, session.encoding)

                    elif message_type == "session.end":
                        validated = SessionEndEvent.model_validate(data)
                        # Close provider first so Azure flushes the final transcript
                        if provider:
                            await provider.close()
                            provider = None
                        logger.info("session_ended", session_id=session.session_id,
                            chunk_count=session.chunk_count, total_bytes=session.total_bytes)
                        break

                elif "bytes" in message:
                    audio_data = message["bytes"]

                    if session is None:
                        await websocket.send_text(ErrorEvent(
                            type="error", session_id=None, code="NO_SESSION",
                            message="No session started").model_dump_json())
                        continue

                    session.total_bytes += len(audio_data)
                    session.chunk_count += 1
                    if session.first_audio_ts is None:
                        session.first_audio_ts = datetime.now().timestamp()
                    logger.info("audio_chunk_received", session_id=session.session_id,
                        seq=session.chunk_count, size=len(audio_data))

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
        logger.info("Browser disconnected", session_id=session.session_id if session else None)
    except Exception as e:
        logger.error("Error in WebSocket", session_id=session.session_id if session else None, error=str(e))
    finally:
        if provider:
            await provider.close()
        if session:
            logger.info("Closing session", session_id=session.session_id)
            session = None
