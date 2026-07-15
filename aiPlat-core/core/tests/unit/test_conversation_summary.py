"""Tests for P1-1: conversation-level LLM semantic summary (Hermes Layer 4).

Covers:
  - _context_summary_enabled() respects env var toggles
  - _llm_summarize_conversation() returns "" for empty input
  - _do_llm_conversation_summary() produces structured JSON with 4 categories
  - _aggressive_compress falls back to mechanical placeholder when LLM unavailable
  - _aggressive_compress uses LLM summary when the model is available
  - _emergency_compress preserves continuity via summary
  - SUMMARY_TIMEOUT does not throw (graceful fallback)
"""

import pytest
import sys

sys.path.insert(0, "aiPlat-core")

from core.harness.memory.compression import (
    _context_summary_enabled,
    _llm_summarize_conversation,
    ContextCompression,
    CompressionLevel,
    CONTEXT_SUMMARY_TIMEOUT,
)


class TestContextSummaryEnabled:
    def test_enabled_by_default(self, monkeypatch):
        monkeypatch.delenv("AIPLAT_LLM_CONTEXT_SUMMARY_ENABLED", raising=False)
        assert _context_summary_enabled() is True

    def test_disabled_by_false(self, monkeypatch):
        monkeypatch.setenv("AIPLAT_LLM_CONTEXT_SUMMARY_ENABLED", "false")
        assert _context_summary_enabled() is False

    def test_disabled_by_zero(self, monkeypatch):
        monkeypatch.setenv("AIPLAT_LLM_CONTEXT_SUMMARY_ENABLED", "0")
        assert _context_summary_enabled() is False


class TestLLMSummarizeConversation:
    @pytest.mark.asyncio
    async def test_empty_returns_empty(self):
        result = await _llm_summarize_conversation([], "")
        assert result == ""

    @pytest.mark.asyncio
    async def test_result_has_key_categories(self, monkeypatch):
        """Simulate a successful LLM call with a controlled summary."""
        monkeypatch.setenv("AIPLAT_LLM_CONTEXT_SUMMARY_ENABLED", "true")

        from core.harness.memory import compression as _cp
        import asyncio

        async def _mock_summarize(messages, prev_summary):
            return (
                'CONTEXT_SUMMARY (LLM semantic):\n'
                '🎯 目标: fix the auth bug\n'
                '📌 结论: root cause is expired token; fix is to refresh\n'
                '🔧 工具: grep auth.py; read token.py\n'
                '⏳ 待办: write test for refresh logic'
            )

        original = getattr(_cp, '_do_llm_conversation_summary', None)
        _cp._do_llm_conversation_summary = _mock_summarize
        try:
            msgs = [{"role": "user", "content": "the auth is broken"},
                    {"role": "assistant", "content": "I found the bug in token.py"}]
            result = await _llm_summarize_conversation(msgs, "")
            assert "fix the auth bug" in result
            assert "expired token" in result
            assert "grep auth.py" in result
            assert "write test" in result
        finally:
            if original is not None:
                _cp._do_llm_conversation_summary = original

    @pytest.mark.asyncio
    async def test_timeout_returns_empty(self, monkeypatch):
        monkeypatch.setenv("AIPLAT_LLM_CONTEXT_SUMMARY_ENABLED", "true")
        from core.harness.memory import compression as _cp
        import asyncio

        async def _mock_slow(*args, **kwargs):
            await asyncio.sleep(999)
            return "never"

        original = getattr(_cp, '_do_llm_conversation_summary', None)
        _cp._do_llm_conversation_summary = _mock_slow
        _cp.CONTEXT_SUMMARY_TIMEOUT = 0.01  # force immediate timeout
        try:
            msgs = [{"role": "user", "content": "hello"}]
            result = await _llm_summarize_conversation(msgs, "")
            assert result == ""  # graceful fallback
        finally:
            if original is not None:
                _cp._do_llm_conversation_summary = original
            _cp.CONTEXT_SUMMARY_TIMEOUT = 3.0


