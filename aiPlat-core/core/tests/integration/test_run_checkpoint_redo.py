import importlib

import pytest
from fastapi.testclient import TestClient


@pytest.mark.integration
def test_checkpoint_reject_then_redo_creates_new_run(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("AIPLAT_EXECUTION_DB_PATH", str(tmp_path / "exec.sqlite3"))
    monkeypatch.setenv("AIPLAT_RBAC_MODE", "enforced")
    # Make executable skills runnable without approval in this test.
    monkeypatch.setenv("AIPLAT_EXEC_SKILL_PERMISSION_RULES", '{"demo_readonly_summarize":"allow","*":"ask"}')

    import core.server as server

    importlib.reload(server)

    hdr = {"X-AIPLAT-TENANT-ID": "t_demo", "X-AIPLAT-ACTOR-ID": "admin", "X-AIPLAT-ACTOR-ROLE": "admin"}

    with TestClient(server.app) as client:
        # Grant execute for demo_readonly_summarize
        r = client.post("/api/core/permissions/grant", json={"user_id": "admin", "resource_id": "demo_readonly_summarize", "permission": "execute"})
        assert r.status_code == 200, r.text

        # Run once (completed)
        r1 = client.post(
            "/api/core/gateway/execute",
            headers=hdr,
            json={
                "channel": "web",
                "kind": "skill",
                "target_id": "demo_readonly_summarize",
                "user_id": "admin",
                "session_id": "s_demo",
                "tenant_id": "t_demo",
                "payload": {"input": {"text": "hello world"}, "context": {"tenant_id": "t_demo"}},
            },
        )
        assert r1.status_code == 200, r1.text
        run_id = r1.json().get("run_id")
        assert isinstance(run_id, str) and run_id

        # Request checkpoint
        rq = client.post(
            f"/api/core/runs/{run_id}/checkpoints/request",
            headers=hdr,
            json={"node_id": "final", "title": "结果复核", "blocking": True},
        )
        assert rq.status_code == 200, rq.text
        ckpt = rq.json().get("checkpoint_id")
        assert isinstance(ckpt, str) and ckpt

        # Resolve as rejected (event only)
        rs = client.post(
            f"/api/core/runs/{run_id}/checkpoints/{ckpt}/resolve",
            headers=hdr,
            json={"decision": "rejected", "comments": "redo with more detail"},
        )
        assert rs.status_code == 200, rs.text

        # Redo with patch (change input text)
        redo = client.post(
            f"/api/core/runs/{run_id}/checkpoints/{ckpt}/redo",
            headers=hdr,
            json={"patch": {"input": {"text": "hello world!!!"}}},
        )
        assert redo.status_code == 200, redo.text
        body = redo.json()
        assert body.get("previous_run_id") == run_id
        new_run_id = body.get("new_run_id")
        assert isinstance(new_run_id, str) and new_run_id
        assert body.get("status") in {"completed", "failed", "running", "accepted"}

        # New run exists
        rget = client.get(f"/api/core/runs/{new_run_id}", headers=hdr)
        assert rget.status_code == 200, rget.text
