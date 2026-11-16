"""E1：N01 Raw 读时完整性校验（verify-on-read；certified 恒 false）。"""
from __future__ import annotations

import pytest

from core.harness.knowledge_pipeline.fact_ledger import (
    FactLedger,
    FactLedgerError,
    evaluate_raw_integrity_gate,
)


@pytest.fixture
async def ledger(tmp_path):
    store = FactLedger(
        db_path=str(tmp_path / "fact_ledger.sqlite3"),
        raw_dir=tmp_path / "raw",
    )
    await store.initialize()
    return store


@pytest.mark.asyncio
async def test_verify_ok_and_read_bytes(ledger: FactLedger):
    content = b"n01-raw-ok"
    src = await ledger.register_source(
        tenant_id="t1",
        collection_id="c1",
        kind="file",
        uri="file://n01/ok.txt",
        content=content,
        connector="n01",
        domain_id="lock-service",
    )
    receipt = await ledger.verify_raw_integrity(
        src["source_id"], tenant_id="t1"
    )
    assert receipt["ok"] is True
    assert receipt["sha256"] == src["sha256"]
    got = await ledger.get_source(
        src["source_id"], tenant_id="t1", verify_integrity=True
    )
    assert got is not None and got.get("integrity_ok") is True
    raw = await ledger.read_raw_bytes(src["source_id"], tenant_id="t1")
    assert raw == content


@pytest.mark.asyncio
async def test_tamper_rejected(ledger: FactLedger, tmp_path):
    src = await ledger.register_source(
        tenant_id="t1",
        collection_id="c1",
        kind="file",
        uri="file://n01/tamper.txt",
        content=b"original",
        connector="n01",
    )
    snap = tmp_path / "raw" / "t1" / f"{src['source_id']}.bin"
    # 为什么：去掉只读后覆写模拟篡改；读路径必须拒绝
    snap.chmod(0o644)
    snap.write_bytes(b"tampered")
    with pytest.raises(FactLedgerError, match="integrity failed"):
        await ledger.verify_raw_integrity(src["source_id"], tenant_id="t1")
    with pytest.raises(FactLedgerError, match="integrity failed"):
        await ledger.read_raw_bytes(src["source_id"], tenant_id="t1")


@pytest.mark.asyncio
async def test_missing_snapshot_rejected(ledger: FactLedger, tmp_path):
    src = await ledger.register_source(
        tenant_id="t1",
        collection_id="c1",
        kind="file",
        uri="file://n01/missing.txt",
        content=b"gone",
        connector="n01",
    )
    snap = tmp_path / "raw" / "t1" / f"{src['source_id']}.bin"
    snap.chmod(0o644)
    snap.unlink()
    with pytest.raises(FactLedgerError, match="snapshot missing"):
        await ledger.verify_raw_integrity(src["source_id"], tenant_id="t1")


@pytest.mark.asyncio
async def test_rewrite_same_source_id_rejected(ledger: FactLedger):
    src = await ledger.register_source(
        tenant_id="t1",
        collection_id="c1",
        kind="file",
        uri="file://n01/once.txt",
        content=b"once",
        connector="n01",
        source_id="src-n01-once",
    )
    with pytest.raises(FactLedgerError, match="already exists"):
        await ledger.register_source(
            tenant_id="t1",
            collection_id="c1",
            kind="file",
            uri="file://n01/once2.txt",
            content=b"twice",
            connector="n01",
            source_id=src["source_id"],
        )


@pytest.mark.asyncio
async def test_cross_tenant_verify_denied(ledger: FactLedger):
    src = await ledger.register_source(
        tenant_id="t1",
        collection_id="c1",
        kind="file",
        uri="file://n01/x.txt",
        content=b"x",
        connector="n01",
    )
    with pytest.raises(FactLedgerError, match="not found"):
        await ledger.verify_raw_integrity(src["source_id"], tenant_id="t2")


def test_gate_pass_and_honesty():
    gate = evaluate_raw_integrity_gate(
        [{"ok": True, "source_id": "s1"}, {"ok": True, "source_id": "s2"}]
    )
    assert gate["ok"] is True
    assert gate["certified"] is False
    assert gate["n01_full_conformance"] is False

    empty = evaluate_raw_integrity_gate([])
    assert empty["ok"] is False
    assert empty["certified"] is False

    bad = evaluate_raw_integrity_gate(
        [{"ok": True, "certified": True, "source_id": "s1"}]
    )
    assert bad["ok"] is False
    assert "honesty_certified_flag_forbidden" in bad["issues"]
    assert bad["certified"] is False
