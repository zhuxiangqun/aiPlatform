"""T0/T1a team harness schema + FF pull tests."""
from __future__ import annotations

import json
import subprocess
from pathlib import Path

from core.harness.team_harness import (
    SCHEMA_VERSION,
    backup_team_tree,
    configure_team_harness,
    load_team_harness_schema,
    local_dir,
    materialize_team_harness_schema,
    pull_team_harness,
    read_meta,
    restore_team_backup,
    team_dir,
    team_is_dirty,
)


def _git_init_with_commit(repo: Path, *, message: str = "init") -> str:
    repo.mkdir(parents=True, exist_ok=True)
    subprocess.run(["git", "init"], cwd=repo, check=True, capture_output=True)
    subprocess.run(
        ["git", "config", "user.email", "test@example.com"],
        cwd=repo,
        check=True,
        capture_output=True,
    )
    subprocess.run(
        ["git", "config", "user.name", "test"],
        cwd=repo,
        check=True,
        capture_output=True,
    )
    # default branch main
    subprocess.run(
        ["git", "checkout", "-b", "main"],
        cwd=repo,
        check=False,
        capture_output=True,
    )
    (repo / "skills").mkdir(exist_ok=True)
    (repo / "skills" / "README.md").write_text("# skills\n", encoding="utf-8")
    (repo / "culture.md").write_text("We ship carefully.\n", encoding="utf-8")
    subprocess.run(["git", "add", "-A"], cwd=repo, check=True, capture_output=True)
    subprocess.run(
        ["git", "commit", "-m", message],
        cwd=repo,
        check=True,
        capture_output=True,
    )
    sha = subprocess.check_output(
        ["git", "rev-parse", "HEAD"], cwd=repo, text=True
    ).strip()
    return sha


def _commit_file(repo: Path, rel: str, content: str, message: str) -> str:
    path = repo / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    subprocess.run(["git", "add", "-A"], cwd=repo, check=True, capture_output=True)
    subprocess.run(
        ["git", "commit", "-m", message],
        cwd=repo,
        check=True,
        capture_output=True,
    )
    return subprocess.check_output(
        ["git", "rev-parse", "HEAD"], cwd=repo, text=True
    ).strip()


def test_t0_schema_seed_and_materialize(tmp_path, monkeypatch):
    monkeypatch.setenv("AIPLAT_HOME", str(tmp_path))
    schema = load_team_harness_schema()
    assert schema.get("schema_version") == SCHEMA_VERSION
    assert "skills" in (schema.get("resources") or {})
    assert (schema.get("resources") or {})["skills"].get("locked") is True
    dst = materialize_team_harness_schema()
    assert dst.is_file()
    assert "schema_version" in dst.read_text(encoding="utf-8")


def test_t1a_pull_skips_without_repo(tmp_path, monkeypatch):
    monkeypatch.setenv("AIPLAT_HOME", str(tmp_path))
    result = pull_team_harness()
    assert result["ok"] is True and result.get("skipped") is True
    assert result.get("reason") == "no_repo"
    assert local_dir().is_dir()
    assert team_dir().is_dir()


def test_t1a_pull_clone_and_local_untouched(tmp_path, monkeypatch):
    monkeypatch.setenv("AIPLAT_HOME", str(tmp_path))
    remote = tmp_path / "remote.git"
    # bare-ish: normal repo used as clone source via path
    src = tmp_path / "src"
    sha = _git_init_with_commit(src)

    # local marker must survive pull
    loc = local_dir()
    loc.mkdir(parents=True, exist_ok=True)
    marker = loc / "keep.txt"
    marker.write_text("local-only\n", encoding="utf-8")

    configure_team_harness(str(src), branch="main")
    result = pull_team_harness(str(src), branch="main")
    assert result["ok"] is True, result
    assert result.get("commit")
    assert (team_dir() / "culture.md").is_file()
    assert (team_dir() / "skills" / "README.md").is_file()
    assert marker.read_text(encoding="utf-8") == "local-only\n"
    meta = read_meta()
    assert meta.get("commit") == result["commit"]
    assert sha  # created


def test_t1a_dirty_blocks_pull(tmp_path, monkeypatch):
    monkeypatch.setenv("AIPLAT_HOME", str(tmp_path))
    src = tmp_path / "src"
    _git_init_with_commit(src)
    assert pull_team_harness(str(src))["ok"] is True

    # dirty edit in team/
    edited = team_dir() / "culture.md"
    edited.write_text("LOCAL EDIT\n", encoding="utf-8")
    assert team_is_dirty() is True

    blocked = pull_team_harness(str(src))
    assert blocked["ok"] is False
    assert blocked.get("blocked") is True
    assert blocked.get("error") == "dirty_team_blocks_pull"
    assert "LOCAL EDIT" in edited.read_text(encoding="utf-8")


def test_t1a_ff_pull_updates_and_backup(tmp_path, monkeypatch):
    monkeypatch.setenv("AIPLAT_HOME", str(tmp_path))
    src = tmp_path / "src"
    _git_init_with_commit(src)
    assert pull_team_harness(str(src))["ok"] is True
    first = read_meta().get("commit")

    new_sha = _commit_file(src, "skills/new.md", "hello\n", "add skill")
    result = pull_team_harness(str(src))
    assert result["ok"] is True, result
    assert result.get("commit") == new_sha
    assert result.get("commit") != first
    assert (team_dir() / "skills" / "new.md").is_file()
    assert result.get("backup")
    assert Path(result["backup"]).is_dir()


def test_t1a_dry_run_no_clone(tmp_path, monkeypatch):
    monkeypatch.setenv("AIPLAT_HOME", str(tmp_path))
    src = tmp_path / "src"
    _git_init_with_commit(src)
    result = pull_team_harness(str(src), dry_run=True)
    assert result["ok"] is True and result["dry_run"] is True
    assert not (team_dir() / "culture.md").exists()


def test_t1a_backup_restore(tmp_path, monkeypatch):
    monkeypatch.setenv("AIPLAT_HOME", str(tmp_path))
    src = tmp_path / "src"
    _git_init_with_commit(src)
    pull_team_harness(str(src))
    (team_dir() / "culture.md").write_text("v1\n", encoding="utf-8")
    # discard dirty for backup of clean? use reset then write via commit path
    subprocess.run(
        ["git", "checkout", "--", "culture.md"],
        cwd=team_dir(),
        check=True,
        capture_output=True,
    )
    bak = backup_team_tree(label="test")
    assert bak and bak.is_dir()
    (team_dir() / "culture.md").write_text("broken\n", encoding="utf-8")
    # make clean for restore test of content
    subprocess.run(
        ["git", "checkout", "--", "culture.md"],
        cwd=team_dir(),
        check=False,
        capture_output=True,
    )
    (team_dir() / "culture.md").write_text("broken\n", encoding="utf-8")
    restored = restore_team_backup(bak)
    assert restored["ok"] is True
    assert "We ship carefully" in (team_dir() / "culture.md").read_text(encoding="utf-8")
