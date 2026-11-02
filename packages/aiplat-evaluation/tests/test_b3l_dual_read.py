"""B3-L.2 — local dual-read reconcile + read pointer rollback."""
from __future__ import annotations

from pathlib import Path

from app.migrate.dual_read import (
    canonical_metrics_hash,
    etl_copy_sets_reports,
    inventory_store,
    read_read_pointer,
    reconcile_inventories,
    write_read_pointer,
)
from app.store import open_store
from app.store.store import create_report, create_set


def test_canonical_metrics_hash_stable():
    a = canonical_metrics_hash({"b": 2, "a": 1})
    b = canonical_metrics_hash({"a": 1, "b": 2})
    assert a == b
    assert a != canonical_metrics_hash({"a": 1})


def test_etl_and_reconcile_ok(tmp_path: Path):
    src = open_store(f"sqlite:///{tmp_path / 'src.sqlite3'}", migrate=True)
    dst = open_store(f"sqlite:///{tmp_path / 'dst.sqlite3'}", migrate=True)
    create_set(src, name="s1", set_id="set_1", tenant_id="t1", meta={"k": 1})
    create_report(
        src,
        report_id="rpt_1",
        metrics={"score": 1.0},
        tenant_id="t1",
    )
    etl = etl_copy_sets_reports(src, dst, tenant_id="t1")
    assert etl["copied_sets"] == 1
    assert etl["copied_reports"] == 1
    rec = reconcile_inventories(
        inventory_store(src, tenant_id="t1", label="s"),
        inventory_store(dst, tenant_id="t1", label="d"),
    )
    assert rec["ok"] is True
    assert rec["process_split_authorized"] is False


def test_reconcile_detects_hash_mismatch(tmp_path: Path):
    src = open_store(f"sqlite:///{tmp_path / 'src2.sqlite3'}", migrate=True)
    dst = open_store(f"sqlite:///{tmp_path / 'dst2.sqlite3'}", migrate=True)
    create_report(src, report_id="rpt_x", metrics={"score": 1.0}, tenant_id="t")
    create_report(dst, report_id="rpt_x", metrics={"score": 0.0}, tenant_id="t")
    rec = reconcile_inventories(
        inventory_store(src, tenant_id="t"),
        inventory_store(dst, tenant_id="t"),
    )
    assert rec["ok"] is False
    assert rec["hash_mismatches"]


def test_read_pointer_rollback(tmp_path: Path):
    p = tmp_path / "pointer.json"
    write_read_pointer(p, mode="eval", reason="cutover_drill")
    assert read_read_pointer(p)["mode"] == "eval"
    rb = write_read_pointer(p, mode="cohost", reason="rollback")
    assert rb["mode"] == "cohost"
    assert rb["environment"] == "local"
    assert rb["process_split_authorized"] is False
