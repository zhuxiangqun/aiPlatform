import importlib

import pytest
from fastapi.testclient import TestClient


@pytest.mark.integration
def test_tenant_policy_denies_tool_syscall(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("AIPLAT_EXECUTION_DB_PATH", str(tmp_path / "exec.sqlite3"))

    import core.server as server

    importlib.reload(server)

    with TestClient(server.app) as client:
        # Set tenant policy to deny calculator tool
        p = client.put(
            "/api/core/policies/tenants/t1",
            json={"policy": {"tool_policy": {"deny_tools": ["calculator"]}}},
        )
        assert p.status_code == 200, p.text

        # Execute calculator via gateway with tenant_id=t1
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
        assert body.get("status") == "failed"
        assert (body.get("error_detail") or {}).get("code") == "POLICY_DENIED"

