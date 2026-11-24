"""N24 ops console product surface：默认可用；certified 恒 false。"""
from __future__ import annotations

import os
from pathlib import Path

from core.api.core_facade import (
    build_knowledge_ops_console_product_snapshot,
    evaluate_knowledge_ops_console_product_gate,
    export_knowledge_ops_console_product,
    get_knowledge_ops_console_schema,
    run_knowledge_ops_console_product_suite,
    save_knowledge_ops_console_schema,
)
from core.harness.knowledge_pipeline.ops_console import (
    build_ops_console_product_snapshot,
    evaluate_ops_console_product_gate,
    run_ops_console_product_suite,
)

ROOT = Path(__file__).resolve().parents[6]


def test_product_suite_and_gate_honesty():
    suite = run_ops_console_product_suite()
    assert suite["ok"] is True
    assert suite["passed"] == 5
    assert suite["certified"] is False
    assert suite["n24_full_conformance"] is False
    assert suite["full_ops_console"] is True
    assert suite["export_complete"] is False
    assert suite.get("n24_unified_audit_freeze") is True
    ids = {c["id"] for c in suite["cases"] if c.get("ok")}
    assert "ops_console_product_snapshot" in ids
    assert "ops_console_product_schema" in ids
    assert "ops_console_product_schema_form" in ids
    assert "ops_console_product_export" in ids
    assert "honesty_product_certified_false" in ids
    gate = evaluate_ops_console_product_gate(suite)
    assert gate["ok"] is True
    bad = dict(suite)
    bad["certified"] = True
    honesty = evaluate_ops_console_product_gate(bad)
    assert honesty["ok"] is False
    assert "honesty_certified_flag_forbidden" in honesty["issues"]
    bad2 = dict(suite)
    bad2["full_ops_console"] = False
    honesty2 = evaluate_ops_console_product_gate(bad2)
    assert honesty2["ok"] is False
    assert "product_full_ops_console_required" in honesty2["issues"]


def test_facade_product_suite():
    suite = run_knowledge_ops_console_product_suite()
    assert suite["ok"] is True
    gate = evaluate_knowledge_ops_console_product_gate(suite)
    assert gate["ok"] is True
    assert gate["certified"] is False
    assert gate["full_ops_console"] is True


def test_product_snapshot_without_residual_env():
    os.environ.pop("AIPLAT_KNOWLEDGE_OPS_CONSOLE", None)
    os.environ.pop("AIPLAT_KNOWLEDGE_OPS_CONSOLE_EXPORT", None)
    r = build_ops_console_product_snapshot("t-product", include_live=False)
    assert r["status"] == "ok"
    assert r["full_ops_console"] is True
    assert r["certified"] is False
    assert (r.get("panels") or {}).get("schema_editor") is True
    assert (r.get("panels") or {}).get("schema_form_editor") is True
    fr = build_knowledge_ops_console_product_snapshot("t-product", include_live=False)
    assert fr["status"] == "ok"
    assert fr["full_ops_console"] is True


def test_schema_roundtrip_and_product_export(tmp_path, monkeypatch):
    monkeypatch.setenv("AIPLAT_HOME", str(tmp_path / "home"))
    ot_db = str(tmp_path / "ot.sqlite3")
    saved = save_knowledge_ops_console_schema(
        tenant_id="t-schema",
        object_type_id="Widget",
        definition={"object_type_id": "Widget", "label": "w", "fields": []},
        actor="test",
        reason="roundtrip",
        db_path=ot_db,
    )
    assert saved["status"] == "ok"
    loaded = get_knowledge_ops_console_schema(
        tenant_id="t-schema",
        object_type_id="Widget",
        db_path=ot_db,
    )
    assert loaded["status"] == "ok"
    assert isinstance(loaded.get("definition"), dict)
    assert isinstance(loaded.get("form"), dict)
    assert loaded.get("schema_form_editor") is True

    form_saved = save_knowledge_ops_console_schema(
        tenant_id="t-schema",
        object_type_id="FormWidget",
        form={
            "object_type_id": "FormWidget",
            "label": "fw",
            "fields": [
                {"name": "a", "type": "string", "required": True, "description": "x"},
            ],
        },
        actor="test",
        reason="form-roundtrip",
        db_path=ot_db,
    )
    assert form_saved["status"] == "ok"
    assert form_saved.get("via_form") is True
    form_loaded = get_knowledge_ops_console_schema(
        tenant_id="t-schema",
        object_type_id="FormWidget",
        db_path=ot_db,
    )
    fields = (form_loaded.get("form") or {}).get("fields") or []
    assert len(fields) == 1
    assert fields[0]["name"] == "a"
    assert fields[0]["required"] is True

    exported = export_knowledge_ops_console_product(
        "t-schema",
        include_live=False,
        write=True,
    )
    assert exported["status"] == "ok"
    assert exported["full_ops_console"] is True
    assert exported["export_complete"] is False
    assert (exported.get("payload") or {}).get("download_filename")


def test_docs_and_wiring_state():
    mod = (
        ROOT
        / "aiPlat-core"
        / "core"
        / "harness"
        / "knowledge_pipeline"
        / "ops_console.py"
    )
    text = mod.read_text(encoding="utf-8")
    assert "build_ops_console_product_snapshot" in text
    assert "run_ops_console_product_suite" in text
    facade = ROOT / "aiPlat-core" / "core" / "api" / "core_facade.py"
    assert "build_knowledge_ops_console_product_snapshot" in facade.read_text(
        encoding="utf-8"
    )
    routes = (
        ROOT
        / "aiPlat-platform"
        / "apps"
        / "fde"
        / "api"
        / "ops_console_routes.py"
    )
    assert "ops-console/product/snapshot" in routes.read_text(encoding="utf-8")
    panel = (
        ROOT
        / "aiPlat-management"
        / "frontend"
        / "src"
        / "pages"
        / "KnowledgeFactory"
        / "OpsConsolePanel.tsx"
    )
    panel_text = panel.read_text(encoding="utf-8")
    assert "ops-console/product/snapshot" in panel_text
    assert "schema_form" in panel_text or "字段表单" in panel_text
    assert "form:" in panel_text or '"form"' in panel_text or "formPayload" in panel_text
