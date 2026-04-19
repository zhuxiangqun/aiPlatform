import importlib

import pytest
from fastapi.testclient import TestClient


@pytest.mark.integration
def test_plugin_run_approval_and_replay_and_policy_deny(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("AIPLAT_EXECUTION_DB_PATH", str(tmp_path / "exec.sqlite3"))

    import core.server as server

    importlib.reload(server)

    with TestClient(server.app) as client:
        headers_admin = {"X-AIPLAT-TENANT-ID": "t1", "X-AIPLAT-ACTOR-ID": "admin1", "X-AIPLAT-ACTOR-ROLE": "admin"}

        # tenant policy: approval required for calculator
        p = client.put(
            "/api/core/policy/snapshot",
            json={"tenant_id": "t1", "policy": {"tool_policy": {"approval_required_tools": ["calculator"]}}},
            headers=headers_admin,
        )
        assert p.status_code == 200, p.text

        # install plugin (enabled)
        up = client.put(
            "/api/core/plugins",
            json={
                "manifest": {
                    "plugin_id": "p_demo",
                    "name": "demo",
                    "version": "1.0.0",
                    "dependencies": [],
                    "required_tools": ["calculator"],
                    "permissions": {"tools": ["calculator"], "files": {"read": ["workspace/**"]}},
                    "tests": [{"kind": "pytest", "target": "core/tests/integration/test_plugins_workflow.py"}],
                },
                "enabled": True,
            },
            headers=headers_admin,
        )
        assert up.status_code == 200, up.text

        # upsert new version and verify versions list
        up2 = client.put(
            "/api/core/plugins",
            json={
                "manifest": {
                    "plugin_id": "p_demo",
                    "name": "demo",
                    "version": "1.1.0",
                    "required_tools": ["calculator"],
                },
                "enabled": True,
            },
            headers=headers_admin,
        )
        assert up2.status_code == 200, up2.text

        vs = client.get("/api/core/plugins/p_demo/versions", headers=headers_admin)
        assert vs.status_code == 200, vs.text
        items = vs.json().get("items") or []
        assert any((it.get("version") == "1.0.0") for it in items)
        assert any((it.get("version") == "1.1.0") for it in items)

        rb = client.post("/api/core/plugins/p_demo/rollback", json={"version": "1.0.0"}, headers=headers_admin)
        assert rb.status_code == 200, rb.text
        assert rb.json().get("plugin", {}).get("version") == "1.0.0"

        r = client.post(
            "/api/core/plugins/p_demo/run",
            json={"input": {"x": 1}, "session_id": "s1"},
            headers=headers_admin,
        )
        assert r.status_code == 200, r.text
        body = r.json()
        assert body.get("ok") is False
        assert body.get("status") == "waiting_approval"
        approval_id = body.get("approval_request_id")
        run_id = body.get("run_id")
        assert isinstance(approval_id, str) and approval_id
        assert isinstance(run_id, str) and run_id

        a = client.post(f"/api/core/approvals/{approval_id}/approve", json={"approved_by": "admin1"}, headers=headers_admin)
        assert a.status_code == 200, a.text

        rp = client.post(f"/api/core/approvals/{approval_id}/replay", json={}, headers=headers_admin)
        assert rp.status_code == 200, rp.text
        body2 = rp.json()
        assert body2.get("ok") is True
        assert body2.get("run_id") == run_id

        # tenant policy: deny calculator => plugin run should be denied
        p2 = client.put(
            "/api/core/policy/snapshot",
            json={"tenant_id": "t1", "policy": {"tool_policy": {"deny_tools": ["calculator"]}}},
            headers=headers_admin,
        )
        assert p2.status_code == 200, p2.text

        r2 = client.post("/api/core/plugins/p_demo/run", json={"input": {}}, headers=headers_admin)
        assert r2.status_code == 403, r2.text
        assert r2.json().get("error", {}).get("code") == "POLICY_DENIED"
