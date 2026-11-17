"""E3/K1–K7：N09 跨租户加深（含跨域写边/publish snapshot tenant；certified 恒 false）。"""
from __future__ import annotations

import pytest

from core.harness.knowledge_pipeline.fact_ledger import (
    evaluate_cross_tenant_gate,
    run_cross_tenant_isolation_suite,
)


@pytest.mark.asyncio
async def test_suite_passes_and_honesty():
    suite = await run_cross_tenant_isolation_suite()
    assert suite["ok"] is True
    assert suite["passed"] == 13
    assert suite["certified"] is False
    assert suite["n09_full_conformance"] is False
    ids = {c["id"] for c in suite["cases"]}
    assert ids == {
        "query_facts_no_leak",
        "get_source_no_leak",
        "gateway_no_leak",
        "verify_raw_no_leak",
        "object_set_no_leak",
        "unified_audit_no_leak",
        "kb_retrieve_no_leak",
        "wiki_retrieve_no_leak",
        "graphrag_no_leak",
        "graphrag_caller_passthrough",
        "graphindex_no_leak",
        "graph_write_tenant",
        "cross_domain_resolve_tenant",
    }
    assert all(c["ok"] for c in suite["cases"])

    gate = evaluate_cross_tenant_gate(suite)
    assert gate["ok"] is True
    assert gate["certified"] is False

    forged = dict(suite)
    forged["certified"] = True
    bad = evaluate_cross_tenant_gate(forged)
    assert bad["ok"] is False
    assert "honesty_certified_flag_forbidden" in bad["issues"]
    assert bad["certified"] is False


def test_empty_suite_gate_fails():
    gate = evaluate_cross_tenant_gate({})
    assert gate["ok"] is False
    assert gate["certified"] is False
