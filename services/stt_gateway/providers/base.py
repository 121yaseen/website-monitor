from abc import ABC, abstractmethod
from collections.abc import Callable


class STTProvider(ABC):
    @abstractmethod
    async def connect(self) -> None: ...

    @abstractmethod
    async def send_audio(self, chunk: bytes) -> None: ...

    @abstractmethod
    async def close(self) -> None: ...

    @abstractmethod
    def on_partial(self, callback: Callable[[str], None]) -> None: ...

    @abstractmethod
    def on_final(self, callback: Callable[[str], None]) -> None: ...
