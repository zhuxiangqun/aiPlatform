"""N24 ops console residual：运维台薄壳；certified / full 恒 false。"""
from __future__ import annotations

from pathlib import Path

from core.api.core_facade import (
    build_knowledge_ops_console_snapshot,
    evaluate_knowledge_ops_console_gate,
    run_knowledge_ops_console_suite,
)
from core.harness.knowledge_pipeline.ops_console import (
    build_ops_console_snapshot,
    evaluate_ops_console_gate,
    run_ops_console_suite,
)

ROOT = Path(__file__).resolve().parents[6]


def test_suite_and_gate_honesty():
    suite = run_ops_console_suite()
    assert suite["ok"] is True
    assert suite["passed"] == 3
    assert suite["certified"] is False
    assert suite["n24_full_conformance"] is False
    assert suite["full_ops_console"] is False
    assert suite.get("n24_unified_audit_freeze") is True
    ids = {c["id"] for c in suite["cases"] if c.get("ok")}
    assert "ops_console_unavailable" in ids
    assert "ops_console_opt_in" in ids
    assert "honesty_certified_false" in ids
    gate = evaluate_ops_console_gate(suite)
    assert gate["ok"] is True
    bad = dict(suite)
    bad["certified"] = True
    honesty = evaluate_ops_console_gate(bad)
    assert honesty["ok"] is False
    assert "honesty_certified_flag_forbidden" in honesty["issues"]
    bad2 = dict(suite)
    bad2["full_ops_console"] = True
    honesty2 = evaluate_ops_console_gate(bad2)
    assert honesty2["ok"] is False
    assert "honesty_full_ops_console_forbidden" in honesty2["issues"]


def test_facade_suite():
    suite = run_knowledge_ops_console_suite()
    assert suite["ok"] is True
    gate = evaluate_knowledge_ops_console_gate(suite)
    assert gate["ok"] is True
    assert gate["certified"] is False
    assert gate["full_ops_console"] is False


def test_ops_console_unavailable_default():
    r = build_ops_console_snapshot("t1", include_live=False)
    assert r["status"] == "ops_console_unavailable"
    assert r["certified"] is False
    assert r["full_ops_console"] is False
    fr = build_knowledge_ops_console_snapshot("t1", include_live=False)
    assert fr["status"] == "ops_console_unavailable"


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
    assert "build_ops_console_snapshot" in text
    assert "run_ops_console_suite" in text
    facade = ROOT / "aiPlat-core" / "core" / "api" / "core_facade.py"
    assert "build_knowledge_ops_console_snapshot" in facade.read_text(
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
    assert "ops-console/snapshot" in routes.read_text(encoding="utf-8")
    panel = (
        ROOT
        / "aiPlat-management"
        / "frontend"
        / "src"
        / "pages"
        / "KnowledgeFactory"
        / "OpsConsolePanel.tsx"
    )
    assert "ops-console/snapshot" in panel.read_text(encoding="utf-8")
    page = (
        ROOT
        / "aiPlat-management"
        / "frontend"
        / "src"
        / "pages"
        / "KnowledgeFactory"
        / "KnowledgeFactoryPage.tsx"
    )
    assert "OpsConsolePanel" in page.read_text(encoding="utf-8")
