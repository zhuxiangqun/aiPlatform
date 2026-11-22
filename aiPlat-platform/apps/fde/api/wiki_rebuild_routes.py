"""FDE N05 Wiki 有条件重建 — 薄路由，经 CoreFacade。"""
from __future__ import annotations

from typing import Any, Dict, Optional

from fastapi import APIRouter, Body, HTTPException, Query
from pydantic import BaseModel, Field

router = APIRouter(tags=["fde-wiki-rebuild"])


class WikiRebuildBody(BaseModel):
    """触发 Wiki 派生重建。"""

    rebuild_mode: str = Field("", description="exact|semantic|non；空则 exact")
    rebuild_reason: str = Field("", description="分类理由")
    clear_projected: bool = Field(True, description="先清该租户/域派生页")
    exact_capable: bool = Field(True, description="是否可精确重放")


class WikiRebuildGateBody(BaseModel):
    """门槛门探针。"""

    suite: Optional[Dict[str, Any]] = None


@router.post("/wiki-rebuild")
async def project_facts_to_wiki_route(
    body: WikiRebuildBody = Body(default_factory=WikiRebuildBody),
    tenant_id: str = Query(..., description="tenant id (required)"),
    domain_id: str = Query(..., description="domain id (required)"),
):
    """Fact → Wiki 派生页重建。

    Args:
        body: 重建参数。
        tenant_id: 租户。
        domain_id: 域。
    """
    from core.api.core_facade import fact_ledger_project_to_wiki

    try:
        return await fact_ledger_project_to_wiki(
            tenant_id=tenant_id,
            domain_id=domain_id,
            clear_projected=body.clear_projected,
            rebuild_mode=body.rebuild_mode,
            rebuild_reason=body.rebuild_reason,
            exact_capable=body.exact_capable,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/wiki-rebuild/pages")
async def list_wiki_rebuild_pages_route(
    tenant_id: str = Query(..., description="tenant id (required)"),
    domain_id: Optional[str] = Query(None),
    limit: int = Query(200, ge=1, le=1000),
):
    """列出 Wiki 重建派生页。

    Args:
        tenant_id: 租户。
        domain_id: 可选域。
        limit: 最大条数。
    """
    from core.api.core_facade import list_wiki_rebuild_pages

    return {
        "pages": list_wiki_rebuild_pages(
            tenant_id=tenant_id,
            domain_id=domain_id or "",
            limit=limit,
        )
    }


@router.post("/wiki-rebuild/suite")
async def run_wiki_rebuild_suite_route():
    """运行 Wiki 重建套件。"""
    from core.api.core_facade import run_wiki_rebuild_suite

    return await run_wiki_rebuild_suite()


@router.post("/wiki-rebuild/gate")
async def evaluate_wiki_rebuild_gate_route(
    body: WikiRebuildGateBody = Body(default_factory=WikiRebuildGateBody),
):
    """Wiki 重建门槛门。

    Args:
        body: 可选 suite 回执。
    """
    from core.api.core_facade import (
        evaluate_wiki_rebuild_gate,
        run_wiki_rebuild_suite,
    )

    suite = body.suite
    if suite is None:
        suite = await run_wiki_rebuild_suite()
    return evaluate_wiki_rebuild_gate(suite)
