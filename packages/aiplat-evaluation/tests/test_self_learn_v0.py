"""P2-3 self_learn v0 — resistance fixtures."""
from __future__ import annotations

import json
from pathlib import Path

from app.scoring.self_learn import KINDS, LearnSim, score_case, score_pack
from app.worker.runners import execute_runner

ROOT = Path(__file__).resolve().parents[1]
PACK = ROOT / "docs/a3/self_learn_tasks.v0.json"


def test_kinds_and_calibration_blocks_writeback():
    assert len(KINDS) == 5
    sim = LearnSim(writeback_authorized=True, calibration_disagree_rate=0.2667)
    assert sim.writeback_authorized is False


def test_bad_feedback_rejected():
    r = score_case(
        {
            "case_id": "t",
            "kind": "bad_feedback",
            "ops": [
                {"op": "seed", "rules": {"safe": True}},
                {"op": "feedback", "malicious": True, "set_rules": {"safe": False}},
            ],
            "expect": {"feedback_applied": False, "rules_true": ["safe"]},
        },
        pack_meta={"writeback_authorized": False, "calibration_disagree_rate": 0.2667},
    )
    assert r["ok"] is True


def test_unauthorized_trusted_feedback_blocked():
    r = score_case(
        {
            "case_id": "t2",
            "kind": "bad_feedback",
            "ops": [
                {"op": "seed", "rules": {"a": True}},
                {"op": "feedback", "trusted": True, "set_rules": {"a": False}},
            ],
            "expect": {"feedback_applied": False, "rules_true": ["a"]},
        },
        pack_meta={"writeback_authorized": False},
    )
    assert r["ok"] is True


def test_pack_and_runner():
    pack = json.loads(PACK.read_text(encoding="utf-8"))
    meta = {
        "writeback_authorized": pack["writeback_authorized"],
        "calibration_disagree_rate": pack["calibration_disagree_rate"],
    }
    dim = score_pack(pack["cases"], pack_id=pack["schema"], pack_meta=meta)
    assert dim["self_learn_pass"] is True, dim
    assert dim["writeback_authorized"] is False

    out = execute_runner(
        {
            "job_id": "sl-pack",
            "runner_id": "self_learn",
            "payload": {
                "cases": pack["cases"],
                "pack_id": "v0",
                "writeback_authorized": False,
                "calibration_disagree_rate": 0.2667,
            },
        }
    )
    assert out["ok"] is True
    assert out["mode"] == "self_learn_v0"
    assert out["accuracy_claim"] is False
