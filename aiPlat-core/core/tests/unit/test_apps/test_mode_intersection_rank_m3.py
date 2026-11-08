"""M3 intersection rank — Wilson/Pareto/gate; rank_claim never auto."""
from __future__ import annotations

import pytest

from core.apps.eval.service.mode_intersection_rank import (
    ModeIntersectionRankError,
    build_mode_intersection_rank,
    dominance_relation,
    evaluate_rank_gate,
    list_rank_eligible_cases,
    load_intersection_cases,
    pareto_frontier,
    verify_intersection_case_hashes,
    wilson_score_ci,
)


def test_wilson_ci_bounds():
    lo, hi = wilson_score_ci(23, 30)
    assert lo is not None and hi is not None
    assert 0.0 <= lo <= hi <= 1.0


def test_dominance_dominates_and_undetermined():
    # Non-overlap: A clearly above B
    assert dominance_relation(0.9, 0.99, 0.1, 0.2) == "dominates"
    assert dominance_relation(0.1, 0.2, 0.9, 0.99) == "dominated"
    assert dominance_relation(0.4, 0.7, 0.5, 0.8) == "undetermined"


def test_pareto_no_single_winner():
    vectors = {
        "plan_execute": {"task_completion": 0.9, "safety": 0.5},
        "conversational": {"task_completion": 0.5, "safety": 0.9},
    }
    pf = pareto_frontier(vectors)
    assert set(pf["frontier"]) == {"plan_execute", "conversational"}
    assert pf["single_winner"] is None


def test_list_eligible_a1_passed():
    eligible = list_rank_eligible_cases()
    assert len(eligible) >= 2
    assert all(c.get("capability_id") == "task_completion" for c in eligible)
    assert all(c.get("parity_status") == "passed" for c in eligible)
    assert all(c.get("rank_eligible") is True for c in eligible)
    # A12 never eligible via blocked_trace_parity
    assert all(c.get("capability_id") != "observability" for c in eligible)


def test_load_intersection_cases_hash_ok():
    cases = load_intersection_cases()
    assert len(cases) >= 3
    for c in cases:
        assert verify_intersection_case_hashes(c) == []


def test_load_intersection_cases_hash_mismatch():
    cases = load_intersection_cases(verify_hashes=False)
    bad = dict(cases[0])
    bad["prompt"] = "tampered prompt body"
    errs = verify_intersection_case_hashes(bad)
    assert "prompt_hash_mismatch" in errs


def test_gate_blocks_fixture_and_unsigned():
    cols = {
        "plan_execute": {
            "runtime_tier": "fixture",
            "model_fingerprint": "m1",
            "rank_fingerprint": "rf1",
            "intersection_manifest_hash": "im1",
            "by_case": {},
        },
        "conversational": {
            "runtime_tier": "fixture",
            "model_fingerprint": "m1",
            "rank_fingerprint": "rf1",
            "intersection_manifest_hash": "im1",
            "by_case": {},
        },
    }
    gate = evaluate_rank_gate(mode_columns=cols)
    assert gate["ok"] is False
    assert gate["rank_claim_allowed"] is False
    assert any(b.startswith("no_fixture_on_board") or b == "no_fixture_on_board" for b in gate["blockers"]) or any(
        c["id"] == "no_fixture_on_board" and not c["ok"] for c in gate["checks"]
    )


def test_build_rank_report_without_eligible():
    cols = {
        "plan_execute": {
            "runtime_tier": "workspace_execute",
            "model_fingerprint": "m1",
            "rank_fingerprint": "rf1",
            "intersection_manifest_hash": "im1",
            "subject": {"impl_mode": "plan_execute"},
            "by_case": {},
        },
        "conversational": {
            "runtime_tier": "workspace_execute",
            "model_fingerprint": "m1",
            "rank_fingerprint": "rf1",
            "intersection_manifest_hash": "im1",
            "subject": {"impl_mode": "conversational"},
            "by_case": {},
        },
    }
    out = build_mode_intersection_rank(cols)
    assert out["phase"] == "m3"
    assert out["rank_claim"] is False
    assert out["single_winner"] is None
    assert out["gate"]["ok"] is False  # no eligible cases + unsigned


def test_build_with_synthetic_eligible_parity():
    parity = {
        "schema": "eval.mode_intersection_parity.v1",
        "ci_method_default": "wilson",
        "cases": [
            {
                "case_id": "ix.a1.001",
                "capability_id": "task_completion",
                "prompt_hash": "sha256:p",
                "oracle_hash": "sha256:o",
                "env_contract_hash": "sha256:e",
                "rank_eligible": True,
                "parity_status": "passed",
            },
            {
                "case_id": "ix.a7.001",
                "capability_id": "safety",
                "prompt_hash": "sha256:p2",
                "oracle_hash": "sha256:o2",
                "env_contract_hash": "sha256:e",
                "rank_eligible": True,
                "parity_status": "passed",
            },
        ],
        "signoff": {
            "method_owner": "A",
            "engineering": "B",
            "independent_qa": "C",
            "status": "signed",
        },
    }
    # Enough n via by_capability for sample gate; by_case for completion
    def _col(mode: str, a1_ok: bool, a7_ok: bool) -> dict:
        return {
            "runtime_tier": "workspace_execute",
            "model_fingerprint": "model-x",
            "rank_fingerprint": "rf-shared",
            "intersection_manifest_hash": "im-shared",
            "subject": {"impl_mode": mode, "config_hash": "c1"},
            "by_case": {
                "ix.a1.001": {
                    "capability_id": "task_completion",
                    "ok": a1_ok,
                    "status": "ok" if a1_ok else "fail",
                },
                "ix.a7.001": {
                    "capability_id": "safety",
                    "ok": a7_ok,
                    "status": "ok" if a7_ok else "fail",
                },
            },
            # Inflate n for sample_size gate in unit test
            "by_capability": {
                "task_completion": {"successes": 5 if a1_ok else 1, "n": 5},
                "safety": {"successes": 5 if a7_ok else 1, "n": 5},
            },
        }

    cols = {
        "plan_execute": _col("plan_execute", True, False),
        "conversational": _col("conversational", False, True),
    }
    out = build_mode_intersection_rank(cols, parity=parity, min_n_per_capability=5)
    assert out["rank_claim"] is False  # builder never emits claim
    assert out["rank_claim_allowed"] is True  # gate+signoff unlock permission only
    assert out["gate"]["ok"] is True
    assert out["single_winner"] is None
    assert set(out["pareto"]["frontier"]) == {"plan_execute", "conversational"}


def test_force_rank_claim_forbidden():
    with pytest.raises(ModeIntersectionRankError, match="force_rank_claim_forbidden"):
        build_mode_intersection_rank({}, force_rank_claim=True)
