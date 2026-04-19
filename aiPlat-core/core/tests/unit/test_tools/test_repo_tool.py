import os
import shutil
import subprocess
from pathlib import Path

import pytest

from core.apps.tools.repo import RepoTool
from core.harness.tools.toolsets import resolve_toolset, is_tool_allowed


def _git(cwd: Path, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(["git", *args], cwd=str(cwd), check=True, capture_output=True, text=True)


@pytest.mark.unit
def test_toolset_repo_ops_allowed_and_denied():
    ws = resolve_toolset("workspace_default")
    assert is_tool_allowed(ws, "repo", {"operation": "status"})[0] is True
    assert is_tool_allowed(ws, "repo", {"operation": "diff"})[0] is True
    assert is_tool_allowed(ws, "repo", {"operation": "commit"})[0] is False
    assert is_tool_allowed(ws, "repo", {"operation": "unstage"})[0] is False
    assert is_tool_allowed(ws, "repo", {"operation": "revert"})[0] is False

    wr = resolve_toolset("write_repo")
    assert is_tool_allowed(wr, "repo", {"operation": "commit"})[0] is True
    assert is_tool_allowed(wr, "repo", {"operation": "unstage"})[0] is True
    assert is_tool_allowed(wr, "repo", {"operation": "revert"})[0] is False


@pytest.mark.unit
@pytest.mark.skipif(shutil.which("git") is None, reason="git not installed")
@pytest.mark.asyncio
async def test_repo_tool_status_and_ls_files(tmp_path: Path, monkeypatch):
    repo = tmp_path / "r"
    repo.mkdir(parents=True, exist_ok=True)
    _git(repo, "init")
    _git(repo, "config", "user.email", "test@example.com")
    _git(repo, "config", "user.name", "tester")

    (repo / "a.txt").write_text("hello", encoding="utf-8")
    _git(repo, "add", "a.txt")
    _git(repo, "commit", "-m", "init")
    (repo / "b.txt").write_text("world", encoding="utf-8")

    t = RepoTool(timeout=10000)
    r1 = await t.execute({"operation": "status", "repo_root": str(repo)})
    assert r1.success is True
    assert "b.txt" in (r1.output or "")

    r2 = await t.execute({"operation": "ls_files", "repo_root": str(repo)})
    assert r2.success is True
    assert "a.txt" in (r2.output or {}).get("tracked", [])
    assert "b.txt" in (r2.output or {}).get("untracked", [])

    r3 = await t.execute({"operation": "search", "repo_root": str(repo), "query": "world"})
    assert r3.success is True
    assert (r3.output or {}).get("returned", 0) >= 1
