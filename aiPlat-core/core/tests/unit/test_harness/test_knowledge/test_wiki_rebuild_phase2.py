"""N05 deepen：Wiki 有条件重建；certified 恒 false。"""
from __future__ import annotations

from pathlib import Path

import pytest

from core.api.core_facade import (
    evaluate_wiki_rebuild_gate,
    run_wiki_rebuild_suite,
)
from core.harness.knowledge_pipeline.wiki_rebuild import (
    evaluate_wiki_rebuild_gate as core_gate,
    run_wiki_rebuild_suite as core_suite,
)

ROOT = Path(__file__).resolve().parents[6]


@pytest.mark.asyncio
async def test_suite_and_gate_honesty():
    suite = await core_suite()
    assert suite["ok"] is True
    assert suite["passed"] == 6
    assert suite["certified"] is False
    assert suite["n05_full_conformance"] is False
    assert suite["wiki_full_certified"] is False
    gate = core_gate(suite)
    assert gate["ok"] is True
    bad = dict(suite)
    bad["certified"] = True
    honesty = core_gate(bad)
    assert honesty["ok"] is False
    assert "honesty_certified_flag_forbidden" in honesty["issues"]


@pytest.mark.asyncio
async def test_facade_suite():
    suite = await run_wiki_rebuild_suite()
    assert suite["ok"] is True
    gate = evaluate_wiki_rebuild_gate(suite)
    assert gate["ok"] is True
    assert gate["certified"] is False


def test_docs_and_wiring_state():
    mod = (
        ROOT
        / "aiPlat-core"
        / "core"
        / "harness"
        / "knowledge_pipeline"
        / "wiki_rebuild.py"
    )
    text = mod.read_text(encoding="utf-8")
    assert "project_facts_to_wiki" in text
    assert "run_wiki_rebuild_suite" in text
    facade = ROOT / "aiPlat-core" / "core" / "api" / "core_facade.py"
    assert "fact_ledger_project_to_wiki" in facade.read_text(encoding="utf-8")
    route = (
        ROOT
        / "aiPlat-platform"
        / "apps"
        / "fde"
        / "api"
        / "wiki_rebuild_routes.py"
    )
    assert "fact_ledger_project_to_wiki" in route.read_text(encoding="utf-8")
    router = ROOT / "aiPlat-platform" / "apps" / "fde" / "api" / "router.py"
    assert "wiki_rebuild_routes" in router.read_text(encoding="utf-8")
