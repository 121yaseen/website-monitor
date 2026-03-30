"""Provider-agnostic TTS adapter interface."""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import AsyncGenerator


class TTSAdapter(ABC):
    """Abstract TTS adapter.  Concrete implementations wrap a specific provider."""

    @abstractmethod
    def synthesize(self, text: str) -> AsyncGenerator[bytes, None]:
        """Yield raw audio chunks (PCM or encoded) for the given text."""
        ...

    @abstractmethod
    async def cancel(self) -> None:
        """Cancel any in-progress synthesis."""
        ...
