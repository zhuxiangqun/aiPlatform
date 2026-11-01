"""EVAL_V1 G2a — solo adjudicate → lock v0 → local gate_claim (no accuracy)."""
from __future__ import annotations

from pathlib import Path

from core.apps.eval.service.g2a import (
    adjudicate_label,
    g2a_status,
    lock_v0,
    preannotate_review_queue,
    run_g2a_gate,
)
from core.apps.eval.service.gold_bootstrap import E3_V0_LOCK_TARGET, bootstrap_e3_gold
from core.apps.eval.service.store import EvalStore


def test_g2a_lock_and_gate_claim(tmp_path):
    db = tmp_path / "g2a.sqlite3"
    seed = (
        Path(__file__).resolve().parents[3]
        / "workspace_seeds"
        / "eval"
        / "code_review_gold"
    )
    boot = bootstrap_e3_gold(
        tenant_id="g2a-unit", gold_dir=str(seed), db_path=str(db)
    )
    assert boot["task_count"] >= E3_V0_LOCK_TARGET

    # Cannot lock without adjudication
    blocked = lock_v0(tenant_id="g2a-unit", db_path=str(db))
    assert blocked["ok"] is False
    assert blocked["error"] == "v0_lock_not_ready"

    pre = preannotate_review_queue(tenant_id="g2a-unit", db_path=str(db))
    assert pre["adjudicated"] is False
    assert pre["updated"] >= E3_V0_LOCK_TARGET

    store = EvalStore(db_path=db)
    pending = store.list_labels(
        set_id=boot["set_id"], adjudicated=False, limit=E3_V0_LOCK_TARGET
    )
    assert len(pending) >= E3_V0_LOCK_TARGET
    for lab in pending[:E3_V0_LOCK_TARGET]:
        sug = (lab.get("label") or {}).get("ai_preannotate") or {}
        adjudicate_label(
            lab["id"],
            passed=bool(sug.get("pass", True)),
            notes="unit solo review",
            tenant_id="g2a-unit",
            db_path=str(db),
        )

    st = g2a_status(tenant_id="g2a-unit", db_path=str(db))
    assert st["v0_lock_ready"] is True
    assert st["v0_locked"] is False
    assert st["accuracy_claim"] is False
    assert st["kappa"] is None

    locked = lock_v0(tenant_id="g2a-unit", db_path=str(db))
    assert locked["ok"] is True
    assert locked["v0_locked"] is True
    assert locked["accuracy_claim"] is False

    st2 = g2a_status(tenant_id="g2a-unit", db_path=str(db))
    assert st2["v0_locked"] is True
    assert st2["g2a_ready"] is True

    out = run_g2a_gate(
        mode="nightly",
        tenant_id="g2a-unit",
        set_id=boot["set_id"],
        limit=20,
        db_path=str(db),
    )
    assert out["ok"] is True
    assert out["accuracy_claim"] is False
    assert out["kappa"] is None
    if out.get("engineering_pass"):
        assert out["gate_claim"] is True
        assert out["decision"] == "pass"


def test_g2a_gate_requires_lock(tmp_path):
    db = tmp_path / "g2a2.sqlite3"
    seed = (
        Path(__file__).resolve().parents[3]
        / "workspace_seeds"
        / "eval"
        / "code_review_gold"
    )
    bootstrap_e3_gold(tenant_id="g2a-nolock", gold_dir=str(seed), db_path=str(db))
    out = run_g2a_gate(mode="pr", tenant_id="g2a-nolock", db_path=str(db))
    assert out["ok"] is False
    assert out["error"] == "v0_not_locked"
    assert out["gate_claim"] is False
