"""N11/N14 deepen + residual：迁移切写授权 / 生产就绪回执；certified 恒 false。"""
from __future__ import annotations

from pathlib import Path

from core.api.core_facade import (
    attest_knowledge_production_cutover_readiness,
    evaluate_migration_cutover_auth_gate,
    run_migration_cutover_auth_suite,
)
from core.harness.knowledge_pipeline.knowledge_migration import (
    attest_production_cutover_readiness,
    evaluate_migration_cutover_auth_gate as core_gate,
    run_migration_cutover_auth_suite as core_suite,
)

ROOT = Path(__file__).resolve().parents[6]


def test_suite_and_gate_honesty():
    suite = core_suite()
    assert suite["ok"] is True
    assert suite["passed"] == 10
    assert suite["certified"] is False
    assert suite["production_cutover_certified"] is False
    assert suite.get("n11_n14_migration_freeze") is True
    assert suite["checks"]["prod_attest_unavailable"] is True
    assert suite["checks"]["prod_attest_opt_in"] is True
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


def test_prod_attest_unavailable_default():
    r = attest_production_cutover_readiness(
        "no-job",
        tenant_id="t",
        actor="ops",
        reason="check",
    )
    assert r["status"] == "production_attestation_unavailable"
    assert r["production_cutover_certified"] is False
    fr = attest_knowledge_production_cutover_readiness(
        "no-job",
        tenant_id="t",
        actor="ops",
        reason="check",
    )
    assert fr["status"] == "production_attestation_unavailable"


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
    assert "attest_production_cutover_readiness" in text
    assert "run_migration_cutover_auth_suite" in text
    facade = ROOT / "aiPlat-core" / "core" / "api" / "core_facade.py"
    ftext = facade.read_text(encoding="utf-8")
    assert "run_migration_cutover_auth_suite" in ftext
    assert "attest_knowledge_production_cutover_readiness" in ftext
