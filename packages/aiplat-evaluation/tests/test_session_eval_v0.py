"""session_eval multi-turn v0 (2–3 turns)."""
from __future__ import annotations

import json
from pathlib import Path

from app.runner_allowlist import classify_runner, is_enqueue_allowed
from app.scoring.session import MAX_TURNS_V0, MIN_TURNS_V0, normalize_turns, session_dimension
from app.worker.runners import execute_runner

ROOT = Path(__file__).resolve().parents[1]
PACK = ROOT / "docs/a3/session_tasks.v0.json"


def test_allowlist_and_clamp():
    assert classify_runner("session_eval") == "allowed"
    assert is_enqueue_allowed("session_eval") is True
    assert len(normalize_turns([{"prompt": "a"}] * 5)) == MAX_TURNS_V0
    dim = session_dimension(
        turns=[{"prompt": "a"}, {"prompt": "b"}],
        turn_oks=[True, False],
        session_id="s",
    )
    assert dim["schema"] == "eval.scoring.session.v0"
    assert dim["accuracy_claim"] is False
    assert dim["turns_n"] == 2
    assert dim["session_pass"] is False


def test_session_eval_requires_min_turns():
    out = execute_runner(
        {
            "job_id": "s0",
            "runner_id": "session_eval",
            "payload": {"turns": [{"prompt": "only one", "actual": "x"}]},
        }
    )
    assert out["ok"] is False
    assert out["accuracy_claim"] is False
    assert f"{MIN_TURNS_V0}" in out["detail"]


def test_session_eval_fixture_pass():
    pack = json.loads(PACK.read_text(encoding="utf-8"))
    sess = pack["sessions"][0]
    out = execute_runner(
        {
            "job_id": "s1",
            "runner_id": "session_eval",
            "payload": sess,
        }
    )
    assert out["ok"] is True
    assert out["accuracy_claim"] is False
    assert out["metrics"]["session_pass"] == 1.0
    assert out["metrics"]["turn_success_rate"] == 1.0
    sdim = out["scoring"]["dimensions"]["session"]
    assert sdim["schema"] == "eval.scoring.session.v0"
    assert sdim["session_pass"] is True
    assert sdim["turns_n"] == 2


def test_session_eval_three_turns_and_fail():
    out = execute_runner(
        {
            "job_id": "s2",
            "runner_id": "session_eval",
            "payload": {
                "session_id": "bad",
                "turns": [
                    {"prompt": "a", "expected": "1", "actual": "1"},
                    {"prompt": "b", "expected": "2", "actual": "2"},
                    {"prompt": "c", "expected": "3", "actual": "nope"},
                ],
            },
        }
    )
    assert out["ok"] is False
    assert out["metrics"]["turns_n"] == 3.0
    assert out["metrics"]["turn_success_rate"] < 1.0
    assert out["scoring"]["dimensions"]["session"]["session_pass"] is False


def test_session_eval_stub_llm_fills_turns(monkeypatch):
    monkeypatch.setenv("AIPLAT_EVAL_LLM", "stub")
    monkeypatch.setenv("AIPLAT_EVAL_LLM_STUB_OUTPUT", "ok")
    out = execute_runner(
        {
            "job_id": "s3",
            "runner_id": "session_eval",
            "payload": {
                "session_id": "llm",
                "turns": [
                    {"prompt": "say ok", "expected": "ok"},
                    {"prompt": "again", "expected": "ok"},
                ],
            },
        }
    )
    assert out["ok"] is True
    assert out["mode"].startswith("session_v0_llm_")
    assert out["evidence"]["llm_audits_n"] == 2
