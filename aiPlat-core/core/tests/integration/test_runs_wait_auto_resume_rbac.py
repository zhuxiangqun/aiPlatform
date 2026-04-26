import importlib
from pathlib import Path

import pytest
from fastapi.testclient import TestClient


@pytest.mark.integration
def test_runs_wait_auto_resume_rbac_enforced_denies_developer(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("AIPLAT_EXECUTION_DB_PATH", str(tmp_path / "exec.sqlite3"))
    monkeypatch.setenv("AIPLAT_SYSCALL_ENFORCE_APPROVAL", "false")
    monkeypatch.setenv("AIPLAT_RUN_WAIT_AUTO_RESUME_ENABLED", "true")
    monkeypatch.setenv("AIPLAT_RUN_WAIT_AUTO_RESUME_ALLOWLIST", "skill:*")
    monkeypatch.setenv("AIPLAT_RBAC_MODE", "enforced")

    out_dir = tmp_path / "out"
    out_dir.mkdir(parents=True, exist_ok=True)
    monkeypatch.setenv("AIPLAT_FILE_OPERATIONS_ALLOWED_ROOTS", str(out_dir))
    monkeypatch.setenv("AIPLAT_FILE_OPERATIONS_ALLOW_WRITE", "true")

    import core.server as server

    importlib.reload(server)

    with TestClient(server.app) as client:
        for rid in ["demo_write_file_note", "file_operations"]:
            r = client.post("/api/core/permissions/grant", json={"user_id": "admin", "resource_id": rid, "permission": "execute"})
            assert r.status_code == 200, r.text

        target = str((out_dir / "note.txt").resolve())
        r1 = client.post(
            "/api/core/gateway/execute",
            headers={"X-AIPLAT-TENANT-ID": "t_demo", "X-AIPLAT-ACTOR-ID": "admin", "X-AIPLAT-ACTOR-ROLE": "admin"},
            json={
                "channel": "web",
                "kind": "skill",
                "target_id": "demo_write_file_note",
                "user_id": "admin",
                "session_id": "s_demo",
                "tenant_id": "t_demo",
                "payload": {"input": {"path": target, "content": "hello"}, "context": {"tenant_id": "t_demo"}},
            },
        )
        assert r1.status_code == 200, r1.text
        run_id = r1.json().get("run_id")
        assert isinstance(run_id, str) and run_id

        # approval id is available
        w1 = client.post(
            f"/api/core/runs/{run_id}/wait",
            headers={"X-AIPLAT-TENANT-ID": "t_demo", "X-AIPLAT-ACTOR-ID": "admin", "X-AIPLAT-ACTOR-ROLE": "admin"},
            json={"timeout_ms": 2000, "after_seq": 0},
        )
        approval_id = w1.json().get("approval_request_id")
        assert isinstance(approval_id, str) and approval_id

        # approve as operator/admin is allowed
        a = client.post(
            f"/api/core/approvals/{approval_id}/approve",
            json={"approved_by": "admin", "comments": "ok"},
            headers={"X-AIPLAT-TENANT-ID": "t_demo", "X-AIPLAT-ACTOR-ID": "admin", "X-AIPLAT-ACTOR-ROLE": "admin"},
        )
        assert a.status_code == 200, a.text

        # attempt auto-resume as developer should be forbidden (403) in enforced mode
        last_seq = int(w1.json().get("last_seq") or 0)
        w2 = client.post(
            f"/api/core/runs/{run_id}/wait",
            headers={"X-AIPLAT-TENANT-ID": "t_demo", "X-AIPLAT-ACTOR-ID": "dev1", "X-AIPLAT-ACTOR-ROLE": "developer"},
            json={"timeout_ms": 2000, "after_seq": last_seq, "auto_resume": True},
        )
        assert w2.status_code == 403, w2.text

