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


def test_seed_purpose_ok_unlocks_profile_complete_claim_closed():
    # Real agent.capability seeds are purpose_ok (+ pack.meta frozen) after #675.
    out = evaluate_certification_readiness(profile_id=PROFILE_ID_BENCHMARK)
    assert out["profile_complete"] is True
    assert out["certification_eligible"] is False
    assert out["claim_eligible"] is False
    assert "cases_not_fully_reviewed_or_pack_not_frozen" not in out["blockers"]


def test_draft_cases_still_blocked_on_review():
    from core.apps.eval.service.capability_case_bank import build_agent_capability_cases

    draft_cases = []
    for row in build_agent_capability_cases():
        c = dict(row)
        c["review"] = {"status": "draft"}
        draft_cases.append(c)
    out = evaluate_certification_readiness(
        profile=agent_regression_profile(),
        cases=draft_cases,
        pack_kind="curated",
        pack_status="draft",
    )
    assert out["certification_eligible"] is False
    assert out["claim_eligible"] is False
    assert "cases_not_fully_reviewed_or_pack_not_frozen" in out["blockers"]
    assert out["profile_complete"] is False


def test_eval_p1_regression_status_facade():
    from core.api.core_facade import eval_p1_regression_status

    st = eval_p1_regression_status()
    assert st["ok"] is True
    assert st["profile_id"] == "agent.regression.v1"
    assert st["quota_inventory_ok"] is True
    assert st["profile_complete"] is True
    assert st["accuracy_claim"] is False
    assert st["claim_eligible"] is False
    assert st["certification_eligible"] is False
    assert st["case_count"] >= 57
    assert st["purpose_ok_or_better"] == st["case_count"]
    assert st["draft_pending"] == 0
    assert st["review_status_counts"].get("purpose_ok", 0) == st["case_count"]
    assert st["draft_by_capability"] == []
    assert st["review_links"]["case_packs_tab"] == "/eval?tab=case-packs"
    assert st["review_links"]["case_editor_tab"] == "/eval?tab=case-editor"
    assert st["blockers"] == []


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
