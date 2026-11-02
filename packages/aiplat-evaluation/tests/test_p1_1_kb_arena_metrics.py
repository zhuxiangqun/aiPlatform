"""P1.1 — kb_rag / arena emit P1 family metrics; accuracy stays empty."""
from __future__ import annotations

from app.worker.runners import execute_runner


def test_kb_rag_p1_metrics():
    out = execute_runner(
        {
            "job_id": "kb1",
            "runner_id": "kb_rag",
            "payload": {
                "query": "cat sat",
                "hits": [{"id": "1", "text": "the cat sat on the mat"}],
                "expected_ids": ["1"],
            },
        }
    )
    assert out["ok"] is True
    assert out["accuracy_claim"] is False
    m = out["metrics"]
    assert m["hit_count"] == 1.0
    assert "groundedness" in m
    assert m["groundedness"] > 0.0
    assert "text_quality" in m
    assert "content_safety" in m
    assert "accuracy" not in m
    assert out["scoring"]["families"]["accuracy"] == {}
    assert "groundedness" in out["scoring"]["families"]["quality"]


def test_arena_p1_metrics():
    out = execute_runner(
        {
            "job_id": "ar1",
            "runner_id": "arena",
            "payload": {
                "response_a": "longer answer here",
                "response_b": "short",
                "prefer": "a",
            },
        }
    )
    assert out["ok"] is True
    assert out["accuracy_claim"] is False
    m = out["metrics"]
    assert m["winner"] == "a"
    assert "text_quality" in m
    assert "content_safety" in m
    assert "accuracy" not in m
    assert out["scoring"]["families"]["accuracy"] == {}
