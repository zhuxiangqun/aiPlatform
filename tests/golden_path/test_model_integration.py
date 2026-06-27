"""真模型集成行为平面 — 真实 LLM 推理（Ollama 本地模型）。"""
import asyncio

import pytest


@pytest.mark.integration
def test_real_llm_generate_produces_output(isolated_env, monkeypatch):
    """真模型推理：create_selected_adapter → sys_llm_generate → 有意义的输出。"""
    monkeypatch.setenv("AIPLAT_CHAT_MODEL", "qwen2.5:3b")
    from core.harness.utils.model_injection import create_selected_adapter
    from core.harness.syscalls.llm import sys_llm_generate

    adapter = create_selected_adapter(model_name="qwen2.5:3b")
    assert adapter is not None, "create_selected_adapter 返回 None"
    resp = asyncio.run(sys_llm_generate(adapter, "用一句话回答：1+1等于几？"))
    content = str(getattr(resp, "content", str(resp)))
    assert "2" in content or "二" in content, f"模型未正确回答: {content!r}"


@pytest.mark.integration
def test_model_injection_chain(isolated_env, monkeypatch):
    """模型注入全链路：env → best_model_for_purpose → adapter → 中文推理。"""
    monkeypatch.setenv("AIPLAT_CHAT_MODEL", "qwen2.5:3b")
    monkeypatch.setenv("AIPLAT_EMBED_BACKEND", "hash")
    from core.harness.utils.model_injection import best_model_for_purpose, create_selected_adapter
    from core.harness.syscalls.llm import sys_llm_generate

    assert best_model_for_purpose("chat") == "qwen2.5:3b"
    adapter = create_selected_adapter(model_name="qwen2.5:3b")
    resp = asyncio.run(sys_llm_generate(adapter, "请用中文回答：世界上最高的山是什么？"))
    content = str(getattr(resp, "content", str(resp)))
    assert "珠穆朗玛" in content or "Everest" in content or "喜马拉雅" in content, (
        f"模型未回答山名: {content!r}")


@pytest.mark.integration
def test_real_llm_multi_turn_format(isolated_env, monkeypatch):
    """真模型多轮对话：消息列表格式 → 返回非空内容。"""
    monkeypatch.setenv("AIPLAT_CHAT_MODEL", "qwen2.5:3b")
    from core.harness.utils.model_injection import create_selected_adapter
    from core.harness.syscalls.llm import sys_llm_generate

    adapter = create_selected_adapter(model_name="qwen2.5:3b")
    messages = [
        {"role": "system", "content": "用中文回答。"},
        {"role": "user", "content": "你好"},
    ]
    resp = asyncio.run(sys_llm_generate(adapter, messages))
    content = str(getattr(resp, "content", str(resp)))
    assert content and len(content) > 2, f"多轮对话未返回有效内容: {content!r}"


@pytest.mark.integration
def test_domain_router_llm_tier(isolated_env, monkeypatch):
    """DomainRouter T3 LLM 分级：无域时用 LLM 回退分类不崩。"""
    monkeypatch.setenv("AIPLAT_CHAT_MODEL", "qwen2.5:3b")
    monkeypatch.setenv("AIPLAT_DOMAIN_ROUTER_MODEL", "qwen2.5:3b")
    monkeypatch.setenv("AIPLAT_EMBED_BACKEND", "hash")

    from core.harness.knowledge.domain_router import DomainRouter
    router = DomainRouter()
    # 无注册域 → 应回退到 LLM 分类或返回默认值，不应崩
    did = router.classify("kubernetes pod crashloop backoff")
    assert isinstance(did, str) and did, f"LLM 分级应返回合法 domain_id: {did!r}"


@pytest.mark.integration
def test_agent_execute_with_real_model(isolated_env, monkeypatch):
    """Agent 编排 happy-path：BaseAgent + 真模型 → 产生有意义输出。"""
    monkeypatch.setenv("AIPLAT_CHAT_MODEL", "qwen2.5:3b")
    monkeypatch.setenv("AIPLAT_EMBED_BACKEND", "hash")

    from core.harness.utils.model_injection import create_selected_adapter
    from core.harness.interfaces.agent import AgentConfig, AgentContext
    from core.apps.agents.base import BaseAgent

    adapter = create_selected_adapter(model_name="qwen2.5:3b")
    config = AgentConfig(name="test-model-agent")
    agent = BaseAgent(config=config, model=adapter)
    ctx = AgentContext(
        session_id="s1", user_id="system",
        messages=[{"role": "user", "content": "用一句话回答：中国的首都是哪里？"}],
    )
    result = asyncio.run(agent.execute(ctx))
    output = str(getattr(result, "output", str(result)))
    assert "北京" in output, f"Agent 未正确回答首都: {output!r}"


@pytest.mark.integration
def test_http_agent_execute_with_real_model(tmp_path, monkeypatch):
    """HTTP → conversational_agent → 真模型推理 → 非空输出。

    全链路端到端：TestClient → POST /agents/conversational_agent/execute → BaseAgent → LLM。
    """
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("AIPLAT_EXECUTION_DB_PATH", str(tmp_path / "exec.sqlite3"))
    monkeypatch.setenv("AIPLAT_EMBED_BACKEND", "hash")
    monkeypatch.setenv("AIPLAT_CHAT_MODEL", "qwen2.5:3b")

    import importlib
    import core.server as server
    importlib.reload(server)
    from fastapi.testclient import TestClient

    with TestClient(server.app) as client:
        r = client.post(
            "/api/core/agents/conversational_agent/execute",
            json={"input": {"message": "用一句话回答：1+1等于几？"},
                  "user_id": "system", "session_id": "s1"},
        )
    assert r.status_code == 200, f"HTTP {r.status_code}: {r.text[:300]}"
    body = r.json()
    output = str(body.get("output", ""))
    assert output and "No model" not in output, f"Agent 未产生有效输出: {output!r}"
