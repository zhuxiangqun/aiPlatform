import importlib

import pytest
from fastapi.testclient import TestClient


@pytest.mark.integration
def test_policy_denied_writes_audit_log(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("AIPLAT_EXECUTION_DB_PATH", str(tmp_path / "exec.sqlite3"))

    import core.server as server

    importlib.reload(server)

    with TestClient(server.app) as client:
        # Deny calculator tool for tenant t1
        p = client.put("/api/core/policies/tenants/t1", json={"policy": {"tool_policy": {"deny_tools": ["calculator"]}}})
        assert p.status_code == 200, p.text

        r = client.post(
            "/api/core/gateway/execute",
            json={
                "channel": "api",
                "kind": "tool",
                "target_id": "calculator",
                "tenant_id": "t1",
                "payload": {"input": {"expression": "1+1"}, "context": {"tenant_id": "t1"}},
            },
        )
        assert r.status_code == 200, r.text
        body = r.json()
        assert body.get("ok") is False
        run_id = body.get("run_id")
        assert isinstance(run_id, str) and run_id.startswith("run_")

        a = client.get("/api/core/audit/logs", params={"action": "tool_policy_denied", "run_id": run_id, "limit": 50, "offset": 0})
        assert a.status_code == 200, a.text
        items = a.json().get("items") or []
        assert len(items) >= 1
        assert items[0]["action"] in ("tool_policy_denied", "tool_permission_denied")
        assert items[0]["run_id"] == run_id

