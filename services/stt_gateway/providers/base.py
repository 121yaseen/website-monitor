from abc import ABC, abstractmethod
from collections.abc import Awaitable, Callable


class STTProvider(ABC):
    @abstractmethod
    async def connect(self, sample_rate: int, channels: int, encoding: str) -> None: ...

    @abstractmethod
    async def send_audio(self, chunk: bytes) -> None: ...

    @abstractmethod
    async def close(self) -> None: ...

    @abstractmethod
    def on_partial(self, callback: Callable[[str], Awaitable[None]]) -> None: ...

    @abstractmethod
    def on_final(self, callback: Callable[[str], Awaitable[None]]) -> None: ...
