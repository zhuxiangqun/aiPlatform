import os
import sqlite3

import pytest


@pytest.mark.unit
def test_policy_gate_wildcard_approval_required(tmp_path, monkeypatch):
    # Ensure syscall approval not globally enforced, but tenant policy forces it.
    monkeypatch.setenv("AIPLAT_SYSCALL_ENFORCE_APPROVAL", "false")

    # Patch permission manager to always allow
    import core.apps.tools.permission as perm_mod

    perm_mod._global_permission_manager = perm_mod.PermissionManager()
    pm = perm_mod.get_permission_manager()
    pm.grant_permission("system", "calculator", perm_mod.Permission.EXECUTE, granted_by="admin")

    # Create a minimal ExecutionStore-like runtime with a sqlite db containing tenant_policies
    db_path = tmp_path / "db.sqlite3"
    conn = sqlite3.connect(str(db_path))
    try:
        conn.execute(
            "CREATE TABLE tenant_policies (tenant_id TEXT PRIMARY KEY, version INTEGER NOT NULL, policy_json TEXT NOT NULL, updated_at REAL NOT NULL);"
        )
        conn.execute(
            "INSERT INTO tenant_policies(tenant_id, version, policy_json, updated_at) VALUES(?,?,?,?);",
            ("default", 1, '{"tool_policy":{"deny_tools":[],"approval_required_tools":["*"]}}', 0.0),
        )
        conn.commit()
    finally:
        conn.close()

    # Monkeypatch kernel runtime to expose execution_store db_path but NO approval manager → should fail-closed to approval_required
    class _StoreCfg:
        def __init__(self, p):
            self.db_path = str(p)

    class _Store:
        def __init__(self, p):
            self._config = _StoreCfg(p)

    class _Runtime:
        def __init__(self, p):
            self.execution_store = _Store(p)
            self.approval_manager = None

    from core.harness.infrastructure.gates import policy_gate as pg_mod

    # PolicyGate imported get_kernel_runtime by name; patch the symbol in its module.
    monkeypatch.setattr(pg_mod, "get_kernel_runtime", lambda: _Runtime(db_path))

    from core.harness.infrastructure.gates.policy_gate import PolicyGate, PolicyDecision

    gate = PolicyGate()
    res = gate.check_tool(user_id="system", tool_name="calculator", tool_args={"_tenant_id": "default", "_session_id": "s1"})
    assert res.decision == PolicyDecision.APPROVAL_REQUIRED
