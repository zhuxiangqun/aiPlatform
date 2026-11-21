"""N10 deepen：知识域 gold 评测流水线；accuracy/certified 恒 false。"""
from __future__ import annotations

from pathlib import Path

import pytest

from core.api.core_facade import (
    evaluate_knowledge_gold_eval_gate,
    run_knowledge_gold_eval_suite,
)
from core.harness.knowledge_pipeline.knowledge_gold_eval import (
    KnowledgeGoldEvalError,
    evaluate_knowledge_gold_eval_gate as core_gate,
    register_gold_dataset,
    run_knowledge_gold_eval_suite as core_suite,
)

ROOT = Path(__file__).resolve().parents[6]


@pytest.mark.asyncio
async def test_suite_and_gate_honesty():
    suite = await core_suite()
    assert suite["ok"] is True
    assert suite["passed"] == 6
    assert suite["certified"] is False
    assert suite["n10_full_conformance"] is False
    assert suite["accuracy_claim"] is False
    gate = core_gate(suite)
    assert gate["ok"] is True
    bad = dict(suite)
    bad["accuracy_claim"] = True
    honesty = core_gate(bad)
    assert honesty["ok"] is False
    assert "honesty_accuracy_claim_forbidden" in honesty["issues"]


@pytest.mark.asyncio
async def test_facade_suite():
    suite = await run_knowledge_gold_eval_suite()
    assert suite["ok"] is True
    gate = evaluate_knowledge_gold_eval_gate(suite)
    assert gate["ok"] is True
    assert gate["certified"] is False
    assert gate["accuracy_claim"] is False


def test_register_requires_cases(tmp_path):
    db = str(tmp_path / "gold.sqlite3")
    with pytest.raises(KnowledgeGoldEvalError, match="cases_required"):
        register_gold_dataset(
            tenant_id="t1",
            domain_id="suite-domain",
            version="v1",
            cases=[],
            db_path=db,
        )


def test_docs_and_wiring_state():
    mod = (
        ROOT
        / "aiPlat-core"
        / "core"
        / "harness"
        / "knowledge_pipeline"
        / "knowledge_gold_eval.py"
    )
    text = mod.read_text(encoding="utf-8")
    assert "run_knowledge_gold_eval_pipeline" in text
    assert "accuracy_claim" in text
    facade = ROOT / "aiPlat-core" / "core" / "api" / "core_facade.py"
    assert "run_knowledge_gold_eval_suite" in facade.read_text(encoding="utf-8")
    route = (
        ROOT
        / "aiPlat-platform"
        / "apps"
        / "fde"
        / "api"
        / "knowledge_gold_eval_routes.py"
    )
    assert "register_knowledge_gold_dataset" in route.read_text(encoding="utf-8")
    router = ROOT / "aiPlat-platform" / "apps" / "fde" / "api" / "router.py"
    assert "knowledge_gold_eval_routes" in router.read_text(encoding="utf-8")
