"""N01 deepen：Core file/sql/api 连接器矩阵 + hash 强制快照；certified 恒 false。"""
from __future__ import annotations

from pathlib import Path

import pytest

from core.api.core_facade import (
    ensure_datasource_raw_connector,
    evaluate_fact_datasource_connector_matrix_gate,
    fact_ledger_run_datasource_connector_matrix_suite,
    get_datasource_raw_connector_matrix,
)
from core.harness.knowledge_pipeline.fact_ledger import (
    evaluate_datasource_connector_matrix_gate,
    run_datasource_connector_matrix_suite,
)
from core.harness.ontology_engine.data_source import (
    DATASOURCE_RAW_CONNECTOR_MATRIX,
    DataSourceConfig,
    DataSourceIntegrityError,
    datasource_raw_connector_matrix,
    require_datasource_raw_connector,
    sha256_bytes,
    snapshot_datasource_bytes,
    validate_datasource_content_hash,
)

ROOT = Path(__file__).resolve().parents[6]


def test_matrix_declares_file_sql_api():
    meta = datasource_raw_connector_matrix()
    assert list(meta["connectors"]) == list(DATASOURCE_RAW_CONNECTOR_MATRIX)
    assert meta["connectors"] == ["file", "sql", "api"]
    assert meta["certified"] is False
    assert meta["n01_full_conformance"] is False
    assert require_datasource_raw_connector("SQL") == "sql"
    with pytest.raises(DataSourceIntegrityError, match="unsupported source_type"):
        require_datasource_raw_connector("postgres")


def test_sql_api_hash_snapshot_and_mismatch():
    records = [{"b": 2, "a": 1}]
    for st in ("sql", "api"):
        cfg = DataSourceConfig(name=f"m-{st}", source_type=st, connection={})
        blob = snapshot_datasource_bytes(cfg, records=records)
        cfg.content_hash = sha256_bytes(blob)
        ok = validate_datasource_content_hash(cfg, blob, require_hash=True)
        assert ok["ok"] is True
        bad = DataSourceConfig(
            name=f"m-{st}-bad",
            source_type=st,
            connection={},
            content_hash="0" * 64,
        )
        with pytest.raises(DataSourceIntegrityError, match="mismatch"):
            validate_datasource_content_hash(
                bad,
                snapshot_datasource_bytes(bad, records=records),
                require_hash=True,
            )


@pytest.mark.asyncio
async def test_suite_and_gate_honesty():
    suite = await run_datasource_connector_matrix_suite()
    assert suite["ok"] is True
    assert suite["passed"] == 6
    assert suite["certified"] is False
    assert suite["n01_full_conformance"] is False
    gate = evaluate_datasource_connector_matrix_gate(suite)
    assert gate["ok"] is True
    assert gate["certified"] is False
    bad = dict(suite)
    bad["n01_full_conformance"] = True
    honesty = evaluate_datasource_connector_matrix_gate(bad)
    assert honesty["ok"] is False
    assert "honesty_certified_flag_forbidden" in honesty["issues"]


@pytest.mark.asyncio
async def test_facade_matrix_suite_and_helpers():
    meta = get_datasource_raw_connector_matrix()
    assert meta["connectors"] == ["file", "sql", "api"]
    assert ensure_datasource_raw_connector("file") == "file"
    suite = await fact_ledger_run_datasource_connector_matrix_suite()
    assert suite["ok"] is True
    gate = evaluate_fact_datasource_connector_matrix_gate(suite)
    assert gate["ok"] is True
    assert gate["certified"] is False


def test_docs_and_wiring_state():
    ds = (
        ROOT
        / "aiPlat-core"
        / "core"
        / "harness"
        / "ontology_engine"
        / "data_source.py"
    )
    text = ds.read_text(encoding="utf-8")
    assert "DATASOURCE_RAW_CONNECTOR_MATRIX" in text
    assert "require_datasource_raw_connector" in text
    fl = (
        ROOT
        / "aiPlat-core"
        / "core"
        / "harness"
        / "knowledge_pipeline"
        / "fact_ledger.py"
    )
    ftext = fl.read_text(encoding="utf-8")
    assert "run_datasource_connector_matrix_suite" in ftext
    assert "evaluate_datasource_connector_matrix_gate" in ftext
    facade = ROOT / "aiPlat-core" / "core" / "api" / "core_facade.py"
    fct = facade.read_text(encoding="utf-8")
    assert "fact_ledger_run_datasource_connector_matrix_suite" in fct
    assert "get_datasource_raw_connector_matrix" in fct
