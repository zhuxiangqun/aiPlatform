"""W9 Ontology Package：版本/哈希可验证；兼容矩阵；依赖锁定；回滚。"""
from __future__ import annotations

from core.harness.knowledge_pipeline import ontology_package as op


def test_publish_validate_hash(tmp_path):
    db = str(tmp_path / "pkg.db")
    out = op.publish_package(
        tenant_id="t1",
        package_id="lock-service-ontology",
        version="1.2.0",
        schema=["Ticket", "Person"],
        actions=["ticket.close"],
        functions=["ticket.priority_score"],
        interfaces=["Assignable"],
        dependencies=[{"package": "core-ontology", "version": ">=1.0.0"}],
        compatibility={"backward": ["1.1.0"], "forward": ["1.3.0"]},
        migrations=["001_add_priority"],
        db_path=db,
    )
    assert out["status"] == "published"
    assert out["content_hash"]
    assert out["active"] is True

    # 先发依赖包以满足锁定检查
    op.publish_package(
        tenant_id="t1",
        package_id="core-ontology",
        version="1.0.0",
        schema=["Base"],
        db_path=db,
    )

    v = op.validate_package(
        "lock-service-ontology", tenant_id="t1", version="1.2.0", db_path=db
    )
    assert v["valid"] is True
    assert v["content_hash"] == out["content_hash"]

    # 为什么：payload 被改但旧 hash 保留时，validate 必须 fail closed（不直连 sqlite）
    got = op.get_package("lock-service-ontology", tenant_id="t1", db_path=db)
    assert got is not None
    tampered = dict(got)
    payload = dict(tampered["payload"])
    payload["schema"] = list(payload.get("schema") or []) + ["Hacked"]
    tampered["payload"] = payload
    assert op.compute_content_hash(payload) != tampered["content_hash"]

    import core.harness.knowledge_pipeline.ontology_package as op_mod

    real_get = op_mod.get_package

    def _fake_get(*args, **kwargs):
        return tampered

    op_mod.get_package = _fake_get  # type: ignore[assignment]
    try:
        bad = op.validate_package(
            "lock-service-ontology", tenant_id="t1", version="1.2.0", db_path=db
        )
    finally:
        op_mod.get_package = real_get  # type: ignore[assignment]
    assert bad["valid"] is False
    assert "content_hash_mismatch" in bad["issues"]


def test_compatibility_matrix(tmp_path):
    db = str(tmp_path / "pkg.db")
    op.publish_package(
        tenant_id="t1",
        package_id="p",
        version="1.1.0",
        schema=["A"],
        compatibility={"backward": [], "forward": ["1.2.0"]},
        db_path=db,
    )
    op.publish_package(
        tenant_id="t1",
        package_id="p",
        version="1.2.0",
        schema=["A", "B"],
        compatibility={"backward": ["1.1.0"], "forward": []},
        db_path=db,
    )
    ok = op.check_compatibility(
        "p", tenant_id="t1", from_version="1.1.0", to_version="1.2.0", db_path=db
    )
    assert ok["compatible"] is True
    assert ok["via"] in ("forward", "backward")

    no = op.check_compatibility(
        "p", tenant_id="t1", from_version="1.2.0", to_version="9.9.9", db_path=db
    )
    assert no["status"] == "not_found"


def test_dependency_lock_and_rollback(tmp_path):
    db = str(tmp_path / "pkg.db")
    op.publish_package(
        tenant_id="t1",
        package_id="core-ontology",
        version="1.0.0",
        schema=["Base"],
        db_path=db,
    )
    op.publish_package(
        tenant_id="t1",
        package_id="app",
        version="1.0.0",
        schema=["X"],
        dependencies=[{"package": "core-ontology", "version": ">=1.0.0"}],
        db_path=db,
    )
    lock = op.check_dependency_lock(
        tenant_id="t1", package_id="app", version="1.0.0", db_path=db
    )
    assert lock["satisfied"] is True

    op.publish_package(
        tenant_id="t1",
        package_id="app",
        version="1.1.0",
        schema=["X", "Y"],
        compatibility={"backward": ["1.0.0"]},
        db_path=db,
    )
    active = op.get_package("app", tenant_id="t1", db_path=db)
    assert active and active["version"] == "1.1.0"

    rb = op.rollback_package(
        "app", tenant_id="t1", to_version="1.0.0", db_path=db
    )
    assert rb["status"] == "rolled_back"
    assert rb["active_version"] == "1.0.0"
    restored = op.get_package("app", tenant_id="t1", db_path=db)
    assert restored and restored["version"] == "1.0.0"
    assert restored["active"] is True


def test_cross_tenant_hidden(tmp_path):
    db = str(tmp_path / "pkg.db")
    op.publish_package(
        tenant_id="t1",
        package_id="secret",
        version="1.0.0",
        schema=["S"],
        db_path=db,
    )
    assert op.get_package("secret", tenant_id="t2", db_path=db) is None
    assert (
        op.validate_package("secret", tenant_id="t2", db_path=db)["status"]
        == "not_found"
    )
