import importlib
from pathlib import Path

import pytest
from fastapi.testclient import TestClient


@pytest.mark.integration
def test_skill_approval_then_replay_writes_file(tmp_path, monkeypatch):
    """
    End-to-end:
    1) gateway/execute -> skill requires approval -> returns approval_request_id
    2) approve
    3) replay -> skill executes and writes file
    """
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("AIPLAT_EXECUTION_DB_PATH", str(tmp_path / "exec.sqlite3"))
    monkeypatch.setenv("AIPLAT_SYSCALL_ENFORCE_APPROVAL", "false")
    # file_operations safety switches
    out_dir = tmp_path / "out"
    out_dir.mkdir(parents=True, exist_ok=True)
    monkeypatch.setenv("AIPLAT_FILE_OPERATIONS_ALLOWED_ROOTS", str(out_dir))
    monkeypatch.setenv("AIPLAT_FILE_OPERATIONS_ALLOW_WRITE", "true")

    import core.server as server

    importlib.reload(server)

    with TestClient(server.app) as client:
        # Grant permissions (approval is additive; it doesn't bypass EXECUTE checks).
        for rid in ["demo_write_file_note", "file_operations"]:
            r = client.post(
                "/api/core/permissions/grant",
                json={"user_id": "admin", "resource_id": rid, "permission": "execute", "granted_by": "test"},
            )
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
        body = r1.json()
        assert body.get("status") == "waiting_approval"
        approval_id = ((body.get("error") or {}).get("extra") or {}).get("approval_request_id")
        assert isinstance(approval_id, str) and approval_id
        run_id = body.get("run_id")
        assert isinstance(run_id, str) and run_id

        a = client.post(
            f"/api/core/approvals/{approval_id}/approve",
            json={"approved_by": "admin", "comments": "ok"},
            headers={"X-AIPLAT-TENANT-ID": "t_demo", "X-AIPLAT-ACTOR-ID": "admin", "X-AIPLAT-ACTOR-ROLE": "admin"},
        )
        assert a.status_code == 200, a.text

        rp = client.post(
            f"/api/core/approvals/{approval_id}/replay",
            json={},
            headers={"X-AIPLAT-TENANT-ID": "t_demo", "X-AIPLAT-ACTOR-ID": "admin", "X-AIPLAT-ACTOR-ROLE": "admin"},
        )
        assert rp.status_code == 200, rp.text
        body2 = rp.json()
        assert body2.get("ok") is True
        assert body2.get("status") == "completed"
        # keep the same run for linkage
        assert body2.get("run_id") == run_id

        p = Path(target)
        assert p.exists()
        assert p.read_text(encoding="utf-8") == "hello"

