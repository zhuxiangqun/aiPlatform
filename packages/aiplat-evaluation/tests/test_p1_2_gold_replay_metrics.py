"""P1.2 — code_review_gold / replay_trace emit P1 families; accuracy empty."""
from __future__ import annotations

from app.worker.runners import execute_runner


def test_code_review_gold_p1_metrics():
    out = execute_runner(
        {
            "job_id": "g1",
            "runner_id": "code_review_gold",
            "payload": {"findings": ["bug-a", "bug-b"], "gold": ["bug-a", "bug-b"]},
        }
    )
    assert out["ok"] is True
    assert out["accuracy_claim"] is False
    m = out["metrics"]
    assert m["exact_match"] == 1.0
    assert m["coverage"] == 1.0
    assert "groundedness" in m
    assert "content_safety" in m
    assert "accuracy" not in m
    assert out["scoring"]["families"]["accuracy"] == {}


def test_replay_trace_p1_metrics():
    out = execute_runner(
        {
            "job_id": "r1",
            "runner_id": "replay_trace",
            "payload": {
                "trace": {"ok": True, "steps": [{}, {}], "duration_ms": 12},
                "expected": {"ok": True},
            },
        }
    )
    assert out["ok"] is True
    assert out["accuracy_claim"] is False
    m = out["metrics"]
    assert m["steps"] == 2.0
    assert m["latency_ms"] == 12.0
    assert "accuracy" not in m
    assert "latency_ms" in out["scoring"]["families"]["efficiency"]
    assert out["scoring"]["families"]["accuracy"] == {}
