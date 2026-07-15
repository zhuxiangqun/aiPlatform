"""Wiring tests: credential rotation in OpenAICompatibleClient.

Proves that the CredentialPool is on the *hot path* (not a dead stub):
  1. Single-key mode → no pool, unchanged behavior (backward compat).
  2. Multi-key mode → pool is created, keys rotate on 429/403/timeout.
  3. mark_rate_limited is called when a key receives a rotatable error.
  4. mark_success is called after a successful chat (liveness signal).
  5. When all keys are exhausted, the original exception is raised.
"""
import sys, os
from pathlib import Path
_REPO = os.path.basename(str(Path(__file__).resolve().parents[4]))
sys.path.insert(0, str(Path(__file__).resolve().parents[4] / _REPO))

import pytest
from unittest.mock import patch, MagicMock, PropertyMock
from infra.llm.schemas import LLMConfig, ChatRequest, Message


@pytest.fixture(autouse=True)
def _clear_pool_cache():
    """CredentialPool is a process-wide singleton per provider; reset between tests."""
    from infra.management.model import credential_pool as _cp
    _cp._pools.clear()
    yield
    _cp._pools.clear()


# ── Helper: create a minimal config ──

def _cfg(provider="test_provider", api_key="sk-test-default"):
    return LLMConfig(provider=provider, api_key=api_key, model="test-model")


def _req():
    return ChatRequest(
        model="test-model",
        messages=[Message(role="user", content="hello")],
        temperature=0.7,
        max_tokens=100,
    )


class TestSingleKeyBackwardCompat:
    """When no {PROVIDER}_KEYS env var is set, pool stays None (unchanged path)."""

    def test_no_pool_without_multi_keys(self, monkeypatch):
        monkeypatch.delenv("TEST_PROVIDER_KEYS", raising=False)
        monkeypatch.delenv("TEST_PROVIDER_API_KEY", raising=False)
        monkeypatch.setenv("TEST_PROVIDER_API_KEY", "sk-single")

        from infra.llm.providers.openai_compatible import OpenAICompatibleClient
        client = OpenAICompatibleClient(_cfg())
        assert client._pool is None
        assert client._resolve_api_key() == "sk-test-default"

    def test_pool_created_with_multi_keys(self, monkeypatch):
        monkeypatch.setenv("TEST_PROVIDER_KEYS", "sk-a,sk-b,sk-c")
        monkeypatch.delenv("TEST_PROVIDER_API_KEY", raising=False)

        from infra.llm.providers.openai_compatible import OpenAICompatibleClient
        client = OpenAICompatibleClient(_cfg())
        assert client._pool is not None, "pool must be created when {PROVIDER}_KEYS is set"
        assert client._pool.key_count == 3

    def test_single_key_env_skips_pool(self, monkeypatch):
        monkeypatch.delenv("TEST_PROVIDER_KEYS", raising=False)
        monkeypatch.setenv("TEST_PROVIDER_API_KEY", "sk-solo")

        from infra.llm.providers.openai_compatible import OpenAICompatibleClient
        client = OpenAICompatibleClient(_cfg())
        assert client._pool is None, "single key from env should not create a pool (key_count=1)"


class TestRotationMechanism:
    """Key rotation: mark_rate_limited → pool.next → client rebuild."""

    @patch("infra.management.model.credential_pool.CredentialPool")
    def test_mark_rate_limited_called_on_429(self, mock_pool_cls, monkeypatch):
        monkeypatch.setenv("TEST_PROVIDER_KEYS", "sk-a,sk-b")

        mock_pool = MagicMock()
        mock_pool.key_count = 2
        mock_pool.next.return_value = "sk-b"
        mock_pool_cls.return_value = mock_pool

        from infra.llm.providers.openai_compatible import OpenAICompatibleClient
        client = OpenAICompatibleClient(_cfg())
        client._pool = mock_pool  # override with our mock
        client._current_key = "sk-a"

        # Fake rotatable error carrying a Retry-After header (version-agnostic)
        exc = RuntimeError("rate limited: 429")
        exc.status_code = 429
        exc.response = MagicMock()
        exc.response.headers = {"retry-after": "7"}

        assert client._is_rotatable_error(exc) is True
        client._rotate_key(exc)

        mock_pool.mark_rate_limited.assert_called_once()
        call_args = mock_pool.mark_rate_limited.call_args
        assert call_args[0][0] == "sk-a"
        assert call_args[0][1] == 7.0  # retry_after parsed from header
        assert client._current_key == "sk-b", "must switch to next key"
        assert client._client is None, "must clear cached client for rebuild"

    def test_mark_success_called_after_chat(self, monkeypatch):
        monkeypatch.setenv("TEST_PROVIDER_KEYS", "sk-a,sk-b")

        from infra.llm.providers.openai_compatible import OpenAICompatibleClient
        client = OpenAICompatibleClient(_cfg())
        assert client._pool is not None
        assert client._pool.key_count == 2

        mock_response = MagicMock()
        mock_response.id = "chat-123"
        mock_response.model = "test-model"
        mock_response.usage = type("obj", (object,), {
            "prompt_tokens": 10,
            "completion_tokens": 5,
            "total_tokens": 15,
        })()
        mock_choice = MagicMock()
        mock_choice.finish_reason = "stop"
        mock_choice.message.content = "hi"
        mock_choice.message.role = "assistant"
        mock_response.choices = [mock_choice]

        mock_openai = MagicMock()
        mock_openai.chat.completions.create.return_value = mock_response

        pool = client._pool
        orig_mark_success = pool.mark_success
        pool.mark_success = MagicMock(wraps=orig_mark_success)

        # Resolve a key first (production flow does this inside _get_client)
        assert client._resolve_api_key() in ("sk-a", "sk-b")
        result = client._execute_chat(mock_openai, _req())

        pool.mark_success.assert_called_once_with(client._current_key)
        assert result.content == "hi"
        assert result.usage["total_tokens"] == 15


