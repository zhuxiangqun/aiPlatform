"""N06 deepen：统一 Query Gateway（fact+object_set+wiki+index → F.1）；certified 恒 false。"""
from __future__ import annotations

from pathlib import Path

import pytest

from core.api.core_facade import (
    ensure_unified_query_route,
    evaluate_fact_unified_query_gateway_gate,
    fact_ledger_run_unified_query_gateway_suite,
    get_unified_query_gateway_routes,
)
from core.harness.knowledge_pipeline.fact_ledger import (
    FactLedgerError,
    UNIFIED_QUERY_GATEWAY_ROUTES,
    evaluate_unified_query_gateway_gate,
    require_unified_query_route,
    run_unified_query_gateway_suite,
    unified_query_gateway_routes,
)

ROOT = Path(__file__).resolve().parents[6]


def test_routes_declare_fact_object_set_wiki_index():
    meta = unified_query_gateway_routes()
    assert list(meta["routes"]) == list(UNIFIED_QUERY_GATEWAY_ROUTES)
    assert meta["routes"] == ["fact", "object_set", "wiki", "index"]
    assert meta["wiki_index_routes"] is True
    assert meta["certified"] is False
    assert require_unified_query_route("FACT") == "fact"
    assert require_unified_query_route("wiki") == "wiki"
    assert require_unified_query_route("INDEX") == "index"
    with pytest.raises(FactLedgerError, match="unsupported route"):
        require_unified_query_route("materials_chat")


@pytest.mark.asyncio
async def test_suite_and_gate_honesty():
    suite = await run_unified_query_gateway_suite()
    assert suite["ok"] is True
    assert suite["passed"] == 6
    assert suite["wiki_index_routes"] is True
    assert suite["certified"] is False
    assert suite["n06_full_conformance"] is False
    gate = evaluate_unified_query_gateway_gate(suite)
    assert gate["ok"] is True
    assert gate["certified"] is False
    assert gate["wiki_index_routes"] is True
    bad = dict(suite)
    bad["n06_full_conformance"] = True
    honesty = evaluate_unified_query_gateway_gate(bad)
    assert honesty["ok"] is False
    assert "honesty_certified_flag_forbidden" in honesty["issues"]
    missing_flag = dict(suite)
    missing_flag.pop("wiki_index_routes", None)
    flag_gate = evaluate_unified_query_gateway_gate(missing_flag)
    assert flag_gate["ok"] is False
    assert "wiki_index_routes_required" in flag_gate["issues"]


@pytest.mark.asyncio
async def test_facade_unified_gateway():
    meta = get_unified_query_gateway_routes()
    assert meta["routes"] == ["fact", "object_set", "wiki", "index"]
    assert meta["wiki_index_routes"] is True
    assert ensure_unified_query_route("object_set") == "object_set"
    assert ensure_unified_query_route("wiki") == "wiki"
    suite = await fact_ledger_run_unified_query_gateway_suite()
    assert suite["ok"] is True
    gate = evaluate_fact_unified_query_gateway_gate(suite)
    assert gate["ok"] is True
    assert gate["certified"] is False


def test_docs_and_wiring_state():
    fl = (
        ROOT
        / "aiPlat-core"
        / "core"
        / "harness"
        / "knowledge_pipeline"
        / "fact_ledger.py"
    )
    text = fl.read_text(encoding="utf-8")
    assert "UNIFIED_QUERY_GATEWAY_ROUTES" in text
    assert "async def unified_query_gateway(" in text
    assert "run_unified_query_gateway_suite" in text
    assert "query_wiki_with_abstain" in text
    assert "query_kb_with_abstain" in text
    assert "wiki_index_routes" in text
    facade = ROOT / "aiPlat-core" / "core" / "api" / "core_facade.py"
    fct = facade.read_text(encoding="utf-8")
    assert "fact_ledger_unified_query_gateway" in fct
    assert "fact_ledger_run_unified_query_gateway_suite" in fct
