"""
InfraLLMAdapter — bridges aiPlat-infra LLMClient to core's ILLMAdapter interface.

This adapter wraps an infra LLMClient (from create_llm_client factory) so it
can be used anywhere core expects an ILLMAdapter. Per architecture contract:
core should access LLM capabilities through infra, not maintain parallel adapters.

Message flow:
  core caller → InfraLLMAdapter.generate(messages, config)
                  → converts messages+config to infra ChatRequest
                  → calls infra_client.achat(request) with retry
                  → converts ChatResponse back to LLMResponse
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from typing import Any, AsyncIterator, Dict, List, Optional

from core.adapters.llm.base import (
    ILLMAdapter,
    LLMConfig as CoreLLMConfig,
    LLMResponse,
    AdapterMetadata,
)
from infra.llm.schemas import (
    Message as InfraMessage,
    ChatRequest,
    LLMConfig as InfraLLMConfig,
)


class InfraLLMAdapter(ILLMAdapter):
    """Wraps an aiPlat-infra LLMClient to satisfy core's ILLMAdapter interface."""

    def __init__(self, client: Any, provider: str = "infra", model: str = ""):
        self._client = client
        self._provider = provider
        self._model = model or getattr(getattr(client, "config", None), "model", None) or "unknown"
        self._metadata = AdapterMetadata(
            name=f"infra-{self._provider}",
            provider=self._provider,
            version="1.0.0",
            capabilities=["chat", "stream", "embed"],
            supports_streaming=hasattr(client, "stream_chat"),
        )

    @property
    def metadata(self) -> AdapterMetadata:
        return self._metadata

    @property
    def model_name(self) -> str:
        return self._model

    @model_name.setter
    def model_name(self, value: str) -> None:
        self._model = value

    async def generate(
        self,
        messages: List[Dict[str, str]],
        config: Optional[CoreLLMConfig] = None,
    ) -> LLMResponse:
        return await self._generate_with_retry(
            self._generate_impl, messages, config,
            max_retries=config.max_retries if config else 3,
        )

    async def _generate_impl(
        self,
        messages: List[Dict[str, str]],
        config: Optional[CoreLLMConfig],
    ) -> LLMResponse:
        request = self._build_request(messages, config)
        response = await self._client.achat(request)
        return self._convert_response(response)

    async def _generate_with_retry(
        self,
        func: Any,
        messages: List[Dict[str, str]],
        config: Optional[CoreLLMConfig],
        max_retries: int = 3,
    ) -> LLMResponse:
        last_error = None
        for attempt in range(max_retries):
            try:
                return await func(messages, config)
            except Exception as e:
                last_error = e
                if attempt < max_retries - 1:
                    delay = 2 ** attempt
                    await asyncio.sleep(delay)
        raise last_error

    async def stream_generate(
        self,
        messages: List[Dict[str, str]],
        config: Optional[CoreLLMConfig] = None,
    ) -> AsyncIterator[str]:
        request = self._build_request(messages, config)
        request.stream = True
        async for chunk in self._client.stream_chat(request):
            yield chunk.content or chunk.delta or ""

    async def validate_connection(self) -> bool:
        try:
            test_request = ChatRequest(
                model=self._model,
                messages=[InfraMessage(role="user", content="ping")],
                max_tokens=1,
            )
            await self._client.achat(test_request)
            return True
        except Exception:
            return False

    # ── Conversion helpers ─────────────────────────────────────────

    @staticmethod
    def _convert_message(msg: Dict[str, str]) -> InfraMessage:
        return InfraMessage(
            role=msg.get("role", "user"),
            content=msg.get("content", ""),
            name=msg.get("name"),
        )

    def _build_request(
        self,
        messages: List[Dict[str, str]],
        config: Optional[CoreLLMConfig],
    ) -> ChatRequest:
        infra_msgs = [self._convert_message(m) for m in messages]
        return ChatRequest(
            model=config.model if config and config.model else self._model,
            messages=infra_msgs,
            temperature=config.temperature if config else 0.7,
            max_tokens=config.max_tokens if config else None,
        )

    @staticmethod
    def _convert_response(response: Any) -> LLMResponse:
        # Handles both ChatResponse dataclass and plain object/compat
        return LLMResponse(
            content=getattr(response, "content", "") or "",
            model=getattr(response, "model", "") or "",
            usage=dict(getattr(response, "usage", {}) or {}),
            finish_reason=getattr(response, "finish_reason", "stop") or "stop",
            metadata={
                "latency": getattr(response, "latency", 0.0) or 0.0,
                "role": getattr(response, "role", "assistant") or "assistant",
            },
        )
