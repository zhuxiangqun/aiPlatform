"""Tests for infra/llm/providers/local.py — LocalLLMClient."""
import sys
from pathlib import Path
import os as _os; _REPO = _os.path.basename(str(Path(__file__).resolve().parents[4])); sys.path.insert(0, str(Path(__file__).resolve().parents[4] / _REPO))

import pytest


class TestLocalLLMClientConstruction:
    def test_default_construction(self):
        from infra.llm.providers.local import LocalLLMClient
        from infra.llm.schemas import LLMConfig
        client = LocalLLMClient(LLMConfig(provider="local"))
        assert client.config.provider == "local"
        assert client._backend is None  # not yet resolved

    def test_backend_detection(self):
        from infra.llm.providers.local import LocalLLMClient
        client = LocalLLMClient.__new__(LocalLLMClient)
        prio = client._get_backend_priority()
        assert "llama_cpp" in prio
        assert "transformers" in prio

    def test_options_parsing(self):
        from infra.llm.providers.local import LocalLLMClient
        from infra.llm.schemas import LLMConfig
        client = LocalLLMClient(LLMConfig(provider="local"))
        opts = client._parse_model_options()
        assert isinstance(opts, dict)

    def test_chat_sync_bridge(self):
        from infra.llm.providers.local import LocalLLMClient
        from infra.llm.schemas import LLMConfig
        client = LocalLLMClient(LLMConfig(provider="local"))
        assert callable(client.chat)
        assert callable(client.achat)
        assert callable(client.stream_chat)

    def test_embed_is_async(self):
        from infra.llm.providers.local import LocalLLMClient
        from infra.llm.schemas import LLMConfig
        client = LocalLLMClient(LLMConfig(provider="local"))
        import asyncio
        assert asyncio.iscoroutinefunction(client.embed)

    def test_clear_cache_classmethod(self):
        from infra.llm.providers.local import LocalLLMClient
        assert callable(LocalLLMClient.clear_cache)

    def test_unload_model_classmethod(self):
        from infra.llm.providers.local import LocalLLMClient
        assert callable(LocalLLMClient.unload_model)

    def test_count_tokens(self):
        from infra.llm.providers.local import LocalLLMClient
        from infra.llm.schemas import LLMConfig
        client = LocalLLMClient(LLMConfig(provider="local"))
        tokens = client.count_tokens("hello world")
        assert tokens > 0  # rough estimate: len // 4

    def test_get_metrics(self):
        from infra.llm.providers.local import LocalLLMClient
        from infra.llm.schemas import LLMConfig
        client = LocalLLMClient(LLMConfig(provider="local"))
        metrics = client.get_metrics()
        assert isinstance(metrics, dict)
