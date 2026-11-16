"""v4.3.1 Phase 2：Fact → GraphIndex 投影（可重建读模型 + 重建分类契约）。

职责：
  - 从 FactLedger 按租户/域读取 Fact
  - 按 ObjectType 绑定形状投影为 GraphIndex 实体属性
  - 写入 ``rebuild_mode`` / ``rebuild_reason``（三分类契约）

非目标：
  - Wiki 只读化全量；Wiki/KB 全入口重建分类
  - 替代抽取直写 Graph 路径（本投影是事实层派生视图）
  - 宣称 N05 全量认证
"""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from core.harness.knowledge_pipeline.fact_ledger import (
    FactLedger,
    FactLedgerError,
    get_fact_ledger,
    load_object_type_bindings,
)

logger = logging.getLogger(__name__)

_PROJECTION_SOURCE = "fact_ledger"

REBUILD_MODE_EXACT = "exact_replay_from_facts"
REBUILD_MODE_SEMANTIC = "semantic_rebuild"
REBUILD_MODE_NON = "non_rebuildable"
REBUILD_MODES = frozenset(
    {REBUILD_MODE_EXACT, REBUILD_MODE_SEMANTIC, REBUILD_MODE_NON}
)


class RebuildTaxonomyError(ValueError):
    """重建分类契约违反（缺 mode / 不可重建标成 exact 等）。"""


def classify_rebuild(
    *,
    rebuild_mode: Optional[str] = None,
    rebuild_reason: str = "",
    facts_read: int = 0,
    exact_capable: bool = True,
) -> Tuple[str, str]:
    """解析投影/重建分类。

    Args:
        rebuild_mode: 显式 mode；空则按能力推断。
        rebuild_reason: 分类理由；空则填默认。
        facts_read: 已读事实数（证据辅助）。
        exact_capable: 是否可从 Fact 精确重放（本投影路径默认 True）。

    Returns:
        ``(rebuild_mode, rebuild_reason)``。

    Raises:
        RebuildTaxonomyError: mode 非法，或把 non_rebuildable 标成 exact。
    """
    mode = (rebuild_mode or "").strip()
    reason = (rebuild_reason or "").strip()
    if not mode:
        if exact_capable:
            mode = REBUILD_MODE_EXACT
            reason = reason or "fact_ledger_triple_replay"
        else:
            mode = REBUILD_MODE_NON
            reason = reason or "not_exact_capable"
    if mode not in REBUILD_MODES:
        raise RebuildTaxonomyError(f"invalid_rebuild_mode:{mode}")
    # 为什么：禁止把不可重建视图冒充 exact（N05 诚实锁）
    if mode == REBUILD_MODE_EXACT and not exact_capable:
        raise RebuildTaxonomyError("exact_forbidden_when_not_exact_capable")
    if mode == REBUILD_MODE_NON and not reason:
        reason = "marked_non_rebuildable"
    if mode == REBUILD_MODE_SEMANTIC and not reason:
        reason = "semantic_transform_beyond_facts"
    if mode == REBUILD_MODE_EXACT and not reason:
        reason = "fact_ledger_triple_replay"
    if facts_read < 0:
        raise RebuildTaxonomyError("facts_read_negative")
    return mode, reason


