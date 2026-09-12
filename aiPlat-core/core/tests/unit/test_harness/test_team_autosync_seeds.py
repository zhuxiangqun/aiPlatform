"""T1b autosync + F-T1 factory seed materialize/rollback tests."""
from __future__ import annotations

import json
import subprocess
import time
from pathlib import Path

from core.harness.team_factory_seeds import (
    apply_team_factory_seeds,
    resolve_factory_sanitize_file,
    resolve_team_yaml_candidates,
    rollback_team_factory_seeds,
    runtime_sanitize_dir,
    runtime_teams_dir,
)
from core.harness.team_harness import (
    configure_team_harness,
    is_autosync_enabled,
    maybe_autosync_team_harness,
    pull_team_harness,
    team_dir,
)


def _git_init(repo: Path) -> None:
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
    subprocess.run(
        ["git", "checkout", "-b", "main"], cwd=repo, check=False, capture_output=True
    )


def _commit_all(repo: Path, message: str) -> None:
    subprocess.run(["git", "add", "-A"], cwd=repo, check=True, capture_output=True)
    subprocess.run(
        ["git", "commit", "-m", message], cwd=repo, check=True, capture_output=True
    )


def test_t1b_autosync_default_off(tmp_path, monkeypatch):
    monkeypatch.setenv("AIPLAT_HOME", str(tmp_path))
    monkeypatch.delenv("AIPLAT_TEAM_HARNESS_AUTOSYNC", raising=False)
    assert is_autosync_enabled() is False
    r = maybe_autosync_team_harness(background=False)
    assert r.get("skipped") is True
    assert r.get("reason") == "autosync_disabled"


def test_t1b_autosync_background_never_blocks(tmp_path, monkeypatch):
    monkeypatch.setenv("AIPLAT_HOME", str(tmp_path))
    monkeypatch.setenv("AIPLAT_TEAM_HARNESS_AUTOSYNC", "1")
    monkeypatch.setenv("AIPLAT_TEAM_HARNESS_AUTOSYNC_INTERVAL", "0")
    assert is_autosync_enabled() is True
    t0 = time.time()
    r = maybe_autosync_team_harness(background=True)
    assert time.time() - t0 < 0.5
    assert r.get("scheduled") is True
    # no repo → background worker degrades/skips; give it a moment
    time.sleep(0.2)


def test_t1b_autosync_pull_when_enabled(tmp_path, monkeypatch):
    monkeypatch.setenv("AIPLAT_HOME", str(tmp_path))
    monkeypatch.setenv("AIPLAT_TEAM_HARNESS_AUTOSYNC", "1")
    monkeypatch.setenv("AIPLAT_TEAM_HARNESS_AUTOSYNC_INTERVAL", "0")
    remote = tmp_path / "remote"
    _git_init(remote)
    (remote / "culture.md").write_text("ship\n", encoding="utf-8")
    (remote / "teams").mkdir()
    (remote / "teams" / "default.yaml").write_text(
        "team_name: Team From Git\nstages: []\n", encoding="utf-8"
    )
    _commit_all(remote, "init")
    configure_team_harness(str(remote), branch="main")
    r = maybe_autosync_team_harness(background=False, timeout_sec=60)
    assert r.get("ok") is True
    assert r.get("degraded") is not True or r.get("commit")
    assert (team_dir() / "culture.md").is_file()


def test_ft1_apply_and_rollback(tmp_path, monkeypatch):
    monkeypatch.setenv("AIPLAT_HOME", str(tmp_path))
    # Simulate pulled team/ content
    td = team_dir()
    (td / "teams").mkdir(parents=True)
    (td / "teams" / "hybrid.yaml").write_text(
        "team_name: From Team\nstages: []\n", encoding="utf-8"
    )
    (td / "factory_sanitize").mkdir(parents=True)
    (td / "factory_sanitize" / "frame_analyzer.SKILL.md").write_text(
        "TEAM_SEED {{app_name}}\n", encoding="utf-8"
    )

    # Pre-existing runtime file to prove rollback restores
    runtime_teams_dir().mkdir(parents=True)
    (runtime_teams_dir() / "hybrid.yaml").write_text(
        "team_name: Old\nstages: []\n", encoding="utf-8"
    )

    applied = apply_team_factory_seeds()
    assert applied["ok"] is True and not applied.get("skipped")
    assert "hybrid.yaml" in (applied["applied"]["teams"]["copied"])
    assert (runtime_teams_dir() / "hybrid.yaml").read_text(encoding="utf-8").startswith(
        "team_name: From Team"
    )
    assert resolve_factory_sanitize_file("frame_analyzer.SKILL.md") is not None
    assert "TEAM_SEED" in resolve_factory_sanitize_file(
        "frame_analyzer.SKILL.md"
    ).read_text(encoding="utf-8")

    # Candidates prefer team/ first
    cands = resolve_team_yaml_candidates("hybrid")
    assert str(td / "teams" / "hybrid.yaml") == cands[0]

    rolled = rollback_team_factory_seeds(applied["backup"])
    assert rolled["ok"] is True
    assert (runtime_teams_dir() / "hybrid.yaml").read_text(encoding="utf-8").startswith(
        "team_name: Old"
    )


def test_ft1_apply_skips_without_team_sources(tmp_path, monkeypatch):
    monkeypatch.setenv("AIPLAT_HOME", str(tmp_path))
    team_dir().mkdir(parents=True, exist_ok=True)
    r = apply_team_factory_seeds()
    assert r["ok"] is True and r.get("skipped") is True


def test_pull_applies_factory_seeds(tmp_path, monkeypatch):
    monkeypatch.setenv("AIPLAT_HOME", str(tmp_path))
    remote = tmp_path / "remote"
    _git_init(remote)
    (remote / "teams").mkdir()
    (remote / "teams" / "code.yaml").write_text(
        "team_name: Code From Pull\nstages: []\n", encoding="utf-8"
    )
    (remote / "factory_sanitize").mkdir()
    (remote / "factory_sanitize" / "video_downloader.SKILL.md").write_text(
        "pulled\n", encoding="utf-8"
    )
    _commit_all(remote, "seeds")
    result = pull_team_harness(str(remote), branch="main")
    assert result["ok"] is True
    seeds = result.get("factory_seeds") or {}
    assert seeds.get("ok") is True
    assert (runtime_teams_dir() / "code.yaml").is_file()
    assert (runtime_sanitize_dir() / "video_downloader.SKILL.md").read_text(
        encoding="utf-8"
    ).startswith("pulled")
