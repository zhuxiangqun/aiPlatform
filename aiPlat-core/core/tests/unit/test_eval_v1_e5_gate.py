"""EVAL_V1 E5 — failure taxonomy + local engineering gate (no accuracy claim)."""
from __future__ import annotations

from pathlib import Path

from core.apps.eval.service.gate_v1 import (
    SCHEMA_VERSION,
    classify_failure,
    run_e5_gate,
)
from core.apps.eval.service.gold_bootstrap import bootstrap_e3_gold


def test_classify_failure_buckets():
    assert classify_failure({"pass": True, "score": 1.0, "evidence": {}}) == "none"
    assert (
        classify_failure({"pass": False, "score": 0.0, "evidence": {"fn": 2, "fp": 0, "tp": 0}})
        == "miss_gold"
    )
    assert (
        classify_failure({"pass": False, "score": 0.0, "evidence": {"fn": 0, "fp": 2, "tp": 0}})
        == "false_alarm"
    )
    assert (
        classify_failure({"pass": False, "score": 0.5, "evidence": {"fn": 1, "fp": 1, "tp": 1}})
        == "partial_match"
    )


def test_e5_pr_gate_on_seed_gold(tmp_path):
    db = tmp_path / "e5.sqlite3"
    seed = (
        Path(__file__).resolve().parents[3]
        / "workspace_seeds"
        / "eval"
        / "code_review_gold"
    )
    boot = bootstrap_e3_gold(
        tenant_id="e5-unit", gold_dir=str(seed), db_path=str(db)
    )
    assert boot["runnable_gate"] is True
    out = run_e5_gate(
        mode="pr",
        tenant_id="e5-unit",
        set_id=boot["set_id"],
        limit=15,
        db_path=str(db),
    )
    assert out["ok"] is True
    assert out["mode"] == "pr"
    assert out["accuracy_claim"] is False
    assert out["gate_claim"] is False
    assert out["decision"] in ("pass", "fail", "advisory_pass")
    m = out["metrics"]
    assert m["schema_version"] == SCHEMA_VERSION
    assert m["accuracy_claim"] is False
    assert m["gate_claim"] is False
    assert m["kappa"] is None
    assert m["regression_detection_rate"] >= 0.7
    # measured path (not hard-coded): uncorrupted inject cohort should not false-block
    assert m["false_block_rate"] == 0.0
    assert m["regression_injected"] >= 1
    assert "failure_taxonomy" in m
    assert out["gate_id"]
    assert out["report_id"]

    from core.apps.eval.service.store import EvalStore

    store = EvalStore(db_path=db)
    gate = store.get_gate(out["gate_id"])
    assert gate is not None
    assert gate["decision"] == out["decision"]
    assert store.list_gates(limit=5)


def test_e5_release_advisory_without_v0_lock(tmp_path):
    db = tmp_path / "e5r.sqlite3"
    seed = (
        Path(__file__).resolve().parents[3]
        / "workspace_seeds"
        / "eval"
        / "code_review_gold"
    )
    boot = bootstrap_e3_gold(
        tenant_id="e5-rel", gold_dir=str(seed), db_path=str(db)
    )
    out = run_e5_gate(
        mode="release",
        tenant_id="e5-rel",
        set_id=boot["set_id"],
        limit=20,
        db_path=str(db),
    )
    assert out["gate_claim"] is False
    assert out["accuracy_claim"] is False
    # v0 not locked → cannot be a release claim; pass becomes advisory_pass
    if out["engineering_pass"]:
        assert out["decision"] == "advisory_pass"


def test_gate_schema_exists():
    root = Path(__file__).resolve().parents[4]
    p = root / "packages/aiplat-evaluation/contracts/schemas/eval_gate.schema.json"
    assert p.is_file()
    assert "eval.gate.v0" in p.read_text(encoding="utf-8")
