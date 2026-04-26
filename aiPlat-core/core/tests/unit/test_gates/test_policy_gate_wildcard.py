import os

import pytest


@pytest.mark.unit
@pytest.mark.asyncio
async def test_policy_gate_wildcard_approval_required(tmp_path, monkeypatch):
    # Ensure syscall approval not globally enforced, but tenant policy forces it.
    monkeypatch.setenv("AIPLAT_SYSCALL_ENFORCE_APPROVAL", "false")

    # Patch permission manager to always allow
    import core.apps.tools.permission as perm_mod

    perm_mod._global_permission_manager = perm_mod.PermissionManager()
    pm = perm_mod.get_permission_manager()
    pm.grant_permission("system", "calculator", perm_mod.Permission.EXECUTE, granted_by="admin")

    class _Store:
        async def get_tenant_policy(self, tenant_id: str):
            assert str(tenant_id) == "default"
            return {"tenant_id": "default", "version": 1, "policy": {"tool_policy": {"deny_tools": [], "approval_required_tools": ["*"]}}, "updated_at": 0.0}

    class _Runtime:
        def __init__(self):
            self.execution_store = _Store()
            self.approval_manager = None

    from core.harness.infrastructure.gates import policy_gate as pg_mod

    # PolicyGate imported get_kernel_runtime by name; patch the symbol in its module.
    monkeypatch.setattr(pg_mod, "get_kernel_runtime", lambda: _Runtime())

    from core.harness.infrastructure.gates.policy_gate import PolicyGate, PolicyDecision

    gate = PolicyGate()
    res = await gate.check_tool(user_id="system", tool_name="calculator", tool_args={"_tenant_id": "default", "_session_id": "s1"})
    assert res.decision == PolicyDecision.APPROVAL_REQUIRED
