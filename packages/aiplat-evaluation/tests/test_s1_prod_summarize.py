"""s1_prod_summarize — commit-safe aggregate honesty."""
from __future__ import annotations

import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "s1_prod_summarize",
    ROOT / "scripts" / "s1_prod_summarize.py",
)
mod = importlib.util.module_from_spec(SPEC)
assert SPEC and SPEC.loader
SPEC.loader.exec_module(mod)


def test_summarize_s1_prod_honesty():
    drill = {
        "ok": True,
        "suite_id": "s1_live_attacks.v0",
        "cases": 25,
        "asr": 0.11,
        "leak_rate": 0.33,
        "false_refusal_rate": 0.0,
        "llm_ok_n": 25,
        "llm_fail_n": 0,
        "prod_model": "qwen2.5-coder:7b",
    }
    agg = mod.summarize_s1_prod(drill)
    assert agg["accuracy_claim"] is False
    assert agg["not_security_certification"] is True
    assert agg["process_split_authorized"] is False
    assert agg["gate_ok"] is True
    assert agg["prod_model"] == "qwen2.5-coder:7b"
    assert agg["asr"] == 0.11
