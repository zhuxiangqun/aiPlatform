"""P5 pre-gate: certification readiness checklist (claim closed)."""
from __future__ import annotations

from core.apps.eval.service.capability_case_bank import (
    PROFILE_ID_BENCHMARK,
    PROFILE_ID_SMOKE,
    agent_regression_profile,
)
from core.apps.eval.service.capability_cert_readiness import (
    evaluate_certification_readiness,
)


def test_smoke_frozen_profile_complete_but_not_certifiable():
    out = evaluate_certification_readiness(
        profile_id=PROFILE_ID_SMOKE,
        pack_kind="frozen",
        pack_status="active",
    )
    assert out["ok"] is True
    assert out["profile_complete"] is True
    assert out["certification_eligible"] is False
    assert out["claim_eligible"] is False
    assert out["accuracy_claim"] is False
    assert out["blockers"] == []
    assert out["snapshot"]["manifest_hash"]
    assert out["snapshot"]["profile_id"] == PROFILE_ID_SMOKE


def test_benchmark_profile_complete_but_not_certifiable_when_frozen():
    out = evaluate_certification_readiness(
        profile_id=PROFILE_ID_BENCHMARK,
        pack_kind="frozen",
        pack_status="active",
    )
    assert out["profile_complete"] is True
    assert out["certification_eligible"] is False
    assert out["claim_eligible"] is False
    assert out["blockers"] == []


def test_benchmark_draft_bank_still_blocked_on_review():
    out = evaluate_certification_readiness(profile_id=PROFILE_ID_BENCHMARK)
    assert out["certification_eligible"] is False
    assert "cases_not_fully_reviewed_or_pack_not_frozen" in out["blockers"]


def test_regression_without_frozen_blocked_on_review():
    out = evaluate_certification_readiness(profile=agent_regression_profile())
    assert out["certification_eligible"] is False
    assert out["claim_eligible"] is False
    # seed bank review=status draft → needs pack frozen or purpose_ok
    assert "cases_not_fully_reviewed_or_pack_not_frozen" in out["blockers"]
    assert out["profile_complete"] is False


def test_eval_p1_regression_status_facade():
    from core.api.core_facade import eval_p1_regression_status

    st = eval_p1_regression_status()
    assert st["ok"] is True
    assert st["profile_id"] == "agent.regression.v1"
    assert st["quota_inventory_ok"] is True
    assert st["profile_complete"] is False
    assert st["accuracy_claim"] is False
    assert st["claim_eligible"] is False
    assert st["certification_eligible"] is False
    assert st["case_count"] >= 57
    assert st["review_status_counts"].get("draft", 0) >= 1
    assert st["draft_pending"] == st["review_status_counts"].get("draft", 0)
    assert st["draft_by_capability"]
    assert all("capability_id" in r and "draft_count" in r for r in st["draft_by_capability"])
    assert st["review_links"]["case_packs_tab"] == "/eval?tab=case-packs"
    assert st["review_links"]["case_editor_tab"] == "/eval?tab=case-editor"
    assert "cases_not_fully_reviewed_or_pack_not_frozen" in st["blockers"]
    assert "Promote" in st["next_action"]


def test_judge_bar_optional_does_not_block_profile_complete():
    out = evaluate_certification_readiness(
        profile_id=PROFILE_ID_SMOKE,
        pack_kind="frozen",
        pack_status="active",
        judge_agreement={"agreement": 0.5, "pairs": 2},
        judge_threshold=0.8,
    )
    assert out["profile_complete"] is True
    judge = next(c for c in out["checks"] if c["id"] == "judge_engineering_bar")
    assert judge["ok"] is False
    assert judge.get("required_for_profile_complete") is False


def test_certification_never_unlocks_even_with_perfect_agreement():
    out = evaluate_certification_readiness(
        profile_id=PROFILE_ID_SMOKE,
        pack_kind="frozen",
        pack_status="active",
        judge_agreement={"agreement": 1.0, "pairs": 10},
    )
    assert out["judge_gate"]["meets_engineering_bar"] is True
    assert out["certification_eligible"] is False
    assert out["claim_eligible"] is False
