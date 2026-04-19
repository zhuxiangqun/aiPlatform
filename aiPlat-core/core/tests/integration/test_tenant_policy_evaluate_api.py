import importlib

import pytest
from fastapi.testclient import TestClient


@pytest.mark.integration
def test_tenant_policy_evaluate_tool(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("AIPLAT_EXECUTION_DB_PATH", str(tmp_path / "exec.sqlite3"))

    import core.server as server

    importlib.reload(server)

    with TestClient(server.app) as client:
        client.put(
            "/api/core/policies/tenants/t1",
            json={"policy": {"tool_policy": {"deny_tools": ["calculator"], "approval_required_tools": ["file_operations"]}}},
        )

        r1 = client.get("/api/core/policies/tenants/t1/evaluate-tool", params={"tool_name": "calculator"})
        assert r1.status_code == 200
        assert r1.json()["decision"] == "deny"

        r2 = client.get("/api/core/policies/tenants/t1/evaluate-tool", params={"tool_name": "file_operations"})
        assert r2.status_code == 200
        assert r2.json()["decision"] == "approval_required"

        r3 = client.get("/api/core/policies/tenants/t1/evaluate-tool", params={"tool_name": "search"})
        assert r3.status_code == 200
        assert r3.json()["decision"] == "allow"

