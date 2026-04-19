import shutil
import subprocess
from pathlib import Path

import pytest

from core.harness.assembly.prompt_assembler import PromptAssembler
from core.harness.kernel.execution_context import ActiveWorkspaceContext, set_active_workspace_context, reset_active_workspace_context


def _git(cwd: Path, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(["git", *args], cwd=str(cwd), check=True, capture_output=True, text=True)


@pytest.mark.integration
@pytest.mark.skipif(shutil.which("git") is None, reason="git not installed")
def test_repo_diff_context_injected(monkeypatch, tmp_path: Path):
    repo = tmp_path / "r"
    repo.mkdir(parents=True, exist_ok=True)
    _git(repo, "init")
    _git(repo, "config", "user.email", "test@example.com")
    _git(repo, "config", "user.name", "tester")
    (repo / "a.txt").write_text("hello\n", encoding="utf-8")
    _git(repo, "add", "a.txt")
    _git(repo, "commit", "-m", "init")
    # unstaged change
    (repo / "a.txt").write_text("hello\nworld\n", encoding="utf-8")

    monkeypatch.setenv("AIPLAT_ENABLE_REPO_DIFF_CONTEXT", "true")
    monkeypatch.setenv("AIPLAT_REPO_DIFF_CONTEXT_POLICY", "warn")
    monkeypatch.setenv("AIPLAT_ENABLE_SESSION_SEARCH", "false")

    tok = set_active_workspace_context(ActiveWorkspaceContext(repo_root=str(repo)))
    try:
        pa = PromptAssembler()
        res = pa.assemble("hi", metadata={})
        # should include repo diff injected as a system message
        sys_msgs = [m for m in res.messages if isinstance(m, dict) and m.get("role") == "system"]
        assert any("# Repo Diff (Ephemeral)" in str(m.get("content", "")) for m in sys_msgs)
        assert res.metadata.get("repo_diff_sha256")
        # workspace_context_hash should incorporate diff sha when enabled
        assert res.metadata.get("workspace_context_hash")
    finally:
        reset_active_workspace_context(tok)

