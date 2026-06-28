import asyncio


def test_get_skill_version_returns_real_config(monkeypatch):
    # Endpoint moved from core.server to the engine_skills router.
    import core.api.routers.engine_skills as engine_skills

    class _DummyRegistry:
        def get_version(self, skill_id: str, version: str):
            # SkillConfig is a dataclass in core.harness.interfaces.skill
            from core.harness.interfaces import SkillConfig

            return SkillConfig(
                name=skill_id,
                description="desc",
                input_schema={"type": "object"},
                output_schema={"type": "object"},
                timeout=123,
                metadata={"k": "v"},
            )

    monkeypatch.setattr(engine_skills, "get_skill_registry", lambda: _DummyRegistry())

    out = asyncio.run(engine_skills.get_skill_version("s1", "v1"))
    assert out["version"] == "v1"
    assert isinstance(out["config"], dict)
    assert out["config"]["name"] == "s1"
    assert out["config"]["timeout"] == 123
    assert out["config"]["metadata"]["k"] == "v"

