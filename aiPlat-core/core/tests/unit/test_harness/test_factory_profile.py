"""F2a: factory_profile HITL demotion."""
from __future__ import annotations

from core.harness.execution.factory_profile import (
    FACTORY_PROFILE_DEMO,
    FACTORY_PROFILE_STANDARD,
    apply_factory_profile_to_stages,
    normalize_factory_profile,
)


def test_normalize_aliases():
    assert normalize_factory_profile("minimal") == FACTORY_PROFILE_DEMO
    assert normalize_factory_profile("DEMO") == FACTORY_PROFILE_DEMO
    assert normalize_factory_profile("nope") == FACTORY_PROFILE_STANDARD


def test_demo_keeps_qa_hitl_only():
    stages = [
        {"agent_id": "pm_agent", "hitl": True, "hitl_phase": "review"},
        {"agent_id": "architect_agent", "hitl": True, "hitl_phase": "review"},
        {"agent_id": "qa_agent", "hitl": True, "hitl_phase": "review"},
    ]
    out = apply_factory_profile_to_stages(stages, FACTORY_PROFILE_DEMO)
    assert out[0]["hitl"] is False
    assert out[1]["hitl"] is False
    assert out[2]["hitl"] is True
    assert out[2]["hitl_phase"] == "review"


def test_standard_preserves_hitl():
    stages = [
        {"agent_id": "pm_agent", "hitl": True},
        {"agent_id": "qa_agent", "hitl": True},
    ]
    out = apply_factory_profile_to_stages(stages, FACTORY_PROFILE_STANDARD)
    assert out[0]["hitl"] is True
    assert out[1]["hitl"] is True
