"""N02 seed authority 产品面：默认可用；certified / complete 恒 false。"""
from __future__ import annotations

import os
from pathlib import Path

from core.api.core_facade import (
    apply_published_seed_authority_product,
    evaluate_seed_authority_product_gate,
    list_knowledge_object_type_seed_catalog,
    run_seed_authority_product_suite,
)
from core.harness.knowledge_pipeline.object_type_publish import (
    apply_published_seed_authority,
    evaluate_seed_authority_product_gate as _gate,
    list_object_type_seed_catalog,
    run_seed_authority_product_suite as _suite,
)

ROOT = Path(__file__).resolve().parents[6]


def test_product_suite_and_gate_honesty():
    suite = _suite()
    assert suite["ok"] is True
    assert suite["passed"] == 3
    assert suite["certified"] is False
    assert suite["seed_replacement_complete"] is False
    assert suite["seed_product_surface"] is True
    assert suite["workspace_seeds_mutated"] is False
    ids = {c["id"] for c in suite["cases"] if c.get("ok")}
    assert "seed_authority_product_catalog" in ids
    assert "seed_authority_product_apply" in ids
    assert "honesty_product_certified_false" in ids
    gate = _gate(suite)
    assert gate["ok"] is True
    bad = dict(suite)
    bad["certified"] = True
    honesty = _gate(bad)
    assert honesty["ok"] is False
    assert "honesty_certified_flag_forbidden" in honesty["issues"]


def test_facade_product_suite():
    suite = run_seed_authority_product_suite()
    assert suite["ok"] is True
    gate = evaluate_seed_authority_product_gate(suite)
    assert gate["ok"] is True
    assert gate["certified"] is False
    assert gate["seed_product_surface"] is True


def test_product_without_residual_env(tmp_path, monkeypatch):
    monkeypatch.setenv("AIPLAT_HOME", str(tmp_path / "home"))
    os.environ.pop("AIPLAT_KNOWLEDGE_OBJECT_TYPE_SEED_REPLACE", None)
    catalog = list_object_type_seed_catalog()
    assert catalog["status"] == "ok"
    assert catalog["seed_product_surface"] is True
    assert (catalog.get("items") or []), "expected workspace_seeds *-object-types.json"
    # residual 仍关闭
    residual = apply_published_seed_authority(
        tenant_id="t-seed-product",
        seed_path=str(catalog["items"][0]["path"]),
        write=False,
    )
    assert residual["status"] == "seed_replacement_unavailable"
    # 产品面默认可用
    applied = apply_published_seed_authority_product(
        tenant_id="t-seed-product",
        seed_path=str(catalog["items"][0]["name"]),
        write=False,
    )
    assert applied["status"] == "ok"
    assert applied["via"] == "product"
    assert applied["workspace_seeds_mutated"] is False
    assert applied["seed_replacement_complete"] is False
    fr = list_knowledge_object_type_seed_catalog()
    assert fr["status"] == "ok"


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
    assert "apply_published_seed_authority_product" in text
    assert "list_object_type_seed_catalog" in text
    facade = ROOT / "aiPlat-core" / "core" / "api" / "core_facade.py"
    assert "apply_published_seed_authority_product" in facade.read_text(encoding="utf-8")
    routes = (
        ROOT
        / "aiPlat-platform"
        / "apps"
        / "fde"
        / "api"
        / "object_type_publish_routes.py"
    )
    assert "object-types/product/seed-authority" in routes.read_text(encoding="utf-8")
    panel = (
        ROOT
        / "aiPlat-management"
        / "frontend"
        / "src"
        / "pages"
        / "KnowledgeFactory"
        / "ObjectTypePublishPanel.tsx"
    )
    assert "object-types/product/seed-files" in panel.read_text(encoding="utf-8")
