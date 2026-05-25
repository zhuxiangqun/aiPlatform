"""Tests for infra/llm/providers/deepseek.py — DeepSeekClient."""
import sys, os
from pathlib import Path
_REPO = os.path.basename(str(Path(__file__).resolve().parents[4]))
sys.path.insert(0, str(Path(__file__).resolve().parents[4] / _REPO))

import pytest
from infra.llm.schemas import LLMConfig, ChatRequest, Message


class TestDeepSeekConstruction:
    def test_default_construction(self):
        from infra.llm.providers.deepseek import DeepSeekClient
        client = DeepSeekClient(LLMConfig(provider="deepseek", api_key="test"))
        assert client.config.provider == "deepseek"

    def test_achat_is_async(self):
        from infra.llm.providers.deepseek import DeepSeekClient
        client = DeepSeekClient(LLMConfig(provider="deepseek", api_key="test"))
        import asyncio
        assert asyncio.iscoroutinefunction(client.achat)
        assert callable(client.stream_chat)  # may be sync generator

    def test_embed_is_async(self):
        from infra.llm.providers.deepseek import DeepSeekClient
        client = DeepSeekClient(LLMConfig(provider="deepseek", api_key="test"))
        import asyncio
        assert asyncio.iscoroutinefunction(client.embed)

    def test_count_tokens(self):
        from infra.llm.providers.deepseek import DeepSeekClient
        client = DeepSeekClient(LLMConfig(provider="deepseek", api_key="test"))
        assert client.count_tokens("hello") == 1  # len("hello") // 4 == 1

    def test_get_metrics(self):
        from infra.llm.providers.deepseek import DeepSeekClient
        client = DeepSeekClient(LLMConfig(provider="deepseek", api_key="test"))
        assert isinstance(client.get_metrics(), dict)

    def test_retry_function_exists(self):
        from infra.llm.providers.deepseek import _retry_chat
        import asyncio
        assert asyncio.iscoroutinefunction(_retry_chat)
