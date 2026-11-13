"""G2b L5 gap disclosure — accuracy_claim / authorize stay false."""
from __future__ import annotations

from core.apps.eval.service.claims_gate import evaluate_l5_claims_gate
from core.apps.eval.service.g2b import g2b_l5_gap_disclosure


def test_g2b_l5_gap_disclosure_locked():
    out = g2b_l5_gap_disclosure(tenant_id="eval-v1")
    assert out["schema"] == "eval.g2b_l5_gap.v1"
    assert out["ok"] is True
    assert out["accuracy_claim"] is False
    assert out["explicit_authorize"] is False
    assert out["claims_gate"]["accuracy_claim"] is False
    assert isinstance(out.get("gaps"), list)
    assert out["wilson_lower_threshold"] == 0.70
    assert out["l5_default_min_sample_n"] == 100
    unlock = out.get("claim_unlock") or {}
    assert unlock.get("schema") == "eval.g2b.claim_unlock_checklist.v0"
    assert unlock.get("accuracy_claim") is False
    assert unlock.get("g2b_scoped_ready") is False
    assert "owner_accept_accuracy_claim" in (unlock.get("g2b_scoped_blockers") or [])
    assert unlock.get("gates", {}).get("section4_pass_rate_met") is True
    assert unlock.get("gates", {}).get("section4_wilson_lo_met") is True
    assert out.get("distance_summary") == "awaiting_owner_accept_attestation"


def test_claims_gate_default_authorize_false():
    r = evaluate_l5_claims_gate(
        {
            "object_type": "agent",
            "object_id": "g2b_pack",
            "object_version": "v0",
            "runtime_tier": "workspace_execute",
            "plan_id": "g2b",
            "set_ids": ["g2b"],
            "oracle_types": ["human_adjudicated"],
            "dimensions": ["task_result"],
            "sample_n": 100,
            "has_run_evidence": True,
            "untested_applicable_n": 0,
            "runtime_claim": True,
            "fixture_only": False,
            "human_review": True,
            "min_sample_n": 100,
        },
        explicit_authorize=False,
    )
    assert r["accuracy_claim"] is False


def test_eval_g2b_l5_gap_facade():
    from core.api.core_facade import eval_g2b_l5_gap_disclosure

    st = eval_g2b_l5_gap_disclosure()
    assert st["accuracy_claim"] is False


def test_eval_g2b_claim_unlock_checklist_facade():
    from core.api.core_facade import eval_g2b_claim_unlock_checklist

    st = eval_g2b_claim_unlock_checklist()
    assert st["accuracy_claim"] is False
    assert st["g2b_scoped_ready"] is False
    assert "owner_accept_accuracy_claim" in st["g2b_scoped_blockers"]
    assert st.get("gates", {}).get("arena_send_ready") is True
    assert st.get("gates", {}).get("arena_qa_overall_pass") is False
    assert "QA_RESIGN_CHECKLIST" in str(st.get("qa_resign_checklist") or "")
