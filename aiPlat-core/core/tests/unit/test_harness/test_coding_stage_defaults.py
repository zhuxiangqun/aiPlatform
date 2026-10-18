"""Coding closed-loop defaults for uses_file_output stages (config-driven)."""

from __future__ import annotations

import os

from core.schemas_builder import PipelineStageConfig, apply_coding_stage_defaults


def test_file_output_enables_sandbox_and_autoreview(monkeypatch):
    monkeypatch.setenv("AIPLAT_CODING_STAGE_SANDBOX", "true")
    monkeypatch.setenv("AIPLAT_CODING_STAGE_AUTOREVIEW", "true")
    stage = PipelineStageConfig(
        id="fe",
        agent_id="frontend_engineer",
        uses_file_output=True,
        sandbox=False,
        review_gate="quick",
    )
    assert stage.sandbox is True
    assert "autoreview" in (stage.required_skills or [])
    assert isinstance(stage.done_verify, dict) and stage.done_verify.get("enabled") is True
    assert stage.done_verify.get("require_testability") is True
    assert stage.done_verify.get("require_completion_standard") is True
    assert "## FILE:" in (stage.done_verify.get("require_substrings") or [])


def test_sandbox_mode_none_opts_out(monkeypatch):
    monkeypatch.setenv("AIPLAT_CODING_STAGE_SANDBOX", "true")
    stage = PipelineStageConfig(
        id="fe",
        agent_id="frontend_engineer",
        uses_file_output=True,
        sandbox=False,
        sandbox_mode="none",
    )
    assert stage.sandbox is False


def test_review_gate_none_skips_autoreview(monkeypatch):
    monkeypatch.setenv("AIPLAT_CODING_STAGE_AUTOREVIEW", "true")
    stage = PipelineStageConfig(
        id="fe",
        agent_id="frontend_engineer",
        uses_file_output=True,
        review_gate="none",
        required_skills=[],
    )
    assert "autoreview" not in (stage.required_skills or [])


def test_refactor_sop_enables_full_gate_set(monkeypatch):
    monkeypatch.delenv("AIPLAT_CODING_STAGE_REFACTOR_SOP", raising=False)
    stage = PipelineStageConfig(
        id="be",
        agent_id="backend_developer",
        uses_file_output=True,
        review_gate="",
        refactor_sop=True,
    )
    dv = stage.done_verify
    assert stage.tdd_enforce is True
    assert stage.review_gate == "quick"
    assert dv.get("require_tdd") is True
    assert dv.get("require_diagnosis") is True
    assert dv.get("require_refactor_plan") is True
    assert dv.get("require_dependency_map") is True
    assert dv.get("require_rollback_checkpoint") is True
    assert dv.get("require_rollback_command") is True
    assert dv.get("require_feature_flag") is True
    assert dv.get("require_review") is True


def test_refactor_sop_env_still_enables_full_gate_set(monkeypatch):
    monkeypatch.setenv("AIPLAT_CODING_STAGE_REFACTOR_SOP", "true")
    stage = PipelineStageConfig(
        id="be",
        agent_id="backend_developer",
        uses_file_output=True,
        review_gate="",
    )
    assert stage.done_verify.get("require_feature_flag") is True
    assert stage.done_verify.get("require_rollback_command") is True


def test_require_review_binds_autoreview_even_when_soft_autoreview_off(monkeypatch):
    """Hard Step 5 must bind autoreview so follow-up can dispatch."""
    monkeypatch.setenv("AIPLAT_CODING_STAGE_AUTOREVIEW", "false")
    monkeypatch.setenv("AIPLAT_CODING_STAGE_REQUIRE_REVIEW", "true")
    stage = PipelineStageConfig(
        id="be",
        agent_id="backend_developer",
        uses_file_output=True,
        review_gate="none",
        required_skills=["code_generation"],
    )
    assert stage.done_verify.get("require_review") is True
    assert stage.review_gate == "quick"
    assert "autoreview" in (stage.required_skills or [])


def test_require_review_ignores_keep_llm_and_upgrades_to_react(monkeypatch):
    """KEEP_LLM must not leave hard review on oneshot (schema hard-block)."""
    monkeypatch.setenv("AIPLAT_CODING_STAGE_REQUIRE_REVIEW", "true")
    monkeypatch.setenv("AIPLAT_CODING_STAGE_KEEP_LLM", "true")
    stage = PipelineStageConfig(
        id="be",
        agent_id="backend_developer",
        uses_file_output=True,
        architecture_profile="oneshot",
        execution_backend="llm",
        required_skills=[],
    )
    assert stage.done_verify.get("require_review") is True
    assert stage.architecture_profile == "react_tools"
    assert str(stage.execution_backend or "").lower() in ("agent", "react", "react_tools")
    assert "autoreview" in (stage.required_skills or [])


def test_pipeline_compiler_keeps_refactor_sop():
    from core.apps.agents.pipeline_compiler import PipelineCompiler

    stages = PipelineCompiler.compile(
        [
            {
                "id": "be",
                "order": 0,
                "agent_id": "backend_developer",
                "uses_file_output": True,
                "refactor_sop": True,
                "done_verify": {
                    "enabled": True,
                    "require_substrings": ["## FILE:"],
                },
            }
        ]
    )
    assert len(stages) == 1
    assert stages[0].refactor_sop is True
    assert stages[0].done_verify.get("require_feature_flag") is True
    assert stages[0].done_verify.get("require_tdd") is True


