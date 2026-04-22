import os
import subprocess
import time
from pathlib import Path

import anyio


def _run(cmd, cwd: Path):
    cp = subprocess.run(cmd, cwd=str(cwd), capture_output=True, text=True)
    assert cp.returncode == 0, (cp.stderr or cp.stdout)
    return (cp.stdout or "").strip()


def test_skill_installer_git_install_update_uninstall(monkeypatch, tmp_path):
    # Create a local git repo holding skills under "skills/<id>/SKILL.md"
    repo = tmp_path / "repo"
    repo.mkdir(parents=True, exist_ok=True)
    _run(["git", "init"], cwd=repo)
    _run(["git", "config", "user.email", "ci@example.com"], cwd=repo)
    _run(["git", "config", "user.name", "CI"], cwd=repo)

    skill_dir = repo / "skills" / "demo-skill"
    skill_dir.mkdir(parents=True, exist_ok=True)
    (skill_dir / "SKILL.md").write_text(
        """---
name: demo-skill
description: demo
version: 1.0.0
permissions: [filesystem_read]
---

## SOP
v1
""",
        encoding="utf-8",
    )
    _run(["git", "add", "."], cwd=repo)
    _run(["git", "commit", "-m", "v1"], cwd=repo)
    ref1 = _run(["git", "rev-parse", "HEAD"], cwd=repo)

    # Workspace skills install target
    ws = tmp_path / "workspace_skills"
    ws.mkdir(parents=True, exist_ok=True)
    monkeypatch.setenv("AIPLAT_WORKSPACE_SKILLS_PATH", str(ws))

    from core.management.skill_manager import SkillManager

    mgr = SkillManager(seed=False, scope="workspace", reserved_ids=set())
    res = anyio.run(
        lambda: mgr.installer_install(
            source_type="git",
            url=f"file://{repo}",
            ref=ref1,
            subdir="skills",
            allow_overwrite=False,
            metadata={"test": True},
        )
    )
    assert "demo-skill" in (res.get("installed") or [])
    assert (ws / "demo-skill" / "SKILL.md").exists()
    assert (ws / "demo-skill" / "SKILL.manifest.json").exists()

    # Update repo to v2 and update installed skill
    (skill_dir / "SKILL.md").write_text(
        """---
name: demo-skill
description: demo
version: 1.0.1
permissions: [filesystem_read]
---

## SOP
v2
""",
        encoding="utf-8",
    )
    _run(["git", "add", "."], cwd=repo)
    _run(["git", "commit", "-m", "v2"], cwd=repo)
    ref2 = _run(["git", "rev-parse", "HEAD"], cwd=repo)

    res2 = anyio.run(lambda: mgr.installer_update(skill_id="demo-skill", ref=ref2))
    assert "demo-skill" in (res2.get("installed") or [])
    content = (ws / "demo-skill" / "SKILL.md").read_text(encoding="utf-8")
    assert "v2" in content

    # Uninstall
    res3 = anyio.run(lambda: mgr.installer_uninstall(skill_id="demo-skill", delete_files=True))
    assert res3.get("deleted") is True
    assert not (ws / "demo-skill").exists()


def test_skill_installer_git_host_allowlist(monkeypatch, tmp_path):
    # deny evil.com
    monkeypatch.setenv("AIPLAT_SKILL_INSTALL_GIT_ALLOWLIST_HOSTS", "github.com")
    from core.management.skill_installer import SkillInstaller

    inst = SkillInstaller(target_base_dir=tmp_path)
    try:
        inst.install_from_git(url="https://evil.com/x.git", ref="deadbeef", subdir=None)
        assert False, "expected failure"
    except ValueError as e:
        assert "git_url_not_allowed" in str(e)


def test_resolve_remote_head_sha_file_url(monkeypatch, tmp_path):
    # Build a local git repo and resolve HEAD via file://
    repo = tmp_path / "repo"
    repo.mkdir(parents=True, exist_ok=True)
    _run(["git", "init"], cwd=repo)
    _run(["git", "config", "user.email", "ci@example.com"], cwd=repo)
    _run(["git", "config", "user.name", "CI"], cwd=repo)
    (repo / "README.md").write_text("hi", encoding="utf-8")
    _run(["git", "add", "."], cwd=repo)
    _run(["git", "commit", "-m", "init"], cwd=repo)
    head = _run(["git", "rev-parse", "HEAD"], cwd=repo)

    from core.management.skill_installer import resolve_remote_head_sha

    sha = resolve_remote_head_sha(f"file://{repo}")
    assert sha == head


def test_skill_installer_plan_autodetect_subdir(monkeypatch, tmp_path):
    root = tmp_path / "bundle"
    sdir = root / ".opencode" / "skills" / "x-skill"
    sdir.mkdir(parents=True, exist_ok=True)
    (sdir / "SKILL.md").write_text(
        """---
name: x-skill
description: demo
version: 0.1.0
permissions: [filesystem_read]
---

## SOP
hello
""",
        encoding="utf-8",
    )

    monkeypatch.setenv("AIPLAT_WORKSPACE_SKILLS_PATH", str(tmp_path / "ws"))
    from core.management.skill_manager import SkillManager

    mgr = SkillManager(seed=False, scope="workspace", reserved_ids=set())
    plan = anyio.run(lambda: mgr.installer_plan(source_type="path", path=str(root), subdir=None, auto_detect_subdir=True))
    assert plan["detected_subdir"] == ".opencode/skills"
    assert isinstance(plan["skills"], list) and len(plan["skills"]) == 1
    assert plan["skills"][0]["skill_id"] == "x-skill"


def test_plan_id_canonicalization_roundtrip(monkeypatch):
    monkeypatch.setenv("AIPLAT_SKILL_INSTALL_PLAN_SECRET", "secret")
    from core.management.skill_install_plan_token import build_plan_token, canonical_plan_data, verify_plan_token

    data = canonical_plan_data(
        scope="workspace",
        source_type="git",
        url="https://github.com/a/b.git",
        ref="deadbeef",
        path=None,
        skill_id="x",
        subdir="skills",
        auto_detect_subdir=True,
        allow_overwrite=False,
        metadata={"k": "v"},
        detected_subdir="skills",
        planned_skills_digest="digest",
    )
    token, _ = build_plan_token(data=data, ttl_seconds=60)
    verify_plan_token(token=token, expected_data=data, now=time.time())
