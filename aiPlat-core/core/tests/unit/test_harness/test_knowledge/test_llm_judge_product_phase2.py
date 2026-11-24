"""N10 LLM judge 产品面：默认可用；accuracy / certified 恒 false。"""
from __future__ import annotations

import os
from pathlib import Path

import pytest

from core.api.core_facade import (
    evaluate_llm_judge_product_gate,
    llm_judge_object_equiv,
    llm_judge_object_equiv_product,
    run_llm_judge_product_suite,
)
from core.harness.knowledge_pipeline.knowledge_gold_eval import (
    evaluate_llm_judge_product_gate as _gate,
    llm_judge_object_equiv_product as _product_core,
    run_llm_judge_product_suite as _suite,
)

ROOT = Path(__file__).resolve().parents[6]


@pytest.mark.asyncio
async def test_product_suite_and_gate_honesty():
    suite = await _suite()
    assert suite["ok"] is True
    assert suite["passed"] == 3
    assert suite["certified"] is False
    assert suite["accuracy_claim"] is False
    assert suite["llm_judge_product_surface"] is True
    ids = {c["id"] for c in suite["cases"] if c.get("ok")}
    assert "llm_judge_product_eval" in ids
    assert "llm_judge_product_unavailable" in ids
    assert "honesty_product_certified_false" in ids
    gate = _gate(suite)
    assert gate["ok"] is True
    bad = dict(suite)
    bad["certified"] = True
    honesty = _gate(bad)
    assert honesty["ok"] is False
    assert "honesty_certified_flag_forbidden" in honesty["issues"]
    bad2 = dict(suite)
    bad2["accuracy_claim"] = True
    honesty2 = _gate(bad2)
    assert honesty2["ok"] is False
    assert "honesty_accuracy_claim_forbidden" in honesty2["issues"]


@pytest.mark.asyncio
async def test_facade_product_suite():
    suite = await run_llm_judge_product_suite()
    assert suite["ok"] is True
    gate = evaluate_llm_judge_product_gate(suite)
    assert gate["ok"] is True
    assert gate["llm_judge_product_surface"] is True
    assert gate["accuracy_claim"] is False


@pytest.mark.asyncio
async def test_product_without_residual_env():
    os.environ.pop("AIPLAT_KNOWLEDGE_GOLD_LLM_JUDGE", None)
    residual = await llm_judge_object_equiv(expected="opened", actual="open")
    assert residual["status"] == "llm_judge_unavailable"
    assert residual.get("via") == "env_disabled"
    assert residual.get("llm_judge_product_surface") is False

    # Facade 产品面：exact 路径无 residual env 即可
    exact = await llm_judge_object_equiv_product(expected="open", actual="open")
    assert exact["status"] == "ok"
    assert exact.get("via") == "exact"
    assert exact["llm_judge_product_surface"] is True
    assert exact["accuracy_claim"] is False
    assert exact["certified"] is False

    # 注入路径仅 core 暴露 judge_fn（Facade 不透传）
    def _ok(*, expected: str, actual: str, **_kw):
        return {
            "status": "ok",
            "matched": {str(expected), str(actual)} <= {"open", "opened"},
        }

    product = await _product_core(
        expected="opened",
        actual="open",
        judge_fn=_ok,
    )
    assert product["status"] == "ok"
    assert product["matched"] is True
    assert product["llm_judge_product_surface"] is True
    assert product["accuracy_claim"] is False
    assert product["certified"] is False


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
    assert "llm_judge_object_equiv_product" in text
    assert "run_llm_judge_product_suite" in text
    facade = ROOT / "aiPlat-core" / "core" / "api" / "core_facade.py"
    assert "llm_judge_object_equiv_product" in facade.read_text(encoding="utf-8")
    routes = (
        ROOT
        / "aiPlat-platform"
        / "apps"
        / "fde"
        / "api"
        / "knowledge_gold_eval_routes.py"
    )
    assert "knowledge-gold/product/llm-judge" in routes.read_text(encoding="utf-8")
    panel = (
        ROOT
        / "aiPlat-management"
        / "frontend"
        / "src"
        / "pages"
        / "KnowledgeFactory"
        / "LlmJudgePanel.tsx"
    )
    assert "knowledge-gold/product/llm-judge" in panel.read_text(encoding="utf-8")
