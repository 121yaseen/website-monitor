import asyncio

from collections.abc import Awaitable, Callable

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

    def on_partial(self, callback):
        self._on_partial_cb = callback

    def on_final(self, callback):
        self._on_final_cb = callback

    async def connect(self, sample_rate, channels, encoding):
        # 1. Create audio format
        audio_format = speechsdk.audio.AudioStreamFormat(
            samples_per_second=sample_rate,
            bits_per_sample=16,
            channels=channels
        )
        # 2. Create push stream + audio config
        self._push_stream = speechsdk.audio.PushAudioInputStream(audio_format)
        audio_config = speechsdk.audio.AudioConfig(stream=self._push_stream)
        # 3. Create recognizer
        self._recognizer = speechsdk.SpeechRecognizer(
            speech_config=self.speech_config,
            audio_config=audio_config
        )
        # 4. Wire events (sync → async bridge)
        loop = asyncio.get_event_loop()
        
        def on_recognizing(evt):
            if self._on_partial_cb and evt.result.text:
                asyncio.run_coroutine_threadsafe(self._on_partial_cb(evt.result.text), loop)
        
        def on_recognized(evt):
            if self._on_final_cb and evt.result.text:
                asyncio.run_coroutine_threadsafe(self._on_final_cb(evt.result.text), loop)
        
        self._recognizer.recognizing.connect(on_recognizing)
        self._recognizer.recognized.connect(on_recognized)
        # 5. Start
        self._recognizer.start_continuous_recognition_async()

    async def send_audio(self, chunk):
        if self._push_stream:
            self._push_stream.write(chunk)  # chunk is bytes

    async def close(self):
        if self._push_stream:
            self._push_stream.close()  # signals end of audio
        if self._recognizer:
            # Run the blocking .get() in a thread so it doesn't block the event loop
            # (Azure fires the final callback on its own thread, which needs the loop free)
            loop = asyncio.get_event_loop()
            await loop.run_in_executor(
                None, self._recognizer.stop_continuous_recognition_async().get
            )

