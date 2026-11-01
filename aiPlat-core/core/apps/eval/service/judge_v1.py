"""EVAL_V1 E4 — Judge v1 (deterministic code-review match) + k=3 / ECE calibration.

Honesty: engineering calibration only — does NOT claim accuracy / κ.
"""
from __future__ import annotations

import statistics
from typing import Any, Dict, List, Optional, Sequence, Tuple

from core.apps.eval.service.store import EvalStore, get_eval_store

JUDGE_V1_ID = "judge.deterministic.code_review_gold.v1"
JUDGE_V1_PROMPT_VERSION = "match_review_findings@v0"
JUDGE_V1_MODEL = "deterministic"
PASS_SCORE_THRESHOLD = 0.75
K_DEFAULT = 3
ECE_BINS = 5


def register_judge_v1(store: EvalStore) -> Dict[str, Any]:
    return store.upsert_judge(
        judge_id=JUDGE_V1_ID,
        model=JUDGE_V1_MODEL,
        prompt_version=JUDGE_V1_PROMPT_VERSION,
        calibration={"status": "uncalibrated", "schema": "eval.calibration.v0"},
    )


def _f1(precision: float, recall: float) -> float:
    if precision + recall <= 0:
        return 0.0
    return 2.0 * precision * recall / (precision + recall)


def score_task_match_only(task: Dict[str, Any]) -> Dict[str, Any]:
    """Deterministic judge: predicted fixtures vs gold_findings."""
    from core.harness.evaluation.code_review_gold import (
        GoldFinding,
        match_review_findings,
    )

    expected = task.get("expected") or {}
    inp = task.get("input") or {}
    gold_raw = expected.get("gold_findings") or []
    pred_raw = inp.get("predicted") or []
    golds = [GoldFinding.from_dict(x) for x in gold_raw if isinstance(x, dict)]
    preds = [x for x in pred_raw if isinstance(x, dict)]
    scored = match_review_findings(
        preds, golds, line_window=int(inp.get("line_window") or 8)
    )
    precision = float(scored.get("precision") or 0.0)
    recall = float(scored.get("recall") or 0.0)
    f1 = _f1(precision, recall)
    passed = f1 >= PASS_SCORE_THRESHOLD
    # Confidence: proximity of F1 to extremes (well-separated → higher)
    confidence = round(min(1.0, max(0.0, abs(f1 - 0.5) * 2.0)), 4)
    return {
        "score": round(f1, 4),
        "pass": passed,
        "precision": precision,
        "recall": recall,
        "p0_recall": scored.get("p0_recall"),
        "confidence": confidence,
        "reason": f"match_only F1={f1:.3f} P={precision:.3f} R={recall:.3f}",
        "evidence": {
            "tp": scored.get("tp"),
            "fp": scored.get("fp"),
            "fn": scored.get("fn"),
            "comment_count": scored.get("comment_count"),
        },
    }


def _stdev(vals: Sequence[float]) -> float:
    if len(vals) < 2:
        return 0.0
    return float(statistics.pstdev(vals))


def expected_calibration_error(
    pairs: Sequence[Tuple[float, bool]],
    *,
    n_bins: int = ECE_BINS,
) -> Dict[str, Any]:
    """ECE over (confidence, correct) pairs. Empty → recorded as None."""
    if not pairs:
        return {"ece": None, "n": 0, "bins": []}
    bins: List[Dict[str, Any]] = []
    ece = 0.0
    n = len(pairs)
    for i in range(n_bins):
        lo, hi = i / n_bins, (i + 1) / n_bins
        bucket = [(c, int(y)) for c, y in pairs if (c >= lo and (c < hi or (i == n_bins - 1 and c <= hi)))]
        if not bucket:
            bins.append({"lo": lo, "hi": hi, "n": 0, "acc": None, "conf": None})
            continue
        acc = sum(y for _, y in bucket) / len(bucket)
        conf = sum(c for c, _ in bucket) / len(bucket)
        ece += (len(bucket) / n) * abs(acc - conf)
        bins.append({"lo": lo, "hi": hi, "n": len(bucket), "acc": round(acc, 4), "conf": round(conf, 4)})
    return {"ece": round(ece, 4), "n": n, "bins": bins}


