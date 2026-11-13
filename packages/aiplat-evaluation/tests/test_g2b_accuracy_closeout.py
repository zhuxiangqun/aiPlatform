"""G2b accuracy closeout — adjudicated gold + Wilson CI (claim locked)."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.scoring.g2b_accuracy import build_gold, wilson_ci

ROOT = Path(__file__).resolve().parents[1]


def test_wilson_ci_bounds():
    lo, hi = wilson_ci(23, 30)
    assert lo is not None and hi is not None
    assert 0.0 <= lo <= hi <= 1.0
    assert lo < 23 / 30 < hi


def test_build_gold_agreements_and_disputes():
    la = {"t1": True, "t2": False, "t3": True}
    lb = {"t1": True, "t2": False, "t3": False}
    adj = {"t3": {"task_id": "t3", "gold_pass": True}}
    gold, agreed, disputed = build_gold(la, lb, adj)
    assert agreed == ["t1", "t2"]
    assert disputed == ["t3"]
    assert gold == {"t1": True, "t2": False, "t3": True}


def test_missing_adjudication_raises():
    with pytest.raises(SystemExit):
        build_gold({"t1": True}, {"t1": False}, {})


def test_committed_evidence_honesty():
    evid = ROOT / "docs" / "a3" / "evidence"
    agg = json.loads((evid / "g2b_accuracy_aggregate.v1.json").read_text(encoding="utf-8"))
    adj = json.loads((evid / "g2b_adjudication.v1.json").read_text(encoding="utf-8"))
    assert agg["accuracy_claim"] is False
    assert agg["n"] == 100
    assert agg["pass_n"] == 78
    assert agg["pass_rate"] == 0.78
    assert agg["disputed_n"] == 10
    assert len(adj["disputes"]) == 10
    assert agg["wilson_ci95"][0] < 0.70  # §4 CI_lo still unmet
    assert adj.get("pending_human_confirm") is False
    assert adj.get("human_confirm", {}).get("status") == "confirmed"
