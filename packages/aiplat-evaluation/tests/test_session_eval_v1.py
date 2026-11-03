"""session_eval multi-turn v1 (5–8 turns)."""
from __future__ import annotations

import json
from pathlib import Path

from app.scoring.session import MAX_TURNS_V1, MIN_TURNS_V1, normalize_turns, session_dimension
from app.worker.runners import execute_runner

ROOT = Path(__file__).resolve().parents[1]
PACK = ROOT / "docs/a3/session_tasks.v1.json"


def test_v1_bounds_and_clamp():
    assert MIN_TURNS_V1 == 5
    assert MAX_TURNS_V1 == 8
    assert len(normalize_turns([{"prompt": "a"}] * 12, profile="v1")) == MAX_TURNS_V1
    dim = session_dimension(
        turns=[{"prompt": "a"}] * 5,
        turn_oks=[True] * 5,
        session_id="s",
        profile="v1",
    )
    assert dim["schema"] == "eval.scoring.session.v1"
    assert dim["profile"] == "v1"
    assert dim["session_pass"] is True
    assert dim["accuracy_claim"] is False


def test_v1_requires_min_turns():
    out = execute_runner(
        {
            "job_id": "v1-short",
            "runner_id": "session_eval",
            "payload": {
                "profile": "v1",
                "turns": [{"prompt": "a", "actual": "x"}] * 3,
            },
        }
    )
    assert out["ok"] is False
    assert "5" in out["detail"]
    assert out["mode"] == "session_v1"


def test_v1_pack_pass():
    pack = json.loads(PACK.read_text(encoding="utf-8"))
    sess = pack["sessions"][0]
    out = execute_runner(
        {
            "job_id": "v1-pack",
            "runner_id": "session_eval",
            "payload": sess,
        }
    )
    assert out["ok"] is True
    assert out["scoring"]["dimensions"]["session"]["profile"] == "v1"
    assert out["metrics"]["turns_n"] >= 5


def test_v1_infer_profile_from_length():
    turns = [{"prompt": str(i), "expected": str(i), "actual": str(i)} for i in range(6)]
    out = execute_runner(
        {
            "job_id": "v1-infer",
            "runner_id": "session_eval",
            "payload": {"session_id": "infer", "turns": turns},
        }
    )
    assert out["scoring"]["dimensions"]["session"]["profile"] == "v1"
    assert out["ok"] is True
