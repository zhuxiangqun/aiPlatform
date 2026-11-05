"""P1b report scoring stamp — composite_version for comparable store reports."""
from __future__ import annotations

from app.scoring.report_compare import compare_reports, extract_composite_version
from app.scoring.report_stamp import ensure_report_scoring


def test_stamps_composite_when_known_metrics():
    out = ensure_report_scoring({"exact_match": 1.0, "content_safety": 1.0})
    assert extract_composite_version(out) == "v1.1"
    assert out["scoring"]["accuracy_claim"] is False
    assert out["scoring"]["composite"]["score"] is not None


def test_skips_unknown_only_metrics():
    out = ensure_report_scoring({"phase": "A2", "process_split_authorized": False})
    assert extract_composite_version(out) is None
    assert "scoring" not in out


def test_preserves_existing_version():
    existing = {
        "exact_match": 0.5,
        "scoring": {
            "composite": {
                "score": 10.0,
                "policy": {"composite_version": "v1"},
            }
        },
    }
    out = ensure_report_scoring(existing)
    assert extract_composite_version(out) == "v1"
    assert out["scoring"]["composite"]["score"] == 10.0


def test_stamped_reports_are_comparable():
    a = {"id": "a", "metrics": ensure_report_scoring({"exact_match": 1.0, "refusal": 1.0})}
    b = {"id": "b", "metrics": ensure_report_scoring({"exact_match": 0.5, "refusal": 1.0})}
    # compare looks at report root scoring OR metrics.scoring
    a_full = {"id": "a", **a["metrics"]}
    b_full = {"id": "b", **b["metrics"]}
    # Prefer store shape: metrics nested
    cmp = compare_reports(
        {"id": "a", "metrics": a["metrics"]},
        {"id": "b", "metrics": b["metrics"]},
    )
    assert cmp["comparable"] is True
    assert cmp["accuracy_claim"] is False
    _ = a_full, b_full
