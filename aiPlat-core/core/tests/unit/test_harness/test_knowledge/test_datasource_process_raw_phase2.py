"""N01 deepen：process_from_datasource → Raw ingest（opt-in；certified 恒 false）。"""
from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from core.harness.knowledge_pipeline.fact_ledger import FactLedger
from core.harness.ontology_engine.data_source import (
    DataSourceConfig,
    DataSourceRegistry,
    FileDataSource,
    datasource_require_raw_ingest_enabled,
    sha256_bytes,
    snapshot_datasource_bytes,
)
from core.harness.ontology_engine.engine import OntologyEngine, ProcessResult


ROOT = Path(__file__).resolve().parents[6]


def test_snapshot_file_and_sql_stable(tmp_path: Path):
    p = tmp_path / "rows.json"
    p.write_text('[{"id":1,"name":"a"}]', encoding="utf-8")
    cfg = DataSourceConfig(
        name="f1",
        source_type="file",
        connection={"file_path": str(p), "format": "json"},
    )
    blob = snapshot_datasource_bytes(cfg)
    assert blob == p.read_bytes()

    scfg = DataSourceConfig(name="s1", source_type="sql", connection={}, mapping={})
    a = snapshot_datasource_bytes(scfg, records=[{"b": 2, "a": 1}])
    b = snapshot_datasource_bytes(scfg, records=[{"a": 1, "b": 2}])
    assert a == b
    assert sha256_bytes(a) == sha256_bytes(b)


def test_require_raw_ingest_opt_in(monkeypatch):
    monkeypatch.delenv("AIPLAT_DATASOURCE_REQUIRE_RAW_INGEST", raising=False)
    assert datasource_require_raw_ingest_enabled() is False
    assert datasource_require_raw_ingest_enabled(explicit=True) is True
    monkeypatch.setenv("AIPLAT_DATASOURCE_REQUIRE_RAW_INGEST", "1")
    assert datasource_require_raw_ingest_enabled() is True


@pytest.fixture
async def ledger(tmp_path: Path):
    store = FactLedger(
        db_path=str(tmp_path / "fact_ledger.sqlite3"),
        raw_dir=tmp_path / "raw",
    )
    await store.initialize()
    return store


def _engine(monkeypatch) -> OntologyEngine:
    from core.harness.ontology_engine import engine as eng_mod

    domain = SimpleNamespace(id="lock-service", classes=[], object_properties=[])
    monkeypatch.setattr(eng_mod, "ClassMapper", lambda d: MagicMock())
    monkeypatch.setattr(eng_mod, "PropertyExtractor", lambda d: MagicMock())
    monkeypatch.setattr(eng_mod, "StateMachine", lambda d: MagicMock())
    return OntologyEngine(domain, tenant_id="n01-process-tenant")


def _register_file_source(tmp_path: Path, *, content_hash: str = "") -> str:
    sid = "n01-process-file"
    path = tmp_path / "ds.json"
    path.write_text('[{"name":"Ticket-1","status":"open"}]', encoding="utf-8")
    cfg = DataSourceConfig(
        name=sid,
        source_type="file",
        connection={"file_path": str(path), "format": "json"},
        content_hash=content_hash or sha256_bytes(path.read_bytes()),
        locator=str(path),
    )
    DataSourceRegistry._configs[sid] = cfg
    DataSourceRegistry._sources[sid] = FileDataSource(cfg)
    return sid


@pytest.mark.asyncio
async def test_process_raw_ingest_opt_in_ok(tmp_path: Path, monkeypatch, ledger: FactLedger):
    eng = _engine(monkeypatch)
    sid = _register_file_source(tmp_path)

    async def _fake_chunks(chunks, doc_id="", model_name=""):
        r = ProcessResult()
        r.stats["total_chunks"] = len(chunks)
        return r

    monkeypatch.setattr(eng, "process_chunks", _fake_chunks)

    from core.harness.knowledge_pipeline import fact_ledger as fl

    real_ingest = fl.ingest_datasource_raw

    async def _ingest(**kwargs):
        kwargs = dict(kwargs)
        kwargs["ledger"] = ledger
        return await real_ingest(**kwargs)

    monkeypatch.setattr(fl, "ingest_datasource_raw", _ingest)

    # import path used inside process_from_datasource
    import core.harness.ontology_engine.engine as eng_mod

    monkeypatch.setattr(
        "core.harness.knowledge_pipeline.fact_ledger.ingest_datasource_raw",
        _ingest,
    )

    out = await eng.process_from_datasource(sid, require_raw_ingest=True)
    assert not out.errors, out.errors
    assert out.raw_ingest is not None
    assert out.raw_ingest["certified"] is False
    assert out.raw_ingest["integrity"]["ok"] is True


@pytest.mark.asyncio
async def test_process_raw_ingest_missing_hash_hard_stop(tmp_path: Path, monkeypatch):
    eng = _engine(monkeypatch)
    sid = _register_file_source(tmp_path, content_hash="")
    DataSourceRegistry._configs[sid].content_hash = ""

    called = {"chunks": False}

    async def _fake_chunks(*_a, **_k):
        called["chunks"] = True
        return ProcessResult()

    monkeypatch.setattr(eng, "process_chunks", _fake_chunks)
    out = await eng.process_from_datasource(sid, require_raw_ingest=True)
    assert out.errors
    assert "raw ingest failed" in out.errors[0]
    assert out.raw_ingest is None
    assert called["chunks"] is False


@pytest.mark.asyncio
async def test_process_default_skips_raw_ingest(tmp_path: Path, monkeypatch):
    eng = _engine(monkeypatch)
    sid = _register_file_source(tmp_path)
    monkeypatch.delenv("AIPLAT_DATASOURCE_REQUIRE_RAW_INGEST", raising=False)

    async def _fake_chunks(chunks, doc_id="", model_name=""):
        r = ProcessResult()
        r.stats["total_chunks"] = len(chunks)
        return r

    monkeypatch.setattr(eng, "process_chunks", _fake_chunks)
    out = await eng.process_from_datasource(sid, require_raw_ingest=False)
    assert not out.errors
    assert out.raw_ingest is None


def test_panel_or_route_documents_require_raw_ingest():
    route = (
        ROOT
        / "aiPlat-core"
        / "core"
        / "api"
        / "routers"
        / "wiki_ontology_engine.py"
    )
    text = route.read_text(encoding="utf-8")
    assert "require_raw_ingest" in text
    assert "raw_ingest" in text
    assert '"certified": False' in text or "certified\": False" in text
