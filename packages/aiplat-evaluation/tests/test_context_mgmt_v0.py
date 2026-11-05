"""P2-1 context_mgmt v0 — fixture scoring + pack gate."""
from __future__ import annotations

import json
from pathlib import Path

from app.scoring.context_mgmt import KINDS, score_case, score_pack
from app.worker.runners import execute_runner

ROOT = Path(__file__).resolve().parents[1]
PACK = ROOT / "docs/a3/context_tasks.v0.json"


def test_kinds_cover_four_axes():
    assert set(KINDS) == {
        "long_context_recall",
        "summary_fidelity",
        "conflict",
        "truncation_degradation",
    }


def test_score_case_pass_and_fail():
    ok = score_case(
        {
            "case_id": "t1",
            "kind": "long_context_recall",
            "actual": "ZX-4419",
            "must_contain": ["ZX-4419"],
        }
    )
    assert ok["ok"] is True
    bad = score_case(
        {
            "case_id": "t2",
            "kind": "conflict",
            "actual": "4",
            "must_contain": ["8"],
            "must_not_contain": ["4"],
        }
    )
    assert bad["ok"] is False


def test_pack_pass_and_missing_kind():
    pack = json.loads(PACK.read_text(encoding="utf-8"))
    dim = score_pack(pack["cases"], pack_id=pack["schema"])
    assert dim["context_pass"] is True
    assert dim["accuracy_claim"] is False
    assert not dim["kinds_missing"]

    only_recall = [c for c in pack["cases"] if c["kind"] == "long_context_recall"]
    dim2 = score_pack(only_recall, pack_id="partial")
    assert dim2["context_pass"] is False
    assert "conflict" in dim2["kinds_missing"]


def test_runner_pack_and_single():
    pack = json.loads(PACK.read_text(encoding="utf-8"))
    out = execute_runner(
        {
            "job_id": "ctx-pack",
            "runner_id": "context_mgmt",
            "payload": {"cases": pack["cases"], "pack_id": "v0"},
        }
    )
    assert out["ok"] is True
    assert out["accuracy_claim"] is False
    assert out["mode"] == "context_mgmt_v0"
    assert out["metrics"]["context_pass"] == 1.0

    case = pack["cases"][0]
    one = execute_runner(
        {"job_id": "ctx-one", "runner_id": "context_mgmt", "payload": case}
    )
    assert one["ok"] is True
