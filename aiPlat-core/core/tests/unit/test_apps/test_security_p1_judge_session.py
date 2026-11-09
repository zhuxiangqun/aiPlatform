"""P1-2: judge calibration session + dual-review (importlib; avoid Py3.9 eval package import)."""
from __future__ import annotations

import importlib.util
import sys
import types
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[4]
CALIB_PATH = ROOT / "core" / "apps" / "eval" / "service" / "security_judge_calib.py"
SESS_PATH = ROOT / "core" / "apps" / "eval" / "service" / "security_p1_judge_session.py"


def _ensure_pkg(name: str) -> None:
    if name not in sys.modules:
        sys.modules[name] = types.ModuleType(name)


def _load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    assert spec.loader is not None
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture(scope="module")
def p12():
    for pkg in (
        "core",
        "core.apps",
        "core.apps.eval",
        "core.apps.eval.service",
    ):
        _ensure_pkg(pkg)
    calib = _load("core.apps.eval.service.security_judge_calib", CALIB_PATH)
    sys.modules["core.apps.eval.service.security_judge_calib"] = calib
    return _load("core.apps.eval.service.security_p1_judge_session", SESS_PATH)


def test_empty_session_honesty_locks(p12):
    s = p12.empty_session()
    assert s["schema"] == "eval.security_p1_2_judge_session.v1"
    assert s["accuracy_claim"] is False
    assert s["security_certification"] is False
    assert s["pairs"] == []


def test_disagree_queues_dual_review(p12, tmp_path: Path):
    path = tmp_path / "session.json"
    s = p12.empty_session()
    p12.record_judge_gold_pair(s, case_id="c1", gold=True, judge=False)
    p12.record_judge_gold_pair(s, case_id="c2", gold=True, judge=True)
    p12.save_session(s, path)
    loaded = p12.load_session(path)
    assert p12.failure_case_ids(loaded) == ["c1"]
    assert "c1" in loaded["dual_reviews"]
    assert p12.dual_human_completed(loaded) is False


def test_dual_review_a_b_agree(p12):
    s = p12.empty_session()
    p12.record_judge_gold_pair(s, case_id="f1", gold=True, judge=False)
    p12.submit_dual_review(s, case_id="f1", reviewer="alice", slot="a", label=True)
    p12.submit_dual_review(s, case_id="f1", reviewer="bob", slot="b", label=True)
    assert p12.dual_human_completed(s) is True
    assert s["dual_reviews"]["f1"]["final_label"] is True
    report = p12.evaluate_p1_2_session(s)
    assert report["dual_human_completed"] is True
    assert report["pending_dual_review"] == []
    assert report["accuracy_claim"] is False
    assert report["security_certification"] is False


def test_arbiter_required_when_a_neq_b(p12):
    s = p12.empty_session()
    p12.record_judge_gold_pair(s, case_id="f1", gold=True, judge=False)
    p12.submit_dual_review(s, case_id="f1", reviewer="a", slot="a", label=True)
    p12.submit_dual_review(s, case_id="f1", reviewer="b", slot="b", label=False)
    assert s["dual_reviews"]["f1"].get("needs_arbiter") is True
    assert p12.dual_human_completed(s) is False
    p12.submit_dual_review(s, case_id="f1", reviewer="arb", slot="arbiter", label=True)
    assert p12.dual_human_completed(s) is True
    assert s["dual_reviews"]["f1"]["final_label"] is True


def test_invalid_slot_rejected(p12):
    s = p12.empty_session()
    with pytest.raises(p12.SecurityP12SessionError, match="slot_must"):
        p12.submit_dual_review(s, case_id="x", reviewer="r", slot="c", label=True)


def test_perfect_pairs_engineering_bar(p12):
    s = p12.empty_session()
    for i in range(10):
        label = i % 2 == 0
        p12.record_judge_gold_pair(s, case_id=f"c{i}", gold=label, judge=label)
    out = p12.evaluate_p1_2_session(s)
    assert out["session_status"] == "calibrated_engineering"
    assert out["calibration"]["meets_engineering_bar"] is True
    assert out["l5_eligible"] is False
