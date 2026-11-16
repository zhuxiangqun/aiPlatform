"""G1：N01 DataSourceConfig content_hash → FactLedger Raw（certified 恒 false）。"""
from __future__ import annotations

import pytest

from core.harness.knowledge_pipeline.fact_ledger import (
    FactLedger,
    FactLedgerError,
    evaluate_datasource_raw_gate,
    ingest_datasource_raw,
    run_datasource_raw_suite,
)
from core.harness.ontology_engine.data_source import (
    DataSourceConfig,
    DataSourceIntegrityError,
    read_file_datasource_bytes,
    sha256_bytes,
    validate_datasource_content_hash,
)


@pytest.fixture
async def ledger(tmp_path):
    store = FactLedger(
        db_path=str(tmp_path / "fact_ledger.sqlite3"),
        raw_dir=tmp_path / "raw",
    )
    await store.initialize()
    return store


def test_validate_require_hash_and_mismatch(tmp_path):
    p = tmp_path / "a.bin"
    p.write_bytes(b"abc")
    cfg = DataSourceConfig(
        name="a",
        source_type="file",
        connection={"file_path": str(p)},
        content_hash="",
    )
    blob = read_file_datasource_bytes(cfg)
    with pytest.raises(DataSourceIntegrityError, match="missing content_hash"):
        validate_datasource_content_hash(cfg, blob, require_hash=True)
    cfg.content_hash = "0" * 64
    with pytest.raises(DataSourceIntegrityError, match="mismatch"):
        validate_datasource_content_hash(cfg, blob, require_hash=True)
    cfg.content_hash = sha256_bytes(blob)
    ok = validate_datasource_content_hash(cfg, blob, require_hash=True)
    assert ok["ok"] is True and ok["hash_declared"] is True


@pytest.mark.asyncio
async def test_ingest_missing_hash_rejected(ledger: FactLedger):
    with pytest.raises(FactLedgerError, match="missing content_hash"):
        await ingest_datasource_raw(
            tenant_id="t1",
            collection_id="c1",
            content=b"x",
            content_hash="",
            require_hash=True,
            ledger=ledger,
        )


@pytest.mark.asyncio
async def test_ingest_ok_and_verify(ledger: FactLedger, tmp_path):
    content = b"datasource-ok"
    digest = sha256_bytes(content)
    path = tmp_path / "ok.bin"
    path.write_bytes(content)
    receipt = await ingest_datasource_raw(
        tenant_id="t1",
        collection_id="c1",
        content=content,
        content_hash=digest,
        name="ok",
        locator=str(path),
        require_hash=True,
        ledger=ledger,
    )
    assert receipt["integrity"]["ok"] is True
    assert receipt["source"]["sha256"] == digest
    assert receipt["certified"] is False


@pytest.mark.asyncio
async def test_suite_and_gate_honesty():
    suite = await run_datasource_raw_suite()
    assert suite["ok"] is True
    assert suite["certified"] is False
    assert suite["n01_full_conformance"] is False
    gate = evaluate_datasource_raw_gate(suite)
    assert gate["ok"] is True
    assert gate["certified"] is False
    bad = dict(suite)
    bad["n01_full_conformance"] = True
    honesty = evaluate_datasource_raw_gate(bad)
    assert honesty["ok"] is False
    assert "honesty_certified_flag_forbidden" in honesty["issues"]
