"""N07/N22 ObjectSet $where/$expr 产品面：默认可用；$where unavailable；certified 恒 false。"""
from __future__ import annotations

from pathlib import Path

from core.api.core_facade import (
    evaluate_object_set_where_expr_product,
    evaluate_object_set_where_expr_product_gate,
    run_object_set_where_expr_product_suite,
)
from core.harness.knowledge_pipeline.object_set import (
    ObjectSetFilterError,
    evaluate_object_set_where_expr_product_gate as _gate,
    match_filter_expr,
    run_object_set_where_expr_product_suite as _suite,
)

ROOT = Path(__file__).resolve().parents[6]


def test_product_suite_and_gate_honesty():
    suite = _suite()
    assert suite["ok"] is True
    assert suite["passed"] == 3
    assert suite["certified"] is False
    assert suite["where_js_eval"] is False
    assert suite["objectset_where_expr_product_surface"] is True
    ids = {c["id"] for c in suite["cases"] if c.get("ok")}
    assert "where_expr_product_eval" in ids
    assert "where_expr_product_where_unavailable" in ids
    assert "honesty_product_certified_false" in ids
    gate = _gate(suite)
    assert gate["ok"] is True
    bad = dict(suite)
    bad["certified"] = True
    honesty = _gate(bad)
    assert honesty["ok"] is False
    assert "honesty_certified_flag_forbidden" in honesty["issues"]
    bad2 = dict(suite)
    bad2["where_js_eval"] = True
    honesty2 = _gate(bad2)
    assert honesty2["ok"] is False
    assert "honesty_where_js_eval_forbidden" in honesty2["issues"]


def test_facade_product_suite():
    suite = run_object_set_where_expr_product_suite()
    assert suite["ok"] is True
    gate = evaluate_object_set_where_expr_product_gate(suite)
    assert gate["ok"] is True
    assert gate["objectset_where_expr_product_surface"] is True
    assert gate["where_js_eval"] is False


def test_product_expr_and_where_honesty():
    item = {"status": "open", "n": 3}
    product = evaluate_object_set_where_expr_product(
        item, {"$expr": {"$eq": ["$status", "open"]}}
    )
    assert product["status"] == "ok"
    assert product["matched"] is True
    assert product.get("via") == "product_expr"
    assert product["objectset_where_expr_product_surface"] is True
    assert product["certified"] is False
    assert product["where_js_eval"] is False

    where_prod = evaluate_object_set_where_expr_product(
        item, {"$where": "this.status=='open'"}
    )
    assert where_prod["status"] == "where_unavailable"
    assert where_prod["matched"] is False
    assert where_prod["objectset_where_expr_product_surface"] is True

    try:
        match_filter_expr(item, {"$where": "this.status=='open'"})
        raise AssertionError("residual $where should raise")
    except ObjectSetFilterError as exc:
        assert "where_unavailable" in str(exc)


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
    assert "evaluate_object_set_where_expr_product" in text
    assert "run_object_set_where_expr_product_suite" in text
    facade = ROOT / "aiPlat-core" / "core" / "api" / "core_facade.py"
    assert "evaluate_object_set_where_expr_product" in facade.read_text(
        encoding="utf-8"
    )
    routes = (
        ROOT
        / "aiPlat-platform"
        / "apps"
        / "fde"
        / "api"
        / "object_set_routes.py"
    )
    assert "object-sets/product/where-expr" in routes.read_text(encoding="utf-8")
    panel = (
        ROOT
        / "aiPlat-management"
        / "frontend"
        / "src"
        / "pages"
        / "KnowledgeFactory"
        / "ObjectSetWhereExprPanel.tsx"
    )
    assert "object-sets/product/where-expr" in panel.read_text(encoding="utf-8")
