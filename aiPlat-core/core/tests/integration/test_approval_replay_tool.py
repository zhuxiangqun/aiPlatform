import importlib

import pytest
from fastapi.testclient import TestClient


@pytest.mark.integration
def test_tool_approval_then_replay(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("AIPLAT_EXECUTION_DB_PATH", str(tmp_path / "exec.sqlite3"))
    monkeypatch.setenv("AIPLAT_SYSCALL_ENFORCE_APPROVAL", "true")

    import core.server as server

    importlib.reload(server)

    with TestClient(server.app) as client:
        r = client.post(
            "/api/core/tools/calculator/execute",
            json={
                "input": {"expression": "1+2", "_approval_required": True},
                # PermissionManager 默认对非 system 用户可能是 deny（避免误用），测试用 system。
                "context": {"tenant_id": "t_demo", "actor_id": "system", "actor_role": "admin", "session_id": "s1"},
            },
            headers={"X-AIPLAT-TENANT-ID": "t_demo", "X-AIPLAT-ACTOR-ID": "system", "X-AIPLAT-ACTOR-ROLE": "admin"},
        )
        assert r.status_code == 200, r.text
        body = r.json()
        run_id = body.get("run_id")
        assert isinstance(run_id, str) and run_id

        # Extract approval_request_id from run events
        ev = client.get(f"/api/core/runs/{run_id}/events", params={"after_seq": 0, "limit": 200})
        assert ev.status_code == 200, ev.text
        approval_id = None
        for it in (ev.json().get("items") or []):
            if it.get("type") == "approval_requested":
                approval_id = (it.get("payload") or {}).get("approval_request_id")
                break
        assert isinstance(approval_id, str) and approval_id

        a = client.post(
            f"/api/core/approvals/{approval_id}/approve",
            json={"approved_by": "u_op", "comments": "ok"},
            headers={"X-AIPLAT-TENANT-ID": "t_demo", "X-AIPLAT-ACTOR-ID": "u_op", "X-AIPLAT-ACTOR-ROLE": "operator"},
        )
        assert a.status_code == 200, a.text

        rp = client.post(
            f"/api/core/approvals/{approval_id}/replay",
            json={},
            headers={"X-AIPLAT-TENANT-ID": "t_demo", "X-AIPLAT-ACTOR-ID": "u_op", "X-AIPLAT-ACTOR-ROLE": "operator"},
        )
        assert rp.status_code == 200, rp.text
        body2 = rp.json()
        # Replay should continue on the same run_id when metadata carries it.
        assert body2.get("run_id") == run_id