def run_e4_calibration(
    *,
    tenant_id: str = "eval-v1",
    set_id: str = "",
    k: int = K_DEFAULT,
    limit: int = 500,
    db_path: Optional[str] = None,
) -> Dict[str, Any]:
    """Run judge v1 over gold tasks with k repeats; persist judgments + calibration report.

    Does not claim accuracy. κ is always null under D5 solo review.
    """
    store = get_eval_store(tenant_id=tenant_id, db_path=db_path)
    register_judge_v1(store)

    if not set_id:
        for s in store.list_sets(limit=100):
            if str(s.get("id", "")).startswith("set_crg_"):
                set_id = s["id"]
                break
    if not set_id:
        raise ValueError("no gold set_id; run bootstrap_e3_gold first")

    tasks = store.list_tasks(set_id=set_id, limit=limit)
    if not tasks:
        raise ValueError(f"no tasks in set {set_id}")

    k = max(1, min(int(k or K_DEFAULT), 5))
    run_ids: List[str] = []
    per_task: List[Dict[str, Any]] = []
    all_scores: List[float] = []
    ece_pairs: List[Tuple[float, bool]] = []
    pass_count = 0
    profile_scores: Dict[str, List[float]] = {}

    for task in tasks:
        scores_k: List[float] = []
        last_result: Dict[str, Any] = {}
        for i in range(k):
            result = score_task_match_only(task)
            last_result = result
            scores_k.append(float(result["score"]))
            run = store.create_run(
                task_id=task["id"],
                target_kind="skill",
                target_ref="code_review_gold",
                model=JUDGE_V1_MODEL,
                params={"k_index": i, "judge": JUDGE_V1_ID},
                status="passed" if result["pass"] else "failed",
                versions={
                    "dataset": set_id,
                    "judge": JUDGE_V1_ID,
                    "prompt": JUDGE_V1_PROMPT_VERSION,
                    "model": JUDGE_V1_MODEL,
                    "code_commit": "",
                },
            )
            run_ids.append(run["id"])
            store.create_judgment(
                run_id=run["id"],
                judge_id=JUDGE_V1_ID,
                score=result["score"],
                passed=bool(result["pass"]),
                reason=result["reason"],
                evidence=result.get("evidence") or {},
                confidence=float(result["confidence"]),
            )
        mean_score = sum(scores_k) / len(scores_k)
        stdev_k = _stdev(scores_k)
        all_scores.append(mean_score)
        if last_result.get("pass"):
            pass_count += 1
        # For ECE: treat deterministic F1 as confidence; correctness = pass threshold
        ece_pairs.append((float(last_result["confidence"]), bool(last_result["pass"])))
        tags = task.get("tags") or []
        profile = next((t for t in tags if t not in ("code-review-gold",)), "default")
        profile_scores.setdefault(str(profile), []).append(mean_score)
        per_task.append(
            {
                "task_id": task["id"],
                "mean_score": round(mean_score, 4),
                "stdev_k": round(stdev_k, 4),
                "pass": bool(last_result.get("pass")),
                "precision": last_result.get("precision"),
                "recall": last_result.get("recall"),
            }
        )

    score_stdev_across_tasks = _stdev(all_scores)
    # k=3 repeat stdev (mean of per-task stdevs) — deterministic → ~0
    mean_k_stdev = (
        sum(float(t["stdev_k"]) for t in per_task) / len(per_task) if per_task else 0.0
    )
    ece = expected_calibration_error(ece_pairs)
    bias = {
        profile: {
            "n": len(vals),
            "mean_score": round(sum(vals) / len(vals), 4),
        }
        for profile, vals in sorted(profile_scores.items())
    }
    metrics = {
        "schema_version": "eval.calibration.v0",
        "judge_id": JUDGE_V1_ID,
        "k": k,
        "task_count": len(tasks),
        "pass_rate": round(pass_count / len(tasks), 4) if tasks else None,
        "mean_score": round(sum(all_scores) / len(all_scores), 4) if all_scores else None,
        "k_repeat_stdev_mean": round(mean_k_stdev, 4),
        "k_repeat_stdev_gate_v0": mean_k_stdev <= 0.08,
        "score_stdev_across_tasks": round(score_stdev_across_tasks, 4),
        "ece": ece.get("ece"),
        "ece_detail": ece,
        "bias_by_profile": bias,
        "kappa": None,
        "accuracy_claim": False,
        "note": "E4 engineering calibration only (D5); not accuracy / not G2a",
    }
    report = store.create_report(
        run_ids=run_ids,
        metrics=metrics,
        slices={"by_profile": bias, "per_task": per_task[:100]},
        failures=[t for t in per_task if not t.get("pass")],
    )
    store.upsert_judge(
        judge_id=JUDGE_V1_ID,
        model=JUDGE_V1_MODEL,
        prompt_version=JUDGE_V1_PROMPT_VERSION,
        calibration={
            "status": "recorded",
            "report_id": report["id"],
            "ece": ece.get("ece"),
            "k_repeat_stdev_mean": metrics["k_repeat_stdev_mean"],
            "accuracy_claim": False,
        },
    )
    return {
        "ok": True,
        "judge_id": JUDGE_V1_ID,
        "set_id": set_id,
        "report_id": report["id"],
        "metrics": metrics,
        "report": report,
        "accuracy_claim": False,
    }
