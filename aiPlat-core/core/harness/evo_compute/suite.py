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


def run_evo_compute_g1_suite() -> Dict[str, Any]:
    """G1 最小套件：DE/ES + holdout + 演练；``g1_complete`` 恒 false。"""
    from core.harness.evo_compute.drill import run_human_gate_canary_rollback_drill
    from core.harness.evo_compute.exit_readiness import evaluate_g1_exit_readiness
    from core.harness.evo_compute.holdout import compare_holdout
    from core.harness.evo_compute.orchestrator import run_de_es_offline
    from core.harness.evo_compute.pilots import register_pilot_genomes
    from core.harness.evo_compute.budget import clear_budget_for_tests, approve_budget
    from core.harness.evo_compute.genome_registry import clear_registry_for_tests
    from core.harness.evo_compute.safety import clear_safety_for_tests

    clear_registry_for_tests()
    clear_budget_for_tests()
    clear_safety_for_tests()
    cases: list = []

    pilots = register_pilot_genomes(persist=False)
    cases.append({"id": "pilots_ready", "pass": bool(pilots.get("ok"))})
    # 预算批准仅满足硬停检查上下文；不宣称生产授权
    approve_budget(actor="g1-suite", persist=False)

    de = run_de_es_offline(
        genome_id="routing.weights.v1",
        algorithm="de",
        population_size=6,
        generations=3,
        seed=42,
    )
    cases.append(
        {
            "id": "de_offline_ranked",
            "pass": bool(de.get("ok"))
            and float(de.get("lineage_completeness") or 0) >= 1.0
            and bool(de.get("reproducible_check"))
            # 0 是合法值，禁止用 ``or 1``（会把零回归误判为失败）
            and int(de.get("hard_constraint_regressions", 1)) == 0
            and de.get("production_write") is False,
        }
    )

    es = run_de_es_offline(
        genome_id="routing.weights.v1",
        algorithm="es",
        population_size=6,
        generations=2,
        seed=7,
    )
    cases.append({"id": "es_offline_ok", "pass": bool(es.get("ok"))})

    best = (de.get("ranked_candidates") or [{}])[0]
    baseline = {"semantic_weight": 0.33, "cost_weight": 0.33, "latency_weight": 0.34}
    hold = compare_holdout(
        genome_id="routing.weights.v1",
        baseline_genes=baseline,
        challenger_genes=dict(best.get("genes") or baseline),
        n_batches=4,
        seed=1,
    )
    cases.append(
        {
            "id": "holdout_confirm",
            "pass": bool(hold.get("ok")) and hold.get("certified") is False,
        }
    )

    drill = run_human_gate_canary_rollback_drill(candidate_id="g1-drill-1")
    cases.append(
        {
            "id": "human_gate_canary_rollback_drill",
            "pass": bool(drill.get("ok"))
            and bool(drill.get("human_gate_ok"))
            and bool(drill.get("canary_ok"))
            and bool(drill.get("rollback_ok"))
            and drill.get("production_write") is False,
        }
    )

    ready = evaluate_g1_exit_readiness(
        de_es_ok=bool(de.get("ok")),
        lineage_rate=float(de.get("lineage_completeness") or 0),
        reproducible=bool(de.get("reproducible_check")),
        hard_constraint_ok=int(de.get("hard_constraint_regressions", 1)) == 0,
        holdout_significant=bool(hold.get("significant")),
        drill_ok=bool(drill.get("ok")),
    )
    cases.append(
        {
            "id": "g1_exit_readiness_computable",
            "pass": bool(ready.get("ok")) and ready.get("certified") is False,
        }
    )

    passed = sum(1 for c in cases if c["pass"])
    return {
        "ok": passed == len(cases),
        "passed": passed,
        "total": len(cases),
        "cases": cases,
        "holdout_significant": bool(hold.get("significant")),
        "exit_ready": bool(ready.get("ready")),
        "g1_foundation": True,
        "g1_complete": False,
        "certified": False,
        "e2_claimed": False,
        "note": "G1 slice-1 machinery; suite green ≠ claimed G1/E2 exit",
    }


