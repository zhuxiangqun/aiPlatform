"""P1 groundedness (gold-gated) + latency/cost efficiency dimensions."""
from __future__ import annotations

from app.scoring.semantics import (
    efficiency_dimension,
    groundedness_dimension,
    prompt_eval_p1_metrics,
)
from app.worker.runners import execute_runner


def test_groundedness_unscored_without_gold():
    dim = groundedness_dimension(actual="the cat sat", expected="", context="", sources=[])
    assert dim["schema"] == "eval.scoring.groundedness.v0"
    assert dim["accuracy_claim"] is False
    assert dim["gold_present"] is False
    assert dim["scored"] is False
    assert dim["score"] is None
    m = prompt_eval_p1_metrics(actual="the cat sat", expected="", ok=True)
    assert "groundedness" not in m


def test_groundedness_scored_with_context_gold():
    dim = groundedness_dimension(
        actual="cat sat",
        context="the cat sat on the mat",
    )
    assert dim["scored"] is True
    assert dim["score"] is not None and dim["score"] > 0.0
    assert "context" in dim["gold_kinds"]


def test_groundedness_correctness_with_expected():
    dim = groundedness_dimension(actual="paris", expected="paris")
    assert dim["correctness"] == 1.0
    dim2 = groundedness_dimension(actual="london", expected="paris")
    assert dim2["correctness"] == 0.0


def test_efficiency_p50_p95_and_cost_per_success():
    audits = [
        {"latency_ms": 10, "cost_estimate": 0.01},
        {"latency_ms": 20, "cost_estimate": 0.02},
        {"latency_ms": 100, "cost_estimate": 0.03},
        {"latency_ms": 40, "cost_estimate": 0.04},
    ]
    dim = efficiency_dimension(audits, success_flags=[True, True, False, True])
    assert dim["schema"] == "eval.scoring.efficiency.v0"
    assert dim["accuracy_claim"] is False
    assert dim["n_total"] == 4
    assert dim["n_success"] == 3
    assert dim["latency_p50_ms"] is not None
    assert dim["latency_p95_ms"] is not None
    assert dim["latency_p95_ms"] >= dim["latency_p50_ms"]
    assert dim["cost_per_success"] == round((0.01 + 0.02 + 0.03 + 0.04) / 3, 6)


def test_prompt_eval_attaches_dimensions():
    out = execute_runner(
        {
            "job_id": "d1",
            "runner_id": "prompt_eval",
            "payload": {
                "prompt": "say hi",
                "expected": "hi",
                "actual": "hi",
                "context": "hi there friend",
            },
        }
    )
    assert out["accuracy_claim"] is False
    assert out["scoring"]["schema"] == "eval.scoring.semantics.v1"
    assert out["scoring"]["composite"]["schema"] == "eval.scoring.composite.v1"
    g = out["scoring"]["dimensions"]["groundedness"]
    assert g["scored"] is True
    assert g["score"] is not None
    e = out["scoring"]["dimensions"]["efficiency"]
    assert e["schema"] == "eval.scoring.efficiency.v0"


def test_prompt_eval_no_gold_omits_groundedness_metric():
    out = execute_runner(
        {
            "job_id": "d2",
            "runner_id": "prompt_eval",
            "payload": {"prompt": "freeform", "actual": "anything goes"},
        }
    )
    assert "groundedness" not in out["metrics"]
    assert out["scoring"]["dimensions"]["groundedness"]["scored"] is False
    assert "groundedness" not in out["scoring"]["composite"]["scored_metrics"]
