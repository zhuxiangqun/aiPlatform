"""N11/N14 生产切写就绪产品面：默认可用；certified / production_cutover_certified 恒 false。"""
from __future__ import annotations

import os
from pathlib import Path

from core.api.core_facade import (
    attest_knowledge_production_cutover_readiness,
    attest_knowledge_production_cutover_readiness_product,
    evaluate_knowledge_production_attest_product_gate,
    run_knowledge_production_attest_product_suite,
)
from core.harness.knowledge_pipeline.knowledge_migration import (
    evaluate_production_attest_product_gate as _gate,
    run_production_attest_product_suite as _suite,
)

ROOT = Path(__file__).resolve().parents[6]


def test_product_suite_and_gate_honesty():
    suite = _suite()
    assert suite["ok"] is True
    assert suite["passed"] == 3
    assert suite["certified"] is False
    assert suite["production_cutover_certified"] is False
    assert suite["prod_attest_product_surface"] is True
    ids = {c["id"] for c in suite["cases"] if c.get("ok")}
    assert "prod_attest_product_eval" in ids
    assert "prod_attest_product_blocked_unauthorized" in ids
    assert "honesty_product_certified_false" in ids
    gate = _gate(suite)
    assert gate["ok"] is True
    bad = dict(suite)
    bad["certified"] = True
    honesty = _gate(bad)
    assert honesty["ok"] is False
    assert "honesty_certified_flag_forbidden" in honesty["issues"]
    bad2 = dict(suite)
    bad2["production_cutover_certified"] = True
    honesty2 = _gate(bad2)
    assert honesty2["ok"] is False
    # 为什么：gate 将 certified / production_cutover_certified 并入同一 honesty 码
    assert "honesty_certified_flag_forbidden" in honesty2["issues"]


def test_facade_product_suite():
    suite = run_knowledge_production_attest_product_suite()
    assert suite["ok"] is True
    gate = evaluate_knowledge_production_attest_product_gate(suite)
    assert gate["ok"] is True
    assert gate["prod_attest_product_surface"] is True
    assert gate["production_cutover_certified"] is False


def test_product_without_residual_env(tmp_path, monkeypatch):
    monkeypatch.setenv("AIPLAT_HOME", str(tmp_path / "home"))
    os.environ.pop("AIPLAT_KNOWLEDGE_PRODUCTION_ATTEST", None)
    residual = attest_knowledge_production_cutover_readiness(
        "missing-job",
        tenant_id="t-prod",
        actor="ops",
        reason="residual-check",
    )
    assert residual["status"] == "production_attestation_unavailable"
    assert residual.get("prod_attest_product_surface") is False
    # 产品面默认可用（无授权作业时诚实阻断，但不是 unavailable）
    product = attest_knowledge_production_cutover_readiness_product(
        "missing-job",
        tenant_id="t-prod",
        actor="ops",
        reason="product-check",
    )
    assert product["status"] == "not_found"
    assert product.get("via") == "product"
    assert product.get("prod_attest_product_surface") is True
    assert product.get("production_cutover_certified") is False
    assert product.get("certified") is False


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
    assert "attest_production_cutover_readiness_product" in text
    assert "run_production_attest_product_suite" in text
    facade = ROOT / "aiPlat-core" / "core" / "api" / "core_facade.py"
    assert "attest_knowledge_production_cutover_readiness_product" in facade.read_text(
        encoding="utf-8"
    )
    routes = (
        ROOT
        / "aiPlat-platform"
        / "apps"
        / "fde"
        / "api"
        / "knowledge_migration_routes.py"
    )
    assert "knowledge-migrations/product/production-attest" in routes.read_text(
        encoding="utf-8"
    )
    panel = (
        ROOT
        / "aiPlat-management"
        / "frontend"
        / "src"
        / "pages"
        / "KnowledgeFactory"
        / "ProductionAttestPanel.tsx"
    )
    assert "knowledge-migrations/product/production-attest" in panel.read_text(
        encoding="utf-8"
    )
