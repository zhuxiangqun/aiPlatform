"""T1c push / T3b sources / T6' TeamAI seed export tests."""
from __future__ import annotations

import json
import subprocess
from pathlib import Path

from core.harness.team_harness import (
    configure_team_harness,
    pull_team_harness,
    push_team_harness,
    render_mr_template,
    team_dir,
)
from core.harness.team_sources import (
    list_source_namespaces,
    merge_source_tree,
    namespaced_skill_candidates,
)
from core.harness.teamai_seed_export import export_teamai_seed


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


def test_t1c_mr_template_and_refuse_main():
    md = render_mr_template(branch="teamai/x", base="main", files=["learnings/a.json"])
    assert "teamai/x" in md and "learnings/a.json" in md
    # refuse push to base
    # (full push tested below with temp remotes)


def test_t1c_push_dry_run_and_branch(tmp_path, monkeypatch):
    monkeypatch.setenv("AIPLAT_HOME", str(tmp_path))
    remote = tmp_path / "remote"
    _git_init(remote)
    (remote / "learnings").mkdir()
    (remote / "learnings" / "keep.json").write_text("{}", encoding="utf-8")
    _commit_all(remote, "init")

    # bare remote for push
    bare = tmp_path / "remote.git"
    subprocess.run(
        ["git", "clone", "--bare", str(remote), str(bare)],
        check=True,
        capture_output=True,
    )

    configure_team_harness(str(bare), branch="main")
    assert pull_team_harness(str(bare), branch="main")["ok"] is True

    # stage a learning in team/
    learn = team_dir() / "learnings" / "contrib.json"
    learn.parent.mkdir(parents=True, exist_ok=True)
    learn.write_text(json.dumps({"id": "c1"}), encoding="utf-8")

    dry = push_team_harness(
        paths=["learnings/contrib.json"],
        branch="teamai/test-contrib",
        dry_run=True,
    )
    assert dry["ok"] is True and dry.get("would_push")
    assert "mr_template" in dry

    refused = push_team_harness(paths=["learnings/contrib.json"], branch="main")
    assert refused["ok"] is False and refused.get("error") == "refuse_push_to_base"

    pushed = push_team_harness(
        paths=["learnings/contrib.json"],
        branch="teamai/test-contrib",
        message="test contribute",
    )
    assert pushed["ok"] is True and pushed.get("pushed") is True
    assert pushed.get("commit")


def test_t3b_merge_never_overwrites_primary(tmp_path, monkeypatch):
    monkeypatch.setenv("AIPLAT_HOME", str(tmp_path))
    primary_skills = team_dir() / "skills"
    primary_skills.mkdir(parents=True)
    (primary_skills / "core").mkdir()
    (primary_skills / "core" / "SKILL.md").write_text("PRIMARY\n", encoding="utf-8")

    partner = tmp_path / "partner"
    (partner / "skills" / "extra").mkdir(parents=True)
    (partner / "skills" / "extra" / "SKILL.md").write_text("PARTNER\n", encoding="utf-8")
    # Attempt to ship a conflicting primary-looking skill
    (partner / "skills" / "core").mkdir(parents=True)
    (partner / "skills" / "core" / "SKILL.md").write_text("OVERWRITE?\n", encoding="utf-8")

    r = merge_source_tree(partner, namespace="partner")
    assert r["ok"] is True and r.get("primary_untouched") is True
    # primary unchanged
    assert (primary_skills / "core" / "SKILL.md").read_text(encoding="utf-8").startswith(
        "PRIMARY"
    )
    # namespaced copy exists
    assert "partner" in list_source_namespaces()
    ns_core = (
        team_dir() / "sources" / "partner" / "skills" / "core" / "SKILL.md"
    )
    assert ns_core.is_file()
    assert ns_core.read_text(encoding="utf-8").startswith("OVERWRITE?")
    cands = namespaced_skill_candidates("core")
    assert any("sources/partner" in c or "sources\\partner" in c for c in cands)


def test_t6_export_refuses_ide_and_writes_seed(tmp_path, monkeypatch):
    monkeypatch.setenv("AIPLAT_HOME", str(tmp_path))
    td = team_dir()
    (td / "skills" / "demo").mkdir(parents=True)
    (td / "skills" / "demo" / "SKILL.md").write_text("demo\n", encoding="utf-8")
    (td / "culture.md").write_text("We ship.\n", encoding="utf-8")

    bad = export_teamai_seed(str(tmp_path / ".cursor" / "team"))
    assert bad["ok"] is False and "refuse_ide" in bad.get("error", "")

    good = export_teamai_seed()
    assert good["ok"] is True and good.get("ide_write") is False
    dest = Path(good["dest"])
    assert (dest / "culture.md").is_file()
    assert (dest / "skills" / "demo" / "SKILL.md").is_file()
    assert (dest / ".teamai-manifest.json").is_file()
    assert (dest / "README.md").is_file()
