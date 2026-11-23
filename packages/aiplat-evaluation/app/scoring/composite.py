"""P1 engineering composite (eval-production-independent-service §7.1).

Decision (explicit):
- **Scored into composite**: groundedness (gold-gated) / exact_match / pass /
  coverage / latency / cost (normalized).
- **Report-only (not scored)**: text_quality / content_safety / refusal (keyword
  heuristics — smoke only), asr/security, winner/ids/counts, accuracy.
- ``accuracy_claim`` stays false — composite is engineering, not G2b accuracy.
- composite_version ``v1.1``: text_quality demoted to report-only (P1a).
- composite_version ``v1.2``: content_safety / refusal demoted to report-only
  (same weak-proxy honesty as text_quality; S1 still owns ASR).
- composite_version ``v1.3``: drop unused safety family weight; unknown metrics
  default to report_only (fail-closed registration).

Central ``AgentEvalResult`` 7-dim weights remain a separate path; this module
owns the independent eval package runner_result.scoring.composite.
"""
from __future__ import annotations

from typing import Any, Dict, List, Mapping, Optional, Tuple  # Tuple: profile family sets

# Metric → role (scored | report_only). Unknown keys → report_only.
_METRIC_ROLE: Dict[str, str] = {
    # quality — scored
    "pass": "scored",
    "exact_match": "scored",
    "text_quality": "report_only",  # length/printable heuristic — smoke only (P1a)
    "groundedness": "scored",
    "coverage": "scored",
    "parsed": "scored",
    # safety — report-only keyword smoke (v1.2); not ASR
    "content_safety": "report_only",
    "refusal": "report_only",
    # efficiency — scored (normalized)
    "latency_ms": "scored",
    "cost_estimate": "scored",
    "cost_per_success": "scored",
    "steps": "scored",
    "turn_success_rate": "scored",
    "session_pass": "scored",
    # report-only counters / labels
    "turns_n": "report_only",
    "turns_ok": "report_only",
    "winner": "report_only",
    "gold_n": "report_only",
    "findings_n": "report_only",
    "hit_count": "report_only",
    "cases": "report_only",
    "passed": "report_only",
    "len_a": "report_only",
    "len_b": "report_only",
    "fetched": "report_only",
    "tokens_in": "report_only",
    "tokens_out": "report_only",
    # security / accuracy / compliance — never scored here
    "asr": "report_only",
    "attack_success_rate": "report_only",
    "security_eval": "report_only",
    "accuracy": "report_only",
    "pii_clean": "report_only",
    "pii_leak": "report_only",
}

# Safety has no scored metrics (v1.2+); omit weight so the table matches scored=.
# Present families still renormalize to sum 1.0.
_FAMILY_WEIGHTS: Dict[str, float] = {
    "quality": 0.55,
    "efficiency": 0.20,
}


def metric_role(name: str) -> str:
    """Return scored | report_only.

    Args:
        name: Metric key from runner metrics.

    Returns:
        Role string. Unknown metrics default to ``report_only`` (fail-closed).
    """
    key = (name or "").strip().lower()
    if key in _METRIC_ROLE:
        return _METRIC_ROLE[key]
    # Fail-closed: only explicitly registered metrics may enter composite.
    return "report_only"


def _to_unit(name: str, value: Any) -> Optional[float]:
    """Normalize a metric to 0..1 for composite; None = skip."""
    try:
        v = float(value)
    except (TypeError, ValueError):
        return None
    key = (name or "").strip().lower()
    if key == "latency_ms":
        return round(1.0 / (1.0 + max(0.0, v) / 1000.0), 4)
    if key in ("cost_estimate", "cost_per_success"):
        return round(1.0 / (1.0 + max(0.0, v) * 100.0), 4)
    if key == "steps":
        # fewer steps slightly better after 1; clamp
        return round(min(1.0, 1.0 / (1.0 + max(0.0, v - 1.0) / 10.0)), 4)
    if v < 0:
        return 0.0
    if v > 1.0:
        # allow 0..100 style by scaling
        if v <= 100.0:
            return round(v / 100.0, 4)
        return 1.0
    return round(v, 4)


# B-P5：固定 family 集的可比 profile；缺维 → incomplete，禁止当「完整分」
_COMPOSITE_PROFILES: Dict[str, Tuple[str, ...]] = {
    "engineering_v1": ("quality", "efficiency"),
}


