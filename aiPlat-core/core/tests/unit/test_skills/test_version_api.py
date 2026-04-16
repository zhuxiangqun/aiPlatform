import asyncio
import importlib.util
from pathlib import Path


def _load_server_module():
    core_dir = Path(__file__).resolve().parents[3]  # .../aiPlat-core/core
    module_path = core_dir / "server.py"
    spec = importlib.util.spec_from_file_location("core_server_module", module_path)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(module)
    return module


def test_get_skill_version_returns_real_config(monkeypatch):
    server = _load_server_module()

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

    monkeypatch.setattr(server, "get_skill_registry", lambda: _DummyRegistry())

    out = asyncio.run(server.get_skill_version("s1", "v1"))
    assert out["version"] == "v1"
    assert isinstance(out["config"], dict)
    assert out["config"]["name"] == "s1"
    assert out["config"]["timeout"] == 123
    assert out["config"]["metadata"]["k"] == "v"

