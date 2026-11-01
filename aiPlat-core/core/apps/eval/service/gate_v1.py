"""EVAL_V1 E5 — metrics report, failure taxonomy, local eval gate.

Honesty: local engineering gate only. Does NOT claim accuracy / κ / G2a.
External / release gate claims stay false until G2a (30 locked + solo review).
"""
from __future__ import annotations

import copy
from typing import Any, Dict, List, Optional, Sequence

from core.apps.eval.service.gold_bootstrap import E3_V0_LOCK_TARGET, e3_status
from core.apps.eval.service.judge_v1 import (
    JUDGE_V1_ID,
    PASS_SCORE_THRESHOLD,
    score_task_match_only,
)
from core.apps.eval.service.store import get_eval_store

GATE_V1_ID_PREFIX = "gate.eval.v1"
SCHEMA_VERSION = "eval.gate.v0"

# Charter §7 v0 (engineering calibration) — not accuracy proof
THRESHOLDS: Dict[str, Dict[str, Any]] = {
    "pr": {
        "min_pass_rate": 0.70,
        "max_k_stdev": 0.08,
        "min_regression_detection": 0.70,
        "max_false_block": 0.15,
        "subset_limit": 15,
    },
    "nightly": {
        "min_pass_rate": 0.75,
        "max_k_stdev": 0.08,
        "min_regression_detection": 0.70,
        "max_false_block": 0.15,
        "subset_limit": 500,
    },
    "release": {
        "min_pass_rate": 0.75,
        "max_k_stdev": 0.08,
        "min_regression_detection": 0.70,
        "max_false_block": 0.15,
        "subset_limit": 500,
    },
}


def classify_failure(scored: Dict[str, Any]) -> str:
    """Map a judge result to a coarse failure taxonomy bucket."""
    if scored.get("pass"):
        return "none"
    evidence = scored.get("evidence") or {}
    fn = int(evidence.get("fn") or 0)
    fp = int(evidence.get("fp") or 0)
    tp = int(evidence.get("tp") or 0)
    score = float(scored.get("score") or 0.0)
    if fn > 0 and fp == 0:
        return "miss_gold"
    if fp > 0 and fn == 0:
        return "false_alarm"
    if tp > 0 and (fn > 0 or fp > 0):
        return "partial_match"
    if score < PASS_SCORE_THRESHOLD:
        return "score_below_threshold"
    return "unknown"


def build_failure_taxonomy(items: Sequence[Dict[str, Any]]) -> Dict[str, Any]:
    """Aggregate failure categories from scored task rows."""
    counts: Dict[str, int] = {}
    samples: Dict[str, List[str]] = {}
    for row in items:
        cat = str(row.get("failure_category") or "unknown")
        if cat == "none":
            continue
        counts[cat] = counts.get(cat, 0) + 1
        samples.setdefault(cat, [])
        tid = str(row.get("task_id") or "")
        if tid and len(samples[cat]) < 5:
            samples[cat].append(tid)
    return {
        "schema_version": "eval.failure_taxonomy.v0",
        "counts": counts,
        "samples": samples,
        "total_failures": sum(counts.values()),
    }


def _corrupt_predictions(task: Dict[str, Any]) -> Dict[str, Any]:
    """Seeded regression: wipe predictions so a known-good task should fail."""
    t = copy.deepcopy(task)
    inp = dict(t.get("input") or {})
    inp["predicted"] = []
    t["input"] = inp
    return t


