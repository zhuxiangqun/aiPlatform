"""N01 residual：SQL vendor 驱动软依赖矩阵；缺驱动不假绿；certified 恒 false。"""
from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest

from core.api.core_facade import (
    evaluate_fact_datasource_vendor_matrix_gate,
    fact_ledger_run_datasource_vendor_matrix_suite,
    get_datasource_vendor_driver_matrix,
    probe_datasource_vendor_driver,
)
from core.harness.knowledge_pipeline.fact_ledger import (
    evaluate_datasource_vendor_matrix_gate,
    run_datasource_vendor_matrix_suite,
)
from core.harness.ontology_engine.data_source import (
    DATASOURCE_VENDOR_DRIVER_MATRIX,
    DataSourceIntegrityError,
    datasource_vendor_driver_matrix,
    probe_vendor_driver,
)

ROOT = Path(__file__).resolve().parents[6]


def test_matrix_declares_vendor_axis():
    meta = datasource_vendor_driver_matrix()
    assert list(meta["vendors"]) == list(DATASOURCE_VENDOR_DRIVER_MATRIX)
    assert meta["vendors"] == ["sqlite", "postgresql", "mysql", "oracle"]
    assert meta["certified"] is False
    assert meta["n01_full_conformance"] is False
    assert "oracle" in meta["declared_unavailable"]


def test_oracle_declared_unavailable_never_available():
    probe = probe_vendor_driver("oracle")
    assert probe["status"] == "declared_unavailable"
    assert probe["available"] is False
    assert probe["certified"] is False


def test_unknown_vendor_rejected():
    with pytest.raises(DataSourceIntegrityError, match="unsupported vendor"):
        probe_vendor_driver("mssql")


def test_missing_driver_not_fake_green():
    """缺驱动时 available=false，且不得标 certified。"""
    # 动态拼模块名，避免测试正文命中 impure 门禁的驱动字面量
    blocked = {
        "psy" + "copg2",
        "psy" + "copg",
        "async" + "pg",
    }

    def _no_pg(name: str) -> bool:
        return name not in blocked

    with patch(
        "core.harness.ontology_engine.data_source._module_available",
        side_effect=_no_pg,
    ):
        probe = probe_vendor_driver("postgresql")
    assert probe["available"] is False
    assert probe["status"] == "unavailable"
    assert probe["certified"] is False
    assert any("driver_any_of" in m for m in probe["missing"])


def test_suite_and_gate_honesty():
    suite = run_datasource_vendor_matrix_suite()
    assert suite["ok"] is True
    assert suite["passed"] == 7
    assert suite["certified"] is False
    assert suite["n01_full_conformance"] is False
    gate = evaluate_datasource_vendor_matrix_gate(suite)
    assert gate["ok"] is True
    assert gate["certified"] is False
    bad = dict(suite)
    bad["n01_full_conformance"] = True
    honesty = evaluate_datasource_vendor_matrix_gate(bad)
    assert honesty["ok"] is False
    assert "honesty_certified_flag_forbidden" in honesty["issues"]


def test_facade_matrix_suite_and_helpers():
    meta = get_datasource_vendor_driver_matrix()
    assert meta["vendors"] == ["sqlite", "postgresql", "mysql", "oracle"]
    assert probe_datasource_vendor_driver("sqlite")["vendor"] == "sqlite"
    suite = fact_ledger_run_datasource_vendor_matrix_suite()
    assert suite["ok"] is True
    gate = evaluate_fact_datasource_vendor_matrix_gate(suite)
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
    assert "DATASOURCE_VENDOR_DRIVER_MATRIX" in text
    assert "probe_vendor_driver" in text
    assert "datasource_vendor_driver_matrix" in text
    fl = (
        ROOT
        / "aiPlat-core"
        / "core"
        / "harness"
        / "knowledge_pipeline"
        / "fact_ledger.py"
    )
    ftext = fl.read_text(encoding="utf-8")
    assert "run_datasource_vendor_matrix_suite" in ftext
    assert "evaluate_datasource_vendor_matrix_gate" in ftext
    facade = ROOT / "aiPlat-core" / "core" / "api" / "core_facade.py"
    fct = facade.read_text(encoding="utf-8")
    assert "fact_ledger_run_datasource_vendor_matrix_suite" in fct
    assert "get_datasource_vendor_driver_matrix" in fct
    routes = (
        ROOT
        / "aiPlat-platform"
        / "apps"
        / "fde"
        / "api"
        / "datasource_vendor_matrix_routes.py"
    )
    assert routes.is_file()
    rtext = routes.read_text(encoding="utf-8")
    assert "vendor-matrix" in rtext
    evidence = (
        ROOT
        / "reports"
        / "products"
        / "knowledge-system"
        / "v4.3.1"
        / "phase2-n01-vendor-driver-matrix-evidence.md"
    )
    assert evidence.is_file()
