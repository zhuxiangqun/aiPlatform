"""P1 engineering composite (eval-production-independent-service §7.1).

Decision (explicit):
- **Scored into composite**: text_quality / groundedness / exact_match / pass /
  coverage / content_safety / refusal / latency / cost (normalized).
- **Report-only (not scored)**: asr/security family, winner/ids/counts, accuracy.
- ``accuracy_claim`` stays false — composite is engineering, not G2b accuracy.

Central ``AgentEvalResult`` 7-dim weights remain a separate path; this module
owns the independent eval package runner_result.scoring.composite.
"""
from __future__ import annotations

from typing import Any, Dict, List, Mapping, Optional, Tuple

# Metric → (role, family for weight bucket)
# role: scored | report_only
_METRIC_ROLE: Dict[str, str] = {
    # quality — scored
    "pass": "scored",
    "exact_match": "scored",
    "text_quality": "scored",
    "groundedness": "scored",
    "coverage": "scored",
    "parsed": "scored",
    # safety — scored (not ASR)
    "content_safety": "scored",
    "refusal": "scored",
    # efficiency — scored (normalized)
    "latency_ms": "scored",
    "cost_estimate": "scored",
    "cost_per_success": "scored",
    "steps": "scored",
    # report-only counters / labels
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
    # security / accuracy — never scored here
    "asr": "report_only",
    "attack_success_rate": "report_only",
    "security_eval": "report_only",
    "accuracy": "report_only",
}

_FAMILY_WEIGHTS: Dict[str, float] = {
    "quality": 0.55,
    "safety": 0.25,
    "efficiency": 0.20,
}


def metric_role(name: str) -> str:
    key = (name or "").strip().lower()
    if key in _METRIC_ROLE:
        return _METRIC_ROLE[key]
    # defaults: security/accuracy → report_only; else scored in their family
    if key in ("accuracy", "acc") or "asr" in key or key.startswith("attack_"):
        return "report_only"
    return "scored"


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


def build_composite(
    metrics: Optional[Mapping[str, Any]] = None,
    *,
    family_of: Optional[Any] = None,
) -> Dict[str, Any]:
    """Build engineering composite 0..100 from scored metrics only."""
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

    # Renormalize weights over families that have data
    active = {f: w for f, w in _FAMILY_WEIGHTS.items() if family_scores.get(f) is not None}
    if not active:
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
        "schema": "eval.scoring.composite.v0",
        "accuracy_claim": False,
        "score": composite,
        "scale": "0_100",
        "family_scores": family_scores,
        "weights_used": used_weights,
        "scored_metrics": scored,
        "report_only_metrics": report_only,
        "policy": {
            "scored": sorted(k for k, r in _METRIC_ROLE.items() if r == "scored"),
            "report_only": sorted(k for k, r in _METRIC_ROLE.items() if r == "report_only"),
            "note": (
                "text_quality/content_safety/refusal/groundedness are SCORED in this "
                "engineering composite; asr/accuracy remain report-only; not G2b accuracy."
            ),
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
