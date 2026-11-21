"""
Graph neighbor / query syscalls — thin wrappers over GraphIndex (v3.1).

Prevents agents from directly importing GraphIndex by providing
shared syscalls for entity neighbor traversal, graph stats/classes,
and recommendations.

N19：显式 ``tenant_id`` 非空时 best-effort 落 Fact/Query 审计快照（certified 恒 false）。
"""
from __future__ import annotations

import logging
from typing import Any, Dict

from ._trace import trace_syscall_entry

from core.harness.knowledge.domain_router import DomainRouter
_log = logging.getLogger(__name__)


# ladder-ok: fill already-exported sys_graph_query slot MaterialsChat calls; extends graph.py neighbors surface, not a new capability family
async def sys_graph_query(
    query: str = "",
    *,
    operation: str = "stats",
    domain_id: str = DomainRouter.PLATFORM_DEFAULT_GRAPH_DOMAIN,
    tenant_id: str = "",
) -> Dict[str, Any]:
    """只读图查询（stats / classes）；供 MaterialsChat 注入图谱摘要。

    Args:
        query: 保留参数（当前未用于过滤）。
        operation: ``stats`` 或 ``classes``。
        domain_id: 域标识。
        tenant_id: 显式租户；非空落 N19；空则仅解析上下文加载图（不审计）。
    """
    trace_syscall_entry("sys_graph_query")
    op = (operation or "stats").strip() or "stats"
    out: Dict[str, Any] = {
        "success": False,
        "operation": op,
        "domain_id": domain_id,
        "query": query or "",
        "data": {},
        "result": "",
        # 为什么：禁止图查询自签 certified；N19 deepen ≠ 全量认证
        "certified": False,
        "n19_full_conformance": False,
    }
    audit_tid = (tenant_id or "").strip()

    try:
        from core.harness.ontology_engine.graph_index import GraphIndex
        from core.harness.knowledge.context_bus import _resolve_graph_tenant

        tid = audit_tid or _resolve_graph_tenant()
        # 为什么：N09 K24 — 图查询须按租户图
        graph = GraphIndex.load(domain_id, tenant_id=tid)
        if op == "stats":
            st = graph.stats() if hasattr(graph, "stats") else {}
            nodes = int(st.get("node_count") or 0)
            edges = int(st.get("edge_count") or 0)
            out["data"] = {
                "nodes": nodes,
                "edges": edges,
                "avg_degree": st.get("avg_degree", 0),
                "domain_id": st.get("domain_id") or domain_id,
            }
            out["result"] = f"nodes={nodes} edges={edges}"
            out["success"] = True
        elif op == "classes":
            classes = list(graph.get_entity_classes() or [])[:30]
            out["data"] = {"classes": classes, "count": len(classes)}
            out["result"] = (
                f"classes({len(classes)}): " + ", ".join(classes[:15])
                if classes
                else "classes(0)"
            )
            out["success"] = True
        else:
            out["result"] = f"unsupported_operation:{op}"
    except Exception:
        _log.debug(
            "sys_graph_query failed op=%s domain=%s", op, domain_id, exc_info=True
        )

    if audit_tid:
        # 为什么：MaterialsChat 图摘要旁路曾因函数缺失静默跳过；须可审计
        try:
            from core.harness.knowledge_pipeline.fact_query_audit import (
                maybe_record_wiki_kb_hotpath,
            )

            out = maybe_record_wiki_kb_hotpath(
                tenant_id=audit_tid,
                response=out,
                channel="graph_query",
                query=f"{op}:{query or domain_id}",
            )
        except Exception as e:
            _log.warning(
                "sys_graph_query N19 audit skipped: %s", e, exc_info=True
            )

    return out


async def sys_graph_neighbors(
    entity_name: str,
    domain_id: str = DomainRouter.PLATFORM_DEFAULT_GRAPH_DOMAIN,
    max_hops: int = 1,
    include_edges: bool = False,
    *,
    tenant_id: str = "",
) -> Dict[str, Any]:
    """Look up an entity in the graph and return its neighbors.

    Args:
        entity_name: entity_name 参数。
        domain_id: domain 标识。
        max_hops: max_hops 参数。
        include_edges: include_edges 参数。
        tenant_id: 显式租户；非空落 N19；空则仅解析 ActiveRequestContext 加载图（不审计）。
    """
    trace_syscall_entry("sys_graph_neighbors")
    result: Dict[str, Any] = {
        "entity": entity_name,
        "neighbors": [],
        "edges": [],
        # 为什么：禁止图邻居查询自签 certified；N19 deepen ≠ 全量认证
        "certified": False,
        "n19_full_conformance": False,
    }
    audit_tid = (tenant_id or "").strip()

    try:
        from core.harness.ontology_engine.graph_index import GraphIndex
        from core.harness.knowledge.context_bus import _resolve_graph_tenant
        tid = audit_tid or _resolve_graph_tenant()
        # 为什么：N09 K24 — 邻居查询须按租户图
        graph = GraphIndex.load(domain_id, tenant_id=tid)
        node = graph.get_node(entity_name) or graph.find_by_name(entity_name)
        if node:
            neighbors: set = set()
            for edge in (node.out_edges or []):
                n = graph.get_node(edge.target_id)
                if n:
                    neighbors.add(n.entity_name)
                if include_edges:
                    result["edges"].append({
                        "source": entity_name,
                        "target": n.entity_name if n else edge.target_id,
                        "relation": getattr(edge, "relation_label", "related_to"),
                    })

            for edge in (node.in_edges or []):
                n = graph.get_node(edge.source_id)
                if n:
                    neighbors.add(n.entity_name)
                if include_edges:
                    result["edges"].append({
                        "source": n.entity_name if n else edge.source_id,
                        "target": entity_name,
                        "relation": getattr(edge, "relation_label", "related_to"),
                    })

            result["neighbors"] = list(neighbors)[:max_hops * 10]
    except Exception:
        _log.debug("sys_graph_neighbors failed for %s in %s", entity_name, domain_id, exc_info=True)

    if audit_tid:
        # 为什么：MaterialsChat / Agent 图邻居旁路须 best-effort 落 Query 快照
        try:
            from core.harness.knowledge_pipeline.fact_query_audit import (
                maybe_record_wiki_kb_hotpath,
            )

            result = maybe_record_wiki_kb_hotpath(
                tenant_id=audit_tid,
                response=result,
                channel="graph_neighbors",
                query=entity_name or "",
            )
        except Exception as e:
            _log.warning(
                "sys_graph_neighbors N19 audit skipped: %s", e, exc_info=True
            )

    return result
