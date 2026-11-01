"""EVAL_V1 G2c — intra-rater self-consistency (never accuracy / never G2b)."""
from __future__ import annotations

from pathlib import Path

from core.apps.eval.service.g2a import adjudicate_label, lock_v0, preannotate_review_queue
from core.apps.eval.service.g2c import (
    G2C_RETEST_ANNOTATOR,
    cohen_kappa_binary,
    compute_g2c_report,
    g2c_status,
    list_g2c_retest_queue,
    record_g2c_retest,
)
from core.apps.eval.service.gold_bootstrap import E3_V0_LOCK_TARGET, bootstrap_e3_gold
from core.apps.eval.service.store import EvalStore


def test_cohen_kappa_perfect_and_chance():
    perfect = cohen_kappa_binary([(True, True), (False, False), (True, True), (False, False)])
    assert perfect["n"] == 4
    assert perfect["agreement"] == 1.0
    assert perfect["intra_rater_kappa"] == 1.0

    # all agree on pass → pe=1 → κ defined as 1.0 when agree==1
    all_pass = cohen_kappa_binary([(True, True)] * 5)
    assert all_pass["intra_rater_kappa"] == 1.0

    empty = cohen_kappa_binary([])
    assert empty["intra_rater_kappa"] is None
    assert empty["agreement"] is None


def test_cohen_kappa_disagreement():
    # classic mismatch: half agree
    pairs = [(True, True), (True, False), (False, True), (False, False)]
    out = cohen_kappa_binary(pairs)
    assert out["n"] == 4
    assert out["agreement"] == 0.5
    assert out["intra_rater_kappa"] == 0.0


def test_g2c_retest_report_honesty(tmp_path):
    db = tmp_path / "g2c.sqlite3"
    seed = (
        Path(__file__).resolve().parents[3]
        / "workspace_seeds"
        / "eval"
        / "code_review_gold"
    )
    boot = bootstrap_e3_gold(
        tenant_id="g2c-unit", gold_dir=str(seed), db_path=str(db)
    )
    preannotate_review_queue(tenant_id="g2c-unit", db_path=str(db))
    store = EvalStore(db_path=db)
    pending = store.list_labels(
        set_id=boot["set_id"], adjudicated=False, limit=E3_V0_LOCK_TARGET
    )
    for lab in pending[:E3_V0_LOCK_TARGET]:
        sug = (lab.get("label") or {}).get("ai_preannotate") or {}
        adjudicate_label(
            lab["id"],
            passed=bool(sug.get("pass", True)),
            notes="g2c unit solo",
            tenant_id="g2c-unit",
            db_path=str(db),
        )
    locked = lock_v0(tenant_id="g2c-unit", db_path=str(db))
    assert locked["ok"] is True

    st0 = g2c_status(tenant_id="g2c-unit", db_path=str(db))
    assert st0["accuracy_claim"] is False
    assert st0["claim_kind"] == "self_consistency"
    assert st0["kappa_kind"] == "intra_rater"
    assert st0["v0_locked"] is True

    queue = list_g2c_retest_queue(tenant_id="g2c-unit", limit=10, db_path=str(db))
    assert queue["total"] >= 10
    assert queue["accuracy_claim"] is False

    # Retest first 8 matching primary; flip 2 to create partial κ
    for i, item in enumerate(queue["pending"][:8]):
        passed = bool(item.get("primary_pass", True))
        if i < 2:
            passed = not passed
        out = record_g2c_retest(
            item["task_id"],
            passed=passed,
            notes="unit retest",
            tenant_id="g2c-unit",
            db_path=str(db),
        )
        assert out["ok"] is True
        assert out["accuracy_claim"] is False
        assert out["label"]["annotator"] == G2C_RETEST_ANNOTATOR

    report = compute_g2c_report(tenant_id="g2c-unit", db_path=str(db), persist=True)
    assert report["ok"] is True
    assert report["accuracy_claim"] is False
    assert report["claim_kind"] == "self_consistency"
    assert report["kappa_kind"] == "intra_rater"
    assert report["n_paired"] == 8
    assert report["intra_rater_kappa"] is not None
    note = (report.get("note") or "").lower()
    assert "not inter-annotator" in note
    assert "self-consistency" in note
    assert report.get("kappa_kind") == "intra_rater"

    st1 = g2c_status(tenant_id="g2c-unit", db_path=str(db))
    assert st1["paired_count"] == 8
    assert st1["g2c_ready"] is True
