"""EVAL_V1 E4 — judge v1 + k=3 / ECE calibration (no accuracy claim)."""
from __future__ import annotations

from pathlib import Path

from core.apps.eval.service.gold_bootstrap import bootstrap_e3_gold
from core.apps.eval.service.judge_v1 import (
    JUDGE_V1_ID,
    expected_calibration_error,
    run_e4_calibration,
    score_task_match_only,
)


def test_ece_basic():
    # perfectly calibrated mid bin
    pairs = [(0.5, True), (0.5, False), (0.9, True), (0.1, False)]
    out = expected_calibration_error(pairs, n_bins=5)
    assert out["n"] == 4
    assert out["ece"] is not None
    assert 0.0 <= float(out["ece"]) <= 1.0


def test_e4_calibration_on_seed_gold(tmp_path):
    db = tmp_path / "e4.sqlite3"
    seed = (
        Path(__file__).resolve().parents[3]
        / "workspace_seeds"
        / "eval"
        / "code_review_gold"
    )
    boot = bootstrap_e3_gold(
        tenant_id="e4-unit", gold_dir=str(seed), db_path=str(db)
    )
    assert boot["runnable_gate"] is True
    out = run_e4_calibration(
        tenant_id="e4-unit",
        set_id=boot["set_id"],
        k=3,
        limit=20,
        db_path=str(db),
    )
    assert out["ok"] is True
    assert out["judge_id"] == JUDGE_V1_ID
    assert out["accuracy_claim"] is False
    m = out["metrics"]
    assert m["schema_version"] == "eval.calibration.v0"
    assert m["k"] == 3
    assert m["task_count"] >= 1
    assert m["kappa"] is None
    assert m["k_repeat_stdev_gate_v0"] is True  # deterministic → ~0
    assert m["accuracy_claim"] is False
    # sample task scores via judge
    from core.apps.eval.service.store import EvalStore

    store = EvalStore(db_path=db)
    task = store.list_tasks(set_id=boot["set_id"], limit=1)[0]
    scored = score_task_match_only(task)
    assert "score" in scored and "confidence" in scored


def test_calibration_schema_exists():
    root = Path(__file__).resolve().parents[4]
    p = root / "packages/aiplat-evaluation/contracts/schemas/eval_calibration.schema.json"
    assert p.is_file()
    assert "eval.calibration.v0" in p.read_text(encoding="utf-8")
