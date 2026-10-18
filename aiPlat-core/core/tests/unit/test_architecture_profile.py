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


def test_file_output_plan_execute_stays_on_react():
    from core.schemas_builder import (
        control_fuses_for_stage,
        file_stage_control_stack,
        stage_uses_react_loop,
    )

    chat = PipelineStageConfig(id="a", agent_id="x", agent_type="plan", uses_file_output=False)
    assert stage_uses_react_loop(chat) is False
    assert file_stage_control_stack(chat)["execute"] == "chat"

    code = PipelineStageConfig(
        id="be",
        agent_id="backend_developer",
        uses_file_output=True,
        architecture_profile="plan_execute",
    )
    assert stage_uses_react_loop(code, "plan") is True
    stack = file_stage_control_stack(code)
    assert stack == {
        "schedule": "pipeline+plan_execute",
        "execute": "react",
        "quality": "external",
    }
    fuses = control_fuses_for_stage(code, max_steps=12)
    assert fuses["fuses"]["execute_max_steps"] == 12
    assert fuses["fuses"]["quality_soft_veto_limit"] == 2
    assert fuses["fuses"]["schedule_upgrade_policy"] == "signals"


def test_code_split_file_stages_use_external_quality():
    from pathlib import Path
    import yaml

    from core.schemas_builder import file_stage_control_stack

    p = Path(__file__).resolve().parents[3] / "core/workspace_seeds/teams/code_split.yaml"
    data = yaml.safe_load(p.read_text(encoding="utf-8"))
    seen = 0
    for row in data["stages"]:
        if not row.get("uses_file_output"):
            continue
        kwargs = {k: v for k, v in row.items() if k in PipelineStageConfig.model_fields}
        kwargs["id"] = kwargs.get("id") or str(row.get("agent_id") or "stage")
        stack = file_stage_control_stack(PipelineStageConfig(**kwargs))
        assert stack["execute"] == "react"
        assert stack["quality"] == "external"
        seen += 1
    assert seen == 3


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
