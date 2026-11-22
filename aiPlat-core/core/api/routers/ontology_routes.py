"""统一知识本体查询 API — 跨域 SPO 三元组查询。

提供对 TripleStore 的 REST 访问:
  - POST /query  — 跨域本体查询（支持 upstream/downstream）
  - GET  /impact/{path_urn} — 一次性上下游影响分析
  - GET  /stats — 三元组统计

N19：可选 tenant_id 时 best-effort 落 Fact/Query 审计（certified 恒 false）。
SECURITY V2：显式 tenant_id 时 TripleStore 读路径按租户+共享过滤。
"""

from __future__ import annotations

import logging
from typing import Any, Dict

from fastapi import APIRouter, HTTPException, Query, Body

from core.api.core_facade import get_triple_store  # P0-A2: 经 CoreFacade

router = APIRouter(tags=["ontology"])

MAX_DEPTH = 5  # 硬上限，防止 BFS 遍历爆炸


def _n19_audit(result: Dict[str, Any], *, tenant_id: str, channel: str, query: str) -> Dict[str, Any]:
    """有 tenant 时落 N19 Query 快照；失败不阻断。

    Args:
        result: 查询回执。
        tenant_id: 租户。
        channel: 审计 channel。
        query: 查询摘要（URN）。
    """
    out = dict(result)
    # 为什么：禁止 HTTP 本体查询自签 certified
    out["certified"] = False
    out["n19_full_conformance"] = False
    tid = (tenant_id or "").strip()
    if not tid:
        return out
    try:
        from core.harness.knowledge_pipeline.fact_query_audit import (
            maybe_record_wiki_kb_hotpath,
        )

        return maybe_record_wiki_kb_hotpath(
            tenant_id=tid,
            response=out,
            channel=channel,
            query=query or "",
        )
    except Exception as e:
        logging.warning(
            "ontology_routes N19 audit skipped: %s", e, exc_info=True
        )
        return out


@router.get("/healthz")
async def ontology_healthz() -> Dict[str, Any]:
    """Ontology capability healthz (D1 co-hosted; product_id=ontology)."""
    from core.api.core_facade import ontology_healthz_payload

    return ontology_healthz_payload()


@router.post("/query")
async def ontology_query(body: dict = Body(...)) -> Dict[str, Any]:
    """跨域本体查询。

    Args:
        body: 请求体 dict（可含 tenant_id）。
    """
    urn = body.get("urn", "")
    if not urn:
        raise HTTPException(status_code=400, detail="urn is required")

    store = get_triple_store()
    depth = min(body.get("depth", 3), MAX_DEPTH)
    direction = body.get("direction", "downstream")
    tid = str(body.get("tenant_id") or "").strip()

    # 为什么：HTTP 显式 tenant 须过滤，禁止跨租户图泄漏
    if direction == "upstream":
        results = store.get_upstream(urn, depth, tenant_id=tid)
    else:
        results = store.get_downstream(urn, depth, tenant_id=tid)

    return _n19_audit(
        {
            "urn": urn,
            "direction": direction,
            "depth": depth,
            "count": len(results),
            "results": results,
            "tenant_scoped": bool(tid),
        },
        tenant_id=tid,
        channel="ontology_urn_http",
        query=urn,
    )


@router.get("/impact/{path_urn:path}")
async def ontology_impact(
    path_urn: str,
    depth: int = Query(3, le=MAX_DEPTH),
    tenant_id: str = Query(""),
) -> Dict[str, Any]:
    """一次性返回上游（谁依赖我）+ 下游（我依赖谁）。

    Args:
        path_urn: path_urn 参数。
        depth: depth 参数。
        tenant_id: 可选租户（N19 审计 + TripleStore 过滤）。
    """
    urn = f"urn:aiplat:{path_urn}"
    store = get_triple_store()
    tid = (tenant_id or "").strip()
    downstream = store.get_downstream(urn, depth, tenant_id=tid)
    upstream = store.get_upstream(urn, depth, tenant_id=tid)
    return _n19_audit(
        {
            "urn": urn,
            "depth": depth,
            "downstream_count": len(downstream),
            "upstream_count": len(upstream),
            "downstream": downstream,
            "upstream": upstream,
            "tenant_scoped": bool(tid),
        },
        tenant_id=tid,
        channel="ontology_urn_http",
        query=urn,
    )


@router.get("/stats")
async def ontology_stats(tenant_id: str = Query("")) -> Dict[str, Any]:
    """TripleStore 统计 — 三元组总数 + 按谓词分布。

    Args:
        tenant_id: 非空时按租户+共享过滤。
    """
    return get_triple_store().stats(tenant_id=(tenant_id or "").strip())
