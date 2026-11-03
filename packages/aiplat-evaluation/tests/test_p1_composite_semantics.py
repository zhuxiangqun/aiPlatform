"""P1 composite — scored vs report-only; accuracy_claim stays false."""
from __future__ import annotations

from app.scoring.composite import build_composite, metric_role
from app.scoring.semantics import build_scoring_block
from app.worker.runners import execute_runner


def test_metric_roles_explicit():
    assert metric_role("text_quality") == "scored"
    assert metric_role("content_safety") == "scored"
    assert metric_role("refusal") == "scored"
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
    assert "asr" in block["report_only_metrics"]
    assert "text_quality" in block["scored_metrics"]
    assert "content_safety" in block["scored_metrics"]
    assert "groundedness" in block["scored_metrics"]


def test_scoring_block_embeds_composite():
    block = build_scoring_block(
        {"exact_match": 1.0, "content_safety": 1.0, "latency_ms": 0, "asr": 0.0}
    )
    assert block["accuracy_claim"] is False
    assert block["composite"]["schema"] == "eval.scoring.composite.v0"
    assert block["metric_roles"]["exact_match"] == "scored"
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
    assert "text_quality" in comp["scored_metrics"]
    assert "content_safety" in comp["scored_metrics"]