def evaluate_evo_compute_g1_gate(suite: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """G1 门槛门：套件全过；g1_complete/certified/e2 恒 false。

    Args:
        suite: ``run_evo_compute_g1_suite`` 回执。
    """
    s = suite if suite is not None else run_evo_compute_g1_suite()
    ok = bool(s.get("ok")) and int(s.get("passed") or 0) == int(s.get("total") or -1)
    return {
        "ok": ok,
        "passed": ok,
        "g1_foundation": True,
        "g1_complete": False,
        "certified": False,
        "e2_claimed": False,
        "suite": s,
    }


def run_evo_compute_g1_slice2_suite() -> Dict[str, Any]:
    """G1 slice-2：三试点 DE/ES 电池 + 指标汇总；``g1_complete`` 恒 false。"""
    from core.harness.evo_compute.battery import run_pilot_de_es_battery
    from core.harness.evo_compute.budget import approve_budget, clear_budget_for_tests
    from core.harness.evo_compute.drill import run_human_gate_canary_rollback_drill
    from core.harness.evo_compute.exit_readiness import evaluate_g1_exit_readiness
    from core.harness.evo_compute.genome_registry import clear_registry_for_tests
    from core.harness.evo_compute.safety import clear_safety_for_tests

    clear_registry_for_tests()
    clear_budget_for_tests()
    clear_safety_for_tests()
    cases: list = []

    approve_budget(actor="g1-slice2-suite", persist=False)
    bat = run_pilot_de_es_battery(
        algorithms=["de", "es"],
        population_size=6,
        generations=2,
        seed=42,
        register_pilots=True,
        run_holdout=True,
    )
    summary = bat.get("summary") or {}
    cases.append(
        {
            "id": "three_pilot_battery_ok",
            "pass": bool(bat.get("ok"))
            and len(bat.get("genome_ids") or []) == 3
            and bat.get("production_write") is False,
        }
    )
    cases.append(
        {
            "id": "repro_rate_gate",
            "pass": bool(summary.get("meets_repro_gate"))
            and float(summary.get("reproducible_rate") or 0) >= 0.95,
        }
    )
    cases.append(
        {
            "id": "lineage_and_hard_gates",
            "pass": bool(summary.get("meets_lineage_gate"))
            and bool(summary.get("meets_hard_gate")),
        }
    )
    cases.append(
        {
            "id": "holdout_at_least_one",
            "pass": bool(summary.get("meets_holdout_gate"))
            and int(summary.get("holdout_significant_count") or 0) >= 1,
        }
    )

    drill = run_human_gate_canary_rollback_drill(candidate_id="g1-s2-drill")
    cases.append(
        {
            "id": "drill_ok",
            "pass": bool(drill.get("ok")) and drill.get("production_write") is False,
        }
    )

    ready = evaluate_g1_exit_readiness(
        de_es_ok=bool(bat.get("ok")),
        lineage_rate=float(summary.get("lineage_min") or 0),
        reproducible=bool(summary.get("meets_repro_gate")),
        hard_constraint_ok=bool(summary.get("meets_hard_gate")),
        holdout_significant=bool(summary.get("meets_holdout_gate")),
        drill_ok=bool(drill.get("ok")),
    )
    cases.append(
        {
            "id": "g1_exit_readiness_from_battery",
            "pass": bool(ready.get("ok"))
            and ready.get("certified") is False
            and ready.get("e2_claimed") is False,
        }
    )

    passed = sum(1 for c in cases if c["pass"])
    return {
        "ok": passed == len(cases),
        "passed": passed,
        "total": len(cases),
        "cases": cases,
        "battery_summary": summary,
        "exit_ready": bool(ready.get("ready")),
        "g1_foundation": True,
        "g1_complete": False,
        "certified": False,
        "e2_claimed": False,
        "note": "G1 slice-2 three-pilot battery; suite green ≠ claimed G1/E2 exit",
    }


def run_evo_compute_g2_suite() -> Dict[str, Any]:
    """G2 最小套件：离散 GA + 覆盖率诚实锁；``g2_complete`` 恒 false。"""
    from core.harness.evo_compute.budget import approve_budget, clear_budget_for_tests
    from core.harness.evo_compute.coverage import (
        measure_eval_coverage,
        measure_fde_evidence_coverage,
    )
    from core.harness.evo_compute.exit_readiness import evaluate_g2_exit_readiness
    from core.harness.evo_compute.ga import run_ga_offline
    from core.harness.evo_compute.genome_registry import clear_registry_for_tests
    from core.harness.evo_compute.pilots import register_pilot_genomes
    from core.harness.evo_compute.safety import clear_safety_for_tests

    clear_registry_for_tests()
    clear_budget_for_tests()
    clear_safety_for_tests()
    cases: list = []

    pilots = register_pilot_genomes(persist=False)
    cases.append({"id": "pilots_ready", "pass": bool(pilots.get("ok"))})
    approve_budget(actor="g2-suite", persist=False)

    # timeout.retry 含 int 离散字段
    ga = run_ga_offline(
        genome_id="timeout.retry.v1",
        population_size=6,
        generations=3,
        seed=21,
    )
    cases.append(
        {
            "id": "ga_discrete_ok",
            "pass": bool(ga.get("ok"))
            and ga.get("algorithm") == "ga"
            and int(ga.get("hard_constraint_regressions", 1)) == 0
            and ga.get("safety_regression") is False
            and ga.get("production_write") is False
            and len(ga.get("discrete_fields") or []) >= 1,
        }
    )

    # 再跑 retrieval（含 top_k int）
    ga2 = run_ga_offline(
        genome_id="retrieval.params.v1",
        population_size=5,
        generations=2,
        seed=7,
    )
    cases.append({"id": "ga_retrieval_ok", "pass": bool(ga2.get("ok"))})

    # 缺测诚实：覆盖率门不得因缺测而通过
    ev = measure_eval_coverage()
    fde = measure_fde_evidence_coverage()
    cases.append(
        {
            "id": "eval_coverage_honest_missing",
            "pass": bool(ev.get("ok"))
            and ev.get("baseline_missing") is True
            and ev.get("meets_g2_threshold") is False,
        }
    )
    cases.append(
        {
            "id": "fde_coverage_honest_missing",
            "pass": bool(fde.get("ok"))
            and fde.get("baseline_missing") is True
            and fde.get("meets_g2_threshold") is False,
        }
    )

    ready = evaluate_g2_exit_readiness(
        ga_ok=bool(ga.get("ok")),
        safety_regression_free=ga.get("safety_regression") is False,
        eval_coverage_ok=bool(ev.get("meets_g2_threshold")),
        fde_coverage_ok=bool(fde.get("meets_g2_threshold")),
    )
    cases.append(
        {
            "id": "g2_exit_incomplete_without_coverage",
            "pass": ready.get("g2_complete") is False
            and ready.get("certified") is False
            and "eval_coverage_ok" in (ready.get("missing") or [])
            and "fde_coverage_ok" in (ready.get("missing") or []),
        }
    )

    passed = sum(1 for c in cases if c["pass"])
    return {
        "ok": passed == len(cases),
        "passed": passed,
        "total": len(cases),
        "cases": cases,
        "g2_foundation": True,
        "g2_complete": False,
        "certified": False,
        "e2_claimed": False,
        "note": "G2 slice-1 discrete GA; eval/FDE coverage still baseline_missing",
    }


def evaluate_evo_compute_g2_gate(suite: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """G2 门槛门：套件全过；g2_complete/certified/e2 恒 false。

    Args:
        suite: ``run_evo_compute_g2_suite`` 回执。
    """
    s = suite if suite is not None else run_evo_compute_g2_suite()
    ok = bool(s.get("ok")) and int(s.get("passed") or 0) == int(s.get("total") or -1)
    return {
        "ok": ok,
        "passed": ok,
        "g2_foundation": True,
        "g2_complete": False,
        "certified": False,
        "e2_claimed": False,
        "suite": s,
    }


def run_evo_compute_g2_slice2_suite() -> Dict[str, Any]:
    """G2 slice-2：库存/报告实测覆盖路径；夹具达标 ≠ 宣称生产 L4。

    ``g2_complete`` 在套件回执中恒 false（夹具实测不可冒充出口宣称）。
    """
    from core.harness.evo_compute.budget import approve_budget, clear_budget_for_tests
    from core.harness.evo_compute.coverage import (
        coverage_ratio_from_capability_report,
        default_g2_eval_inventory_fixture,
        default_g2_fde_inventory_fixture,
        measure_eval_coverage,
        measure_eval_coverage_from_capability_report,
        measure_eval_coverage_from_inventory,
        measure_fde_evidence_coverage,
        measure_fde_evidence_coverage_from_inventory,
    )
    from core.harness.evo_compute.exit_readiness import evaluate_g2_exit_readiness
    from core.harness.evo_compute.ga import run_ga_offline
    from core.harness.evo_compute.genome_registry import clear_registry_for_tests
    from core.harness.evo_compute.pilots import register_pilot_genomes
    from core.harness.evo_compute.safety import clear_safety_for_tests

    clear_registry_for_tests()
    clear_budget_for_tests()
    clear_safety_for_tests()
    cases: list = []

    pilots = register_pilot_genomes(persist=False)
    cases.append({"id": "pilots_ready", "pass": bool(pilots.get("ok"))})
    approve_budget(actor="g2-slice2-suite", persist=False)

    ga = run_ga_offline(
        genome_id="timeout.retry.v1",
        population_size=5,
        generations=2,
        seed=11,
    )
    cases.append(
        {
            "id": "ga_ok",
            "pass": bool(ga.get("ok")) and ga.get("safety_regression") is False,
        }
    )

    # 缺测路径仍诚实
    missing = measure_eval_coverage()
    cases.append(
        {
            "id": "eval_still_honest_when_unmeasured",
            "pass": missing.get("baseline_missing") is True
            and missing.get("meets_g2_threshold") is False,
        }
    )

    # 库存达标
    ev_fix = default_g2_eval_inventory_fixture(meet_threshold=True)
    ev = measure_eval_coverage_from_inventory(**ev_fix)
    cases.append(
        {
            "id": "eval_inventory_meets",
            "pass": ev.get("baseline_missing") is False
            and ev.get("meets_g2_threshold") is True
            and float(ev.get("coverage") or 0) >= 0.90,
        }
    )

    ev_low_fix = default_g2_eval_inventory_fixture(meet_threshold=False)
    ev_low = measure_eval_coverage_from_inventory(**ev_low_fix)
    cases.append(
        {
            "id": "eval_inventory_below",
            "pass": ev_low.get("baseline_missing") is False
            and ev_low.get("meets_g2_threshold") is False,
        }
    )

    fde_fix = default_g2_fde_inventory_fixture(meet_threshold=True)
    fde = measure_fde_evidence_coverage_from_inventory(**fde_fix)
    cases.append(
        {
            "id": "fde_inventory_meets",
            "pass": fde.get("baseline_missing") is False
            and fde.get("meets_g2_threshold") is True
            and float(fde.get("coverage") or 0) >= 0.95,
        }
    )

    fde_low = measure_fde_evidence_coverage_from_inventory(
        **default_g2_fde_inventory_fixture(meet_threshold=False)
    )
    cases.append(
        {
            "id": "fde_inventory_below",
            "pass": fde_low.get("meets_g2_threshold") is False,
        }
    )

    # 能力报告形映射（不直导 apps）
    report = {
        "schema": "eval.capability_coverage.v1",
        "covered_capabilities": 9,
        "total_in_scope": 10,
        "n_gaps": 1,
        "subject_kind": "agent",
        "claim_eligible": False,
    }
    ratio = coverage_ratio_from_capability_report(report)
    from_rep = measure_eval_coverage_from_capability_report(report)
    cases.append(
        {
            "id": "capability_report_mapping",
            "pass": ratio.get("baseline_missing") is False
            and abs(float(ratio.get("coverage") or 0) - 0.9) < 1e-9
            and from_rep.get("meets_g2_threshold") is True,
        }
    )

    # 夹具双达标时 exit_readiness 可为 True；套件仍不宣称 g2_complete
    ready = evaluate_g2_exit_readiness(
        ga_ok=bool(ga.get("ok")),
        safety_regression_free=ga.get("safety_regression") is False,
        eval_coverage_ok=bool(ev.get("meets_g2_threshold")),
        fde_coverage_ok=bool(fde.get("meets_g2_threshold")),
    )
    cases.append(
        {
            "id": "exit_ready_on_fixture_but_suite_unclaimed",
            "pass": ready.get("g2_complete") is True
            and ready.get("certified") is False
            and measure_fde_evidence_coverage().get("baseline_missing") is True,
        }
    )

    passed = sum(1 for c in cases if c["pass"])
    return {
        "ok": passed == len(cases),
        "passed": passed,
        "total": len(cases),
        "cases": cases,
        "slice": "g2-slice2",
        "g2_foundation": True,
        "g2_complete": False,
        "certified": False,
        "e2_claimed": False,
        "note": (
            "G2 slice-2 inventory/report measured path; "
            "fixture thresholds ≠ production L4 / Gate claim"
        ),
    }


def evaluate_evo_compute_g2_slice2_gate(
    suite: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """G2 slice-2 门槛门；g2_complete/certified/e2 恒 false。

    Args:
        suite: ``run_evo_compute_g2_slice2_suite`` 回执。
    """
    s = suite if suite is not None else run_evo_compute_g2_slice2_suite()
    ok = bool(s.get("ok")) and int(s.get("passed") or 0) == int(s.get("total") or -1)
    return {
        "ok": ok,
        "passed": ok,
        "g2_foundation": True,
        "g2_complete": False,
        "certified": False,
        "e2_claimed": False,
        "suite": s,
    }
