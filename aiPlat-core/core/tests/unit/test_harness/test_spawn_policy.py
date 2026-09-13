"""Phase B W3: spawn_policy + factory allow_dynamic_spawn=False."""
from __future__ import annotations

from core.harness.coordination.spawn_policy import (
    disable_dynamic_spawn,
    is_dynamic_spawn_disabled,
    should_skip_dynamic_spawn,
    stage_allows_dynamic_spawn,
)
from core.harness.execution.factory_profile import (
    FACTORY_PROFILE_STANDARD,
    apply_factory_profile_to_stages,
)


def test_contextvar_disable():
    assert is_dynamic_spawn_disabled() is False
    with disable_dynamic_spawn(True):
        assert is_dynamic_spawn_disabled() is True
        assert should_skip_dynamic_spawn() is True
    assert is_dynamic_spawn_disabled() is False


def test_stage_field_disables():
    assert stage_allows_dynamic_spawn({"allow_dynamic_spawn": False}) is False
    assert should_skip_dynamic_spawn(stage={"allow_dynamic_spawn": False}) is True
    assert should_skip_dynamic_spawn(stage={"allow_dynamic_spawn": True}) is False


def test_state_flag_disables():
    assert should_skip_dynamic_spawn(state={"_disable_dynamic_spawn": True}) is True


def test_factory_profile_forces_no_spawn():
    stages = [
        {"agent_id": "pm_agent", "hitl": True, "allow_dynamic_spawn": True},
        {"agent_id": "qa_agent", "hitl": True, "allow_dynamic_spawn": True},
    ]
    out = apply_factory_profile_to_stages(stages, FACTORY_PROFILE_STANDARD)
    assert all(s.get("allow_dynamic_spawn") is False for s in out)
    assert all(should_skip_dynamic_spawn(stage=s) for s in out)