class TestAggressiveCompressWithLLMSummary:
    @pytest.mark.asyncio
    async def test_falls_back_to_mechanical_when_disabled(self, monkeypatch):
        monkeypatch.setenv("AIPLAT_LLM_CONTEXT_SUMMARY_ENABLED", "false")
        comp = ContextCompression()
        msgs = [
            {"role": "system", "content": "You are a coder."},
            {"role": "user", "content": "fix auth"},
            {"role": "assistant", "content": "ok"},
            {"role": "user", "content": "where is it?"},
            {"role": "assistant", "content": "in token.py"},
            {"role": "user", "content": "now fix it"},
        ]
        result = await comp._aggressive_compress(msgs)
        # system msg + summary placeholder + last 2 messages
        assert len(result) >= 2
        assert any("Previous" in str(m.get("content", "")) for m in result)

    @pytest.mark.asyncio
    async def test_uses_llm_summary_when_enabled(self, monkeypatch):
        monkeypatch.setenv("AIPLAT_LLM_CONTEXT_SUMMARY_ENABLED", "true")
        from core.harness.memory import compression as _cp

        async def _mock_summarize(messages, prev_summary):
            return "CONTEXT_SUMMARY (LLM semantic):\n🎯 目标: fix auth\n📌 结论: root in token.py"

        original = getattr(_cp, '_do_llm_conversation_summary', None)
        _cp._do_llm_conversation_summary = _mock_summarize
        try:
            comp = ContextCompression()
            msgs = [
                {"role": "system", "content": "You are a coder."},
                {"role": "user", "content": "fix auth"},
                {"role": "assistant", "content": "ok let me look"},
                {"role": "user", "content": "found?"},
                {"role": "assistant", "content": "yes in token.py"},
                {"role": "user", "content": "now fix"},
            ]
            result = await comp._aggressive_compress(msgs)
            assert any("LLM semantic" in str(m.get("content", "")) for m in result)
            assert any("fix auth" in str(m.get("content", "")) for m in result)
        finally:
            if original is not None:
                _cp._do_llm_conversation_summary = original


class TestEmergencyCompressWithSummary:
    @pytest.mark.asyncio
    async def test_emergency_adds_summary(self, monkeypatch):
        monkeypatch.setenv("AIPLAT_LLM_CONTEXT_SUMMARY_ENABLED", "true")
        from core.harness.memory import compression as _cp

        async def _mock_summarize(messages, prev_summary):
            return "CONTEXT_SUMMARY (LLM semantic):\n🎯 目标: urgent fix"

        original = getattr(_cp, '_do_llm_conversation_summary', None)
        _cp._do_llm_conversation_summary = _mock_summarize
        try:
            comp = ContextCompression()
            msgs = [
                {"role": "system", "content": "You are a coder."},
                {"role": "user", "content": "fix auth now"},
                {"role": "assistant", "content": "looking"},
                {"role": "user", "content": "hurry!"},
            ]
            result = await comp._emergency_compress(msgs)
            assert any("LLM semantic" in str(m.get("content", "")) for m in result)
        finally:
            if original is not None:
                _cp._do_llm_conversation_summary = original

    @pytest.mark.asyncio
    async def test_emergency_skips_summary_when_disabled(self, monkeypatch):
        monkeypatch.setenv("AIPLAT_LLM_CONTEXT_SUMMARY_ENABLED", "false")
        comp = ContextCompression()
        msgs = [
            {"role": "system", "content": "You are a coder."},
            {"role": "user", "content": "fix auth"},
            {"role": "assistant", "content": "ok"},
            {"role": "user", "content": "now!"},
        ]
        result = await comp._emergency_compress(msgs)
        # no LLM summary marker when disabled
        assert not any("LLM semantic" in str(m.get("content", "")) for m in result)


class TestDoLLMConversationSummaryAPI:
    @pytest.mark.asyncio
    async def test_uses_generate_api_and_parses_json(self, monkeypatch):
        """Prove _do_llm_conversation_summary uses the real adapter.generate() API
        (not the previously-broken chat_complete/model_name pattern) and parses the
        4-category JSON into a structured summary."""
        from core.harness.memory import compression as _cp
        import core.harness.utils.model_injection as _mi

        class _FakeResp:
            content = (
                '{"current_goal":"fix auth bug",'
                '"key_conclusions":["token expired"],'
                '"recent_tools":["grep auth.py"],'
                '"todos":["write test"]}'
            )

        captured = {}

        class _FakeAdapter:
            async def generate(self, messages, config=None):
                captured["messages"] = messages
                captured["config"] = config
                return _FakeResp()

        monkeypatch.setattr(_mi, "best_model_for_purpose", lambda *a, **k: "test-model")
        monkeypatch.setattr(_mi, "create_selected_adapter", lambda **k: _FakeAdapter())

        result = await _cp._do_llm_conversation_summary(
            [{"role": "user", "content": "auth is broken"}], ""
        )
        assert "fix auth bug" in result
        assert "token expired" in result
        assert "grep auth.py" in result
        assert "write test" in result
        # Verify correct API contract: generate([messages], LLMConfig)
        assert isinstance(captured["messages"], list)
        assert captured["config"].model == "test-model"
        assert captured["config"].temperature == 0.0

    @pytest.mark.asyncio
    async def test_no_model_returns_empty(self, monkeypatch):
        from core.harness.memory import compression as _cp
        import core.harness.utils.model_injection as _mi
        monkeypatch.setattr(_mi, "best_model_for_purpose", lambda *a, **k: "")
        result = await _cp._do_llm_conversation_summary(
            [{"role": "user", "content": "x"}], ""
        )
        assert result == ""
