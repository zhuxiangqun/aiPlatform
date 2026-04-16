import asyncio
import pytest

from core.apps.skills.executor import SkillExecutor
from core.harness.interfaces import SkillResult


class _DummySkillConfig:
    def __init__(self):
        self.name = "dummy_skill"
        self.description = "Dummy skill for fork-mode tests."


class _DummySkill:
    def get_config(self):
        return _DummySkillConfig()


class _DummyRegistry:
    def get(self, name: str):
        if name == "dummy_skill":
            return _DummySkill()
        return None


def test_fork_mode_returns_clear_error_when_no_model(monkeypatch):
    # Force create_adapter to fail via invalid provider so fork mode must return a clear error.
    monkeypatch.setenv("LLM_PROVIDER", "unknown-provider")
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)

    executor = SkillExecutor(registry=_DummyRegistry())
    result = asyncio.run(
        executor.execute(
            "dummy_skill",
            params={"prompt": "hello"},
            context=None,
            mode="fork",
        )
    )

    assert isinstance(result, SkillResult)
    assert result.success is False
    assert result.error is not None
    assert "Fork mode requires a configured LLM adapter" in result.error
