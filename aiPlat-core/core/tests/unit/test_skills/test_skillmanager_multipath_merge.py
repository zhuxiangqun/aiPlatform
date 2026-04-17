import pytest


@pytest.mark.asyncio
async def test_skillmanager_merges_global_and_repo_and_repo_overrides(tmp_path, monkeypatch):
    """
    paths order (low -> high): global, repo
    repo should override global when same skill name exists.
    """
    global_dir = tmp_path / "global_skills"
    repo_dir = tmp_path / "repo_skills"
    (global_dir / "foo").mkdir(parents=True)
    (repo_dir / "foo").mkdir(parents=True)

    (global_dir / "foo" / "SKILL.md").write_text(
        "---\nname: foo\ndisplay_name: FooGlobal\ndescription: g\ncategory: general\nversion: 1.0.0\n---\n\n# SOP g\n",
        encoding="utf-8",
    )
    (repo_dir / "foo" / "SKILL.md").write_text(
        "---\nname: foo\ndisplay_name: FooRepo\ndescription: r\ncategory: general\nversion: 1.0.0\n---\n\n# SOP r\n",
        encoding="utf-8",
    )

    monkeypatch.setenv("AIPLAT_ENGINE_SKILLS_PATHS", f"{global_dir}:{repo_dir}")

    from core.management.skill_manager import SkillManager

    mgr = SkillManager(seed=False, scope="engine")
    s = await mgr.get_skill("foo")
    assert s is not None
    # repo overrides
    assert s.name == "FooRepo"
    assert s.description == "r"
    # ensure filesystem points to repo
    assert str(repo_dir) in str((s.metadata or {}).get("filesystem", {}).get("source", ""))
