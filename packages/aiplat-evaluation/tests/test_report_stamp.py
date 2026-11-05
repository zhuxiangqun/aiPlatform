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
    cmp = compare_reports(
        {"id": "a", "metrics": a["metrics"]},
        {"id": "b", "metrics": b["metrics"]},
    )
    assert cmp["comparable"] is True
    assert cmp["accuracy_claim"] is False


def test_meta_promotes_runner_and_composite_version():
    from app.scoring.report_stamp import ensure_report_meta

    out = ensure_report_scoring(
        {"exact_match": 1.0, "runner_id": "prompt_eval"},
        meta={"judge_id": "j1", "dataset_version": "d1"},
    )
    assert out["meta"]["runner_id"] == "prompt_eval"
    assert out["meta"]["judge_id"] == "j1"
    assert out["meta"]["dataset_version"] == "d1"
    assert out["meta"]["composite_version"] == "v1.1"
    assert out["meta"]["evidence_level"] == "gold"
    only = ensure_report_meta({"runner_version": "rv1"})
    assert only["meta"]["runner_version"] == "rv1"
    assert "evidence_level" not in only["meta"]


def test_evidence_level_smoke_arena_and_preserves_explicit():
    from app.scoring.report_stamp import infer_evidence_level

    arena = ensure_report_scoring(
        {"winner": "a", "len_a": 10, "len_b": 3},
        meta={"runner_id": "arena"},
    )
    assert arena["meta"]["evidence_level"] == "smoke"
    assert infer_evidence_level({"text_quality": 0.9}) == "smoke"
    assert infer_evidence_level({"content_safety": 1.0, "refusal": 1.0}) == "fixture"
    kept = ensure_report_scoring(
        {"exact_match": 1.0},
        meta={"evidence_level": "human", "runner_id": "prompt_eval"},
    )
    assert kept["meta"]["evidence_level"] == "human"
    eet = ensure_report_scoring({"exact_match": 1.0}, meta={"evidence_level": "EET-2"})
    assert eet["meta"]["evidence_level"] == "fixture"