class TestRotationExhaustion:
    """When all keys fail, the last exception propagates."""

    def test_raises_after_all_keys_exhausted(self, monkeypatch):
        monkeypatch.setenv("TEST_PROVIDER_KEYS", "sk-a,sk-b")

        from infra.llm.providers.openai_compatible import OpenAICompatibleClient
        client = OpenAICompatibleClient(_cfg())

        # Inject a mock pool with 2 keys
        mock_pool = MagicMock()
        mock_pool.key_count = 2
        mock_pool.next.side_effect = ["sk-a", "sk-b"]
        client._pool = mock_pool
        client._current_key = "sk-a"

        # Patch _is_rotatable_error to always return True
        with patch.object(client, "_is_rotatable_error", return_value=True), \
             patch.object(client, "_get_client", MagicMock()), \
             patch.object(client, "_execute_chat", side_effect=[Exception("fail1"), Exception("fail2")]):
            with pytest.raises(RuntimeError, match="fail2"):
                client.chat(_req())

        assert mock_pool.mark_rate_limited.call_count == 1, (
            "one rotation happens between the two attempts (2 keys → 1 switch)"
        )

class TestPoolStatusObservability:
    def test_status_masks_keys(self, monkeypatch):
        monkeypatch.setenv("TEST_PROVIDER_KEYS", "sk-aaaa1111,sk-bbbb2222")
        from infra.management.model.credential_pool import get_credential_pool
        pool = get_credential_pool("test_provider")
        st = pool.status()
        assert st["provider"] == "test_provider"
        assert st["key_count"] == 2
        assert st["available_count"] == 2
        for k in st["keys"]:
            assert len(k["suffix"]) <= 4
            assert "sk-" not in k["suffix"]

    def test_status_reflects_cooldown(self, monkeypatch):
        monkeypatch.setenv("TEST_PROVIDER_KEYS", "sk-aaaa1111,sk-bbbb2222")
        from infra.management.model.credential_pool import get_credential_pool
        pool = get_credential_pool("test_provider")
        pool.mark_rate_limited("sk-aaaa1111", retry_after=30)
        st = pool.status()
        assert st["available_count"] == 1
        cooling = [k for k in st["keys"] if k["in_cooldown"]]
        assert len(cooling) == 1
        assert cooling[0]["cooldown_remaining"] > 0


class TestStreamRotation:
    @pytest.mark.asyncio
    async def test_stream_rotates_before_first_chunk(self, monkeypatch):
        """A 429 on the initial stream create -> rotate key -> retry succeeds."""
        monkeypatch.setenv("TEST_PROVIDER_KEYS", "sk-a,sk-b")
        from infra.llm.providers.openai_compatible import OpenAICompatibleClient
        client = OpenAICompatibleClient(_cfg())
        assert client._pool is not None

        class _Delta:
            def __init__(self, c): self.content = c
        class _Choice:
            def __init__(self, c): self.delta = _Delta(c); self.finish_reason = None
        class _Chunk:
            def __init__(self, c): self.choices = [_Choice(c)]

        call_state = {"n": 0}

        class _Completions:
            def create(self, **kwargs):
                call_state["n"] += 1
                if call_state["n"] == 1:
                    exc = RuntimeError("429 rate limit")
                    exc.status_code = 429
                    raise exc
                return iter([_Chunk("hello"), _Chunk(" world")])

        class _Chat:
            completions = _Completions()

        class _FakeOpenAI:
            chat = _Chat()

        monkeypatch.setattr(client, "_get_client", lambda: _FakeOpenAI())

        chunks = []
        async for ch in client.stream_chat(_req()):
            chunks.append(ch.content)
        assert "".join(chunks) == "hello world"
        assert call_state["n"] == 2


class TestGetMetricsObservability:
    def test_metrics_include_pool_status(self, monkeypatch):
        monkeypatch.setenv("TEST_PROVIDER_KEYS", "sk-a,sk-b")
        from infra.llm.providers.openai_compatible import OpenAICompatibleClient
        client = OpenAICompatibleClient(_cfg())
        metrics = client.get_metrics()
        assert "credential_pool" in metrics
        assert metrics["credential_pool"]["key_count"] == 2

    def test_metrics_no_pool_when_single_key(self, monkeypatch):
        monkeypatch.delenv("TEST_PROVIDER_KEYS", raising=False)
        monkeypatch.setenv("TEST_PROVIDER_API_KEY", "sk-solo")
        from infra.llm.providers.openai_compatible import OpenAICompatibleClient
        client = OpenAICompatibleClient(_cfg())
        assert "credential_pool" not in client.get_metrics()
