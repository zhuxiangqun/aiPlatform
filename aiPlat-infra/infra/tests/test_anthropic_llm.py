"""Tests for infra/llm/providers/anthropic.py — AnthropicClient."""
import sys
from pathlib import Path
import os as _os; _REPO = _os.path.basename(str(Path(__file__).resolve().parents[4])); sys.path.insert(0, str(Path(__file__).resolve().parents[4] / _REPO))

import pytest
from infra.llm.schemas import LLMConfig


class TestAnthropicConstruction:
    def test_default_construction(self):
        from infra.llm.providers.anthropic import AnthropicClient
        client = AnthropicClient(LLMConfig(provider="anthropic", api_key="test"))
        assert client.config.provider == "anthropic"

    def test_chat_sync_bridge(self):
        from infra.llm.providers.anthropic import AnthropicClient
        client = AnthropicClient(LLMConfig(provider="anthropic", api_key="test"))
        assert callable(client.chat)

    def test_achat_is_async(self):
        from infra.llm.providers.anthropic import AnthropicClient
        client = AnthropicClient(LLMConfig(provider="anthropic", api_key="test"))
        import asyncio
        assert asyncio.iscoroutinefunction(client.achat)

    def test_achat_is_async(self):
        from infra.llm.providers.anthropic import AnthropicClient
        client = AnthropicClient(LLMConfig(provider="anthropic", api_key="test"))
        import asyncio
        assert asyncio.iscoroutinefunction(client.achat)
        assert callable(client.stream_chat)

    def test_embed_not_implemented(self):
        """Anthropic doesn't support embeddings — should raise NotImplementedError."""
        from infra.llm.providers.anthropic import AnthropicClient
        client = AnthropicClient(LLMConfig(provider="anthropic", api_key="test"))
        import asyncio
        with pytest.raises(NotImplementedError):
            asyncio.run(client.embed(["test"]))
