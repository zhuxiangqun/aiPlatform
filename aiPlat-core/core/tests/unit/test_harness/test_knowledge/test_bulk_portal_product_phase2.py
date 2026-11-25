"""N02 bulk portal 产品面：默认可用；certified / seed_replacement 恒 false。"""
from __future__ import annotations

import os
from pathlib import Path

from core.api.core_facade import (
    bulk_transition_object_types_product,
    evaluate_bulk_portal_product_gate,
    run_bulk_portal_product_suite,
)
from core.harness.knowledge_pipeline.object_type_publish import (
    bulk_transition_object_types,
    bulk_transition_object_types_product as _product,
    evaluate_bulk_portal_product_gate as _gate,
    run_bulk_portal_product_suite as _suite,
    submit_object_type_draft,
)

ROOT = Path(__file__).resolve().parents[6]


def test_product_suite_and_gate_honesty():
    suite = _suite()
    assert suite["ok"] is True
    assert suite["passed"] == 3
    assert suite["certified"] is False
    assert suite["seed_replacement"] is False
    assert suite["bulk_product_surface"] is True
    ids = {c["id"] for c in suite["cases"] if c.get("ok")}
    assert "bulk_product_default_on" in ids
    assert "bulk_product_multi_tenant" in ids
    assert "honesty_bulk_product_certified_false" in ids
    gate = _gate(suite)
    assert gate["ok"] is True
    bad = dict(suite)
    bad["certified"] = True
    honesty = _gate(bad)
    assert honesty["ok"] is False
    assert "honesty_certified_flag_forbidden" in honesty["issues"]


def test_facade_product_suite():
    suite = run_bulk_portal_product_suite()
    assert suite["ok"] is True
    gate = evaluate_bulk_portal_product_gate(suite)
    assert gate["ok"] is True
    assert gate["certified"] is False
    assert gate["bulk_product_surface"] is True


def test_product_without_residual_env(tmp_path, monkeypatch):
    monkeypatch.setenv("AIPLAT_HOME", str(tmp_path / "home"))
    os.environ.pop("AIPLAT_KNOWLEDGE_OBJECT_TYPE_BULK", None)
    db = str(tmp_path / "ot.sqlite3")
    residual = bulk_transition_object_types(
        [
            {
                "tenant_id": "t-bulk-a",
                "object_type_id": "X",
                "version": "1.0.0",
                "to_status": "in_review",
            }
        ],
        actor="a",
        reason="r",
        db_path=db,
    )
    assert residual["status"] == "object_type_bulk_unavailable"
    assert residual.get("bulk_product_surface") is False

    for tid in ("t-bulk-a", "t-bulk-b"):
        submit_object_type_draft(
            tenant_id=tid,
            object_type_id="X",
            version="1.0.0",
            definition={"object_type_id": "X", "label": "x", "primary_key": "id"},
            actor="a",
            reason="draft",
            db_path=db,
        )
    applied = _product(
        [
            {
                "tenant_id": "t-bulk-a",
                "object_type_id": "X",
                "version": "1.0.0",
                "to_status": "in_review",
            },
            {
                "tenant_id": "t-bulk-b",
                "object_type_id": "X",
                "version": "1.0.0",
                "to_status": "in_review",
            },
        ],
        actor="a",
        reason="product",
        db_path=db,
    )
    assert applied["status"] == "ok"
    assert applied["via"] == "product"
    assert applied["bulk_product_surface"] is True
    assert applied["certified"] is False
    assert int(applied["ok_count"]) == 2
    # Facade 不透传 db_path；空 items 仍走产品面（via=empty_items）
    fr = bulk_transition_object_types_product(
        [],
        actor="a",
        reason="facade",
    )
    assert fr.get("bulk_product_surface") is True
    assert fr.get("status") == "object_type_bulk_unavailable"
    assert fr.get("via") == "empty_items"


def test_docs_and_wiring_state():
    mod = (
        ROOT
        / "aiPlat-core"
        / "core"
        / "harness"
        / "knowledge_pipeline"
        / "object_type_publish.py"
    )
    text = mod.read_text(encoding="utf-8")
    assert "bulk_transition_object_types_product" in text
    assert "run_bulk_portal_product_suite" in text
    facade = ROOT / "aiPlat-core" / "core" / "api" / "core_facade.py"
    assert "bulk_transition_object_types_product" in facade.read_text(encoding="utf-8")
    routes = (
        ROOT
        / "aiPlat-platform"
        / "apps"
        / "fde"
        / "api"
        / "object_type_publish_routes.py"
    )
    assert "object-types/product/bulk-transition" in routes.read_text(encoding="utf-8")
    panel = (
        ROOT
        / "aiPlat-management"
        / "frontend"
        / "src"
        / "pages"
        / "KnowledgeFactory"
        / "ObjectTypePublishPanel.tsx"
    )
    assert "object-types/product/bulk-transition" in panel.read_text(encoding="utf-8")
