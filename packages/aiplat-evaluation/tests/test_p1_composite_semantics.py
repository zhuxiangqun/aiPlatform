"""P1 composite — scored vs report-only; accuracy_claim stays false."""
from __future__ import annotations

from app.scoring.composite import (
    build_composite,
    engineering_score_accepted,
    metric_role,
)
from app.scoring.semantics import build_scoring_block
from app.worker.runners import execute_runner


def test_metric_roles_explicit():
    assert metric_role("text_quality") == "report_only"  # P1a smoke
    assert metric_role("content_safety") == "report_only"  # v1.2 weak proxy
    assert metric_role("refusal") == "report_only"  # v1.2 weak proxy
    assert metric_role("groundedness") == "scored"
    assert metric_role("asr") == "report_only"
    assert metric_role("accuracy") == "report_only"
    assert metric_role("winner") == "report_only"


def test_composite_scores_p1_dims_not_asr():
    block = build_composite(
        {
            "text_quality": 1.0,
            "content_safety": 1.0,
            "refusal": 1.0,
            "groundedness": 1.0,
            "asr": 0.9,
        }
    )
    assert block["accuracy_claim"] is False
    assert block["score"] is not None
    assert block["score"] >= 99.0
    assert block["policy"]["composite_version"] == "v1.3"
    assert block["policy"]["safety_family_weight"] is False
    assert block["policy"]["unknown_metric_default"] == "report_only"
    assert "asr" in block["report_only_metrics"]
    assert "text_quality" in block["report_only_metrics"]
    assert "content_safety" in block["report_only_metrics"]
    assert "refusal" in block["report_only_metrics"]
    assert "content_safety" not in block["scored_metrics"]
    assert "groundedness" in block["scored_metrics"]
    assert metric_role("brand_new_unregistered_metric") == "report_only"


def test_scoring_block_embeds_composite():
    block = build_scoring_block(
        {"exact_match": 1.0, "content_safety": 1.0, "latency_ms": 0, "asr": 0.0}
    )
    assert block["accuracy_claim"] is False
    assert block["composite"]["schema"] == "eval.scoring.composite.v1"
    assert block["metric_roles"]["exact_match"] == "scored"
    assert block["metric_roles"]["content_safety"] == "report_only"
    assert block["metric_roles"]["asr"] == "report_only"
    assert block["families"]["accuracy"] == {}


def test_prompt_eval_runner_has_composite():
    out = execute_runner(
        {
            "job_id": "c1",
            "runner_id": "prompt_eval",
            "payload": {
                "prompt": "hi",
                "expected": "hi",
                "actual": "hi",
                "context": "hi there",
            },
        }
    )
    assert out["accuracy_claim"] is False
    comp = out["scoring"]["composite"]
    assert comp["accuracy_claim"] is False
    assert comp["score"] is not None
    assert "text_quality" in comp["report_only_metrics"]
    assert "content_safety" in comp["report_only_metrics"]
    meta = out["metrics"].get("meta") or {}
    assert meta.get("runner_id") == "prompt_eval"
    assert meta.get("composite_version") == "v1.3"


def test_engineering_score_rejects_legacy_path():
    assert engineering_score_accepted("package_build_composite") is True
    assert engineering_score_accepted("build_composite") is True
    assert engineering_score_accepted("legacy_7dim") is False
    assert engineering_score_accepted("") is False


def test_composite_profile_incomplete_without_efficiency():
    # quality-only metrics → default path still scores; profile requires both families
    partial = build_composite({"groundedness": 1.0})
    assert partial["score"] is not None
    assert partial.get("incomplete") is False

    gated = build_composite(
        {"groundedness": 1.0},
        composite_profile_id="engineering_v1",
    )
    assert gated["incomplete"] is True
    assert gated["score"] is None
    assert "efficiency" in (gated.get("missing_families") or [])
    assert gated["composite_profile_id"] == "engineering_v1"


def test_composite_profile_complete_with_quality_and_efficiency():
    full = build_composite(
        {"groundedness": 1.0, "latency_ms": 0},
        composite_profile_id="engineering_v1",
    )
    assert full["incomplete"] is False
    assert full["score"] is not None
    assert full["missing_families"] == []
