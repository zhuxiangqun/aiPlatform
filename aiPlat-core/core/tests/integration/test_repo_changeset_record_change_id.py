import subprocess
from pathlib import Path

import pytest
from fastapi.testclient import TestClient


def _run(cmd: list[str], cwd: str):
    subprocess.run(cmd, cwd=cwd, check=True, capture_output=True, text=True)


@pytest.mark.integration
def test_repo_changeset_record_returns_change_id_and_writes_changeset(tmp_path, monkeypatch):
    monkeypatch.setenv("AIPLAT_EXECUTION_DB_PATH", str(tmp_path / "exec.sqlite3"))

    # Create a minimal git repo with a staged change.
    repo = tmp_path / "repo"
    repo.mkdir(parents=True, exist_ok=True)
    _run(["git", "init"], cwd=str(repo))
    _run(["git", "config", "user.email", "test@example.com"], cwd=str(repo))
    _run(["git", "config", "user.name", "Test"], cwd=str(repo))
    (repo / "a.txt").write_text("hello\n", encoding="utf-8")
    _run(["git", "add", "a.txt"], cwd=str(repo))
    _run(["git", "commit", "-m", "init"], cwd=str(repo))
    (repo / "a.txt").write_text("hello\nworld\n", encoding="utf-8")
    _run(["git", "add", "a.txt"], cwd=str(repo))

    from core.server import app

    with TestClient(app) as client:
        client.get("/api/core/permissions/stats")
        r = client.post("/api/core/diagnostics/repo/changeset/record", json={"repo_root": str(repo), "include_patch": False, "note": "x"})
        assert r.status_code == 200, r.text
        data = r.json()
        assert data.get("status") == "recorded"
        change_id = data.get("change_id")
        assert isinstance(change_id, str) and change_id.startswith("chg-")
        assert isinstance(data.get("links"), dict)

        # ensure syscall event exists via change-control evidence
        s = client.get(f"/api/core/change-control/changes/{change_id}/evidence?format=json&limit=200")
        assert s.status_code == 200, s.text
        evidence = s.json()
        cc = evidence.get("change_control") or {}
        ev = cc.get("events") if isinstance(cc, dict) else None
        items = (ev.get("items") or []) if isinstance(ev, dict) else []
        assert any((isinstance(it, dict) and it.get("name") == "repo_changeset_record") for it in items)


@pytest.mark.integration
def test_repo_changeset_record_requires_approval_on_non_local_backend(tmp_path, monkeypatch):
    monkeypatch.setenv("AIPLAT_EXECUTION_DB_PATH", str(tmp_path / "exec.sqlite3"))
    monkeypatch.setenv("AIPLAT_EXEC_BACKEND", "docker")

    repo = tmp_path / "repo2"
    repo.mkdir(parents=True, exist_ok=True)
    _run(["git", "init"], cwd=str(repo))
    _run(["git", "config", "user.email", "test@example.com"], cwd=str(repo))
    _run(["git", "config", "user.name", "Test"], cwd=str(repo))
    (repo / "a.txt").write_text("hello\n", encoding="utf-8")
    _run(["git", "add", "a.txt"], cwd=str(repo))
    _run(["git", "commit", "-m", "init"], cwd=str(repo))
    (repo / "a.txt").write_text("hello\nworld\n", encoding="utf-8")
    _run(["git", "add", "a.txt"], cwd=str(repo))

    from core.server import app

    with TestClient(app) as client:
        client.get("/api/core/permissions/stats")
        r = client.post("/api/core/diagnostics/repo/changeset/record", json={"repo_root": str(repo), "include_patch": False, "note": "x"})
        assert r.status_code == 200, r.text
        data = r.json()
        assert data.get("status") == "approval_required"
        assert isinstance(data.get("approval_request_id"), str) and data["approval_request_id"]
        assert isinstance(data.get("change_id"), str) and data["change_id"].startswith("chg-")
