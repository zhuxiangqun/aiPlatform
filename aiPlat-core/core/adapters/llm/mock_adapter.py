"""
Mock LLM Adapter

用于本地开发/CI：无需外部 API Key，也能让 agent/skill 跑通执行链路。
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, AsyncIterator

from .base import BaseLLMAdapter, LLMResponse, AdapterMetadata, LLMConfig


class MockAdapter(BaseLLMAdapter):
    """
    A deterministic adapter that always returns a short "DONE" style response.

    NOTE:
    - 该响应格式配合 ReActLoop 的 DONE 检测（见 loop.py）用于快速结束执行。
    - 不尝试真实推理/工具调用，仅用于冒烟与联调。
    """

    def __init__(self, model: str = "mock", **kwargs):
        metadata = AdapterMetadata(
            name="mock",
            provider="mock",
            version="1.0.0",
            capabilities=["text", "chat"],
            supports_streaming=True,
            supports_functions=False,
        )
        config = LLMConfig(model=model, **kwargs)
        super().__init__(metadata, config)

    async def generate(self, messages: List[Dict[str, str]], config: Optional[LLMConfig] = None) -> LLMResponse:
        merged = self._merge_config(config)
        # Keep it deterministic and short; do NOT echo the prompt to avoid
        # accidentally embedding JSON examples that could be parsed as tool calls.
        content = "DONE: ok"
        return LLMResponse(content=content, model=merged.model, usage={"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0})

    async def stream_generate(self, messages: List[Dict[str, str]], config: Optional[LLMConfig] = None) -> AsyncIterator[str]:
        r = await self.generate(messages, config=config)
        # simple chunking
        for ch in r.content:
            yield ch

    async def validate_connection(self) -> bool:
        return True
