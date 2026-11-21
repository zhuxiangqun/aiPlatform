"""N18 部署侧 RBAC deepen 单元测试。"""
from __future__ import annotations

import json

import pytest

from core.harness.knowledge_pipeline import deployed_rbac_policy as rbac


def test_suite_passes_and_gate_never_certifies():
    """套件全绿且 certified / n18_full / reference_policy_used 恒 false。"""
    suite = rbac.run_deployed_rbac_suite()
    assert suite["ok"] is True
    assert suite["passed"] == suite["total"]
    assert suite["certified"] is False
    assert suite["n18_full_conformance"] is False
    assert suite["reference_policy_used"] is False

    gate = rbac.evaluate_deployed_rbac_gate(suite)
    assert gate["ok"] is True
    assert gate["certified"] is False
    assert gate["n18_full_conformance"] is False
    assert gate["issues"] == []


def test_rejects_reference_policy_as_deployed_source():
    """标准包 reference_policy 路径不得作为部署权威。"""
    with pytest.raises(rbac.DeployedRbacError) as ei:
        rbac.load_deployed_policy(
            policy_path=(
                "docs/standards/knowledge-system/v4.3.1/schemas/"
                "conformance/reference_policy.json"
            )
        )
    assert "reference_policy_forbidden" in str(ei.value)


def test_cross_tenant_always_deny():
    """跨租户恒 deny。"""
    r = rbac.evaluate_permission(
        role="support_agent",
        action="Ticket.read",
        actor_tenant="a",
        target_tenant="b",
    )
    assert r["decision"] == "deny"
    assert r["reference_policy_used"] is False


def test_env_json_policy_override(monkeypatch):
    """AIPLAT_DEPLOYED_RBAC_POLICY 覆盖内置默认。"""
    payload = {
        "policy_id": "env-override",
        "roles": {"ops": {"Ticket.read": "allow", "Ticket.close": "deny"}},
    }
    monkeypatch.setenv("AIPLAT_DEPLOYED_RBAC_POLICY", json.dumps(payload))
    pol = rbac.load_deployed_policy()
    assert pol["policy_id"] == "env-override"
    assert pol["_source"] == "env_json"
    assert pol["_reference_policy_used"] is False
    r = rbac.evaluate_permission(
        role="ops",
        action="Ticket.read",
        actor_tenant="t",
        target_tenant="t",
        policy=pol,
    )
    assert r["decision"] == "allow"
