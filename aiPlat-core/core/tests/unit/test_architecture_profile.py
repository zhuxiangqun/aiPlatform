"""W2/B1: architecture_profile + upgrade_policy (config-driven, no agent_id forks)."""
from __future__ import annotations

from core.schemas_builder import (
    PipelineStageConfig,
    apply_architecture_profile,
    resolve_upgrade_agent_type,
)


def test_unset_profile_keeps_llm_defaults():
    s = PipelineStageConfig(id="a", agent_id="x")
    assert s.architecture_profile == ""
    assert s.execution_backend == "llm"
    assert s.agent_type == "react"
    assert s.upgrade_policy == "signals"


def test_plan_execute_profile_overrides_backend():
    s = PipelineStageConfig(
        id="a",
        agent_id="x",
        execution_backend="llm",
        architecture_profile="plan_execute",
    )
    assert s.execution_backend == "agent"
    assert s.agent_type == "plan"


def test_reflect_and_react_tools_profiles():
    r = PipelineStageConfig(id="a", agent_id="x", architecture_profile="reflect_loop")
    assert r.execution_backend == "agent" and r.agent_type == "reflection"
    t = PipelineStageConfig(id="a", agent_id="x", architecture_profile="react_tools")
    assert t.execution_backend == "agent" and t.agent_type == "react"
    o = PipelineStageConfig(id="a", agent_id="x", architecture_profile="oneshot")
    assert o.execution_backend == "llm"


def test_unknown_profile_ignored():
    s = PipelineStageConfig(
        id="a", agent_id="x", architecture_profile="not_a_real_profile", execution_backend="llm"
    )
    assert s.execution_backend == "llm"
    assert s.agent_type == "react"


def test_upgrade_policy_off_skips_plan():
    s = PipelineStageConfig(id="a", agent_id="x", upgrade_policy="off")
    got = resolve_upgrade_agent_type(
        s,
        {"iteration": 1, "description": "x" * 800, "issues": ["boom"]},
    )
    assert got == "react"


def test_upgrade_policy_signals_large_task_to_plan():
    s = PipelineStageConfig(id="a", agent_id="x")
    got = resolve_upgrade_agent_type(s, {"iteration": 1, "description": "x" * 600})
    assert got == "plan"


def test_upgrade_policy_aggressive_retries_to_plan_without_errors():
    s = PipelineStageConfig(id="a", agent_id="x", upgrade_policy="aggressive")
    got = resolve_upgrade_agent_type(s, {"iteration": 2, "description": "short"})
    assert got == "plan"


def test_plan_execute_stage_not_re_upgraded():
    s = apply_architecture_profile(
        PipelineStageConfig(id="a", agent_id="x", architecture_profile="plan_execute")
    )
    got = resolve_upgrade_agent_type(s, {"iteration": 1, "description": "x" * 800, "issues": ["e"]})
    assert got == "plan"


def test_code_split_backend_pilot_yaml():
    from pathlib import Path
    import yaml

    p = Path(__file__).resolve().parents[3] / "core/workspace_seeds/teams/code_split.yaml"
    data = yaml.safe_load(p.read_text(encoding="utf-8"))
    be = next(s for s in data["stages"] if s.get("code_target") == "backend")
    assert be["architecture_profile"] == "plan_execute"
    kwargs = {k: v for k, v in be.items() if k in PipelineStageConfig.model_fields}
    kwargs["id"] = kwargs.get("id") or "backend_pilot"
    stage = PipelineStageConfig(**kwargs)
    assert stage.execution_backend == "agent"
    assert stage.agent_type == "plan"
    assert stage.upgrade_policy == "signals"
