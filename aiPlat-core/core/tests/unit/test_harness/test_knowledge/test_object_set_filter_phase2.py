"""N07/N22 deepen：ObjectSet 嵌套 filter；certified 恒 false。"""
from __future__ import annotations

from pathlib import Path

import pytest

from core.api.core_facade import (
    evaluate_object_set_filter_gate,
    run_object_set_filter_suite,
)
from core.harness.knowledge_pipeline.fact_ledger import FactLedger
from core.harness.knowledge_pipeline.object_set import (
    ObjectSetFilterError,
    evaluate_object_set_filter_gate as core_gate,
    match_filter_expr,
    query_object_set,
    run_object_set_filter_suite as core_suite,
)

ROOT = Path(__file__).resolve().parents[6]


@pytest.fixture()
async def ledger(tmp_path):
    fl = FactLedger(db_path=str(tmp_path / "facts.db"), raw_dir=tmp_path / "raw")
    await fl.initialize()
    src = await fl.register_source(
        tenant_id="t1",
        collection_id="c1",
        kind="text",
        uri="mem://order1",
        content=b"order",
        connector="object_set_filter_test",
    )
    ev = [{"source_id": src["source_id"], "locator": "1", "quote": "o"}]
    for oid, status, priority in (
        ("O-1", "open", "high"),
        ("O-2", "open", "low"),
        ("O-3", "closed", "high"),
    ):
        await fl.put_fact(
            tenant_id="t1",
            collection_id="c1",
            domain_id="lock-service",
            subject=f"InstallOrder:{oid}",
            predicate="status",
            object=status,
            evidence=ev,
            source_policy="primary",
            extractor_version="test-1.0",
            review_status="published",
            confidence=0.9,
            allow_bootstrap_published=True,
        )
        await fl.put_fact(
            tenant_id="t1",
            collection_id="c1",
            domain_id="lock-service",
            subject=f"InstallOrder:{oid}",
            predicate="priority",
            object=priority,
            evidence=ev,
            source_policy="primary",
            extractor_version="test-1.0",
            review_status="published",
            confidence=0.9,
            allow_bootstrap_published=True,
        )
    return fl


def test_suite_and_gate_honesty():
    suite = core_suite()
    assert suite["ok"] is True
    assert suite["passed"] == 7
    assert suite["certified"] is False
    assert suite.get("where_js_eval") is False
    assert suite["checks"].get("where_unavailable") is True
    assert suite["checks"].get("expr_bounded") is True
    gate = core_gate(suite)
    assert gate["ok"] is True
    bad = dict(suite)
    bad["certified"] = True
    honesty = core_gate(bad)
    assert honesty["ok"] is False
    assert "honesty_certified_flag_forbidden" in honesty["issues"]


def test_where_declared_unavailable():
    with pytest.raises(ObjectSetFilterError, match="where_unavailable"):
        match_filter_expr({"status": "open"}, {"$where": "this.status=='open'"})


def test_expr_bounded_compare():
    item = {"status": "open", "n": 3}
    assert match_filter_expr(item, {"$expr": {"$eq": ["$status", "open"]}})
    assert match_filter_expr(item, {"$expr": {"$gt": ["$n", 2]}})
    assert not match_filter_expr(item, {"$expr": {"$lt": ["$n", 1]}})
    with pytest.raises(ObjectSetFilterError, match="unsupported"):
        match_filter_expr(item, {"$expr": {"$regex": ["$status", "o"]}})


def test_facade_suite():
    suite = run_object_set_filter_suite()
    assert suite["ok"] is True
    gate = evaluate_object_set_filter_gate(suite)
    assert gate["ok"] is True
    assert gate["certified"] is False


def test_match_nested_and_depth():
    item = {"status": "open", "priority": "high"}
    assert match_filter_expr(
        item,
        {
            "$and": [
                {"status": {"$eq": "open"}},
                {"$or": [{"priority": {"$in": ["high"]}}, {"status": "x"}]},
            ]
        },
    )
    deep: dict = {"status": "open"}
    for _ in range(6):
        deep = {"$and": [deep]}
    with pytest.raises(ObjectSetFilterError, match="depth"):
        match_filter_expr(item, deep)


@pytest.mark.asyncio
async def test_query_nested_filter(ledger):
    out = await query_object_set(
        {
            "object_type": "InstallOrder",
            "filter": {
                "$and": [
                    {"status": {"$eq": "open"}},
                    {"priority": {"$in": ["high", "urgent"]}},
                ]
            },
        },
        tenant_id="t1",
        permissions=["kb:read"],
        ledger=ledger,
    )
    assert out["status"] == "ok"
    assert out["total"] == 1
    assert out["items"][0]["order_id"] == "O-1"


@pytest.mark.asyncio
async def test_query_invalid_filter(ledger):
    out = await query_object_set(
        {
            "object_type": "InstallOrder",
            "filter": {"$and": [], "status": "open"},
        },
        tenant_id="t1",
        permissions=["kb:read"],
        ledger=ledger,
    )
    assert out["status"] == "error"
    assert "invalid_filter" in out["reason"]


def test_docs_and_wiring_state():
    mod = (
        ROOT
        / "aiPlat-core"
        / "core"
        / "harness"
        / "knowledge_pipeline"
        / "object_set.py"
    )
    text = mod.read_text(encoding="utf-8")
    assert "match_filter_expr" in text
    assert "run_object_set_filter_suite" in text
    facade = ROOT / "aiPlat-core" / "core" / "api" / "core_facade.py"
    assert "run_object_set_filter_suite" in facade.read_text(encoding="utf-8")
