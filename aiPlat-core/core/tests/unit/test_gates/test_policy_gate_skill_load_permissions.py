import pytest

from core.harness.infrastructure.gates.policy_gate import PolicyGate, PolicyDecision
from core.apps.tools.permission import get_permission_manager, Permission


@pytest.mark.asyncio
async def test_policy_gate_denies_skill_load_by_rules(monkeypatch):
    monkeypatch.setenv("AIPLAT_SKILL_PERMISSION_RULES", '{"secret-*":"deny","*":"allow"}')
    get_permission_manager().grant_permission("admin", "skill_load", Permission.EXECUTE)
    g = PolicyGate()
    r = await g.check_tool(user_id="admin", tool_name="skill_load", tool_args={"name": "secret-skill"})
    assert r.decision == PolicyDecision.DENY


@pytest.mark.asyncio
async def test_policy_gate_requires_approval_for_skill_load_ask(monkeypatch):
    monkeypatch.setenv("AIPLAT_SKILL_PERMISSION_RULES", '{"ask-*":"ask","*":"allow"}')
    get_permission_manager().grant_permission("admin", "skill_load", Permission.EXECUTE)
    g = PolicyGate()
    r = await g.check_tool(user_id="admin", tool_name="skill_load", tool_args={"name": "ask-skill"})
    assert r.decision == PolicyDecision.APPROVAL_REQUIRED


def test_security_degraded_audit_wired():
    """安全体系审计 §4.1 方案 B：skill resolver 降级时记录 security_degraded 事件。"""
    import inspect
    from core.harness.infrastructure.gates import policy_gate
    src = inspect.getsource(policy_gate.PolicyGate.check_tool)
    assert "security_degraded" in src
    assert "skill_permission_resolver_unavailable" in src
