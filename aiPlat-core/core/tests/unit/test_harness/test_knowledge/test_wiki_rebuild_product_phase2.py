"""N05 产品面：Wiki 有条件重建 + 有界 FTS sync；certified / fts_full 恒 false。"""
from __future__ import annotations

from pathlib import Path

import pytest

from core.api.core_facade import (
    evaluate_wiki_rebuild_product_gate,
    run_wiki_rebuild_product_suite,
)
from core.harness.knowledge_pipeline.wiki_rebuild import (
    evaluate_wiki_rebuild_product_gate as core_gate,
    rebuild_wiki_fts_product,
    run_wiki_rebuild_product_suite as core_suite,
)

ROOT = Path(__file__).resolve().parents[6]


@pytest.mark.asyncio
async def test_product_suite_and_gate_honesty():
    suite = await core_suite()
    assert suite["ok"] is True
    assert suite["passed"] == 6
    assert suite["certified"] is False
    assert suite["wiki_engine_fts_full"] is False
    assert suite["wiki_rebuild_product_surface"] is True
    assert suite["wiki_fts_product_sync"] is True
    assert suite["n05_wiki_rebuild_freeze"] is True
    gate = core_gate(suite)
    assert gate["ok"] is True
    bad = dict(suite)
    bad["certified"] = True
    honesty = core_gate(bad)
    assert honesty["ok"] is False
    assert "honesty_certified_flag_forbidden" in honesty["issues"]
    bad2 = dict(suite)
    bad2["wiki_engine_fts_full"] = True
    assert "honesty_wiki_engine_fts_full_forbidden" in core_gate(bad2)["issues"]
    missing = dict(suite)
    missing.pop("wiki_rebuild_product_surface", None)
    assert "product_wiki_rebuild_product_surface_required" in core_gate(missing)["issues"]


@pytest.mark.asyncio
async def test_facade_product_suite():
    suite = await run_wiki_rebuild_product_suite()
    assert suite["ok"] is True
    gate = evaluate_wiki_rebuild_product_gate(suite)
    assert gate["ok"] is True
    assert gate["certified"] is False
    assert gate["wiki_engine_fts_full"] is False


def test_rebuild_wiki_fts_product_honesty(tmp_path, monkeypatch):
    monkeypatch.setenv("AIPLAT_WIKI_FTS_PATH", str(tmp_path / "fts.db"))

    def _fake_index() -> int:
        return 0

    monkeypatch.setattr(
        "core.harness.knowledge.wiki_fts.fts_index_pages",
        _fake_index,
    )
    out = rebuild_wiki_fts_product()
    assert out["status"] == "ok"
    assert out["wiki_fts_product_rebuild"] is True
    assert out["wiki_engine_fts_full"] is False
    assert out["certified"] is False
    assert out["wiki_rebuild_product_surface"] is True


def test_docs_and_wiring_product_state():
    mod = (
        ROOT
        / "aiPlat-core"
        / "core"
        / "harness"
        / "knowledge_pipeline"
        / "wiki_rebuild.py"
    )
    text = mod.read_text(encoding="utf-8")
    assert "project_facts_to_wiki_product" in text
    assert "rebuild_wiki_fts_product" in text
    assert "run_wiki_rebuild_product_suite" in text
    facade = ROOT / "aiPlat-core" / "core" / "api" / "core_facade.py"
    fac = facade.read_text(encoding="utf-8")
    assert "project_facts_to_wiki_product" in fac
    assert "rebuild_wiki_fts_product" in fac
    route = (
        ROOT
        / "aiPlat-platform"
        / "apps"
        / "fde"
        / "api"
        / "wiki_rebuild_routes.py"
    )
    rtext = route.read_text(encoding="utf-8")
    assert "/wiki-rebuild/product" in rtext
    assert "/wiki-rebuild/product/fts" in rtext
    panel = (
        ROOT
        / "aiPlat-management"
        / "frontend"
        / "src"
        / "pages"
        / "KnowledgeFactory"
        / "WikiRebuildPanel.tsx"
    )
    assert panel.is_file()
    page = (
        ROOT
        / "aiPlat-management"
        / "frontend"
        / "src"
        / "pages"
        / "KnowledgeFactory"
        / "KnowledgeFactoryPage.tsx"
    )
    assert "WikiRebuildPanel" in page.read_text(encoding="utf-8")
    evidence = (
        ROOT
        / "reports"
        / "products"
        / "knowledge-system"
        / "v4.3.1"
        / "phase2-n05-wiki-rebuild-product-evidence.md"
    )
    assert evidence.is_file()
