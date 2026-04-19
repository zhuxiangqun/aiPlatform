import importlib

import pytest
from fastapi.testclient import TestClient


@pytest.mark.integration
def test_policy_denied_emits_run_event_with_policy_version(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("AIPLAT_EXECUTION_DB_PATH", str(tmp_path / "exec.sqlite3"))

    import core.server as server

    importlib.reload(server)

    with TestClient(server.app) as client:
        # Deny calculator tool for tenant t1
        p = client.put("/api/core/policies/tenants/t1", json={"policy": {"tool_policy": {"deny_tools": ["calculator"]}}})
        assert p.status_code == 200, p.text
        ver = p.json().get("version")

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

        ev = client.get(f"/api/core/runs/{run_id}/events", params={"after_seq": 0, "limit": 50})
        assert ev.status_code == 200, ev.text
        items = ev.json().get("items") or []
        tool_end = [x for x in items if x.get("type") == "tool_end"]
        assert tool_end, items
        payload = tool_end[-1].get("payload") or {}
        assert payload.get("status") == "policy_denied"
        assert payload.get("tenant_id") == "t1"
        assert payload.get("policy_version") == ver

