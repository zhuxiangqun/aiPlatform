"""P1b report compare — same composite_version only; never open accuracy_claim.

ADR: packages/aiplat-evaluation/docs/a3/ADR_SCORE_SCHEMA_VERSIONING_V1.md §4
"""
from __future__ import annotations

from typing import Any, Dict, List, Mapping, Optional, Sequence


def _as_mapping(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def extract_composite_block(report: Mapping[str, Any]) -> Dict[str, Any]:
    """Pull engineering composite from report / metrics / scoring envelopes."""
    scoring = _as_mapping(report.get("scoring"))
    if scoring.get("composite") and isinstance(scoring.get("composite"), Mapping):
        return dict(scoring["composite"])  # type: ignore[arg-type]

    metrics = _as_mapping(report.get("metrics"))
    m_scoring = _as_mapping(metrics.get("scoring"))
    if m_scoring.get("composite") and isinstance(m_scoring.get("composite"), Mapping):
        return dict(m_scoring["composite"])  # type: ignore[arg-type]
    if metrics.get("composite") and isinstance(metrics.get("composite"), Mapping):
        return dict(metrics["composite"])  # type: ignore[arg-type]

    if report.get("composite") and isinstance(report.get("composite"), Mapping):
        return dict(report["composite"])  # type: ignore[arg-type]
    return {}


def extract_composite_version(report: Mapping[str, Any]) -> Optional[str]:
    block = extract_composite_block(report)
    policy = _as_mapping(block.get("policy"))
    ver = policy.get("composite_version")
    if isinstance(ver, str) and ver.strip():
        return ver.strip()
    # Rare: version parked on metrics.policy
    metrics = _as_mapping(report.get("metrics"))
    m_policy = _as_mapping(metrics.get("policy"))
    ver2 = m_policy.get("composite_version")
    if isinstance(ver2, str) and ver2.strip():
        return ver2.strip()
    return None


def _num(value: Any) -> Optional[float]:
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    return None


def _metric_map(report: Mapping[str, Any]) -> Dict[str, float]:
    """Flat numeric metrics from report.metrics (skip nested objects)."""
    metrics = _as_mapping(report.get("metrics"))
    out: Dict[str, float] = {}
    for key, raw in metrics.items():
        if key in {"scoring", "composite", "policy", "families"}:
            continue
        n = _num(raw)
        if n is not None:
            out[str(key)] = n
    return out


def _family_scores(report: Mapping[str, Any]) -> Dict[str, float]:
    block = extract_composite_block(report)
    families = _as_mapping(block.get("family_scores"))
    out: Dict[str, float] = {}
    for key, raw in families.items():
        n = _num(raw)
        if n is not None:
            out[str(key)] = n
    return out


def _delta_map(a: Mapping[str, float], b: Mapping[str, float]) -> Dict[str, Optional[float]]:
    keys = sorted(set(a) | set(b))
    out: Dict[str, Optional[float]] = {}
    for k in keys:
        left, right = a.get(k), b.get(k)
        if left is None or right is None:
            out[k] = None
        else:
            out[k] = round(right - left, 6)
    return out


def _failure_ids(failures: Any) -> List[str]:
    if not isinstance(failures, Sequence) or isinstance(failures, (str, bytes)):
        return []
    ids: List[str] = []
    for item in failures:
        if isinstance(item, Mapping):
            fid = item.get("id") or item.get("task_id") or item.get("sample_id")
            if fid is not None:
                ids.append(str(fid))
            else:
                ids.append(repr(sorted(item.items())[:4]))
        else:
            ids.append(str(item))
    return ids


def _meta_versions(report: Mapping[str, Any]) -> Dict[str, Any]:
    """Surface runner/judge/dataset/schema stamps when present."""
    metrics = _as_mapping(report.get("metrics"))
    slices = _as_mapping(report.get("slices"))
    keys = (
        "runner_id",
        "runner_version",
        "judge_id",
        "judge_version",
        "dataset_id",
        "dataset_version",
        "schema_version",
        "composite_version",
    )
    out: Dict[str, Any] = {}
    for src in (report, metrics, slices, _as_mapping(metrics.get("meta"))):
        for k in keys:
            if k in src and src[k] not in (None, ""):
                out.setdefault(k, src[k])
    ver = extract_composite_version(report)
    if ver:
        out["composite_version"] = ver
    return out


def compare_reports(
    baseline: Mapping[str, Any],
    candidate: Mapping[str, Any],
) -> Dict[str, Any]:
    """Compare two store/runner reports.

    ``comparable`` is True only when both share the same non-empty
    ``policy.composite_version``. Cross-version or missing → incomparable
    (raw deltas still attached for debugging, not for gate/trend claims).
    """
    b_ver = extract_composite_version(baseline)
    c_ver = extract_composite_version(candidate)
    comparable = bool(b_ver and c_ver and b_ver == c_ver)
    if not b_ver or not c_ver:
        reason = "missing_composite_version"
    elif b_ver != c_ver:
        reason = "composite_version_mismatch"
    else:
        reason = None

    b_block = extract_composite_block(baseline)
    c_block = extract_composite_block(candidate)
    b_score = _num(b_block.get("score"))
    c_score = _num(c_block.get("score"))
    score_delta = (
        round(c_score - b_score, 6)
        if b_score is not None and c_score is not None
        else None
    )

    b_fail = set(_failure_ids(baseline.get("failures")))
    c_fail = set(_failure_ids(candidate.get("failures")))

    result: Dict[str, Any] = {
        "schema": "eval.report.compare.v0",
        "accuracy_claim": False,
        "comparable": comparable,
        "incomparable_reason": reason,
        "baseline": {
            "id": baseline.get("id"),
            "composite_version": b_ver,
            "score": b_score,
            "meta": _meta_versions(baseline),
        },
        "candidate": {
            "id": candidate.get("id"),
            "composite_version": c_ver,
            "score": c_score,
            "meta": _meta_versions(candidate),
        },
        "score_delta": score_delta if comparable else None,
        "family_deltas": _delta_map(_family_scores(baseline), _family_scores(candidate))
        if comparable
        else {},
        "metric_deltas": _delta_map(_metric_map(baseline), _metric_map(candidate))
        if comparable
        else {},
        "failures": {
            "baseline_count": len(b_fail),
            "candidate_count": len(c_fail),
            "added": sorted(c_fail - b_fail)[:50],
            "removed": sorted(b_fail - c_fail)[:50],
            "shared_count": len(b_fail & c_fail),
        },
        "note": (
            "Trends/gates only when comparable=true (same composite_version). "
            "Cross-version = 不可直接比较. Not G2b accuracy."
        ),
    }
    if not comparable:
        # Debug-only raw view — must not drive gates.
        result["raw_score_delta"] = score_delta
        result["raw_family_deltas"] = _delta_map(
            _family_scores(baseline), _family_scores(candidate)
        )
        result["raw_metric_deltas"] = _delta_map(
            _metric_map(baseline), _metric_map(candidate)
        )
    return result


def _wire_compare() -> Dict[str, Any]:
    """Same-file caller for method_verify."""
    return compare_reports(
        {
            "id": "rpt_a",
            "metrics": {"exact_match": 1.0},
            "scoring": {
                "composite": {
                    "score": 80.0,
                    "family_scores": {"accuracy": 1.0},
                    "policy": {"composite_version": "v1.1"},
                }
            },
            "failures": [{"id": "t1"}],
        },
        {
            "id": "rpt_b",
            "metrics": {"exact_match": 0.5},
            "scoring": {
                "composite": {
                    "score": 70.0,
                    "family_scores": {"accuracy": 0.5},
                    "policy": {"composite_version": "v1.1"},
                }
            },
            "failures": [{"id": "t2"}],
        },
    )
