"""Deepen governance loop steps ⑥ (quality/value) and ⑦ (locate via ontology).

Vertical slices only — not a full data-platform suite. No material KPIs.
"""

from __future__ import annotations

import logging
import re
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

_TOKEN = re.compile(r"[a-zA-Z0-9_\u4e00-\u9fff]{2,}")


def governance_quality_snapshot(domain_id: str = "data-gov") -> Dict[str, Any]:
    """Step ⑥: OCS + action surface + deep links (read-only)."""
    did = (domain_id or "data-gov").strip() or "data-gov"
    ocs: Dict[str, Any] = {}
    try:
        from core.harness.knowledge.ontology_completeness import compute_domain_ocs

        ocs = compute_domain_ocs(did, credit_test_evidence=True)
    except Exception as e:
        logger.warning("OCS compute failed for %s", did, exc_info=True)
        ocs = {"domain_id": did, "ocs": 0.0, "level": "error", "error": type(e).__name__}

    actions: List[Dict[str, str]] = []
    # Prefer seed YAML (stable; no registry mock)
    try:
        from pathlib import Path
        import yaml

        seed = (
            Path(__file__).resolve().parents[3]
            / "workspace_seeds"
            / "actions"
            / "data_gov_lifecycle.yaml"
        )
        if did == "data-gov" and seed.is_file():
            raw = yaml.safe_load(seed.read_text(encoding="utf-8")) or {}
            rows = (
                raw.get("actions")
                if isinstance(raw, dict)
                else (raw if isinstance(raw, list) else [])
            )
            for row in rows or []:
                if not isinstance(row, dict):
                    continue
                aid = str(row.get("action_id") or "")
                if aid:
                    actions.append(
                        {
                            "action_id": aid,
                            "label": str(row.get("label") or row.get("name") or aid),
                        }
                    )
    except Exception:
        logger.debug("seed action load skipped", exc_info=True)

    if not actions and did == "data-gov":
        actions = [
            {"action_id": "customer_action:data-gov:mount_catalog", "label": "挂载目录"},
            {"action_id": "customer_action:data-gov:discard_ghost", "label": "丢弃幽灵表"},
        ]

    return {
        "step": 6,
        "domain_id": did,
        "ocs": ocs.get("ocs"),
        "ocs_level": ocs.get("level"),
        "ocs_dimensions": ocs.get("dimensions") or {},
        "actions": actions[:12],
        "links": [
            {
                "label": "FDE⑦ 治理动作",
                "href": "/diagnostics/fde",
            },
            {
                "label": "业务价值看板",
                "href": "/diagnostics/business-value",
            },
            {
                "label": "工厂提案门",
                "href": f"/knowledge/business?tab=factory&domain={did}",
            },
        ],
        "authority_note": (
            "⑥=完整性 OCS + 闸2 动作入口 + 价值页链接；非一体化数据治理套件；"
            "禁止宣称材料分类准确率 KPI"
        ),
        "status": "vertical",
        "status_label": "已竖切",
    }


def locate_via_ontology(
    domain_id: str,
    query: str,
    *,
    top_k: int = 8,
) -> Dict[str, Any]:
    """Step ⑦: locate GraphIndex entities by query tokens (ontology-first locate).

    Does not execute SQL against customer DBs. Returns graph hits + optional paths.
    """
    did = (domain_id or "data-gov").strip() or "data-gov"
    q = (query or "").strip()
    if not q:
        return {
            "step": 7,
            "domain_id": did,
            "query": "",
            "hits": [],
            "status": "need_query",
            "authority_note": "请提供业务问句或实体关键词；本接口定位图上资产，非直连业务库取数",
        }

    tokens = set(t.lower() for t in _TOKEN.findall(q.lower()))
    hits: List[Dict[str, Any]] = []
    try:
        from core.harness.ontology_engine.graph_index import GraphIndex

        g = GraphIndex.load(did)
        nodes = list((getattr(g, "_nodes", None) or {}).values())
        scored: List[tuple] = []
        for node in nodes:
            name = str(getattr(node, "entity_name", "") or "")
            eid = str(getattr(node, "entity_id", "") or "")
            cls = str(getattr(node, "class_name", "") or "")
            meta = getattr(node, "metadata", {}) or {}
            state = ""
            if isinstance(meta, dict):
                state = str(meta.get("state") or meta.get("status") or "")
            blob = f"{name} {eid} {cls} {state}".lower()
            blob_tokens = set(_TOKEN.findall(blob))
            if tokens:
                overlap = len(tokens & blob_tokens) / max(len(tokens | blob_tokens), 1)
            else:
                overlap = 0.0
            # also substring boost
            sub = 0.35 if any(t in blob for t in tokens) else 0.0
            score = max(overlap, sub)
            if score >= 0.08 or any(t in blob for t in tokens):
                scored.append(
                    (
                        score,
                        {
                            "entity_id": eid,
                            "entity_name": name,
                            "class_name": cls,
                            "state": state,
                            "score": round(score, 4),
                            "out_degree": len(getattr(node, "out_edges", []) or []),
                            "in_degree": len(getattr(node, "in_edges", []) or []),
                        },
                    )
                )
        scored.sort(key=lambda x: (-x[0], x[1]["entity_id"]))
        hits = [h for _, h in scored[: max(1, min(int(top_k), 20))]]
    except Exception as e:
        logger.warning("locate_via_ontology failed domain=%s", did, exc_info=True)
        return {
            "step": 7,
            "domain_id": did,
            "query": q,
            "hits": [],
            "error": type(e).__name__,
            "status": "error",
            "authority_note": "图定位失败；可先 FDE⑦ 种治理教学图再查",
        }

    return {
        "step": 7,
        "domain_id": did,
        "query": q,
        "hits": hits,
        "count": len(hits),
        "mode": "graph_locate",
        "status": "ok" if hits else "empty",
        "links": [
            {"label": "FDE⑦ 种/选实体", "href": "/diagnostics/fde"},
            {"label": "知识库检索轨", "href": "/knowledge/library"},
        ],
        "authority_note": (
            "⑦=按本体图定位资产（GraphIndex）；非业务库直连取数；"
            "取数仍须后续 Action/连接器。禁止宣称企业全域查数已上线"
        ),
        "status_label": "已竖切",
    }


async def locate_via_ontology_async(
    domain_id: str,
    query: str,
    *,
    top_k: int = 8,
    with_graphrag: bool = False,
) -> Dict[str, Any]:
    """Locate + optional GraphRAG overlay (best-effort)."""
    base = locate_via_ontology(domain_id, query, top_k=top_k)
    if not with_graphrag or not base.get("hits"):
        return base
    try:
        from core.harness.knowledge_pipeline.retriever import GraphRAGRetriever

        rag = GraphRAGRetriever()
        ctx = await rag.retrieve(query, domain_id=domain_id, top_k=min(5, top_k))
        base["graphrag"] = {
            "mode": ctx.get("mode"),
            "subgraph_size": ctx.get("subgraph_size"),
            "paths": (ctx.get("reasoning_paths") or [])[:5],
            "chunk_count": len(ctx.get("chunks") or []),
        }
        base["mode"] = "graph_locate+graphrag"
    except Exception:
        logger.debug("graphrag overlay skipped", exc_info=True)
        base["graphrag"] = {"skipped": True}
    return base
