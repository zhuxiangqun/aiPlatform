from core.harness.infrastructure.gates.policy_gate import PolicyGate, PolicyDecision
from core.apps.tools.permission import get_permission_manager, Permission


def test_policy_gate_denies_skill_load_by_rules(monkeypatch):
    monkeypatch.setenv("AIPLAT_SKILL_PERMISSION_RULES", '{"secret-*":"deny","*":"allow"}')
    get_permission_manager().grant_permission("admin", "skill_load", Permission.EXECUTE)
    g = PolicyGate()
    r = g.check_tool(user_id="admin", tool_name="skill_load", tool_args={"name": "secret-skill"})
    assert r.decision == PolicyDecision.DENY


def test_policy_gate_requires_approval_for_skill_load_ask(monkeypatch):
    monkeypatch.setenv("AIPLAT_SKILL_PERMISSION_RULES", '{"ask-*":"ask","*":"allow"}')
    get_permission_manager().grant_permission("admin", "skill_load", Permission.EXECUTE)
    g = PolicyGate()
    r = g.check_tool(user_id="admin", tool_name="skill_load", tool_args={"name": "ask-skill"})
    assert r.decision == PolicyDecision.APPROVAL_REQUIRED
