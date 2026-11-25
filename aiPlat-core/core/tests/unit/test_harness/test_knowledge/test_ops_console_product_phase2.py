"""N24 ops console product surface slice-2：四面板 + 通用导出；certified 恒 false。"""
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
    export_ops_console_product,
    run_ops_console_product_suite,
)
from core.harness.knowledge_pipeline.unified_audit_bus import append_unified_audit_event

ROOT = Path(__file__).resolve().parents[6]


def test_product_suite_and_gate_honesty():
    suite = run_ops_console_product_suite()
    assert suite["ok"] is True
    assert suite["passed"] == 7
    assert suite["certified"] is False
    assert suite["n24_full_conformance"] is False
    assert suite["full_ops_console"] is True
    assert suite["ops_console_general_export"] is True
    assert suite["export_complete"] is False
    assert suite.get("n24_unified_audit_freeze") is True
    ids = {c["id"] for c in suite["cases"] if c.get("ok")}
    assert "ops_console_product_snapshot" in ids
    assert "ops_console_product_multi_panel" in ids
    assert "ops_console_product_schema" in ids
    assert "ops_console_product_schema_form" in ids
    assert "ops_console_product_export" in ids
    assert "ops_console_product_general_export" in ids
    assert "honesty_product_certified_false" in ids
    gate = evaluate_ops_console_product_gate(suite)
    assert gate["ok"] is True
    assert gate["ops_console_general_export"] is True
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
    bad3 = dict(suite)
    bad3["ops_console_general_export"] = False
    honesty3 = evaluate_ops_console_product_gate(bad3)
    assert honesty3["ok"] is False
    assert "product_ops_console_general_export_required" in honesty3["issues"]
    bad4 = dict(suite)
    bad4["export_complete"] = True
    honesty4 = evaluate_ops_console_product_gate(bad4)
    assert honesty4["ok"] is False
    assert "honesty_export_complete_forbidden" in honesty4["issues"]


def test_facade_product_suite():
    suite = run_knowledge_ops_console_product_suite()
    assert suite["ok"] is True
    gate = evaluate_knowledge_ops_console_product_gate(suite)
    assert gate["ok"] is True
    assert gate["certified"] is False
    assert gate["full_ops_console"] is True
    assert gate["ops_console_general_export"] is True


def test_product_snapshot_multi_panel_without_residual_env():
    os.environ.pop("AIPLAT_KNOWLEDGE_OPS_CONSOLE", None)
    os.environ.pop("AIPLAT_KNOWLEDGE_OPS_CONSOLE_EXPORT", None)
    r = build_ops_console_product_snapshot("t-product", include_live=False)
    assert r["status"] == "ok"
    assert r["full_ops_console"] is True
    assert r["ops_console_general_export"] is True
    assert r["certified"] is False
    panels = r.get("panels") or {}
    for key in ("audit", "slo", "schema", "export"):
        assert panels.get(key) is True
    assert panels.get("schema_editor") is True
    assert panels.get("schema_form_editor") is True
    summaries = r.get("panel_summaries") or {}
    assert isinstance(summaries.get("audit"), dict)
    assert isinstance(summaries.get("slo"), dict)
    assert isinstance(summaries.get("schema"), dict)
    assert isinstance(summaries.get("export"), dict)
    fr = build_knowledge_ops_console_product_snapshot("t-product", include_live=False)
    assert fr["status"] == "ok"
    assert fr["full_ops_console"] is True
    assert (fr.get("panels") or {}).get("audit") is True


def test_schema_roundtrip_and_general_export_bundle(tmp_path, monkeypatch):
    monkeypatch.setenv("AIPLAT_HOME", str(tmp_path / "home"))
    ot_db = str(tmp_path / "ot.sqlite3")
    audit_db = str(tmp_path / "audit.sqlite3")
    append_unified_audit_event(
        tenant_id="t-schema",
        event_id="ops-export-probe-1",
        stream="ops_console_product_probe",
        event_type="probe",
        occurred_at=__import__("time").time(),
        payload={"ok": True},
        db_path=audit_db,
    )
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
        include_audit_sample=True,
        object_type_id="Widget",
        schema_db_path=ot_db,
        audit_db_path=audit_db,
        audit_sample_limit=20,
    )
    assert exported["status"] == "ok"
    assert exported["full_ops_console"] is True
    assert exported["ops_console_general_export"] is True
    assert exported["export_complete"] is False
    assert exported["certified"] is False
    payload = exported.get("payload") or {}
    assert payload.get("kind") == "ops_console_product_bundle"
    assert payload.get("ops_console_general_export") is True
    assert payload.get("export_complete") is False
    assert isinstance(payload.get("snapshot"), dict)
    assert isinstance(payload.get("schema"), dict)
    assert isinstance(payload.get("audit_sample"), list)
    assert len(payload["audit_sample"]) <= 20
    assert len(payload["audit_sample"]) >= 1
    assert isinstance(payload.get("slo_miss_detail"), dict)
    assert payload.get("download_filename")

    capped = export_ops_console_product(
        "t-schema",
        include_live=False,
        write=False,
        include_audit_sample=True,
        audit_db_path=audit_db,
        schema_db_path=ot_db,
        audit_sample_limit=999,
    )
    assert capped["status"] == "ok"
    assert (capped.get("payload") or {}).get("audit_sample_limit") == 20


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
    assert "ops_console_product_multi_panel" in text
    assert "ops_console_product_general_export" in text
    assert "ops_console_general_export" in text
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
    routes_text = routes.read_text(encoding="utf-8")
    assert "ops-console/product/snapshot" in routes_text
    assert "include_audit_sample" in routes_text
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
    assert "Audit" in panel_text and "SLO" in panel_text
    assert "schema_form" in panel_text or "字段表单" in panel_text
    assert "general export" in panel_text or "通用 bundle" in panel_text
    assert "export_complete=false" in panel_text or "非 export_complete" in panel_text
    evidence = (
        ROOT
        / "reports"
        / "products"
        / "knowledge-system"
        / "v4.3.1"
        / "phase2-n24-ops-console-product-slice2-evidence.md"
    )
    assert evidence.is_file()
    ev = evidence.read_text(encoding="utf-8")
    assert "ops_console_general_export" in ev
    assert "ops_console_product_multi_panel" in ev
