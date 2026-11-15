"""v4.3.1 Phase 2：Fact → GraphIndex 投影（可重建读模型）。

职责：
  - 从 FactLedger 按租户/域读取 Fact
  - 按 ObjectType 绑定形状投影为 GraphIndex 实体属性
  - 标记 ``rebuild_mode=exact_replay_from_facts``（证据可重建）

非目标：
  - Wiki 只读化 / ObjectSet SDK / 字段级 ACL（后续 Phase）
  - 替代抽取直写 Graph 路径（本投影是事实层派生视图）
"""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Dict, List, Optional

from core.harness.knowledge_pipeline.fact_ledger import (
    FactLedger,
    FactLedgerError,
    get_fact_ledger,
    load_object_type_bindings,
)

logger = logging.getLogger(__name__)

_PROJECTION_SOURCE = "fact_ledger"
_REBUILD_MODE = "exact_replay_from_facts"


def _parse_subject(subject: str) -> tuple[str, str]:
    """解析 ``Type:id`` 主体；无冒号时类型为 Entity。

    Args:
        subject: Fact subject。

    Returns:
        ``(object_type_or_class, entity_id)``。
    """
    s = (subject or "").strip()
    if ":" in s:
        left, right = s.split(":", 1)
        return left.strip() or "Entity", right.strip() or s
    return "Entity", s or "unknown"


async def project_facts_to_graph(
    *,
    tenant_id: str,
    domain_id: str,
    ledger: Optional[FactLedger] = None,
    bindings_path: Optional[Path] = None,
    clear_projected: bool = False,
) -> Dict[str, Any]:
    """将域内 Fact 投影到 GraphIndex（租户隔离；可重建）。

    Args:
        tenant_id: 租户（召回前过滤）。
        domain_id: 业务域。
        ledger: 可选账本实例；默认进程单例。
        bindings_path: ObjectType 种子路径；缺省尝试
            ``aiPlat-core/workspace_seeds/ontologies/{domain_id}-object-types.json``。
        clear_projected: 为 True 时先移除此前投影标记的实体再写入。

    Returns:
        投影回执（含 ``rebuild_mode`` / 实体数）。

    Raises:
        FactLedgerError: tenant_id / domain_id 为空。
    """
    if not (tenant_id or "").strip():
        raise FactLedgerError("tenant_id required")
    if not (domain_id or "").strip():
        raise FactLedgerError("domain_id required")

    store = ledger or get_fact_ledger()
    await store.initialize()
    facts = await store.query_facts(
        tenant_id=tenant_id,
        domain_id=domain_id,
        limit=5000,
    )

    bindings: List[Dict[str, Any]] = []
    seed = bindings_path
    if seed is None:
        candidate = Path(
            f"aiPlat-core/workspace_seeds/ontologies/{domain_id}-object-types.json"
        )
        if candidate.is_file():
            seed = candidate
    if seed is not None and Path(seed).is_file():
        bindings = load_object_type_bindings(Path(seed))
    type_ids = {str(b.get("object_type_id") or "") for b in bindings if b.get("object_type_id")}

    from core.harness.ontology_engine.graph_index import GraphIndex

    GraphIndex._loaded_instances.clear()
    graph = GraphIndex.load(domain_id, tenant_id=tenant_id)

    removed = 0
    if clear_projected:
        # 仅清本投影源实体，避免误删抽取直写节点
        to_drop = []
        for eid, node in list(getattr(graph, "_nodes", {}).items()):
            meta = getattr(node, "metadata", None) or {}
            if isinstance(meta, dict) and meta.get("projection_source") == _PROJECTION_SOURCE:
                to_drop.append(eid)
        for eid in to_drop:
            if graph.remove_entity(eid):
                removed += 1

    # subject → {predicate: object}
    by_subject: Dict[str, Dict[str, Any]] = {}
    for f in facts:
        subj = str(f.get("subject") or "")
        pred = str(f.get("predicate") or "")
        if not subj or not pred:
            continue
        bucket = by_subject.setdefault(subj, {})
        bucket[pred] = f.get("object")
        bucket["_fact_ids"] = list(bucket.get("_fact_ids") or []) + [f.get("fact_id")]

    created: List[str] = []
    updated: List[str] = []
    skipped: List[str] = []

    for subject, props in by_subject.items():
        cls, eid = _parse_subject(subject)
        if type_ids and cls not in type_ids and cls != "Extraction":
            # 有绑定时：仅投影声明的 ObjectType + Extraction 确认事实
            skipped.append(subject)
            continue
        name = str(props.get("name") or eid)
        fact_ids = props.pop("_fact_ids", [])
        if eid not in getattr(graph, "_nodes", {}):
            graph.add_entity(eid, name, cls, source_doc_id=f"fact:{tenant_id}")
            created.append(eid)
        else:
            updated.append(eid)
        graph.add_entity_property(eid, "projection_source", _PROJECTION_SOURCE)
        graph.add_entity_property(eid, "rebuild_mode", _REBUILD_MODE)
        graph.add_entity_property(eid, "tenant_id", tenant_id)
        if fact_ids:
            graph.add_entity_property(eid, "fact_ids", ",".join(str(x) for x in fact_ids[:20]))
        for pk, pv in props.items():
            if pk.startswith("_"):
                continue
            graph.add_entity_property(eid, str(pk), str(pv)[:500])

    receipt = {
        "status": "ok",
        "rebuild_mode": _REBUILD_MODE,
        "tenant_id": tenant_id,
        "domain_id": domain_id,
        "facts_read": len(facts),
        "subjects": len(by_subject),
        "created": created,
        "updated": updated,
        "skipped": skipped,
        "removed_before": removed,
        "object_type_bindings": len(bindings),
    }
    logger.info(
        "fact_projector: domain=%s tenant=%s created=%s updated=%s",
        domain_id,
        tenant_id,
        len(created),
        len(updated),
    )
    return receipt
