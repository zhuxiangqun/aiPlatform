"""统一知识本体查询 API — 跨域 SPO 三元组查询。

提供对 TripleStore 的 REST 访问:
  - POST /query  — 跨域本体查询（支持 upstream/downstream）
  - GET  /impact/{path_urn} — 一次性上下游影响分析
  - GET  /stats — 三元组统计
"""

from typing import Any, Dict

from fastapi import APIRouter, HTTPException, Query, Body

from core.api.core_facade import get_triple_store  # P0-A2: 经 CoreFacade

router = APIRouter(tags=["ontology"])

MAX_DEPTH = 5  # 硬上限，防止 BFS 遍历爆炸


@router.post("/query")
async def ontology_query(body: dict = Body(...)) -> Dict[str, Any]:
    """跨域本体查询。

    Body: {
        "urn": "urn:aiplat:agent:pm_agent",
        "direction": "downstream|upstream",
        "depth": 3
    }
    """
    urn = body.get("urn", "")
    if not urn:
        raise HTTPException(status_code=400, detail="urn is required")

    store = get_triple_store()
    depth = min(body.get("depth", 3), MAX_DEPTH)
    direction = body.get("direction", "downstream")

    if direction == "upstream":
        results = store.get_upstream(urn, depth)
    else:
        results = store.get_downstream(urn, depth)

    return {
        "urn": urn,
        "direction": direction,
        "depth": depth,
        "count": len(results),
        "results": results,
    }


@router.get("/impact/{path_urn:path}")
async def ontology_impact(
    path_urn: str,
    depth: int = Query(3, le=MAX_DEPTH),
) -> Dict[str, Any]:
    """一次性返回上游（谁依赖我）+ 下游（我依赖谁）。

    示例: GET /api/core/ontology/impact/agent:pm_agent?depth=3
    """
    urn = f"urn:aiplat:{path_urn}"
    store = get_triple_store()
    downstream = store.get_downstream(urn, depth)
    upstream = store.get_upstream(urn, depth)
    return {
        "urn": urn,
        "depth": depth,
        "downstream_count": len(downstream),
        "upstream_count": len(upstream),
        "downstream": downstream,
        "upstream": upstream,
    }


@router.get("/stats")
async def ontology_stats() -> Dict[str, Any]:
    """TripleStore 统计 — 三元组总数 + 按谓词分布。"""
    return get_triple_store().stats()
