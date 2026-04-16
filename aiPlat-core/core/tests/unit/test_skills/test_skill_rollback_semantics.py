import asyncio

import pytest

from core.apps.skills.registry import SkillRegistry, _GenericSkill
from core.harness.interfaces import SkillConfig


def test_skill_registry_rollback_updates_instance_config():
    reg = SkillRegistry()

    cfg_v1 = SkillConfig(name="s1", description="desc-v1", metadata={"version": "v1"})
    skill = _GenericSkill(cfg_v1)
    reg.register(skill)

    cfg_v2 = SkillConfig(name="s1", description="desc-v2", metadata={"version": "v2"})
    # simulate a new version entry + make it active
    reg._add_version("s1", "v2", cfg_v2)  # type: ignore[attr-defined]
    for v in reg.get_versions("s1"):
        v.is_active = (v.version == "v2")
    # simulate "current instance uses v2"
    setattr(skill, "_config", cfg_v2)

    assert reg.get_active_version("s1") == "v2"
    assert reg.get("s1").get_config().description == "desc-v2"

    ok = reg.rollback_version("s1", "v1")
    assert ok is True
    assert reg.get_active_version("s1") == "v1"
    assert reg.get("s1").get_config().description == "desc-v1"


def test_rollback_endpoint_returns_active_version(monkeypatch):
    from core import server as server_mod

    reg = SkillRegistry()
    cfg_v1 = SkillConfig(name="s1", description="desc-v1", metadata={"version": "v1"})
    skill = _GenericSkill(cfg_v1)
    reg.register(skill)

    monkeypatch.setattr(server_mod, "get_skill_registry", lambda: reg)

    out = asyncio.run(server_mod.rollback_skill_version("s1", "v1"))
    assert out["status"] == "rolled_back"
    assert out["active_version"] == "v1"
    assert out["active_config"]["description"] == "desc-v1"

