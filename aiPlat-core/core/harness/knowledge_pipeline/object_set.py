"""ObjectSet 最小查询（附录 E.1/E.2）— 租户前置、只读。

职责：按 object_type + filter 从 FactLedger 组装对象集合视图。
非目标：不实现 SDK、Link traverse、字段级 ACL、写路径。
"""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field

from core.harness.knowledge_pipeline.fact_ledger import (
    FactLedgerError,
    get_fact_ledger,
    load_object_type_bindings,
)
from core.harness.knowledge_pipeline.fact_projector import _parse_subject

logger = logging.getLogger(__name__)


class ObjectSetRequest(BaseModel):
    """附录 E.1 ObjectSet 请求（最小字段）。"""

    model_config = {"extra": "forbid"}

    object_type: str = Field(..., min_length=1, max_length=120)
    filter: Dict[str, Any] = Field(default_factory=dict)
    sort: List[Dict[str, str]] = Field(default_factory=list)
    limit: int = Field(50, ge=1, le=500)
    domain_id: str = ""
    aggregate: List[Dict[str, Any]] = Field(default_factory=list)


def _permissions_allow(need: List[str], have: Optional[List[str]]) -> Dict[str, Any]:
    """L1 权限评估（与 Action/Function 同语义）。"""
    if not need:
        return {"decision": "allow", "reason": "no_required_permissions"}
    held = set(have or [])
    if "*" in held or "admin" in held:
        return {"decision": "allow", "reason": "admin_or_wildcard_scope"}
    missing = [p for p in need if p not in held]
    if missing:
        return {
            "decision": "deny",
            "reason": f"missing_permissions:{sorted(missing)}",
        }
    return {"decision": "allow", "reason": "permissions_satisfied"}


def _default_bindings_path() -> Optional[Path]:
    """workspace_seeds 下 ObjectType 绑定（配置驱动，无域名硬编码）。"""
    # object_set.py → …/core/harness/knowledge_pipeline；seeds 在 aiPlat-core/workspace_seeds
    roots = (
        Path(__file__).resolve().parents[3] / "workspace_seeds" / "ontologies",
        Path(__file__).resolve().parents[2] / "workspace_seeds" / "ontologies",
    )
    for seed_dir in roots:
        if not seed_dir.is_dir():
            continue
        # 取首个 *-object-types.json（多域时由调用方显式传 bindings_path）
        matches = sorted(seed_dir.glob("*-object-types.json"))
        if matches:
            return matches[0]
    return None


def _resolve_binding(
    object_type: str,
    *,
    bindings_path: Optional[Path] = None,
) -> Optional[Dict[str, Any]]:
    """按 object_type_id 解析绑定。

    Args:
        object_type: 对象类型 id。
        bindings_path: 可选种子路径。
    """
    path = bindings_path or _default_bindings_path()
    if path is None or not Path(path).is_file():
        return None
    for b in load_object_type_bindings(Path(path)):
        if str(b.get("object_type_id") or "") == object_type:
            return b
    return None


def _item_matches_filter(item: Dict[str, Any], filt: Dict[str, Any]) -> bool:
    """简单等值过滤（属性级）。"""
    for k, v in (filt or {}).items():
        if item.get(k) != v:
            return False
    return True


def _sort_items(items: List[Dict[str, Any]], sort_spec: List[Dict[str, str]]) -> None:
    """就地排序；仅支持单字段。"""
    if not sort_spec:
        return
    field = str(sort_spec[0].get("field") or "")
    if not field:
        return
    direction = str(sort_spec[0].get("direction") or "asc").lower()
    reverse = direction == "desc"
    items.sort(key=lambda x: (x.get(field) is None, str(x.get(field) or "")), reverse=reverse)


async def query_object_set(
    request: ObjectSetRequest | Dict[str, Any],
    *,
    tenant_id: str,
    permissions: Optional[List[str]] = None,
    required_permissions: Optional[List[str]] = None,
    bindings_path: Optional[Path] = None,
    ledger=None,
) -> Dict[str, Any]:
    """执行 ObjectSet 查询（只读；租户 SQL 前置）。

    Args:
        request: E.1 请求或 dict。
        tenant_id: 租户（必填）。
        permissions: 调用方 scopes。
        required_permissions: 合同级权限，默认 ``["kb:read"]``。
        bindings_path: ObjectType 种子路径。
        ledger: 可选 FactLedger 注入（测试）。

    Returns:
        E.2 形状回执，或 ``policy_denied`` / ``not_found`` / ``error``。
    """
    if not tenant_id:
        return {
            "status": "error",
            "reason": "tenant_id_required",
            "object_type": "",
            "total": 0,
            "items": [],
            "aggregates": [],
            "next_cursor": None,
        }

    req = (
        request
        if isinstance(request, ObjectSetRequest)
        else ObjectSetRequest.model_validate(request)
    )
    need = list(required_permissions if required_permissions is not None else ["kb:read"])
    gate = _permissions_allow(need, permissions)
    if gate["decision"] != "allow":
        return {
            "status": "policy_denied",
            "reason": gate["reason"],
            "policy_gate": gate,
            "object_type": req.object_type,
            "total": 0,
            "items": [],
            "aggregates": [],
            "next_cursor": None,
        }

    binding = _resolve_binding(req.object_type, bindings_path=bindings_path)
    if binding is None:
        return {
            "status": "not_found",
            "reason": "object_type_not_registered",
            "object_type": req.object_type,
            "total": 0,
            "items": [],
            "aggregates": [],
            "next_cursor": None,
        }

    domain_id = (req.domain_id or str(binding.get("domain_id") or "")).strip()
    fl = ledger or get_fact_ledger()
    await fl.initialize()

    try:
        facts = await fl.query_facts(
            tenant_id=tenant_id,
            domain_id=domain_id or None,
            limit=500,
        )
    except FactLedgerError as e:
        return {
            "status": "error",
            "reason": str(e)[:500],
            "object_type": req.object_type,
            "total": 0,
            "items": [],
            "aggregates": [],
            "next_cursor": None,
        }

    # subject → props（与投影器同构：Type:id）
    by_subject: Dict[str, Dict[str, Any]] = {}
    pk_field = str(binding.get("primary_key") or "id")
    for f in facts:
        subj = str(f.get("subject") or "")
        cls, eid = _parse_subject(subj)
        if cls != req.object_type:
            continue
        bucket = by_subject.setdefault(
            eid,
            {pk_field: eid, "object_type": req.object_type},
        )
        pred = str(f.get("predicate") or "")
        if pred:
            bucket[pred] = f.get("object")

    items = [v for v in by_subject.values() if _item_matches_filter(v, req.filter)]
    _sort_items(items, req.sort)
    limited = items[: req.limit]

    aggregates: List[Dict[str, Any]] = []
    for agg in req.aggregate or []:
        if str(agg.get("type") or "") != "count":
            continue
        group_by = list(agg.get("group_by") or [])
        if not group_by:
            aggregates.append({"count": len(items)})
            continue
        gkey = str(group_by[0])
        counts: Dict[str, int] = {}
        for it in items:
            key = str(it.get(gkey) or "")
            counts[key] = counts.get(key, 0) + 1
        for k, c in sorted(counts.items()):
            aggregates.append({gkey: k, "count": c})

    return {
        "status": "ok",
        "object_type": req.object_type,
        "total": len(items),
        "items": limited,
        "aggregates": aggregates,
        "next_cursor": None,
        "policy_gate": gate,
        "domain_id": domain_id,
        "tenant_id": tenant_id,
    }
