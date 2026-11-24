"""FDE N10 知识域 Gold 评测 — 薄路由，经 CoreFacade。"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Body, HTTPException, Query
from pydantic import BaseModel, Field

router = APIRouter(tags=["fde-knowledge-gold-eval"])


class GoldDatasetBody(BaseModel):
    """登记 gold 数据集。"""

    domain_id: str = Field(..., min_length=1)
    version: str = Field(..., min_length=1)
    cases: List[Dict[str, Any]] = Field(..., min_length=1)
    threshold: float = Field(0.8, ge=0.0, le=1.0)


class GoldPipelineBody(BaseModel):
    """跨域 gold 评测。"""

    domain_ids: Optional[List[str]] = None
    judge_mode: str = Field(
        "exact",
        description="exact（默认）或 llm（N10 residual；无准确率宣称）",
    )


class GoldGateBody(BaseModel):
    """门槛门探针。"""

    suite: Optional[Dict[str, Any]] = None


class LlmJudgeProductBody(BaseModel):
    """N10 产品面 LLM judge 请求体。"""

    expected: str = Field(..., min_length=1)
    actual: str = Field(..., min_length=1)
    subject: str = Field(default="")
    predicate: str = Field(default="")


@router.post("/knowledge-gold/datasets")
async def register_knowledge_gold_dataset_route(
    body: GoldDatasetBody = Body(...),
    tenant_id: str = Query(..., description="tenant id (required)"),
):
    """登记域级 gold 数据集。

    Args:
        body: 数据集载荷。
        tenant_id: 租户。
    """
    from core.api.core_facade import register_knowledge_gold_dataset

    try:
        return register_knowledge_gold_dataset(
            tenant_id=tenant_id,
            domain_id=body.domain_id,
            version=body.version,
            cases=body.cases,
            threshold=body.threshold,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/knowledge-gold/pipeline")
async def run_knowledge_gold_eval_pipeline_route(
    body: GoldPipelineBody = Body(default_factory=GoldPipelineBody),
    tenant_id: str = Query(..., description="tenant id (required)"),
):
    """跑跨域 gold 评测流水线。

    Args:
        body: 可选域列表。
        tenant_id: 租户。
    """
    from core.api.core_facade import run_knowledge_gold_eval_pipeline

    try:
        return await run_knowledge_gold_eval_pipeline(
            tenant_id=tenant_id,
            domain_ids=body.domain_ids,
            judge_mode=body.judge_mode,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/knowledge-gold/suite")
async def run_knowledge_gold_eval_suite_route():
    """运行 gold 评测套件。"""
    from core.api.core_facade import run_knowledge_gold_eval_suite

    return await run_knowledge_gold_eval_suite()


@router.post("/knowledge-gold/gate")
async def evaluate_knowledge_gold_eval_gate_route(
    body: GoldGateBody = Body(default_factory=GoldGateBody),
):
    """gold 评测门槛门。

    Args:
        body: 可选 suite 回执。
    """
    from core.api.core_facade import (
        evaluate_knowledge_gold_eval_gate,
        run_knowledge_gold_eval_suite,
    )

    suite = body.suite
    if suite is None:
        suite = await run_knowledge_gold_eval_suite()
    return evaluate_knowledge_gold_eval_gate(suite)


@router.post("/knowledge-gold/product/llm-judge")
async def knowledge_gold_llm_judge_product_route(
    body: LlmJudgeProductBody = Body(...),
) -> Dict[str, Any]:
    """N10 产品面：有界 LLM object 等价（默认可用；非准确率宣称）。

    Args:
        body: expected/actual 对。
    """
    from core.api.core_facade import llm_judge_object_equiv_product

    return await llm_judge_object_equiv_product(
        expected=body.expected,
        actual=body.actual,
        subject=body.subject,
        predicate=body.predicate,
    )


@router.post("/knowledge-gold/product/suite")
async def knowledge_gold_llm_judge_product_suite_route() -> Dict[str, Any]:
    """N10 产品面：LLM judge 套件。"""
    from core.api.core_facade import run_llm_judge_product_suite

    return await run_llm_judge_product_suite()


@router.post("/knowledge-gold/product/gate")
async def knowledge_gold_llm_judge_product_gate_route(
    body: GoldGateBody = Body(default_factory=GoldGateBody),
) -> Dict[str, Any]:
    """N10 产品面：LLM judge 门槛门。

    Args:
        body: 可选 suite 回执。
    """
    from core.api.core_facade import (
        evaluate_llm_judge_product_gate,
        run_llm_judge_product_suite,
    )

    suite = body.suite
    if suite is None:
        suite = await run_llm_judge_product_suite()
    return evaluate_llm_judge_product_gate(suite)
