"""P4 smoke/benchmark profiles, holdout compile, judge calibration gate."""
from __future__ import annotations

from core.apps.eval.service.capability_case_bank import (
    PROFILE_ID_BENCHMARK,
    PROFILE_ID_SMOKE,
    agent_benchmark_profile,
    agent_smoke_profile,
    list_suite_profiles,
)
from core.apps.eval.service.capability_p4_gate import (
    benchmark_readiness_report,
    evaluate_judge_calibration_gate,
    open_capability_judge_calibration,
)
from core.apps.eval.service.suite_profile_compile import compile_plan_from_suite_profile


def test_list_suite_profiles_has_three():
    profiles = list_suite_profiles()
    ids = {p["profile_id"] for p in profiles}
    assert PROFILE_ID_SMOKE in ids
    assert "agent.regression.v1" in ids
    assert PROFILE_ID_BENCHMARK in ids
    for p in profiles:
        assert p["claim_eligible"] is False


def test_compile_smoke_manifest_size():
    plan = compile_plan_from_suite_profile(profile=agent_smoke_profile())
    assert plan["ok"] is True
    assert plan["profile_id"] == PROFILE_ID_SMOKE
    assert len(plan["sample_manifest"]) == 8
    assert plan["claim_eligible"] is False
    assert "smoke" in plan["purpose"]


def test_compile_benchmark_holdout_excludes_from_manifest():
    plan = compile_plan_from_suite_profile(profile_id=PROFILE_ID_BENCHMARK)
    assert plan["ok"] is True
    hold = plan["selection"]["holdout"]
    assert hold["enabled"] is True
    assert hold["n_holdout"] >= 1
    assert len(plan["sample_manifest"]) == hold["n_eval"]
    assert len(plan["holdout_manifest"]) == hold["n_holdout"]
    manifest_ids = {m["case_id"] for m in plan["sample_manifest"]}
    hold_ids = set(hold["holdout_case_ids"])
    assert manifest_ids.isdisjoint(hold_ids)
    assert plan["accuracy_claim"] is False


def test_judge_gate_always_report_only_even_when_agreement_high():
    gate = evaluate_judge_calibration_gate(
        ratings=[
            {"case_id": "a", "score": 1, "rater": "r1"},
            {"case_id": "a", "score": 1, "rater": "r2"},
            {"case_id": "b", "score": 0, "rater": "r1"},
            {"case_id": "b", "score": 0, "rater": "r2"},
        ],
        threshold=0.8,
    )
    assert gate["meets_engineering_bar"] is True
    assert gate["report_only"] is True
    assert gate["claim_eligible"] is False
    assert gate["accuracy_claim"] is False


def test_judge_gate_below_threshold():
    gate = evaluate_judge_calibration_gate(
        ratings=[
            {"case_id": "a", "score": 1, "rater": "r1"},
            {"case_id": "a", "score": 0, "rater": "r2"},
        ],
        threshold=0.8,
    )
    assert gate["meets_engineering_bar"] is False
    assert gate["report_only"] is True


def test_benchmark_readiness_meets_quotas(tmp_path, monkeypatch):
    monkeypatch.setenv("AIPLAT_HOME", str(tmp_path))
    out = benchmark_readiness_report(min_per_capability=8, compile_plan=True)
    assert out["ok"] is True
    assert out["ready_for_benchmark_quotas"] is True
    assert out["coverage"]["n_gaps"] == 0
    assert out["plan"]["selection"]["holdout"]["enabled"] is True
    assert out["plan"]["ok"] is True
    assert len(out["plan"]["sample_manifest"]) >= 1
    assert out["claim_eligible"] is False


def test_open_capability_judge_calibration(tmp_path, monkeypatch):
    monkeypatch.setenv("AIPLAT_HOME", str(tmp_path))
    out = open_capability_judge_calibration(workspace_id="ws-p4", sample_n=4)
    assert out["ok"] is True
    assert out["ticket_id"]
    assert len(out["sample_case_ids"]) == 4
    assert out["gate"]["report_only"] is True
    assert out["claim_eligible"] is False


def test_benchmark_profile_holdout_shape():
    p = agent_benchmark_profile()
    assert p["holdout"]["enabled"] is True
    assert 0 < float(p["holdout"]["ratio"]) <= 0.5
    assert p["on_insufficient"] == "error"
