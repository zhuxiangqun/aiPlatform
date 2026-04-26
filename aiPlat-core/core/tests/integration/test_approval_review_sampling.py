import importlib
from pathlib import Path

import pytest
from fastapi.testclient import TestClient


@pytest.mark.integration
def test_approval_review_sampling_waives_approvals(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("AIPLAT_EXECUTION_DB_PATH", str(tmp_path / "exec.sqlite3"))
    monkeypatch.setenv("AIPLAT_SYSCALL_ENFORCE_APPROVAL", "false")
    # Make file writes possible
    out_dir = tmp_path / "out"
    out_dir.mkdir(parents=True, exist_ok=True)
    monkeypatch.setenv("AIPLAT_FILE_OPERATIONS_ALLOWED_ROOTS", str(out_dir))
    monkeypatch.setenv("AIPLAT_FILE_OPERATIONS_ALLOW_WRITE", "true")

    import core.server as server

    importlib.reload(server)

    hdr = {"X-AIPLAT-TENANT-ID": "t_demo", "X-AIPLAT-ACTOR-ID": "admin", "X-AIPLAT-ACTOR-ROLE": "admin"}

    with TestClient(server.app) as client:
        # Tenant policy: waive approvals via sampling (rate=0 means always waive), even for high risk.
        pol = {"approval_review": {"mode": "sample", "sample_rate": 0.0, "high_risk_always": False}}
        up = client.put("/api/core/policies/tenants/t_demo", headers=hdr, json={"policy": pol})
        assert up.status_code == 200, up.text

        # Permissions
        for rid in ["demo_write_file_note", "file_operations"]:
            r = client.post("/api/core/permissions/grant", json={"user_id": "admin", "resource_id": rid, "permission": "execute"})
            assert r.status_code == 200, r.text

        target = str((out_dir / "note.txt").resolve())
        r1 = client.post(
            "/api/core/gateway/execute",
            headers=hdr,
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
        body = r1.json()
        assert body.get("status") == "completed"
        assert body.get("ok") is True

        # Ensure no pending approvals were created for this run.
        run_id = body.get("run_id")
        lst = client.get("/api/core/approvals", params={"run_id": run_id, "status": "pending", "limit": 50, "offset": 0})
        assert lst.status_code == 200, lst.text
        assert int(lst.json().get("total") or 0) == 0

        # File exists
        p = Path(target)
        assert p.exists()
        assert p.read_text(encoding="utf-8") == "hello"

