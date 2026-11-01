"""EVAL_V1 E3 — gold bootstrap ≥15 + review queue (no κ)."""
from __future__ import annotations

from pathlib import Path

from core.apps.eval.service.gold_bootstrap import (
    E3_MIN_RUNNABLE,
    bootstrap_e3_gold,
    e3_status,
)


def test_bootstrap_e3_meets_runnable_gate(tmp_path):
    db = tmp_path / "e3.sqlite3"
    seed = (
        Path(__file__).resolve().parents[3]
        / "workspace_seeds"
        / "eval"
        / "code_review_gold"
    )
    out = bootstrap_e3_gold(
        tenant_id="e3-unit",
        gold_dir=str(seed),
        db_path=str(db),
    )
    assert out["ok"] is True
    assert out["task_count"] >= E3_MIN_RUNNABLE
    assert out["runnable_gate"] is True
    assert out["v0_locked"] is False
    assert out["labels_created"] >= E3_MIN_RUNNABLE

    st = e3_status(tenant_id="e3-unit", db_path=str(db))
    assert st["runnable_gate"] is True
    assert st["kappa"] is None
    assert st["labels_pending"] >= E3_MIN_RUNNABLE
    # idempotent second pass creates 0 new labels
    out2 = bootstrap_e3_gold(
        tenant_id="e3-unit",
        gold_dir=str(seed),
        db_path=str(db),
    )
    assert out2["labels_created"] == 0


def test_e3_source_inventory_exists():
    root = Path(__file__).resolve().parents[4]
    inv = root / "reports/five-products/ops/EVAL_V1_E3_GOLD_SOURCES.md"
    assert inv.is_file()
    text = inv.read_text(encoding="utf-8")
    assert "≥15" in text or ">=15" in text or "E3" in text
    assert "code-review-gold" in text
    assert "solo" in text.lower() or "D5" in text
