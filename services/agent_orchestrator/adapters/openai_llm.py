"""OpenAI-compatible LLM adapter (works with OpenAI and Azure OpenAI endpoints)."""

from __future__ import annotations

import json
from collections.abc import AsyncGenerator
from typing import Any

import httpx
import structlog

from services.agent_orchestrator.adapters.llm_base import LLMAdapter
from services.agent_orchestrator.models import Turn

logger = structlog.get_logger("agent_orchestrator.adapters.openai_llm")


def _turns_to_messages(system_prompt: str, turns: list[Turn]) -> list[dict[str, str]]:
    messages: list[dict[str, str]] = [{"role": "system", "content": system_prompt}]
    for turn in turns:
        role = "user" if turn.speaker == "user" else "assistant"
        content = turn.text
        if turn.interrupted:
            content += " [interrupted]"
        messages.append({"role": role, "content": content})
    return messages


class OpenAILLMAdapter(LLMAdapter):
    def __init__(
        self,
        api_key: str,
        base_url: str,
        model: str,
        is_azure: bool = False,
    ) -> None:
        self._api_key = api_key
        self._base_url = base_url.rstrip("/")
        self._model = model
        self._is_azure = is_azure

    def _auth_headers(self) -> dict[str, str]:
        """Azure OpenAI uses api-key header; standard OpenAI uses Authorization Bearer."""
        if self._is_azure:
            return {"api-key": self._api_key, "Content-Type": "application/json"}
        return {"Authorization": f"Bearer {self._api_key}", "Content-Type": "application/json"}

    async def complete(self, system_prompt: str, turns: list[Turn]) -> str:
        messages = _turns_to_messages(system_prompt, turns)
        logger.info("llm_request", model=self._model, turn_count=len(turns), is_azure=self._is_azure)
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(
                f"{self._base_url}/chat/completions",
                headers=self._auth_headers(),
                json={
                    "model": self._model,
                    "messages": messages,
                    "max_tokens": 512,
                    "temperature": 0.7,
                },
            )
            response.raise_for_status()
            data: Any = response.json()
            text: str = data["choices"][0]["message"]["content"]
            logger.info("llm_response", chars=len(text))
            return text

    async def stream(
        self, system_prompt: str, turns: list[Turn]
    ) -> AsyncGenerator[str, None]:
        messages = _turns_to_messages(system_prompt, turns)
        async with httpx.AsyncClient(timeout=60.0) as client:
            async with client.stream(
                "POST",
                f"{self._base_url}/chat/completions",
                headers=self._auth_headers(),
                json={
                    "model": self._model,
                    "messages": messages,
                    "max_tokens": 512,
                    "temperature": 0.7,
                    "stream": True,
                },
            ) as resp:
                resp.raise_for_status()
                async for line in resp.aiter_lines():
                    if line.startswith("data: "):
                        chunk_str = line[6:]
                        if chunk_str.strip() == "[DONE]":
                            break
                        chunk = json.loads(chunk_str)
                        delta = chunk["choices"][0].get("delta", {})
                        content = delta.get("content", "")
                        if content:
                            yield content

