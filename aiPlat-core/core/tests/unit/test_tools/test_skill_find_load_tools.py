import os

import anyio


def test_skill_find_filters_denied_and_supports_query(monkeypatch):
    from core.apps.skills.registry import _GenericSkill
    from core.harness.interfaces import SkillConfig
    from core.apps.skills import get_skill_registry
    from core.apps.tools.skill_tools import SkillFindTool

    reg = get_skill_registry()

    # Register two dummy skills
    cfg1 = SkillConfig(name="public-skill", description="hello world", metadata={"skill_kind": "rule", "version": "1.0.0"})
    cfg2 = SkillConfig(name="secret-skill", description="top secret", metadata={"skill_kind": "rule", "version": "1.0.0"})
    reg.register(_GenericSkill(cfg1))
    reg.register(_GenericSkill(cfg2))

    monkeypatch.setenv("AIPLAT_SKILL_PERMISSION_RULES", '{"secret-*":"deny","*":"allow"}')

    t = SkillFindTool()
    out = anyio.run(t.execute, {"query": "skill", "limit": 50})
    assert out.success is True
    items = (out.output or {}).get("items")
    assert isinstance(items, list)
    names = {i.get("name") for i in items}
    assert "public-skill" in names
    assert "secret-skill" not in names


def test_skill_load_returns_sop_and_blocks_denied(monkeypatch):
    from core.apps.skills.registry import _GenericSkill
    from core.harness.interfaces import SkillConfig
    from core.apps.skills import get_skill_registry
    from core.apps.tools.skill_tools import SkillLoadTool

    reg = get_skill_registry()
    cfg = SkillConfig(
        name="loadable-skill",
        description="desc",
        metadata={"skill_kind": "rule", "version": "1.0.0", "sop_markdown": "## SOP\nDo X"},
    )
    reg.register(_GenericSkill(cfg))

    monkeypatch.setenv("AIPLAT_SKILL_PERMISSION_RULES", '{"deny-*":"deny","*":"allow"}')

    t = SkillLoadTool()
    ok = anyio.run(t.execute, {"name": "loadable-skill"})
    assert ok.success is True
    assert "sop_markdown" in (ok.output or {})
    assert "Do X" in (ok.output or {}).get("sop_markdown", "")

    bad = anyio.run(t.execute, {"name": "deny-foo"})
    assert bad.success is False