def test_refactor_sop_overlay_expands_without_pydantic_defaults():
    """StageRunner belt path: light done_verify + refactor_sop still opens SOP gates."""
    from core.harness.execution.done_verify import build_done_verify_config

    ov = {
        "enabled": True,
        "require_substrings": ["## FILE:"],
        "min_output_length": 10,
    }
    for k in (
        "require_tdd",
        "require_diagnosis",
        "require_refactor_plan",
        "require_dependency_map",
        "require_rollback_checkpoint",
        "require_rollback_command",
        "require_feature_flag",
        "require_review",
    ):
        ov.setdefault(k, True)
    cfg = build_done_verify_config(done_verify=ov, review_gate="quick")
    assert cfg.get("require_feature_flag") is True
    assert cfg.get("require_rollback_command") is True
    assert cfg.get("require_review") is True


def test_code_team_seed_programmer_has_refactor_sop():
    from pathlib import Path

    import yaml

    seed = Path(__file__).resolve().parents[4] / "core" / "workspace_seeds" / "teams" / "code.yaml"
    data = yaml.safe_load(seed.read_text(encoding="utf-8"))
    prog = next(s for s in data["stages"] if s.get("uses_file_output"))
    fields = PipelineStageConfig.model_fields
    kwargs = {k: v for k, v in prog.items() if k in fields}
    kwargs["id"] = kwargs.get("id") or str(prog.get("agent_id") or "stage")
    stage = PipelineStageConfig(**kwargs)
    assert stage.refactor_sop is True
    assert stage.done_verify.get("require_diagnosis") is True
    assert stage.done_verify.get("require_tdd") is True


def test_rollback_cmd_env_sets_require_rollback_command(monkeypatch):
    monkeypatch.setenv("AIPLAT_CODING_STAGE_ROLLBACK_CMD", "true")
    stage = PipelineStageConfig(
        id="be",
        agent_id="backend_developer",
        uses_file_output=True,
    )
    assert stage.done_verify.get("require_rollback_command") is True


def test_flag_env_sets_require_feature_flag(monkeypatch):
    monkeypatch.setenv("AIPLAT_CODING_STAGE_FLAG", "true")
    stage = PipelineStageConfig(
        id="be",
        agent_id="backend_developer",
        uses_file_output=True,
    )
    assert stage.done_verify.get("require_feature_flag") is True


def test_rollback_env_sets_require_rollback_checkpoint(monkeypatch):
    monkeypatch.setenv("AIPLAT_CODING_STAGE_ROLLBACK", "true")
    stage = PipelineStageConfig(
        id="be",
        agent_id="backend_developer",
        uses_file_output=True,
    )
    assert stage.done_verify.get("require_rollback_checkpoint") is True


def test_deps_env_sets_require_dependency_map(monkeypatch):
    monkeypatch.setenv("AIPLAT_CODING_STAGE_DEPS", "true")
    stage = PipelineStageConfig(
        id="be",
        agent_id="backend_developer",
        uses_file_output=True,
    )
    assert stage.done_verify.get("require_dependency_map") is True


def test_plan_env_sets_require_refactor_plan(monkeypatch):
    monkeypatch.setenv("AIPLAT_CODING_STAGE_PLAN", "true")
    stage = PipelineStageConfig(
        id="be",
        agent_id="backend_developer",
        uses_file_output=True,
    )
    assert stage.done_verify.get("require_refactor_plan") is True


def test_diagnosis_env_sets_require_diagnosis(monkeypatch):
    monkeypatch.setenv("AIPLAT_CODING_STAGE_DIAGNOSIS", "true")
    stage = PipelineStageConfig(
        id="be",
        agent_id="backend_developer",
        uses_file_output=True,
    )
    assert stage.done_verify.get("require_diagnosis") is True


def test_tdd_env_sets_require_tdd(monkeypatch):
    monkeypatch.setenv("AIPLAT_CODING_STAGE_TDD", "true")
    stage = PipelineStageConfig(
        id="be",
        agent_id="backend_developer",
        uses_file_output=True,
    )
    assert stage.tdd_enforce is True
    assert stage.done_verify.get("require_tdd") is True


def test_non_coding_unchanged():
    stage = PipelineStageConfig(
        id="pm",
        agent_id="pm_agent",
        uses_file_output=False,
        sandbox=False,
    )
    assert stage.sandbox is False
    assert "autoreview" not in (stage.required_skills or [])


def test_apply_helper_idempotent(monkeypatch):
    monkeypatch.setenv("AIPLAT_CODING_STAGE_SANDBOX", "true")
    stage = PipelineStageConfig(
        id="be",
        agent_id="backend_developer",
        uses_file_output=True,
        sandbox=True,
        required_skills=["autoreview"],
        done_verify={"enabled": True, "min_output_length": 40},
    )
    again = apply_coding_stage_defaults(stage)
    assert again.done_verify.get("min_output_length") == 40
    assert again.done_verify.get("require_testability") is True
    assert again.required_skills.count("autoreview") == 1


def test_factory_file_stages_declare_file_marker():
    """Seeded coding teams can start: ## FILE: is the checkable standard."""
    from pathlib import Path

    import yaml

    from core.harness.execution.done_verify import missing_completion_standard_reason
    from core.schemas_builder import PipelineStageConfig

    root = Path(__file__).resolve().parents[4] / "core" / "workspace_seeds" / "teams"
    for name in ("code.yaml", "code_split.yaml", "hybrid.yaml"):
        doc = yaml.safe_load((root / name).read_text(encoding="utf-8"))
        for row in doc.get("stages") or []:
            if not row.get("uses_file_output"):
                continue
            fields = PipelineStageConfig.model_fields
            kwargs = {k: v for k, v in row.items() if k in fields}
            kwargs["id"] = kwargs.get("id") or str(row.get("agent_id") or "stage")
            stage = PipelineStageConfig(**kwargs)
            assert missing_completion_standard_reason(stage) is None
            assert "## FILE:" in (stage.done_verify.get("require_substrings") or [])
