"""N11/N14 deepen：迁移切写授权；certified 恒 false。"""
from __future__ import annotations

from pathlib import Path

from core.api.core_facade import (
    evaluate_migration_cutover_auth_gate,
    run_migration_cutover_auth_suite,
)
from core.harness.knowledge_pipeline.knowledge_migration import (
    evaluate_migration_cutover_auth_gate as core_gate,
    run_migration_cutover_auth_suite as core_suite,
)

ROOT = Path(__file__).resolve().parents[6]


def test_suite_and_gate_honesty():
    suite = core_suite()
    assert suite["ok"] is True
    assert suite["passed"] == 8
    assert suite["certified"] is False
    assert suite["production_cutover_certified"] is False
    gate = core_gate(suite)
    assert gate["ok"] is True
    bad = dict(suite)
    bad["production_cutover_certified"] = True
    honesty = core_gate(bad)
    assert honesty["ok"] is False
    assert "honesty_production_cutover_forbidden" in honesty["issues"]


def test_facade_suite():
    suite = run_migration_cutover_auth_suite()
    assert suite["ok"] is True
    gate = evaluate_migration_cutover_auth_gate(suite)
    assert gate["ok"] is True
    assert gate["certified"] is False


def test_docs_and_wiring_state():
    mod = (
        ROOT
        / "aiPlat-core"
        / "core"
        / "harness"
        / "knowledge_pipeline"
        / "knowledge_migration.py"
    )
    text = mod.read_text(encoding="utf-8")
    assert "authorize_migration_cutover" in text
    assert "run_migration_cutover_auth_suite" in text
    facade = ROOT / "aiPlat-core" / "core" / "api" / "core_facade.py"
    assert "run_migration_cutover_auth_suite" in facade.read_text(encoding="utf-8")
