"""N01 deepen：process_from_datasource Raw ingest 默认强制；可显式/环境 opt-out；certified 恒 false。"""
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
)
from core.harness.ontology_engine.engine import OntologyEngine, ProcessResult


ROOT = Path(__file__).resolve().parents[6]


def test_require_raw_ingest_default_on(monkeypatch):
    monkeypatch.delenv("AIPLAT_DATASOURCE_REQUIRE_RAW_INGEST", raising=False)
    assert datasource_require_raw_ingest_enabled() is True
    assert datasource_require_raw_ingest_enabled(explicit=False) is False
    monkeypatch.setenv("AIPLAT_DATASOURCE_REQUIRE_RAW_INGEST", "0")
    assert datasource_require_raw_ingest_enabled() is False
    monkeypatch.setenv("AIPLAT_DATASOURCE_REQUIRE_RAW_INGEST", "false")
    assert datasource_require_raw_ingest_enabled() is False


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
    return OntologyEngine(domain, tenant_id="n01-default-force-tenant")


def _register_file_source(tmp_path: Path, *, content_hash: str = "") -> str:
    sid = "n01-default-force-file"
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
async def test_process_default_forces_raw_ingest(tmp_path: Path, monkeypatch, ledger: FactLedger):
    eng = _engine(monkeypatch)
    sid = _register_file_source(tmp_path)
    monkeypatch.delenv("AIPLAT_DATASOURCE_REQUIRE_RAW_INGEST", raising=False)

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

    monkeypatch.setattr(
        "core.harness.knowledge_pipeline.fact_ledger.ingest_datasource_raw",
        _ingest,
    )

    # 默认强制：不传 require_raw_ingest
    out = await eng.process_from_datasource(sid)
    assert not out.errors, out.errors
    assert out.raw_ingest is not None
    assert out.raw_ingest["certified"] is False
    assert out.raw_ingest["integrity"]["ok"] is True


@pytest.mark.asyncio
async def test_process_opt_out_skips_raw_ingest(tmp_path: Path, monkeypatch):
    eng = _engine(monkeypatch)
    sid = _register_file_source(tmp_path)

    async def _fake_chunks(chunks, doc_id="", model_name=""):
        r = ProcessResult()
        r.stats["total_chunks"] = len(chunks)
        return r

    monkeypatch.setattr(eng, "process_chunks", _fake_chunks)
    out = await eng.process_from_datasource(sid, require_raw_ingest=False)
    assert not out.errors
    assert out.raw_ingest is None


def test_docs_and_route_state_default_force():
    helper = (
        ROOT
        / "aiPlat-core"
        / "core"
        / "harness"
        / "ontology_engine"
        / "data_source.py"
    )
    text = helper.read_text(encoding="utf-8")
    assert 'getenv("AIPLAT_DATASOURCE_REQUIRE_RAW_INGEST", "1")' in text
    assert "默认强制" in text
    route = (
        ROOT
        / "aiPlat-core"
        / "core"
        / "api"
        / "routers"
        / "wiki_ontology_engine.py"
    )
    rtext = route.read_text(encoding="utf-8")
    assert "require_raw_ingest" in rtext
    assert '"certified": False' in rtext or 'certified": False' in rtext
