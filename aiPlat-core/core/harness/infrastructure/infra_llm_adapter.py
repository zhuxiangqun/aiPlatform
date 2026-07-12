"""
InfraLLMAdapter — bridges core ILLMAdapter interface to infra LLMClient.

This is the primary LLM path: core → infra → provider API.
The legacy core adapters (openai_adapter.py, etc.) are retired and only
available as fallback when AIPLAT_ENABLE_CORE_ADAPTER_FALLBACK=true.
"""

from __future__ import annotations
import logging

from typing import Any, AsyncIterator, Dict, List, Optional

from core.adapters.llm.base import (
    AdapterMetadata,
    ILLMAdapter,
    LLMConfig,
    LLMResponse,
)
from infra.llm.base import LLMClient
from infra.llm.schemas import ChatRequest, Message


def _classify_llm_error(error: Exception, provider: str, model: str = "") -> Exception:
    """Classify provider-specific API error via the 7-level translation pipeline.

    Returns ClassifiedError (with retryable/should_compress/should_fallback flags)
    that consumers can read without re-classifying.
    """
    try:
        from core.harness.infrastructure.gates.error_translator import classify_api_error
        return classify_api_error(error, provider=provider, model=model)
    except Exception:
        pass
    import logging
    logging.getLogger("llm").warning("Error classifier failed, wrapping as unknown", exc_info=True)
    return RuntimeError(f"LLM call failed ({provider}): {str(error)[:300]}")


class InfraLLMAdapter(ILLMAdapter):
    """Wraps an infra LLMClient as a core ILLMAdapter."""

    def __init__(self, client: LLMClient, *, provider: str = "", model: str = ""):
        self._client = client
        self._provider = provider or "openai"
        self._model = model or ""
        self._metadata = AdapterMetadata(
            name=f"infra-{self._provider}-{self._model}",
            provider=self._provider,
        )
        self.model_name = model or ""
        # sys_llm_generate compatibility: provides ._config for per-call overrides
        self._config = LLMConfig(model=model or "default", temperature=0.7, max_tokens=4096)

    @property
    def metadata(self) -> AdapterMetadata:
        return self._metadata

    async def validate_connection(self) -> bool:
        try:
            resp = await self._client.achat(ChatRequest(
                model=self._model, messages=[Message(role="user", content="ping")],
                max_tokens=1, temperature=0,
            ))
            return bool(resp.content)
        except Exception:
            return False

    async def generate(
        self,
        messages: List[Dict[str, str]],
        config: Optional[LLMConfig] = None,
    ) -> LLMResponse:
        config = config or self._config
        infra_messages = [
            Message(role=m.get("role", "user"), content=m.get("content", ""))
            for m in messages
        ]
        req = ChatRequest(
            model=self._model,
            messages=infra_messages,
            temperature=config.temperature or 0.7,
            max_tokens=config.max_tokens or 4096,
        )
        if config:
            if config.temperature is not None:
                req.temperature = config.temperature
            if config.max_tokens is not None:
                req.max_tokens = config.max_tokens
            if config.model:
                req.model = config.model
            if config.timeout:
                req.timeout = config.timeout

        try:
            resp = await self._client.achat(req)
        except Exception as e:
            raise _classify_llm_error(e, self._provider, self._model) from e

        usage = {}
        if resp.usage:
            try:
                u = resp.usage
                usage = {
                    "prompt_tokens": getattr(u, "prompt_tokens", u.get("prompt_tokens", 0) if hasattr(u, "get") else 0),
                    "completion_tokens": getattr(u, "completion_tokens", u.get("completion_tokens", 0) if hasattr(u, "get") else 0),
                    "total_tokens": getattr(u, "total_tokens", u.get("total_tokens", 0) if hasattr(u, "get") else 0),
                }
            except Exception as e:
                logging.debug(str(e), exc_info=True)
        return LLMResponse(
            content=resp.content or "",
            usage=usage,
            model=resp.model or self._model,
            finish_reason=resp.finish_reason or "stop",
        )

    async def stream_generate(
        self,
        messages: List[Dict[str, str]],
        config: Optional[LLMConfig] = None,
    ) -> AsyncIterator[str]:
        infra_messages = [
            Message(role=m.get("role", "user"), content=m.get("content", ""))
            for m in messages
        ]
        req = ChatRequest(
            model=self._model,
            messages=infra_messages,
            temperature=0.7,
            max_tokens=4096,
        )
        if config:
            if config.temperature is not None:
                req.temperature = config.temperature
            if config.max_tokens is not None:
                req.max_tokens = config.max_tokens
            if config.model:
                req.model = config.model

        async for chunk in self._client.stream_chat(req):
            if chunk.content:
                yield chunk.content

    async def count_tokens(self, text: str) -> int:
        return self._client.count_tokens(text)

    def get_metrics(self) -> dict:
        return self._client.get_metrics()
