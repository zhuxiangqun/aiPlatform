"""
Scripted LLM Adapter

用于“线上式验证/CI”：通过环境变量提供一组预设响应，从而让真实 Harness/Agent
走完整链路（llm → tool/skill → syscall_events/run_events）而不依赖外部模型服务。

Env:
  - AIPLAT_SCRIPTED_LLM_RESPONSES: JSON 数组
      [
        {"content": "...", "usage": {"total_tokens": 80}},
        {"content": "DONE: ok", "usage": {"total_tokens": 10}}
      ]
  - AIPLAT_SCRIPTED_LLM_DEFAULT_USAGE: JSON 对象（可选）
"""

from __future__ import annotations

import json
import os
from typing import Any, Dict, List, Optional, AsyncIterator

from .base import BaseLLMAdapter, LLMResponse, AdapterMetadata, LLMConfig


class ScriptedAdapter(BaseLLMAdapter):
    def __init__(self, model: str = "scripted", **kwargs):
        metadata = AdapterMetadata(
            name="scripted",
            provider="scripted",
            version="1.0.0",
            capabilities=["text", "chat"],
            supports_streaming=True,
            supports_functions=False,
        )
        config = LLMConfig(model=model, **kwargs)
        super().__init__(metadata, config)
        self._idx = 0
        self._responses = _load_responses()
        self._default_usage = _load_default_usage()

    async def generate(self, messages: List[Dict[str, str]], config: Optional[LLMConfig] = None) -> LLMResponse:
        merged = self._merge_config(config)
        item = None
        if self._idx < len(self._responses):
            item = self._responses[self._idx]
        self._idx += 1

        if not isinstance(item, dict):
            # fallback: keep it deterministic
            return LLMResponse(content="DONE: ok", model=merged.model, usage=dict(self._default_usage))

        content = str(item.get("content") or "")
        usage = item.get("usage")
        if not isinstance(usage, dict):
            usage = dict(self._default_usage)
        return LLMResponse(content=content, model=merged.model, usage=usage)

    async def stream_generate(self, messages: List[Dict[str, str]], config: Optional[LLMConfig] = None) -> AsyncIterator[str]:
        r = await self.generate(messages, config=config)
        for ch in r.content:
            yield ch

    async def validate_connection(self) -> bool:
        return True


def _load_responses() -> List[Dict[str, Any]]:
    raw = (os.getenv("AIPLAT_SCRIPTED_LLM_RESPONSES") or "").strip()
    if not raw:
        return []
    try:
        data = json.loads(raw)
        if isinstance(data, list):
            return [x for x in data if isinstance(x, dict)]
    except Exception:
        return []
    return []


def _load_default_usage() -> Dict[str, int]:
    raw = (os.getenv("AIPLAT_SCRIPTED_LLM_DEFAULT_USAGE") or "").strip()
    if raw:
        try:
            d = json.loads(raw)
            if isinstance(d, dict):
                return {k: int(v) for k, v in d.items() if isinstance(k, str)}
        except Exception:
            pass
    return {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}

