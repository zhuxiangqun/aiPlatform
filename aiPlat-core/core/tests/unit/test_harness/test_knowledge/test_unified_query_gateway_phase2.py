"""N06 deepen：统一 Query Gateway（含 materials_chat → F.1）；certified 恒 false。"""
from __future__ import annotations

from pathlib import Path

import pytest

from core.api.core_facade import (
    ensure_unified_query_route,
    evaluate_fact_unified_query_gateway_gate,
    fact_ledger_run_unified_query_gateway_suite,
    get_unified_query_gateway_routes,
    materials_chat_to_f1_envelope,
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


def test_routes_declare_fact_object_set_wiki_index_materials():
    """路由轴含 fact/object_set/wiki/index/materials_chat。"""
    meta = unified_query_gateway_routes()
    assert list(meta["routes"]) == list(UNIFIED_QUERY_GATEWAY_ROUTES)
    assert meta["routes"] == [
        "fact",
        "object_set",
        "wiki",
        "index",
        "materials_chat",
    ]
    assert meta["wiki_index_routes"] is True
    assert meta["materials_chat_route"] is True
    assert meta["materials_nonrag_gateway"] is True
    assert meta["certified"] is False
    assert require_unified_query_route("FACT") == "fact"
    assert require_unified_query_route("wiki") == "wiki"
    assert require_unified_query_route("INDEX") == "index"
    assert require_unified_query_route("materials_chat") == "materials_chat"
    with pytest.raises(FactLedgerError, match="unsupported route"):
        require_unified_query_route("foobar_route")


@pytest.mark.asyncio
async def test_suite_and_gate_honesty():
    """套件全绿且 certified / n06_full 恒 false；nonrag 门槛必填。"""
    suite = await run_unified_query_gateway_suite()
    assert suite["ok"] is True
    assert suite["passed"] == 8
    assert suite["wiki_index_routes"] is True
    assert suite["materials_chat_route"] is True
    assert suite["materials_nonrag_gateway"] is True
    assert suite["certified"] is False
    assert suite["n06_full_conformance"] is False
    gate = evaluate_unified_query_gateway_gate(suite)
    assert gate["ok"] is True
    assert gate["certified"] is False
    assert gate["wiki_index_routes"] is True
    assert gate["materials_chat_route"] is True
    assert gate["materials_nonrag_gateway"] is True
    bad = dict(suite)
    bad["n06_full_conformance"] = True
    honesty = evaluate_unified_query_gateway_gate(bad)
    assert honesty["ok"] is False
    assert "honesty_certified_flag_forbidden" in honesty["issues"]
    missing_flag = dict(suite)
    missing_flag.pop("materials_nonrag_gateway", None)
    flag_gate = evaluate_unified_query_gateway_gate(missing_flag)
    assert flag_gate["ok"] is False
    assert "materials_nonrag_gateway_required" in flag_gate["issues"]


@pytest.mark.asyncio
async def test_facade_unified_gateway():
    """Facade 路由轴与套件/门槛门。"""
    meta = get_unified_query_gateway_routes()
    assert "materials_chat" in meta["routes"]
    assert meta["materials_chat_route"] is True
    assert ensure_unified_query_route("object_set") == "object_set"
    assert ensure_unified_query_route("materials_chat") == "materials_chat"
    suite = await fact_ledger_run_unified_query_gateway_suite()
    assert suite["ok"] is True
    gate = evaluate_fact_unified_query_gateway_gate(suite)
    assert gate["ok"] is True
    assert gate["certified"] is False
    f1 = materials_chat_to_f1_envelope(
        tenant_id="n06-facade",
        output={
            "answer": "x",
            "citations": [{"source": "wiki:X", "text": "x"}],
            "strategy": "direct_retrieve",
        },
    )
    assert f1.get("abstained") is False
    assert str(f1.get("route_reason") or "").startswith("unified:materials_chat:")
    sc = materials_chat_to_f1_envelope(
        tenant_id="n06-facade",
        output={
            "answer": "hi",
            "citations": [],
            "strategy": "trivial_bypass",
            "intent": "trivial",
            "quality": "trivial",
        },
        kind="shortcut",
    )
    assert sc.get("abstained") is False
    assert sc.get("answer") == "hi"
    assert str(sc.get("route_reason") or "").endswith(":trivial")


def test_docs_and_wiring_state():
    """核心与 Facade 符号接线。"""
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
    assert "materials_chat_to_f1_envelope" in text
    assert "materials_chat_route" in text
    assert "materials_nonrag_gateway" in text
    facade = ROOT / "aiPlat-core" / "core" / "api" / "core_facade.py"
    fct = facade.read_text(encoding="utf-8")
    assert "fact_ledger_unified_query_gateway" in fct
    assert "materials_chat_to_f1_envelope" in fct
    mc = (
        ROOT
        / "aiPlat-core"
        / "core"
        / "apps"
        / "agents"
        / "materials_chat.py"
    )
    mct = mc.read_text(encoding="utf-8")
    assert "materials_chat_to_f1_envelope" in mct
    assert "gateway_f1" in mct
    assert 'kind="shortcut"' in mct
    assert 'kind="cache_hit"' in mct
