"""P1b report compare — composite_version gate + deltas; accuracy_claim false."""
from __future__ import annotations

from app.scoring.report_compare import compare_reports, extract_composite_version


def _rpt(ver: str, score: float, metrics: dict, failures=None, rid="rpt"):
    return {
        "id": rid,
        "metrics": metrics,
        "scoring": {
            "composite": {
                "score": score,
                "family_scores": {"safety": score / 100.0},
                "policy": {"composite_version": ver},
            }
        },
        "failures": failures or [],
    }


def test_same_version_comparable():
    a = _rpt("v1.1", 80.0, {"exact_match": 1.0, "content_safety": 1.0}, [{"id": "t1"}], "a")
    b = _rpt("v1.1", 70.0, {"exact_match": 0.5, "content_safety": 1.0}, [{"id": "t2"}], "b")
    out = compare_reports(a, b)
    assert out["accuracy_claim"] is False
    assert out["comparable"] is True
    assert out["incomparable_reason"] is None
    assert out["score_delta"] == -10.0
    assert out["metric_deltas"]["exact_match"] == -0.5
    assert out["failures"]["added"] == ["t2"]
    assert out["failures"]["removed"] == ["t1"]


def test_cross_version_incomparable():
    a = _rpt("v1", 80.0, {"exact_match": 1.0})
    b = _rpt("v1.1", 70.0, {"exact_match": 0.5})
    out = compare_reports(a, b)
    assert out["comparable"] is False
    assert out["incomparable_reason"] == "composite_version_mismatch"
    assert out["score_delta"] is None
    assert out["metric_deltas"] == {}
    assert out["raw_score_delta"] == -10.0


def test_missing_version_incomparable():
    a = {"id": "a", "metrics": {"exact_match": 1.0}, "failures": []}
    b = _rpt("v1.1", 50.0, {"exact_match": 0.0})
    out = compare_reports(a, b)
    assert out["comparable"] is False
    assert out["incomparable_reason"] == "missing_composite_version"
    assert extract_composite_version(a) is None
    assert extract_composite_version(b) == "v1.1"
