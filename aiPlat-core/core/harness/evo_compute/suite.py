"""Phase 0 / G0 最小套件与门槛门。

覆盖：genome 登记、离线评估、Pareto 排名、状态机含 human_gate、基线诚实锁；
slice-2：三试点、预算/安全（未签字）、夹具回放、出口就绪诚实锁。
不宣称 E2 / L4 / 认证 / 生产写入。
"""
from __future__ import annotations

from typing import Any, Dict, Optional

from core.harness.evo_compute.baseline import (
    evaluate_closed_loop_baseline_gate,
    run_closed_loop_baseline_suite,
)
from core.harness.evo_compute.budget import (
    check_budget,
    clear_budget_for_tests,
    get_budget_policy,
)
from core.harness.evo_compute.exit_readiness import evaluate_g0_exit_readiness
from core.harness.evo_compute.fitness import rank_candidates
from core.harness.evo_compute.genome_registry import (
    clear_registry_for_tests,
    get_genome,
    register_genome,
)
from core.harness.evo_compute.pilots import register_pilot_genomes
from core.harness.evo_compute.replay import replay_candidate_offline
from core.harness.evo_compute.safety import clear_safety_for_tests, get_safety_boundary
from core.harness.evo_compute.sandbox import evaluate_candidate_offline
from core.harness.evo_compute.status import advance_candidate_status, default_happy_path


def _pilot_genome() -> Dict[str, Any]:
    return {
        "genome_id": "routing.weights.g0_pilot",
        "target": "execution.routing",
        "representation": "continuous_vector",
        "fields": [
            {"name": "semantic_weight", "type": "float", "min": 0.0, "max": 1.0},
            {"name": "cost_weight", "type": "float", "min": 0.0, "max": 1.0},
        ],
        "constraints": ["sum(semantic_weight, cost_weight) == 1.0"],
        "owner": "platform-oncall",
        "evaluation_profile": "routing_replay_v1",
        "rollback": "versioned_config",
        "risk_class": "low",
        "mutable": True,
    }


