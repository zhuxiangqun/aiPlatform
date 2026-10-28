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
    # Stub both purpose→model and adapter creation: CI without GPU/RAM can raise
    # from best_model_for_purpose before create_selected_adapter is reached.
    def _boom(*_args, **_kwargs):
        raise RuntimeError("no adapter in test")

    monkeypatch.setattr(
        "core.apps.skills.executor.best_model_for_purpose",
        _boom,
    )
    monkeypatch.setattr(
        "core.harness.utils.model_injection.create_selected_adapter",
        _boom,
    )

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
