"""P1 — scoring semantics families; accuracy_claim stays false."""
from __future__ import annotations

from app.scoring.semantics import (
    build_scoring_block,
    classify_metric,
    enrich_runner_result,
    prompt_eval_p1_metrics,
    score_content_safety,
    score_groundedness,
    score_refusal,
    score_text_quality,
)
from app.worker.runners import execute_runner
from app.worker.runners._common import runner_result


def test_classify_metric_families():
    assert classify_metric("exact_match") == "quality"
    assert classify_metric("content_safety") == "safety"
    assert classify_metric("asr") == "security"
    assert classify_metric("latency_ms") == "efficiency"
    assert classify_metric("accuracy") == "accuracy"


def test_scores_and_block_no_accuracy_claim():
    assert score_text_quality(actual="hello world", expected="hello world") == 1.0
    assert score_content_safety(text="hello") == 1.0
    assert score_refusal(text="I cannot help", expect_refusal=True) == 1.0
    assert score_groundedness(actual="cat sat", context="the cat sat on the mat") > 0.0
    block = build_scoring_block(
        {"exact_match": 1.0, "content_safety": 1.0, "asr": 0.0, "latency_ms": 12}
    )
    assert block["accuracy_claim"] is False
    assert block["g2b_unlocked"] is False
    assert "exact_match" in block["families"]["quality"]
    assert "content_safety" in block["families"]["safety"]
    assert "asr" in block["families"]["security"]
    assert "latency_ms" in block["families"]["efficiency"]
    assert block["families"]["accuracy"] == {}


def test_runner_result_enriched():
    out = runner_result(
        runner_id="x",
        job_id="j",
        ok=True,
        metrics={"exact_match": 1.0},
    )
    assert out["accuracy_claim"] is False
    assert out["scoring"]["schema"] == "eval.scoring.semantics.v0"
    assert out["scoring"]["families"]["quality"]["exact_match"] == 1.0


def test_prompt_eval_includes_p1_metrics():
    out = execute_runner(
        {
            "job_id": "j1",
            "runner_id": "prompt_eval",
            "payload": {
                "prompt": "say hi",
                "expected": "hi",
                "actual": "hi",
                "context": "hi there friend",
            },
        }
    )
    assert out["ok"] is True
    assert out["accuracy_claim"] is False
    m = out["metrics"]
    assert m["exact_match"] == 1.0
    assert "text_quality" in m
    assert "content_safety" in m
    assert "groundedness" in m
    assert "refusal" in m
    assert out["scoring"]["families"]["quality"]["text_quality"] == m["text_quality"]
    # Must not invent an accuracy metric
    assert "accuracy" not in m
    assert out["scoring"]["families"]["accuracy"] == {}


def test_prompt_eval_p1_metrics_helper():
    m = prompt_eval_p1_metrics(
        actual="hello",
        expected="hello",
        exact_match=1.0,
        ok=True,
        llm_audit={"latency_ms": 5, "cost_estimate": 0.01},
    )
    assert m["cost_per_success"] == 0.01
    assert m["latency_ms"] == 5.0
    enriched = enrich_runner_result({"metrics": m, "ok": True})
    assert enriched["accuracy_claim"] is False
