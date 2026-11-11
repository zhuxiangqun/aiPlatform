"""Subject-aware P4/P5 readiness (claim / cert closed)."""
from __future__ import annotations

from core.apps.eval.service.capability_cert_readiness import evaluate_certification_readiness
from core.apps.eval.service.capability_p4_gate import benchmark_readiness_report


def test_prompt_smoke_benchmark_readiness_subject_local():
    out = benchmark_readiness_report(profile_id="prompt.smoke.v1", compile_plan=True)
    assert out["ok"] is True
    assert out["subject_kind"] == "prompt"
    assert out["profile_id"] == "prompt.smoke.v1"
    assert out["ready_for_benchmark_quotas"] is True
    assert out["coverage"]["total_in_scope"] == 5
    assert out["coverage"]["n_gaps"] == 0
    assert out["claim_eligible"] is False
    assert out["accuracy_claim"] is False
    assert out["plan"]["subject_kind"] == "prompt"


def test_api_subject_kind_resolves_benchmark_first():
    out = benchmark_readiness_report(subject_kind="api", compile_plan=True)
    assert out["ok"] is True
    assert out["subject_kind"] == "api"
    assert out["profile_id"] == "api.benchmark.v1"
    assert out["coverage"]["total_in_scope"] == 3
    assert out["ready_for_benchmark_quotas"] is True
    assert out["claim_eligible"] is False


def test_prompt_cert_readiness_uses_prompt_scope_not_agent():
    out = evaluate_certification_readiness(
        profile_id="prompt.smoke.v1",
        pack_kind="frozen",
        pack_status="active",
    )
    assert out["ok"] is True
    assert out["subject_kind"] == "prompt"
    assert out["profile_complete"] is True
    assert out["certification_eligible"] is False
    assert out["claim_eligible"] is False
    assert out["coverage"]["total_in_scope"] == 5
    assert "efficiency" not in (out.get("unknown_capabilities") or [])


def test_agent_benchmark_default_unchanged():
    out = benchmark_readiness_report(compile_plan=True)
    assert out["subject_kind"] == "agent"
    assert out["profile_id"] == "agent.benchmark.v1"
    assert out["ready_for_benchmark_quotas"] is True