def validate_rebuild_receipt(receipt: Dict[str, Any]) -> Dict[str, Any]:
    """门槛门：重建回执必有合法 mode；禁 non→exact 冒充。

    Args:
        receipt: 投影/重建回执。

    Returns:
        gate 结果；``certified`` / ``n05_full_conformance`` 恒 false。
    """
    r = receipt or {}
    mode = str(r.get("rebuild_mode") or "").strip()
    reason = str(r.get("rebuild_reason") or "").strip()
    errors: List[str] = []
    if not mode:
        errors.append("rebuild_mode_required")
    elif mode not in REBUILD_MODES:
        errors.append(f"invalid_rebuild_mode:{mode}")
    if not reason:
        errors.append("rebuild_reason_required")
    # 为什么：exact 必须可追溯事实源标记，防止空壳 exact
    if mode == REBUILD_MODE_EXACT:
        src = str(r.get("projection_source") or r.get("source") or "").strip()
        if src and src != _PROJECTION_SOURCE:
            errors.append("exact_requires_fact_ledger_source")
        if r.get("exact_capable") is False:
            errors.append("exact_forbidden_when_not_exact_capable")
    if mode == REBUILD_MODE_NON and mode == REBUILD_MODE_EXACT:  # pragma: no cover
        errors.append("non_rebuildable_cannot_be_exact")
    ok = not errors
    return {
        "ok": ok,
        "errors": errors,
        "rebuild_mode": mode,
        "rebuild_reason": reason,
        "certified": False,
        "n05_full_conformance": False,
    }


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
    rebuild_mode: Optional[str] = None,
    rebuild_reason: str = "",
    exact_capable: bool = True,
) -> Dict[str, Any]:
    """将域内 Fact 投影到 GraphIndex（租户隔离；可重建分类）。

    Args:
        tenant_id: 租户（召回前过滤）。
        domain_id: 业务域。
        ledger: 可选账本实例；默认进程单例。
        bindings_path: ObjectType 种子路径；缺省尝试
            ``aiPlat-core/workspace_seeds/ontologies/{domain_id}-object-types.json``。
        clear_projected: 为 True 时先移除此前投影标记的实体再写入。
        rebuild_mode: 可选显式分类；默认 exact（本路径）。
        rebuild_reason: 分类理由。
        exact_capable: 是否可精确重放；False 时禁止标 exact。

    Returns:
        投影回执（含 ``rebuild_mode`` / ``rebuild_reason`` / 实体数）。

    Raises:
        FactLedgerError: tenant_id / domain_id 为空。
        RebuildTaxonomyError: 重建分类非法。
    """
    if not (tenant_id or "").strip():
        raise FactLedgerError("tenant_id required")
    if not (domain_id or "").strip():
        raise FactLedgerError("domain_id required")

    mode, reason = classify_rebuild(
        rebuild_mode=rebuild_mode,
        rebuild_reason=rebuild_reason,
        exact_capable=exact_capable,
    )

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

    # non_rebuildable：记录分类但不写 Graph（避免假可重建视图）
    if mode == REBUILD_MODE_NON:
        receipt = {
            "status": "ok",
            "rebuild_mode": mode,
            "rebuild_reason": reason,
            "projection_source": _PROJECTION_SOURCE,
            "exact_capable": False,
            "tenant_id": tenant_id,
            "domain_id": domain_id,
            "facts_read": len(facts),
            "subjects": len(by_subject),
            "created": [],
            "updated": [],
            "skipped": list(by_subject.keys()),
            "removed_before": removed,
            "object_type_bindings": len(bindings),
            "written": False,
        }
        gate = validate_rebuild_receipt(receipt)
        receipt["rebuild_gate"] = gate
        return receipt

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
        graph.add_entity_property(eid, "rebuild_mode", mode)
        graph.add_entity_property(eid, "rebuild_reason", reason)
        graph.add_entity_property(eid, "tenant_id", tenant_id)
        if fact_ids:
            graph.add_entity_property(eid, "fact_ids", ",".join(str(x) for x in fact_ids[:20]))
        for pk, pv in props.items():
            if pk.startswith("_"):
                continue
            graph.add_entity_property(eid, str(pk), str(pv)[:500])

    receipt = {
        "status": "ok",
        "rebuild_mode": mode,
        "rebuild_reason": reason,
        "projection_source": _PROJECTION_SOURCE,
        "exact_capable": exact_capable,
        "tenant_id": tenant_id,
        "domain_id": domain_id,
        "facts_read": len(facts),
        "subjects": len(by_subject),
        "created": created,
        "updated": updated,
        "skipped": skipped,
        "removed_before": removed,
        "object_type_bindings": len(bindings),
        "written": True,
    }
    gate = validate_rebuild_receipt(receipt)
    receipt["rebuild_gate"] = gate
    logger.info(
        "fact_projector: domain=%s tenant=%s mode=%s created=%s updated=%s",
        domain_id,
        tenant_id,
        mode,
        len(created),
        len(updated),
    )
    return receipt
