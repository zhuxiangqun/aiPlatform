"""sys_ontology_context — Agent ReActLoop 中可调用的知识网络上下文查询。

返回指定 URN 的知识网络上下文（上下游关系），Agent 可调用它以理解
"这个实体与系统中其他部分的关系"。

# SECURITY: V2 需要增加 tenant/scope 隔离
"""

from typing import Any, Dict


async def sys_ontology_context(urn: str, depth: int = 3) -> Dict[str, Any]:
    """返回 URN 的知识网络上下文。

    Agent 在 ReActLoop 中调用:
        ctx = await sys_ontology_context("urn:aiplat:skill:code_generation")
        # → {"entity": "...", "downstream": [...], "upstream": [...]}
    """
    from core.harness.ontology_engine.triple_store import get_triple_store

    store = get_triple_store()
    max_depth = min(depth, 5)

    downstream = store.get_downstream(urn, max_depth)
    upstream = store.get_upstream(urn, max_depth)

    return {
        "entity": urn,
        "downstream_count": len(downstream),
        "upstream_count": len(upstream),
        "downstream": downstream[:20],
        "upstream": upstream[:20],
    }
