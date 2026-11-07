"""exam_runtime_tier annotations — contract eval-exam-runtime-tiers.md v1.3."""

from core.apps.eval.service.exam_runtime_tier import (
    VALID_TIERS,
    annotate_agent_exam_runtime,
    annotate_external_exam_runtime,
    annotate_generated_app_runtime,
    annotate_skill_eval_runtime,
    merge_runtime_fields,
)


def test_valid_tiers_include_core_skill_execute():
    assert "core_skill_execute" in VALID_TIERS
    assert "fixture" in VALID_TIERS


def test_agent_dry_is_fixture_no_claim():
    a = annotate_agent_exam_runtime(live=False)
    assert a["runtime_tier"] == "fixture"
    assert a["target_runtime"] == "workspace_execute"
    assert a["runtime_claim"] is False
    assert "fixture" in a["runtime_claim_reason"]


def test_agent_live_is_workspace_execute():
    a = annotate_agent_exam_runtime(live=True)
    assert a["runtime_tier"] == "workspace_execute"
    assert a["target_runtime"] == "workspace_execute"
    assert a["runtime_claim"] is True
    assert "eval_worker" in a["runtime_claim_reason"]


def test_external_dry_is_fixture_live_is_pull():
    d = annotate_external_exam_runtime(live=False)
    assert d["runtime_tier"] == "fixture"
    assert d["target_runtime"] == "external_pull"
    assert d["runtime_claim"] is False
    L = annotate_external_exam_runtime(live=True)
    assert L["runtime_tier"] == "external_pull"
    assert L["target_runtime"] == "external_pull"
    assert L["runtime_claim"] is True


def test_generated_app_separates_actual_tier_from_target_pi():
    r = annotate_generated_app_runtime(mode="runs_eval")
    assert r["runtime_tier"] == "fixture"
    assert r["target_runtime"] == "pi"
    assert r["runtime_claim"] is False
    o = annotate_generated_app_runtime(mode="pi_offline")
    assert o["runtime_tier"] == "fixture"
    assert o["target_runtime"] == "pi"
    assert o["runtime_claim"] is False
    assert "CLI" in o["runtime_claim_reason"] or "structural" in o["runtime_claim_reason"]
    L = annotate_generated_app_runtime(mode="pi_live")
    assert L["runtime_tier"] == "pi"
    assert L["target_runtime"] == "pi"
    assert L["runtime_claim"] is True


def test_skill_trigger_fixture_quality_core_skill_execute():
    t = annotate_skill_eval_runtime(eval_kind="trigger", mode="heuristic")
    assert t["runtime_tier"] == "fixture"
    assert t["target_runtime"] == "core_skill_execute"
    assert t["runtime_claim"] is False
    assert "routing" in t["runtime_claim_reason"]
    q = annotate_skill_eval_runtime(eval_kind="quality")
    assert q["runtime_tier"] == "core_skill_execute"
    assert q["target_runtime"] == "core_skill_execute"
    assert q["runtime_claim"] is True
    assert "skill_manager" in q["runtime_claim_reason"]
    assert q.get("execution_mode") == "skill_manager_quality"


def test_merge_keeps_accuracy_false_and_target_runtime():
    out = merge_runtime_fields(
        {"ok": True, "accuracy_claim": True},
        annotate_generated_app_runtime(mode="pi_offline"),
    )
    assert out["accuracy_claim"] is False
    assert out["runtime_tier"] == "fixture"
    assert out["target_runtime"] == "pi"
