"""W10 Knowledge Migration：双写 / 对账 / 回滚演练最小门。"""
from __future__ import annotations

from core.harness.knowledge_pipeline import knowledge_migration as km


def test_dual_write_reconcile_ok(tmp_path):
    db = str(tmp_path / "mig.db")
    job = km.start_migration_job(
        tenant_id="t1", domain="lock-service", db_path=db
    )
    assert job["status"] == "created"
    assert job["read_pointer"] == "source"
    assert job["process_cutover_authorized"] is False

    w = km.dual_write_record(
        job["job_id"],
        tenant_id="t1",
        record_key="obj:1",
        payload={"name": "lock-a", "status": "active"},
        db_path=db,
    )
    assert w["status"] == "ok"
    assert w["source_ok"] is True
    assert w["target_ok"] is True

    recon = km.reconcile_migration(job["job_id"], tenant_id="t1", db_path=db)
    assert recon["ok"] is True
    assert recon["missing"] == []
    assert recon["orphans"] == []
    assert recon["stale"] == []


def test_partial_dual_write_repair(tmp_path):
    db = str(tmp_path / "mig.db")
    job = km.start_migration_job(
        tenant_id="t1", domain="lock-service", db_path=db
    )
    jid = job["job_id"]
    km.dual_write_record(
        jid,
        tenant_id="t1",
        record_key="obj:miss",
        payload={"v": 1},
        fail_target=True,
        db_path=db,
    )
    drift = km.reconcile_migration(jid, tenant_id="t1", db_path=db)
    assert drift["ok"] is False
    assert "obj:miss" in drift["missing"]

    fixed = km.reconcile_migration(jid, tenant_id="t1", repair=True, db_path=db)
    assert fixed["ok"] is True
    assert fixed["repaired"]["inserted"] == 1


def test_stale_and_orphan_repair(tmp_path):
    db = str(tmp_path / "mig.db")
    job = km.start_migration_job(
        tenant_id="t1", domain="lock-service", db_path=db
    )
    jid = job["job_id"]
    km.dual_write_record(
        jid,
        tenant_id="t1",
        record_key="obj:stale",
        payload={"v": 1},
        db_path=db,
    )
    # 只更新 source，制造 stale
    km.dual_write_record(
        jid,
        tenant_id="t1",
        record_key="obj:stale",
        payload={"v": 2},
        fail_target=True,
        db_path=db,
    )
    # 仅写 target → orphan
    km.write_store_record(
        jid,
        tenant_id="t1",
        store="target",
        record_key="obj:orphan",
        payload={"orphan": True},
        db_path=db,
    )

    drift = km.reconcile_migration(jid, tenant_id="t1", db_path=db)
    assert drift["ok"] is False
    assert any(s["record_key"] == "obj:stale" for s in drift["stale"])
    assert "obj:orphan" in drift["orphans"]

    fixed = km.reconcile_migration(jid, tenant_id="t1", repair=True, db_path=db)
    assert fixed["ok"] is True
    assert fixed["repaired"]["updated"] >= 1
    assert fixed["repaired"]["deleted_orphans"] == 1


def test_shadow_read_blocked_until_reconcile_then_rollback(tmp_path):
    db = str(tmp_path / "mig.db")
    job = km.start_migration_job(
        tenant_id="t1", domain="lock-service", db_path=db
    )
    jid = job["job_id"]
    km.dual_write_record(
        jid,
        tenant_id="t1",
        record_key="obj:1",
        payload={"ok": True},
        fail_target=True,
        db_path=db,
    )
    blocked = km.set_read_pointer(
        jid, tenant_id="t1", pointer="target", db_path=db
    )
    assert blocked["status"] == "blocked"
    assert blocked["error"] == "reconcile_not_ok"

    km.reconcile_migration(jid, tenant_id="t1", repair=True, db_path=db)
    shadow = km.set_read_pointer(
        jid, tenant_id="t1", pointer="target", db_path=db
    )
    assert shadow["status"] == "ok"
    assert shadow["read_pointer"] == "target"
    assert shadow["phase"] == "shadow_read"
    assert shadow["process_cutover_authorized"] is False

    drill = km.record_rollback_drill(
        jid, tenant_id="t1", note="pilot-drill", db_path=db
    )
    assert drill["status"] == "ok"
    assert drill["job"]["read_pointer"] == "source"
    assert drill["job"]["phase"] == "rollback_drill"
    assert drill["drill"]["data_loss"] is False


def test_cross_tenant_hidden(tmp_path):
    db = str(tmp_path / "mig.db")
    job = km.start_migration_job(
        tenant_id="t1", domain="lock-service", db_path=db
    )
    assert km.get_migration_job(job["job_id"], tenant_id="t2", db_path=db) is None
    assert (
        km.dual_write_record(
            job["job_id"],
            tenant_id="t2",
            record_key="x",
            payload={"a": 1},
            db_path=db,
        )["status"]
        == "not_found"
    )
