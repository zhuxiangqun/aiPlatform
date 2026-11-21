"""sys_ontology_context — Agent ReActLoop 中可调用的知识网络上下文查询。

返回指定 URN 的知识网络上下文（上下游关系），Agent 可调用它以理解
"这个实体与系统中其他部分的关系"。

N19：可选 tenant_id 时 best-effort 落 Fact/Query 审计快照（certified 恒 false）。
SECURITY V2：显式 tenant_id 时 TripleStore 读路径按租户+共享过滤。
"""

from __future__ import annotations

import logging
from typing import Any, Dict


async def sys_ontology_context(
    urn: str,
    depth: int = 3,
    *,
    tenant_id: str = "",
) -> Dict[str, Any]:
    """返回 URN 的知识网络上下文。

    Args:
        urn: 实体 URN。
        depth: BFS 深度（硬上限 5）。
        tenant_id: 非空时：TripleStore 租户过滤 + N19 审计快照。
    """
    from core.harness.ontology_engine.triple_store import get_triple_store

    store = get_triple_store()
    max_depth = min(depth, 5)
    tid = (tenant_id or "").strip()

    # 为什么：显式 tenant 必须过滤，禁止跨租户 URN 图泄漏
    downstream = store.get_downstream(urn, max_depth, tenant_id=tid)
    upstream = store.get_upstream(urn, max_depth, tenant_id=tid)

    result: Dict[str, Any] = {
        "entity": urn,
        "downstream_count": len(downstream),
        "upstream_count": len(upstream),
        "downstream": downstream[:20],
        "upstream": upstream[:20],
        # 为什么：禁止 URN 本体上下文自签 certified；N19 deepen ≠ 全量认证
        "certified": False,
        "n19_full_conformance": False,
    }

    if tid:
        # 为什么：syscall 包导出的是 URN 版，须与 ontology_context 域版一并落盘
        try:
            from core.harness.knowledge_pipeline.fact_query_audit import (
                maybe_record_wiki_kb_hotpath,
            )

            result = maybe_record_wiki_kb_hotpath(
                tenant_id=tid,
                response=result,
                channel="ontology_urn",
                query=urn or "",
            )
        except Exception as e:
            logging.warning(
                "sys_ontology_context URN N19 audit skipped: %s", e, exc_info=True
            )

    return result
