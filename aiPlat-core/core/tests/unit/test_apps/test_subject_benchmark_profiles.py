"""Subject *.benchmark.v1 Suite Profiles — holdout + bank×8 quotas=5 (claim closed)."""
from __future__ import annotations

from core.apps.eval.service.capability_case_bank import list_suite_profiles
from core.apps.eval.service.capability_cert_readiness import evaluate_certification_readiness
from core.apps.eval.service.capability_p4_gate import benchmark_readiness_report
from core.apps.eval.service.subject_capability_promote import list_promotable_subject_kinds
from core.apps.eval.service.suite_profile_compile import compile_plan_from_suite_profile


def test_all_promotable_subjects_have_benchmark_profile():
    ids = {p["profile_id"] for p in list_suite_profiles()}
    for kind in list_promotable_subject_kinds():
        if kind == "agent":
            assert "agent.benchmark.v1" in ids
            continue
        assert f"{kind}.benchmark.v1" in ids, kind


def test_prompt_benchmark_compile_holdout_and_readiness():
    plan = compile_plan_from_suite_profile(profile_id="prompt.benchmark.v1")
    assert plan["ok"] is True
    assert plan["subject_kind"] == "prompt"
    hold = (plan.get("selection") or {}).get("holdout") or {}
    assert hold.get("enabled") is True
    assert int(hold.get("n_holdout") or 0) >= 1
    assert len(plan.get("sample_manifest") or []) == int(hold.get("n_eval") or 0)
    assert plan["claim_eligible"] is False

    ready = benchmark_readiness_report(subject_kind="prompt")
    assert ready["profile_id"] == "prompt.benchmark.v1"
    assert ready["subject_kind"] == "prompt"
    assert ready["ready_for_benchmark_quotas"] is True
    assert ready["claim_eligible"] is False


def test_api_benchmark_cert_readiness_frozen_complete_not_certifiable():
    out = evaluate_certification_readiness(
        profile_id="api.benchmark.v1",
        pack_kind="frozen",
        pack_status="active",
    )
    assert out["subject_kind"] == "api"
    assert out["profile_complete"] is True
    assert out["certification_eligible"] is False
    assert out["claim_eligible"] is False
    assert out["accuracy_claim"] is False
