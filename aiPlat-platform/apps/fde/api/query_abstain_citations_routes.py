"""FDE N21 查询 abstain+citations — 薄路由，经 CoreFacade。"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Body, HTTPException
from pydantic import BaseModel, Field

router = APIRouter(tags=["fde-query-abstain-citations"])


class ValidateBody(BaseModel):
    """校验查询响应。"""

    response: Dict[str, Any] = Field(default_factory=dict)
    require_citations_on_hit: bool = True


class EnforceBody(BaseModel):
    """归一化查询响应。"""

    response: Dict[str, Any] = Field(default_factory=dict)
    require_citations_on_hit: bool = True


class GateBody(BaseModel):
    """门槛门探针。"""

    suite: Optional[Dict[str, Any]] = None


class WikiQueryBody(BaseModel):
    """Wiki 查询形 + abstain。"""

    query: str = ""
    tenant_id: str = ""
    collection_ids: Optional[List[str]] = None
    top_k: int = 8
    require_citations_on_hit: bool = True


class KbQueryBody(BaseModel):
    """KB 查询形 + abstain。"""

    query: str = ""
    tenant_id: str = ""
    doc_ids: Optional[List[str]] = None
    collection_id: str = ""
    top_k: int = 8
    require_citations_on_hit: bool = True


class MaterialsBody(BaseModel):
    """MaterialsChat RAG 出口 enforce。"""

    output: Dict[str, Any] = Field(default_factory=dict)
    require_citations_on_hit: bool = True


class GraphragBody(BaseModel):
    """GraphRAG 信封。"""

    result: Dict[str, Any] = Field(default_factory=dict)
    query: str = ""
    require_citations_on_hit: bool = True


@router.post("/query-abstain-citations/validate")
async def validate_query_abstain_citations_route(
    body: ValidateBody = Body(...),
):
    """校验 abstain+citations 防假绿规则。

    Args:
        body: 响应载荷。
    """
    from core.api.core_facade import validate_query_abstain_citations

    try:
        return validate_query_abstain_citations(
            response=body.response,
            require_citations_on_hit=body.require_citations_on_hit,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/query-abstain-citations/enforce")
async def enforce_query_abstain_citations_route(
    body: EnforceBody = Body(...),
):
    """归一化查询响应。

    Args:
        body: 响应载荷。
    """
    from core.api.core_facade import enforce_query_abstain_citations

    try:
        return enforce_query_abstain_citations(
            response=body.response,
            require_citations_on_hit=body.require_citations_on_hit,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/query-abstain-citations/suite")
async def run_query_abstain_citations_suite_route():
    """运行 abstain+citations 套件。"""
    from core.api.core_facade import run_query_abstain_citations_suite

    return await run_query_abstain_citations_suite()


@router.post("/query-abstain-citations/wiki")
async def query_wiki_with_abstain_route(body: WikiQueryBody = Body(...)):
    """Wiki 查询形入口 + abstain 强制。

    Args:
        body: Wiki 查询载荷。
    """
    from core.api.core_facade import query_wiki_with_abstain

    try:
        return query_wiki_with_abstain(
            body.query,
            tenant_id=body.tenant_id,
            collection_ids=body.collection_ids,
            top_k=body.top_k,
            require_citations_on_hit=body.require_citations_on_hit,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/query-abstain-citations/kb")
async def query_kb_with_abstain_route(body: KbQueryBody = Body(...)):
    """KB 查询形入口 + abstain 强制。

    Args:
        body: KB 查询载荷。
    """
    from core.api.core_facade import query_kb_with_abstain

    try:
        return query_kb_with_abstain(
            body.query,
            tenant_id=body.tenant_id,
            doc_ids=body.doc_ids,
            collection_id=body.collection_id,
            top_k=body.top_k,
            require_citations_on_hit=body.require_citations_on_hit,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/query-abstain-citations/materials")
async def enforce_materials_chat_output_route(body: MaterialsBody = Body(...)):
    """MaterialsChat RAG 出口 abstain 强制。

    Args:
        body: Agent 输出载荷。
    """
    from core.api.core_facade import enforce_materials_chat_output

    try:
        return enforce_materials_chat_output(
            output=body.output,
            require_citations_on_hit=body.require_citations_on_hit,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/query-abstain-citations/materials-shortcut")
async def enforce_materials_chat_shortcut_output_route(
    body: MaterialsBody = Body(...),
):
    """MaterialsChat 非 RAG 捷径出口强制（time/math/greeting）。

    Args:
        body: trivial_bypass 输出载荷。
    """
    from core.api.core_facade import enforce_materials_chat_shortcut_output

    try:
        return enforce_materials_chat_shortcut_output(output=body.output)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/query-abstain-citations/materials-cache-hit")
async def enforce_materials_chat_cache_hit_output_route(
    body: MaterialsBody = Body(...),
):
    """MaterialsChat 语义缓存命中出口强制。

    Args:
        body: cache_hit 输出载荷。
    """
    from core.api.core_facade import enforce_materials_chat_cache_hit_output

    try:
        return enforce_materials_chat_cache_hit_output(
            output=body.output,
            require_citations_on_hit=body.require_citations_on_hit,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/query-abstain-citations/graphrag")
async def attach_graphrag_n21_envelope_route(body: GraphragBody = Body(...)):
    """GraphRAG 结果附加 n21_query 信封。

    Args:
        body: GraphRAG 回执载荷。
    """
    from core.api.core_facade import attach_graphrag_n21_envelope

    try:
        return attach_graphrag_n21_envelope(
            result=body.result,
            query=body.query,
            require_citations_on_hit=body.require_citations_on_hit,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/query-abstain-citations/gate")
async def evaluate_query_abstain_citations_gate_route(
    body: GateBody = Body(default_factory=GateBody),
):
    """abstain+citations 门槛门。

    Args:
        body: 可选 suite 回执。
    """
    from core.api.core_facade import (
        evaluate_query_abstain_citations_gate,
        run_query_abstain_citations_suite,
    )

    suite = body.suite
    if suite is None:
        suite = await run_query_abstain_citations_suite()
    return evaluate_query_abstain_citations_gate(suite)