def engineering_score_accepted(scoring_path: Optional[str]) -> bool:
    """B-P3：新工程门禁只认 package composite，拒绝 legacy_7dim。

    Args:
        scoring_path: ``scoring.path`` 或等价字符串。
    """
    path = str(scoring_path or "").strip()
    return path in {"package_build_composite", "build_composite"}


def build_composite(
    metrics: Optional[Mapping[str, Any]] = None,
    *,
    family_of: Optional[Any] = None,
    composite_profile_id: Optional[str] = None,
) -> Dict[str, Any]:
    """Build engineering composite 0..100 from scored metrics only.

    Args:
        metrics: runner metrics map.
        family_of: optional metric→family classifier.
        composite_profile_id: when set (e.g. ``engineering_v1``), require all
            profile families or return ``incomplete`` with ``score=None``
            instead of silently renormalizing a partial family set as a full score.
    """
    from app.scoring.semantics import classify_metric

    classify = family_of or classify_metric
    m = dict(metrics or {})
    scored: Dict[str, float] = {}
    report_only: Dict[str, Any] = {}
    by_family_units: Dict[str, List[float]] = {
        "quality": [],
        "safety": [],
        "efficiency": [],
    }

    for k, raw in m.items():
        name = str(k)
        role = metric_role(name)
        fam = str(classify(name))
        if role == "report_only" or fam in ("accuracy", "security"):
            report_only[name] = raw
            continue
        unit = _to_unit(name, raw)
        if unit is None:
            report_only[name] = raw
            continue
        scored[name] = unit
        if fam in by_family_units:
            by_family_units[fam].append(unit)

    family_scores: Dict[str, Optional[float]] = {}
    for fam, vals in by_family_units.items():
        family_scores[fam] = round(sum(vals) / len(vals), 4) if vals else None

    profile_id = str(composite_profile_id or "").strip() or None
    required_families = _COMPOSITE_PROFILES.get(profile_id or "", ())
    incomplete = False
    missing_families: List[str] = []
    if required_families:
        missing_families = [f for f in required_families if family_scores.get(f) is None]
        incomplete = bool(missing_families)

    # Renormalize weights over families that have data (legacy default path).
    # Profile path: incomplete → no score (not a silent partial as "full").
    active = {f: w for f, w in _FAMILY_WEIGHTS.items() if family_scores.get(f) is not None}
    if incomplete or not active:
        composite = None
        used_weights: Dict[str, float] = {}
    else:
        total_w = sum(active.values())
        used_weights = {f: round(w / total_w, 4) for f, w in active.items()}
        composite = round(
            100.0 * sum(float(family_scores[f]) * used_weights[f] for f in used_weights),
            2,
        )

    return {
        "schema": "eval.scoring.composite.v1",
        "accuracy_claim": False,
        "score": composite,
        "scale": "0_100",
        "family_scores": family_scores,
        "weights_used": used_weights,
        "scored_metrics": scored,
        "report_only_metrics": report_only,
        "composite_profile_id": profile_id,
        "incomplete": incomplete,
        "missing_families": missing_families,
        "policy": {
            "scored": sorted(k for k, r in _METRIC_ROLE.items() if r == "scored"),
            "report_only": sorted(k for k, r in _METRIC_ROLE.items() if r == "report_only"),
            "note": (
                "groundedness/exact_match/pass/coverage are SCORED when present; "
                "groundedness requires gold (expected/context/sources) to appear in metrics; "
                "text_quality/content_safety/refusal are report-only keyword/length smoke; "
                "asr/accuracy remain report-only; not G2b accuracy."
            ),
            "composite_version": "v1.3",
            "groundedness_gold_gated": True,
            "text_quality_smoke": True,
            "safety_keyword_smoke": True,
            "safety_family_weight": False,
            "unknown_metric_default": "report_only",
            "engineering_gate_paths": ["package_build_composite", "build_composite"],
            "legacy_7dim_gate": False,
        },
    }


def _wire_composite() -> Dict[str, Any]:
    """Same-file caller for method_verify."""
    return build_composite(
        {
            "text_quality": 1.0,
            "content_safety": 1.0,
            "refusal": 1.0,
            "groundedness": 0.8,
            "asr": 0.0,
        }
    )
