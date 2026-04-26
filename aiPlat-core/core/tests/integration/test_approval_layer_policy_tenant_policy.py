import importlib
from pathlib import Path

import pytest
from fastapi.testclient import TestClient


def _setup_common_env(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("AIPLAT_EXECUTION_DB_PATH", str(tmp_path / "exec.sqlite3"))
    monkeypatch.setenv("AIPLAT_SYSCALL_ENFORCE_APPROVAL", "false")
    monkeypatch.setenv("AIPLAT_RUN_WAIT_AUTO_RESUME_ENABLED", "true")
    monkeypatch.setenv("AIPLAT_RUN_WAIT_AUTO_RESUME_ALLOWLIST", "skill:*,tool:*")
    # Ensure env defaults do NOT decide layering (tenant policy should override).
    monkeypatch.setenv("AIPLAT_APPROVAL_LAYER_POLICY", "both")

    out_dir = tmp_path / "out"
    out_dir.mkdir(parents=True, exist_ok=True)
    monkeypatch.setenv("AIPLAT_FILE_OPERATIONS_ALLOWED_ROOTS", str(out_dir))
    monkeypatch.setenv("AIPLAT_FILE_OPERATIONS_ALLOW_WRITE", "true")
    return out_dir


@pytest.mark.integration
def test_tenant_policy_overrides_env_skill_only(tmp_path, monkeypatch):
    out_dir = _setup_common_env(tmp_path, monkeypatch)

    import core.server as server

    importlib.reload(server)

    with TestClient(server.app) as client:
        # Tenant policy: skill_only
        pol = {"approval_layering": {"policy": "skill_only"}}
        up = client.put(
            "/api/core/policies/tenants/t_demo",
            headers={"X-AIPLAT-TENANT-ID": "t_demo", "X-AIPLAT-ACTOR-ID": "admin", "X-AIPLAT-ACTOR-ROLE": "admin"},
            json={"policy": pol},
        )
        assert up.status_code == 200, up.text

        for rid in ["demo_double_approval_file_write", "file_operations"]:
            r = client.post("/api/core/permissions/grant", json={"user_id": "admin", "resource_id": rid, "permission": "execute"})
            assert r.status_code == 200, r.text

        target = str((out_dir / "note.txt").resolve())
        r1 = client.post(
            "/api/core/gateway/execute",
            headers={"X-AIPLAT-TENANT-ID": "t_demo", "X-AIPLAT-ACTOR-ID": "admin", "X-AIPLAT-ACTOR-ROLE": "admin"},
            json={
                "channel": "web",
                "kind": "skill",
                "target_id": "demo_double_approval_file_write",
                "user_id": "admin",
                "session_id": "s_demo",
                "tenant_id": "t_demo",
                "payload": {"input": {"path": target, "content": "hello"}, "context": {"tenant_id": "t_demo"}},
            },
        )
        assert r1.status_code == 200, r1.text
        run_id = r1.json().get("run_id")

        w1 = client.post(
            f"/api/core/runs/{run_id}/wait",
            headers={"X-AIPLAT-TENANT-ID": "t_demo", "X-AIPLAT-ACTOR-ID": "admin", "X-AIPLAT-ACTOR-ROLE": "admin"},
            json={"timeout_ms": 3000, "after_seq": 0},
        )
        approval_id = w1.json().get("approval_request_id")
        assert isinstance(approval_id, str) and approval_id

        a = client.post(
            f"/api/core/approvals/{approval_id}/approve",
            json={"approved_by": "admin", "comments": "ok"},
            headers={"X-AIPLAT-TENANT-ID": "t_demo", "X-AIPLAT-ACTOR-ID": "admin", "X-AIPLAT-ACTOR-ROLE": "admin"},
        )
        assert a.status_code == 200, a.text

        last_seq = int(w1.json().get("last_seq") or 0)
        w2 = client.post(
            f"/api/core/runs/{run_id}/wait",
            headers={"X-AIPLAT-TENANT-ID": "t_demo", "X-AIPLAT-ACTOR-ID": "admin", "X-AIPLAT-ACTOR-ROLE": "admin"},
            json={"timeout_ms": 20000, "after_seq": last_seq, "auto_resume": True},
        )
        assert (w2.json().get("run") or {}).get("status") == "completed"

        p = Path(target)
        assert p.exists()
        assert p.read_text(encoding="utf-8") == "hello"


@pytest.mark.integration
def test_tenant_policy_overrides_env_tool_only(tmp_path, monkeypatch):
    out_dir = _setup_common_env(tmp_path, monkeypatch)

    import core.server as server

    importlib.reload(server)

    with TestClient(server.app) as client:
        # Tenant policy: tool_only
        pol = {"approval_layering": {"policy": "tool_only"}}
        up = client.put(
            "/api/core/policies/tenants/t_demo",
            headers={"X-AIPLAT-TENANT-ID": "t_demo", "X-AIPLAT-ACTOR-ID": "admin", "X-AIPLAT-ACTOR-ROLE": "admin"},
            json={"policy": pol},
        )
        assert up.status_code == 200, up.text

        for rid in ["demo_double_approval_file_write", "file_operations"]:
            r = client.post("/api/core/permissions/grant", json={"user_id": "admin", "resource_id": rid, "permission": "execute"})
            assert r.status_code == 200, r.text

        target = str((out_dir / "note.txt").resolve())
        r1 = client.post(
            "/api/core/gateway/execute",
            headers={"X-AIPLAT-TENANT-ID": "t_demo", "X-AIPLAT-ACTOR-ID": "admin", "X-AIPLAT-ACTOR-ROLE": "admin"},
            json={
                "channel": "web",
                "kind": "skill",
                "target_id": "demo_double_approval_file_write",
                "user_id": "admin",
                "session_id": "s_demo",
                "tenant_id": "t_demo",
                "payload": {"input": {"path": target, "content": "hello"}, "context": {"tenant_id": "t_demo"}},
            },
        )
        assert r1.status_code == 200, r1.text
        run_id = r1.json().get("run_id")

        w1 = client.post(
            f"/api/core/runs/{run_id}/wait",
            headers={"X-AIPLAT-TENANT-ID": "t_demo", "X-AIPLAT-ACTOR-ID": "admin", "X-AIPLAT-ACTOR-ROLE": "admin"},
            json={"timeout_ms": 4000, "after_seq": 0},
        )
        approval_id = w1.json().get("approval_request_id")
        assert isinstance(approval_id, str) and approval_id
        info = client.get(f"/api/core/approvals/{approval_id}")
        assert info.status_code == 200, info.text
        assert str(info.json().get("operation") or "").startswith("tool:")

        a = client.post(
            f"/api/core/approvals/{approval_id}/approve",
            json={"approved_by": "admin", "comments": "ok"},
            headers={"X-AIPLAT-TENANT-ID": "t_demo", "X-AIPLAT-ACTOR-ID": "admin", "X-AIPLAT-ACTOR-ROLE": "admin"},
        )
        assert a.status_code == 200, a.text

        last_seq = int(w1.json().get("last_seq") or 0)
        w2 = client.post(
            f"/api/core/runs/{run_id}/wait",
            headers={"X-AIPLAT-TENANT-ID": "t_demo", "X-AIPLAT-ACTOR-ID": "admin", "X-AIPLAT-ACTOR-ROLE": "admin"},
            json={"timeout_ms": 20000, "after_seq": last_seq, "auto_resume": True},
        )
        assert (w2.json().get("run") or {}).get("status") == "completed"

        p = Path(target)
        assert p.exists()
        assert p.read_text(encoding="utf-8") == "hello"

