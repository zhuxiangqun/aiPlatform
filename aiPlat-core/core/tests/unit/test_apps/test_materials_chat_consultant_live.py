"""materials_chat consultant fallback must skip RAG / wiki."""
from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[4]))

from core.apps.agents.materials_chat import MaterialsChatAgent
from core.harness.interfaces import AgentConfig, AgentContext


@pytest.mark.asyncio
async def test_consultant_live_skips_rag(monkeypatch):
    agent = MaterialsChatAgent(
        AgentConfig(name="materials_chat", model="", temperature=0.2, max_tokens=256)
    )
    fake_model = object()
    agent._model = fake_model

    calls = {"n": 0}

    async def fake_llm(model, messages, **kwargs):
        calls["n"] += 1
        assert model is fake_model
        assert kwargs.get("session_id") is None
        assert (kwargs.get("trace_context") or {}).get("skip_claude_md") is True
        # Must not have gone through retrieval — payload is the user message only
        assert any("简报" in str(m.get("content") or "") for m in messages)
        return SimpleNamespace(content="按简报：工作区有 factory_agent。")

    monkeypatch.setattr(
        "core.harness.syscalls.llm.sys_llm_generate", fake_llm
    )
    # If RAG path runs it will try these — make them explode
    monkeypatch.setattr(
        "core.harness.syscalls.retrieval_crag.sys_crag_retrieve",
        AsyncMock(side_effect=AssertionError("RAG must not run")),
    )

    ctx = AgentContext(
        session_id="dh_test",
        user_id="system",
        messages=[
            {
                "role": "user",
                "content": "有哪些 Agent？\n\n=== 平台实况简报 ===\n工作区 Agent: factory_agent",
            }
        ],
        variables={
            "_consultant_agent": "materials_chat",
            "scope": {"collection_id": "system_docs"},
            "platform_status_brief": "工作区 Agent: factory_agent",
        },
    )
    result = await agent.execute(ctx)
    assert result.success
    out = result.output
    assert isinstance(out, dict)
    assert out.get("strategy") == "consultant_live_only"
    assert "factory_agent" in (out.get("answer") or "")
    assert calls["n"] == 1
    assert result.metadata.get("strategy") == "consultant_live_only"
