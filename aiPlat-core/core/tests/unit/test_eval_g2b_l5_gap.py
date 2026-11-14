"""G2b L5 gap disclosure — scheme A product vs scoped claim."""
from __future__ import annotations

from core.apps.eval.service.claims_gate import evaluate_l5_claims_gate
from core.apps.eval.service.g2b import g2b_l5_gap_disclosure


def test_g2b_l5_gap_disclosure_scoped_claim_accepted():
    out = g2b_l5_gap_disclosure(tenant_id="eval-v1")
    assert out["schema"] == "eval.g2b_l5_gap.v1"
    assert out["ok"] is True
    assert out["accuracy_claim"] is False
    assert out["scoped_accuracy_claim"] is True
    assert out["not_accuracy_certification"] is True
    assert out["explicit_authorize"] is True
    # Broader L5 claims_gate stays unauthorized (runtime_claim false path).
    assert out["claims_gate"]["accuracy_claim"] is False
    assert isinstance(out.get("gaps"), list)
    assert out["wilson_lower_threshold"] == 0.70
    assert out["l5_default_min_sample_n"] == 100
    unlock = out.get("claim_unlock") or {}
    assert unlock.get("schema") == "eval.g2b.claim_unlock_checklist.v0"
    assert unlock.get("accuracy_claim") is False
    assert unlock.get("scoped_accuracy_claim") is True
    assert unlock.get("g2b_scoped_ready") is True
    assert unlock.get("g2b_scoped_blockers") == []
    assert unlock.get("gates", {}).get("section4_pass_rate_met") is True
    assert unlock.get("gates", {}).get("section4_wilson_lo_met") is True
    assert unlock.get("gates", {}).get("owner_accept_accuracy_claim") is True
    assert unlock.get("gates", {}).get("arena_qa_overall_pass") is True
    assert "staging_evidence" in (unlock.get("broader_trust_blockers") or [])
    assert out.get("distance_summary") == "g2b_scoped_accuracy_claim_accepted"


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
    assert st["scoped_accuracy_claim"] is True


def test_eval_g2b_claim_unlock_checklist_facade():
    from core.api.core_facade import eval_g2b_claim_unlock_checklist

    st = eval_g2b_claim_unlock_checklist()
    assert st["accuracy_claim"] is False
    assert st["scoped_accuracy_claim"] is True
    assert st["g2b_scoped_ready"] is True
    assert st["g2b_scoped_blockers"] == []
    assert st.get("gates", {}).get("arena_send_ready") is True
    assert st.get("gates", {}).get("arena_qa_overall_pass") is True
    assert "QA_RESIGN_CHECKLIST" in str(st.get("qa_resign_checklist") or "")
