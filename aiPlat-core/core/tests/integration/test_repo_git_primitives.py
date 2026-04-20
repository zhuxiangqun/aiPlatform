import os
import subprocess

import pytest
from fastapi.testclient import TestClient


def _run(cmd, cwd):
    subprocess.check_call(cmd, cwd=cwd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


@pytest.mark.integration
def test_repo_git_branch_and_commit(tmp_path, monkeypatch):
    # init a tiny git repo
    repo = tmp_path / "r"
    repo.mkdir()
    _run(["git", "init"], cwd=str(repo))
    _run(["git", "config", "user.email", "a@b.c"], cwd=str(repo))
    _run(["git", "config", "user.name", "a"], cwd=str(repo))
    (repo / "a.txt").write_text("v1\n", encoding="utf-8")
    _run(["git", "add", "."], cwd=str(repo))
    _run(["git", "commit", "-m", "init"], cwd=str(repo))

    (repo / "a.txt").write_text("v2\n", encoding="utf-8")
    _run(["git", "add", "."], cwd=str(repo))

    monkeypatch.setenv("AIPLAT_EXECUTION_DB_PATH", str(tmp_path / "exec.sqlite3"))
    from core.server import app

    with TestClient(app) as client:
        client.get("/api/core/permissions/stats")
        r1 = client.post(
            "/api/core/diagnostics/repo/git/branch",
            json={"repo_root": str(repo), "branch": "feat/x", "checkout": True, "require_approval": False},
        )
        assert r1.status_code == 200, r1.text
        data1 = r1.json()
        assert data1["status"] == "ok"
        assert data1["current_branch"] == "feat/x"

        r2 = client.post(
            "/api/core/diagnostics/repo/git/commit",
            json={"repo_root": str(repo), "message": "chore: test", "require_approval": False, "change_id": data1["change_id"]},
        )
        assert r2.status_code == 200, r2.text
        data2 = r2.json()
        assert data2["status"] == "ok"
        assert data2["branch"] == "feat/x"
        assert data2["change_id"] == data1["change_id"]
        assert isinstance(data2.get("commit_sha"), str) and len(data2["commit_sha"]) >= 7