def run_evo_compute_g0_suite() -> Dict[str, Any]:
    """G0 最小可用套件（含 slice-2 试点/预算/安全/回放）。"""
    clear_registry_for_tests()
    clear_budget_for_tests()
    clear_safety_for_tests()
    cases: list = []

    # 1. genome register
    reg = register_genome(_pilot_genome(), persist=False)
    cases.append({"id": "genome_register", "pass": bool(reg.get("ok"))})

    got = get_genome("routing.weights.g0_pilot")
    cases.append({"id": "genome_get", "pass": bool(got.get("ok"))})

    # 2. offline evaluate one candidate
    ev = evaluate_candidate_offline(
        genome_id="routing.weights.g0_pilot",
        candidate_id="g0-cand-1",
        genes={"semantic_weight": 0.6, "cost_weight": 0.4},
        fitness={
            "quality": 0.8,
            "cost_usd": 0.02,
            "latency_p95_ms": 120,
            "safety_violations": 0,
            "policy_violations": 0,
            "evidence_coverage": 0.9,
            "confidence": 0.85,
        },
        seed=42,
        persist_evidence=False,
    )
    cases.append(
        {
            "id": "sandbox_evaluate_ranked",
            "pass": bool(ev.get("ok"))
            and ev.get("status") == "ranked"
            and ev.get("production_write") is False,
        }
    )

    # 3. Pareto → ranked with hard constraint
    ranked = rank_candidates(
        [
            {
                "candidate_id": "a",
                "fitness": {
                    "quality": 0.9,
                    "cost_usd": 0.05,
                    "latency_p95_ms": 100,
                    "safety_violations": 0,
                    "policy_violations": 0,
                    "evidence_coverage": 0.8,
                    "confidence": 0.7,
                },
            },
            {
                "candidate_id": "b",
                "fitness": {
                    "quality": 0.7,
                    "cost_usd": 0.01,
                    "latency_p95_ms": 80,
                    "safety_violations": 0,
                    "policy_violations": 0,
                    "evidence_coverage": 0.95,
                    "confidence": 0.9,
                },
            },
            {
                "candidate_id": "bad",
                "fitness": {
                    "quality": 0.99,
                    "cost_usd": 0.0,
                    "latency_p95_ms": 10,
                    "safety_violations": 1,
                    "policy_violations": 0,
                    "evidence_coverage": 1.0,
                    "confidence": 1.0,
                },
            },
        ],
        seed=1,
    )
    rejected_ids = {r.get("candidate_id") for r in ranked.get("rejected") or []}
    cases.append(
        {
            "id": "pareto_rank_hard_constraint",
            "pass": bool(ranked.get("ok"))
            and "bad" in rejected_ids
            and len(ranked.get("ranked_candidates") or []) >= 1
            and ranked.get("ranking_profile_id") == "scalar_v1",
        }
    )

    # 4. status: approved requires human_gate
    bad_appr = advance_candidate_status(
        candidate_id="x",
        from_status="safety_passed",
        to_status="approved",
        actor="alice",
    )
    cases.append(
        {
            "id": "approved_requires_human_gate",
            "pass": bad_appr.get("ok") is False
            and bad_appr.get("error")
            in ("approved_requires_human_gate", "illegal_transition"),
        }
    )
    ok_appr = advance_candidate_status(
        candidate_id="x",
        from_status="human_gate",
        to_status="approved",
        actor="alice",
        evidence_ref="approval:1",
    )
    cases.append({"id": "human_gate_to_approved", "pass": bool(ok_appr.get("ok"))})

    abolished = advance_candidate_status(
        candidate_id="x",
        from_status="evaluating",
        to_status="evaluated",
        actor="alice",
    )
    cases.append({"id": "abolished_evaluated", "pass": abolished.get("ok") is False})

    happy = default_happy_path()
    cases.append(
        {
            "id": "default_happy_path_includes_human_gate",
            "pass": "human_gate" in happy and happy[0] == "draft" and happy[-1] == "production",
        }
    )

    # 5. baseline honesty
    base_suite = run_closed_loop_baseline_suite()
    base_gate = evaluate_closed_loop_baseline_gate(base_suite)
    cases.append({"id": "baseline_suite", "pass": bool(base_gate.get("ok"))})

    # 6. three pilot genomes (§9)
    pilots = register_pilot_genomes(persist=False)
    cases.append(
        {
            "id": "three_pilot_genomes",
            "pass": bool(pilots.get("ok")) and int(pilots.get("count") or 0) == 3,
        }
    )

    # 7. budget default unsigned + hard stop
    bud = get_budget_policy()
    over = check_budget({"candidates": 9999})
    cases.append(
        {
            "id": "budget_unsigned_and_hard_stop",
            "pass": bud.get("approved") is False
            and over.get("within_budget") is False
            and over.get("auto_stop") is True,
        }
    )

    # 8. safety default unsigned
    saf = get_safety_boundary()
    cases.append(
        {
            "id": "safety_unsigned_default",
            "pass": saf.get("signed") is False
            and "sandbox_no_production_write"
            in ((saf.get("boundary") or {}).get("rules") or []),
        }
    )

    # 9. fixture offline replay on first pilot
    rep = replay_candidate_offline(
        genome_id="routing.weights.v1",
        genes={"semantic_weight": 0.5, "cost_weight": 0.3, "latency_weight": 0.2},
        candidate_id="g0-replay-1",
        seed=7,
        persist_evidence=False,
    )
    cases.append(
        {
            "id": "fixture_replay_ranked",
            "pass": bool(rep.get("ok"))
            and rep.get("status") == "ranked"
            and rep.get("production_sample") is False
            and rep.get("production_write") is False,
        }
    )

    # 10. exit readiness honest: unsigned → phase0_complete false
    ready = evaluate_g0_exit_readiness(replay_ok=bool(rep.get("ok")), baseline_ok=True)
    cases.append(
        {
            "id": "exit_readiness_unsigned_incomplete",
            "pass": ready.get("phase0_complete") is False
            and ready.get("certified") is False
            and "budget_approved" in (ready.get("missing") or [])
            and "safety_signed" in (ready.get("missing") or []),
        }
    )

    passed = sum(1 for c in cases if c["pass"])
    return {
        "ok": passed == len(cases),
        "passed": passed,
        "total": len(cases),
        "cases": cases,
        "pilot_genome_id": "routing.weights.g0_pilot",
        "pilot_genome_ids": pilots.get("registered") or [],
        "g0_foundation": True,
        "certified": False,
        "e2_claimed": False,
        "phase0_complete": False,
        "note": "G0 slice-1+2 machinery; budget/safety human signoff still required for Phase 0 exit",
    }


def evaluate_evo_compute_g0_gate(suite: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """G0 门槛门：套件全过；certified/e2/phase0_complete 恒 false。

    Args:
        suite: ``run_evo_compute_g0_suite`` 回执。
    """
    s = suite if suite is not None else run_evo_compute_g0_suite()
    ok = bool(s.get("ok")) and int(s.get("passed") or 0) == int(s.get("total") or -1)
    return {
        "ok": ok,
        "passed": ok,
        "certified": False,
        "e2_claimed": False,
        "phase0_complete": False,
        "g0_foundation": True,
        "suite": s,
    }


def run_evo_compute_g0_slice2_suite() -> Dict[str, Any]:
    """G0 slice-2 套件别名：与 ``run_evo_compute_g0_suite`` 同路径（已含试点/预算/安全/回放）。"""
    out = run_evo_compute_g0_suite()
    out["slice"] = "g0-slice2"
    return out
