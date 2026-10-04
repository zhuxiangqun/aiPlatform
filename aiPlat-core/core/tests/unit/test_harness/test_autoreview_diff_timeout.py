"""Root-cause autoreview staging: explicit worktree, no global GIT_* mutation."""
from __future__ import annotations

import os
import subprocess
import time

import pytest

from core.engine.skills.autoreview.diff_loader import load_diff
from core.harness.utils.inline_autoreview_workspace import (
    autoreview_git_env_for_inline,
    coerce_inline_delivery_text,
    stage_inline_delivery,
    staged_inline_worktree,
)


def test_load_diff_respects_timeout(monkeypatch):
    def _slow(*_a, **_k):
        raise subprocess.TimeoutExpired(cmd=["git", "diff"], timeout=1)

    monkeypatch.setattr(subprocess, "run", _slow)
    t0 = time.time()
    diff = load_diff("diff", timeout=1)
    assert time.time() - t0 < 2.0
    assert diff.content == ""
    assert diff.truncated is True


def test_load_diff_uses_worktree_cwd(tmp_path):
    repo = tmp_path / "r"
    repo.mkdir()
    subprocess.run(["git", "init"], cwd=repo, check=True, capture_output=True)
    subprocess.run(
        ["git", "config", "user.email", "t@t"],
        cwd=repo,
        check=True,
        capture_output=True,
    )
    subprocess.run(
        ["git", "config", "user.name", "t"],
        cwd=repo,
        check=True,
        capture_output=True,
    )
    subprocess.run(
        ["git", "commit", "--allow-empty", "-m", "b"],
        cwd=repo,
        check=True,
        capture_output=True,
    )
    (repo / "a.ts").write_text("export const x = 1\n", encoding="utf-8")
    subprocess.run(["git", "add", "-A"], cwd=repo, check=True, capture_output=True)
    os.environ["GIT_WORK_TREE"] = str(tmp_path / "missing")
    os.environ["GIT_DIR"] = str(tmp_path / "missing.git")
    try:
        diff = load_diff("diff", cwd=str(repo), timeout=15)
    finally:
        os.environ.pop("GIT_WORK_TREE", None)
        os.environ.pop("GIT_DIR", None)
    assert "a.ts" in diff.content or "export const x" in diff.content


def test_stage_inline_does_not_mutate_git_env():
    prev_dir = os.environ.get("GIT_DIR")
    prev_wt = os.environ.get("GIT_WORK_TREE")
    inline = "## FILE: src/a.ts\n```ts\nexport const n = 1\n```\n"
    with staged_inline_worktree(inline) as wt:
        assert wt
        assert os.environ.get("GIT_DIR") == prev_dir
        assert os.environ.get("GIT_WORK_TREE") == prev_wt
        diff = load_diff("diff", cwd=wt)
        assert diff.content
        assert "export const n" in diff.content or "a.ts" in diff.content
    assert os.environ.get("GIT_DIR") == prev_dir
    assert os.environ.get("GIT_WORK_TREE") == prev_wt


def test_coerce_unwraps_code_dict():
    raw = {"code": "## FILE: x.ts\n```ts\nexport const a = 1\n```\n"}
    text = coerce_inline_delivery_text(raw)
    assert text.startswith("## FILE:")
    assert "export const a" in text


def test_compat_alias_still_stages():
    inline = "## FILE: src/apiClient.ts\n```typescript\nexport async function createReport() { return 1 }\n```\n"
    with autoreview_git_env_for_inline(inline) as wt:
        assert wt
        diff = load_diff("diff", cwd=wt)
    assert diff.content
    assert "apiClient" in diff.content or "createReport" in diff.content


def test_empty_inline_stages_none():
    assert stage_inline_delivery("") is None
    with staged_inline_worktree("") as wt:
        assert wt is None
