"""Provider-agnostic LLM adapter interface."""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import AsyncGenerator

from services.agent_orchestrator.models import Turn


class LLMAdapter(ABC):
    """Abstract LLM adapter.  Concrete implementations wrap a specific provider."""

    @abstractmethod
    async def complete(
        self,
        system_prompt: str,
        turns: list[Turn],
    ) -> str:
        """Return the full assistant text for the given conversation history."""
        ...

    @abstractmethod
    def stream(
        self,
        system_prompt: str,
        turns: list[Turn],
    ) -> AsyncGenerator[str, None]:
        """Yield text tokens as they arrive (for future streaming optimisation)."""
        ...
