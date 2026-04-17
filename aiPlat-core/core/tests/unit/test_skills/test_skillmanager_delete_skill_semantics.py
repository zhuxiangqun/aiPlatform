import pytest
import yaml


def _read_frontmatter(path):
    raw = path.read_text(encoding="utf-8")
    assert raw.startswith("---")
    parts = raw.split("---", 2)
    fm = yaml.safe_load(parts[1]) if len(parts) > 1 else {}
    body = parts[2] if len(parts) > 2 else ""
    return fm or {}, body


@pytest.mark.asyncio
async def test_delete_skill_soft_delete_keeps_directory_and_marks_deprecated(tmp_path, monkeypatch):
    base = tmp_path / "skills"
    monkeypatch.setenv("AIPLAT_WORKSPACE_SKILLS_PATH", str(base))

    from core.management.skill_manager import SkillManager

    mgr = SkillManager(seed=False, scope="workspace")
    s = await mgr.create_skill(
        name="To Delete",
        skill_type="general",
        description="x",
        input_schema={},
        output_schema={},
    )
    skill_dir = base / s.id
    skill_md = skill_dir / "SKILL.md"
    assert skill_md.exists()

    ok = await mgr.delete_skill(s.id)
    assert ok is True
    # directory and file remain
    assert skill_dir.exists()
    fm, _body = _read_frontmatter(skill_md)
    assert fm.get("status") == "deprecated"
    assert fm.get("deprecated_at")


@pytest.mark.asyncio
async def test_delete_skill_hard_delete_removes_directory(tmp_path, monkeypatch):
    base = tmp_path / "skills"
    monkeypatch.setenv("AIPLAT_WORKSPACE_SKILLS_PATH", str(base))

    from core.management.skill_manager import SkillManager

    mgr = SkillManager(seed=False, scope="workspace")
    s = await mgr.create_skill(
        name="To Hard Delete",
        skill_type="general",
        description="x",
        input_schema={},
        output_schema={},
    )
    skill_dir = base / s.id
    assert skill_dir.exists()

    ok = await mgr.delete_skill(s.id, delete_files=True)
    assert ok is True
    assert not skill_dir.exists()
