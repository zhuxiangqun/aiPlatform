"""prod_live_summarize — commit-safe aggregate from drill JSON."""
from __future__ import annotations

import importlib.util
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "prod_live_summarize",
    ROOT / "scripts" / "prod_live_summarize.py",
)
mod = importlib.util.module_from_spec(SPEC)
assert SPEC and SPEC.loader
SPEC.loader.exec_module(mod)


def test_summarize_latency_and_honesty():
    drill = {
        "gate_ok": True,
        "prod_model": "qwen2.5-coder:7b",
        "task_count": 2,
        "repeats": 3,
        "llm_ok_n": 6,
        "total_cost_estimate": 0.01,
        "cost_ok": True,
        "provider": {"model": "qwen2.5-coder:7b", "base_url": "http://127.0.0.1:11434/v1"},
        "runs": [
            {
                "mode_label": "live_r1",
                "status": "succeeded",
                "ok": True,
                "audit": {"latency_ms": 100, "tokens_out": 5, "tokens_in": 10, "cost_estimate": 0.001},
            },
            {
                "mode_label": "live_r2",
                "status": "succeeded",
                "ok": True,
                "audit": {"latency_ms": 200, "tokens_out": 7, "tokens_in": 11, "cost_estimate": 0.001},
            },
            {"mode_label": "stub", "status": "succeeded", "ok": True, "audit": {}},
        ],
    }
    agg = mod.summarize_prod_live(drill)
    assert agg["accuracy_claim"] is False
    assert agg["process_split_authorized"] is False
    assert agg["live_attempt_n"] == 2
    assert agg["latency_ms"]["p50"] is not None
    assert agg["gate_ok"] is True
