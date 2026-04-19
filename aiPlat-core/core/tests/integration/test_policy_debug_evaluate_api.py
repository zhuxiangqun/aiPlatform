import importlib

import pytest
from fastapi.testclient import TestClient


@pytest.mark.integration
def test_policy_debug_evaluate_tool(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("AIPLAT_EXECUTION_DB_PATH", str(tmp_path / "exec.sqlite3"))

    import core.server as server

    importlib.reload(server)

    with TestClient(server.app) as client:
        # seed tenant policy: deny calculator
        client.put(
            "/api/core/policies/tenants/t1",
            json={"policy": {"tool_policy": {"deny_tools": ["calculator"], "approval_required_tools": []}}},
        )
        r = client.post(
            "/api/core/policies/evaluate",
            json={"tenant_id": "t1", "actor_id": "u1", "actor_role": "developer", "kind": "tool", "tool_name": "calculator"},
        )
        assert r.status_code == 200
        data = r.json()
        assert data["policy"]["decision"] == "deny"
        assert data["final_decision"] == "deny"

