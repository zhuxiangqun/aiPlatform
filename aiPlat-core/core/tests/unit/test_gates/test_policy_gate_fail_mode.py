"""PolicyGate fail-mode (安全体系审计 §4.1 方案 C)."""
from __future__ import annotations

import pytest

from core.apps.tools.permission import Permission, get_permission_manager
from core.harness.infrastructure.gates.policy_gate import (
    PolicyDecision,
    PolicyGate,
    resolve_policy_fail_mode,
)


@pytest.mark.parametrize(
    "env,critical,expected",
    [
        (None, False, "open"),
        ("open", True, "open"),
        ("ask", True, "ask"),
        ("closed", True, "closed"),
        ("ask", False, "open"),  # non-critical always open
        ("fail-closed", True, "closed"),
    ],
)
def test_resolve_policy_fail_mode(monkeypatch, env, critical, expected):
    if env is None:
        monkeypatch.delenv("AIPLAT_POLICY_FAIL_MODE", raising=False)
    else:
        monkeypatch.setenv("AIPLAT_POLICY_FAIL_MODE", env)
    monkeypatch.delenv("AIPLAT_POLICY_FAIL_CRITICAL_MODE", raising=False)
    assert resolve_policy_fail_mode(critical=critical) == expected


def test_critical_mode_override(monkeypatch):
    monkeypatch.setenv("AIPLAT_POLICY_FAIL_MODE", "ask")
    monkeypatch.setenv("AIPLAT_POLICY_FAIL_CRITICAL_MODE", "closed")
    assert resolve_policy_fail_mode(critical=True) == "closed"
    assert resolve_policy_fail_mode(critical=False) == "open"


@pytest.mark.asyncio
async def test_skill_load_resolver_fail_open_default(monkeypatch):
    monkeypatch.delenv("AIPLAT_POLICY_FAIL_MODE", raising=False)
    monkeypatch.delenv("AIPLAT_POLICY_FAIL_CRITICAL_MODE", raising=False)
    monkeypatch.setenv("AIPLAT_SKILL_PERMISSION_RULES", '{"secret-*":"deny","*":"allow"}')
    monkeypatch.setenv("AIPLAT_POLICY_ENGINE", "0")
    get_permission_manager().grant_permission("admin", "skill_load", Permission.EXECUTE)

    def _boom(_name):
        raise RuntimeError("resolver unavailable")

    monkeypatch.setattr(
        "core.apps.tools.skill_tools.resolve_skill_permission",
        _boom,
        raising=True,
    )
    g = PolicyGate()
    r = await g.check_tool(
        user_id="admin",
        tool_name="skill_load",
        tool_args={"name": "secret-skill", "_tenant_id": "t1"},
    )
    # Default open: deny rule skipped → falls through → ALLOW (no approval forced)
    assert r.decision == PolicyDecision.ALLOW


@pytest.mark.asyncio
async def test_skill_load_resolver_fail_closed(monkeypatch):
    monkeypatch.setenv("AIPLAT_POLICY_FAIL_MODE", "closed")
    monkeypatch.setenv("AIPLAT_SKILL_PERMISSION_RULES", '{"secret-*":"deny","*":"allow"}')
    monkeypatch.setenv("AIPLAT_POLICY_ENGINE", "0")
    get_permission_manager().grant_permission("admin", "skill_load", Permission.EXECUTE)

    def _boom(_name):
        raise RuntimeError("resolver unavailable")

    monkeypatch.setattr(
        "core.apps.tools.skill_tools.resolve_skill_permission",
        _boom,
        raising=True,
    )
    g = PolicyGate()
    r = await g.check_tool(
        user_id="admin",
        tool_name="skill_load",
        tool_args={"name": "secret-skill"},
    )
    assert r.decision == PolicyDecision.DENY
    assert "fail" in (r.reason or "").lower() or "unavailable" in (r.reason or "").lower()


@pytest.mark.asyncio
async def test_skill_load_resolver_fail_ask(monkeypatch):
    monkeypatch.setenv("AIPLAT_POLICY_FAIL_MODE", "ask")
    monkeypatch.setenv("AIPLAT_SKILL_PERMISSION_RULES", '{"secret-*":"deny","*":"allow"}')
    monkeypatch.setenv("AIPLAT_POLICY_ENGINE", "0")
    get_permission_manager().grant_permission("admin", "skill_load", Permission.EXECUTE)

    def _boom(_name):
        raise RuntimeError("resolver unavailable")

    monkeypatch.setattr(
        "core.apps.tools.skill_tools.resolve_skill_permission",
        _boom,
        raising=True,
    )
    g = PolicyGate()
    r = await g.check_tool(
        user_id="admin",
        tool_name="skill_load",
        tool_args={"name": "secret-skill", "_session_id": "s1"},
    )
    assert r.decision == PolicyDecision.APPROVAL_REQUIRED


@pytest.mark.asyncio
async def test_rollback_to_open(monkeypatch):
    """One-click rollback: FAIL_MODE=open restores fail-open."""
    monkeypatch.setenv("AIPLAT_POLICY_FAIL_MODE", "open")
    monkeypatch.setenv("AIPLAT_POLICY_FAIL_CRITICAL_MODE", "")
    monkeypatch.setenv("AIPLAT_SKILL_PERMISSION_RULES", '{"secret-*":"deny","*":"allow"}')
    monkeypatch.setenv("AIPLAT_POLICY_ENGINE", "0")
    get_permission_manager().grant_permission("admin", "skill_load", Permission.EXECUTE)
    monkeypatch.setattr(
        "core.apps.tools.skill_tools.resolve_skill_permission",
        lambda _n: (_ for _ in ()).throw(RuntimeError("down")),
        raising=True,
    )
    g = PolicyGate()
    r = await g.check_tool(
        user_id="admin",
        tool_name="skill_load",
        tool_args={"name": "secret-skill"},
    )
    assert r.decision == PolicyDecision.ALLOW
