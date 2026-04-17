import pytest
import yaml


def _read_frontmatter(path):
    raw = path.read_text(encoding="utf-8")
    assert raw.startswith("---")
    # naive split
    parts = raw.split("---", 2)
    # parts: ["", "\n<yaml>\n", "\n<body>"]
    fm = yaml.safe_load(parts[1]) if len(parts) > 1 else {}
    body = parts[2] if len(parts) > 2 else ""
    return fm or {}, body


@pytest.mark.asyncio
async def test_update_skill_writes_back_skill_md_and_preserves_body(tmp_path, monkeypatch):
    base = tmp_path / "skills"
    monkeypatch.setenv("AIPLAT_WORKSPACE_SKILLS_PATH", str(base))

    from core.management.skill_manager import SkillManager

    mgr = SkillManager(seed=False, scope="workspace")
    created = await mgr.create_skill(
        name="My Skill",
        skill_type="general",
        description="v1 desc",
        input_schema={"a": {"type": "string"}},
        output_schema={"b": {"type": "string"}},
        metadata={"trigger_conditions": ["my skill"]},
    )

    skill_dir = base / created.id
    skill_md = skill_dir / "SKILL.md"
    fm1, body1 = _read_frontmatter(skill_md)
    assert fm1["description"] == "v1 desc"
    assert "工作流程" in body1 or "# My Skill" in body1

    updated = await mgr.update_skill(
        created.id,
        description="v2 desc",
        input_schema={"file": {"type": "string", "required": True}},
        metadata={"trigger_conditions": ["my skill", "新触发词"], "execution_mode": "fork"},
    )
    assert updated is not None

    fm2, body2 = _read_frontmatter(skill_md)
    assert fm2["description"] == "v2 desc"
    assert fm2["execution_mode"] == "fork"
    assert "新触发词" in (fm2.get("trigger_conditions") or [])
    assert "file" in (fm2.get("input_schema") or {})
    # body preserved (at least starts the same)
    assert body2.strip().startswith(body1.strip().splitlines()[0])
