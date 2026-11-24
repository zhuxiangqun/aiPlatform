"""N24 ops console export residual：有界 JSON 导出；certified / full 恒 false。"""
from __future__ import annotations

from pathlib import Path

from core.api.core_facade import (
    evaluate_knowledge_ops_console_export_gate,
    export_knowledge_ops_console_snapshot,
    run_knowledge_ops_console_export_suite,
)
from core.harness.knowledge_pipeline.ops_console import (
    evaluate_ops_console_export_gate,
    export_ops_console_snapshot,
    run_ops_console_export_suite,
)

ROOT = Path(__file__).resolve().parents[6]


def test_export_suite_and_gate_honesty():
    suite = run_ops_console_export_suite()
    assert suite["ok"] is True
    assert suite["passed"] == 3
    assert suite["certified"] is False
    assert suite["n24_full_conformance"] is False
    assert suite["full_ops_console"] is False
    assert suite["export_complete"] is False
    assert suite.get("n24_unified_audit_freeze") is True
    ids = {c["id"] for c in suite["cases"] if c.get("ok")}
    assert "ops_console_export_unavailable" in ids
    assert "ops_console_export_opt_in" in ids
    assert "honesty_export_certified_false" in ids
    gate = evaluate_ops_console_export_gate(suite)
    assert gate["ok"] is True
    bad = dict(suite)
    bad["certified"] = True
    honesty = evaluate_ops_console_export_gate(bad)
    assert honesty["ok"] is False
    assert "honesty_certified_flag_forbidden" in honesty["issues"]
    bad2 = dict(suite)
    bad2["export_complete"] = True
    honesty2 = evaluate_ops_console_export_gate(bad2)
    assert honesty2["ok"] is False
    assert "honesty_export_complete_forbidden" in honesty2["issues"]


def test_facade_export_suite():
    suite = run_knowledge_ops_console_export_suite()
    assert suite["ok"] is True
    gate = evaluate_knowledge_ops_console_export_gate(suite)
    assert gate["ok"] is True
    assert gate["certified"] is False
    assert gate["full_ops_console"] is False
    assert gate["export_complete"] is False


def test_export_unavailable_default():
    r = export_ops_console_snapshot("t1", include_live=False, write=False)
    assert r["status"] == "ops_console_export_unavailable"
    assert r["certified"] is False
    assert r["full_ops_console"] is False
    assert r["export_complete"] is False
    fr = export_knowledge_ops_console_snapshot("t1", include_live=False, write=False)
    assert fr["status"] == "ops_console_export_unavailable"


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
    assert "export_ops_console_snapshot" in text
    assert "run_ops_console_export_suite" in text
    facade = ROOT / "aiPlat-core" / "core" / "api" / "core_facade.py"
    assert "export_knowledge_ops_console_snapshot" in facade.read_text(
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
    assert "ops-console/export" in routes.read_text(encoding="utf-8")
    panel = (
        ROOT
        / "aiPlat-management"
        / "frontend"
        / "src"
        / "pages"
        / "KnowledgeFactory"
        / "OpsConsolePanel.tsx"
    )
    assert "ops-console/export" in panel.read_text(encoding="utf-8")
