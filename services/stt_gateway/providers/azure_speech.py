import asyncio
from collections.abc import Awaitable, Callable
from typing import Any

import azure.cognitiveservices.speech as speechsdk

from .base import STTProvider


class AzureSpeechProvider(STTProvider):
    def __init__(self, subscription_key: str, endpoint: str) -> None:
        self.speech_config = speechsdk.SpeechConfig(
            subscription=subscription_key,
            endpoint=endpoint,
        )
        self.speech_config.speech_recognition_language = "en-US"

        self._push_stream: speechsdk.audio.PushAudioInputStream | None = None
        self._recognizer: speechsdk.SpeechRecognizer | None = None
        self._on_partial_cb: Callable[[str], Awaitable[None]] | None = None
        self._on_final_cb: Callable[[str], Awaitable[None]] | None = None

    def on_partial(self, callback: Callable[[str], Awaitable[None]]) -> None:
        self._on_partial_cb = callback

    def on_final(self, callback: Callable[[str], Awaitable[None]]) -> None:
        self._on_final_cb = callback

    async def connect(self, sample_rate: int, channels: int, encoding: str) -> None:
        audio_format = speechsdk.audio.AudioStreamFormat(
            samples_per_second=sample_rate, bits_per_sample=16, channels=channels
        )
        self._push_stream = speechsdk.audio.PushAudioInputStream(audio_format)
        audio_config = speechsdk.audio.AudioConfig(stream=self._push_stream)
        self._recognizer = speechsdk.SpeechRecognizer(
            speech_config=self.speech_config, audio_config=audio_config
        )
        loop = asyncio.get_event_loop()

        def on_recognizing(evt: Any) -> None:
            if self._on_partial_cb and evt.result.text:
                asyncio.run_coroutine_threadsafe(
                    self._on_partial_cb(evt.result.text),  # type: ignore[arg-type]
                    loop,
                )

        def on_recognized(evt: Any) -> None:
            if self._on_final_cb and evt.result.text:
                asyncio.run_coroutine_threadsafe(
                    self._on_final_cb(evt.result.text),  # type: ignore[arg-type]
                    loop,
                )

        self._recognizer.recognizing.connect(on_recognizing)
        self._recognizer.recognized.connect(on_recognized)
        self._recognizer.start_continuous_recognition_async()

    async def send_audio(self, chunk: bytes) -> None:
        if self._push_stream:
            self._push_stream.write(chunk)

    async def close(self) -> None:
        if self._push_stream:
            self._push_stream.close()
        if self._recognizer:
            loop = asyncio.get_event_loop()
            await loop.run_in_executor(
                None, self._recognizer.stop_continuous_recognition_async().get
            )