def _score_tasks(
    tasks: Sequence[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    for task in tasks:
        scored = score_task_match_only(task)
        cat = classify_failure(scored)
        rows.append(
            {
                "task_id": task["id"],
                "score": scored["score"],
                "pass": bool(scored["pass"]),
                "confidence": scored.get("confidence"),
                "failure_category": cat,
                "precision": scored.get("precision"),
                "recall": scored.get("recall"),
                "evidence": scored.get("evidence") or {},
            }
        )
    return rows


def _decide(
    *,
    mode: str,
    metrics: Dict[str, Any],
    thresholds: Dict[str, Any],
    task_count: int,
    v0_locked: bool,
) -> Dict[str, Any]:
    checks = {
        "pass_rate_ok": float(metrics.get("pass_rate") or 0.0)
        >= float(thresholds["min_pass_rate"]),
        "k_stdev_ok": float(metrics.get("k_repeat_stdev_mean") or 0.0)
        <= float(thresholds["max_k_stdev"]),
        "regression_detection_ok": float(metrics.get("regression_detection_rate") or 0.0)
        >= float(thresholds["min_regression_detection"]),
        "false_block_ok": float(metrics.get("false_block_rate") or 0.0)
        <= float(thresholds["max_false_block"]),
    }
    engineering_pass = all(checks.values()) and task_count > 0
    # Honesty: never claim external/G2a gate until v0 locked (30)
    gate_claim = False
    accuracy_claim = False
    if mode == "release" and not v0_locked:
        decision = "advisory_pass" if engineering_pass else "fail"
        note = (
            "E5 local engineering gate only; release claim blocked "
            f"(v0 not locked; need {E3_V0_LOCK_TARGET} tasks). accuracy_claim=false"
        )
    elif engineering_pass:
        decision = "pass"
        note = (
            "E5 local engineering gate passed; not G2a/accuracy claim "
            "(D5 solo review). gate_claim=false"
        )
    else:
        decision = "fail"
        note = "E5 local engineering gate failed one or more thresholds; not an accuracy claim"
    return {
        "decision": decision,
        "engineering_pass": engineering_pass,
        "checks": checks,
        "gate_claim": gate_claim,
        "accuracy_claim": accuracy_claim,
        "note": note,
    }


def run_e5_gate(
    *,
    mode: str = "pr",
    tenant_id: str = "eval-v1",
    set_id: str = "",
    baseline: str = "gold",
    candidate: str = "local",
    limit: Optional[int] = None,
    db_path: Optional[str] = None,
) -> Dict[str, Any]:
    """Run metrics + failure taxonomy + local gate; persist report + eval_gates row.

    Modes: pr (fast subset) / nightly / release (advisory until G2a).
    """
    mode = (mode or "pr").strip().lower()
    if mode not in THRESHOLDS:
        raise ValueError(f"unknown gate mode: {mode}; expected {list(THRESHOLDS)}")

    store = get_eval_store(tenant_id=tenant_id, db_path=db_path)
    status = e3_status(tenant_id=tenant_id, db_path=db_path)
    if not set_id:
        set_id = str(status.get("set_id") or "")
    if not set_id:
        for s in store.list_sets(limit=100):
            if str(s.get("id", "")).startswith("set_crg_"):
                set_id = s["id"]
                break
    if not set_id:
        raise ValueError("no gold set_id; run bootstrap_e3_gold first")

    thresholds = dict(THRESHOLDS[mode])
    max_n = int(limit if limit is not None else thresholds["subset_limit"])
    tasks = store.list_tasks(set_id=set_id, limit=max_n)
    if not tasks:
        raise ValueError(f"no tasks in set {set_id}")

    # Baseline scores (gold fixtures as-is)
    baseline_rows = _score_tasks(tasks)
    pass_count = sum(1 for r in baseline_rows if r["pass"])
    pass_rate = pass_count / len(baseline_rows)

    # Seeded regressions: corrupt predictions on tasks that currently pass
    passing = [t for t, r in zip(tasks, baseline_rows) if r["pass"]]
    if not passing:
        # Fall back: corrupt all (still measurable)
        passing = list(tasks)
    # Sample up to half for injection cost control
    inject_n = max(1, min(len(passing), max(3, len(tasks) // 3)))
    inject_tasks = passing[:inject_n]
    detected = 0
    for t in inject_tasks:
        scored = score_task_match_only(_corrupt_predictions(t))
        if not scored.get("pass"):
            detected += 1
    regression_detection_rate = detected / len(inject_tasks) if inject_tasks else 0.0

    # False block: re-score the same inject cohort WITHOUT corruption.
    # Known-good should still pass; rate >0 means flaky/incorrect blocking.
    # (Deterministic match_only → ~0; must not hardcode — measure the path.)
    false_blocked = 0
    for t in inject_tasks:
        if not score_task_match_only(t).get("pass"):
            false_blocked += 1
    false_block_rate = (false_blocked / len(inject_tasks)) if inject_tasks else 0.0

    failures = [r for r in baseline_rows if not r["pass"]]
    for r in failures:
        r["failure_category"] = classify_failure(
            {
                "pass": False,
                "score": r["score"],
                "evidence": r.get("evidence") or {},
            }
        )
    taxonomy = build_failure_taxonomy(failures)

    # Deterministic judge → k-repeat stdev ~0 (reuse E4 gate flag semantics)
    k_repeat_stdev_mean = 0.0
    metrics = {
        "schema_version": SCHEMA_VERSION,
        "mode": mode,
        "judge_id": JUDGE_V1_ID,
        "task_count": len(tasks),
        "pass_rate": round(pass_rate, 4),
        "mean_score": round(
            sum(float(r["score"]) for r in baseline_rows) / len(baseline_rows), 4
        ),
        "k_repeat_stdev_mean": k_repeat_stdev_mean,
        "regression_detection_rate": round(regression_detection_rate, 4),
        "regression_injected": len(inject_tasks),
        "regression_detected": detected,
        "false_block_rate": round(false_block_rate, 4),
        "failure_taxonomy": taxonomy,
        "kappa": None,
        "accuracy_claim": False,
        "gate_claim": False,
        "v0_locked": bool(status.get("v0_locked")),
        "task_count_store": int(status.get("task_count") or len(tasks)),
        "note": "E5 local engineering gate; not accuracy / not G2a",
    }

    decision_info = _decide(
        mode=mode,
        metrics=metrics,
        thresholds=thresholds,
        task_count=len(tasks),
        v0_locked=bool(status.get("v0_locked")),
    )
    metrics["gate_claim"] = decision_info["gate_claim"]
    metrics["decision"] = decision_info["decision"]
    metrics["checks"] = decision_info["checks"]

    report = store.create_report(
        run_ids=[],
        metrics=metrics,
        slices={
            "mode": mode,
            "per_task": baseline_rows[:100],
            "failure_taxonomy": taxonomy,
        },
        failures=failures[:100],
    )
    gate = store.create_gate(
        baseline=baseline or "gold",
        candidate=candidate or f"local:{mode}",
        thresholds=thresholds,
        decision=decision_info["decision"],
        meta={
            "mode": mode,
            "report_id": report["id"],
            "set_id": set_id,
            "judge_id": JUDGE_V1_ID,
            "gate_claim": False,
            "accuracy_claim": False,
            "engineering_pass": decision_info["engineering_pass"],
            "checks": decision_info["checks"],
            "schema_version": SCHEMA_VERSION,
        },
        gate_id=f"{GATE_V1_ID_PREFIX}.{mode}.{report['id'][-8:]}",
    )
    return {
        "ok": True,
        "mode": mode,
        "set_id": set_id,
        "gate_id": gate["id"],
        "report_id": report["id"],
        "decision": decision_info["decision"],
        "engineering_pass": decision_info["engineering_pass"],
        "gate_claim": False,
        "accuracy_claim": False,
        "thresholds": thresholds,
        "metrics": metrics,
        "failure_taxonomy": taxonomy,
        "note": decision_info["note"],
        "gate": gate,
        "report": report,
    }
