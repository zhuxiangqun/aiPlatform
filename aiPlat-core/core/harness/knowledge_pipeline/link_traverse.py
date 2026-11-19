"""Link traverse 最小实现（附录 F.2 link.traverse）— 租户前置、只读、ABox ACL。

从 FactLedger 三元组构造边（object 形如 ``Type:id`` 视为链接目标），BFS 多跳；
经 ``role`` 在召回前做实例拒绝与字段脱敏（复用 graph_abox_acl）。
非目标：不写 Fact；不实现 SDK / action.execute；不宣称 Wiki/KB 全入口字段 ACL。
"""
from __future__ import annotations

import logging
import re
from collections import deque
from typing import Any, Dict, List, Optional, Set, Tuple

from pydantic import BaseModel, Field

from core.harness.knowledge_pipeline.fact_ledger import (
    FactLedgerError,
    get_fact_ledger,
)
from core.harness.knowledge_pipeline.fact_projector import _parse_subject

logger = logging.getLogger(__name__)

_REF_RE = re.compile(r"^[A-Za-z_][\w-]*:[^\s]+$")


def _entity_readable(
    domain_id: str,
    entity_id: str,
    role: str,
    attrs: Optional[Dict[str, Any]] = None,
) -> bool:
    """实例读 ACL；无 domain/role/ACL 时放行（与 ObjectSet 一致）。

    Args:
        domain_id: 域 id。
        entity_id: 实体 id（不含 Type: 前缀）。
        role: 调用方角色。
        attrs: 可选实例属性（H.1 condition）。
    """
    if not domain_id or not entity_id:
        return True
    from core.policy.graph_abox_acl import check_entity_acl

    return bool(check_entity_acl(domain_id, entity_id, role, "read", attrs=attrs))


def _redact_node(
    domain_id: str,
    entity_id: str,
    payload: Dict[str, Any],
    role: str,
) -> Dict[str, Any]:
    """节点字段脱敏。

    Args:
        domain_id: 域 id。
        entity_id: 实体 id。
        payload: 节点 dict。
        role: 调用方角色。
    """
    if not domain_id or not entity_id:
        return payload
    from core.policy.graph_abox_acl import redact_entity_fields

    return redact_entity_fields(domain_id, entity_id, payload, role)


class LinkTraverseRequest(BaseModel):
    """附录 F.2 link.traverse 请求（最小字段）。"""

    model_config = {"extra": "forbid"}

    start_id: str = Field(..., min_length=1, max_length=200)
    object_type: str = ""
    link_types: List[str] = Field(default_factory=list)
    max_hops: int = Field(2, ge=1, le=5)
    domain_id: str = ""
    direction: str = Field("both", pattern="^(outgoing|incoming|both)$")


def _permissions_allow(need: List[str], have: Optional[List[str]]) -> Dict[str, Any]:
    """L1 权限评估（与 ObjectSet 同语义）。"""
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


def _canon_node(raw: str, default_type: str = "") -> Optional[str]:
    """规范化节点 id 为 ``Type:id``；无法识别则 None。

    Args:
        raw: 原始 subject/object 串。
        default_type: 缺省类型（仅当 raw 无冒号时）。
    """
    s = str(raw or "").strip()
    if not s:
        return None
    if _REF_RE.match(s):
        return s
    if default_type and ":" not in s:
        return f"{default_type}:{s}"
    return None


def _is_link_object(obj: Any) -> bool:
    """object 是否像链接目标（Type:id）。"""
    return bool(_REF_RE.match(str(obj or "").strip()))


def _build_adjacency(
    facts: List[Dict[str, Any]],
    *,
    link_types: List[str],
) -> Tuple[Dict[str, List[Tuple[str, str]]], Dict[str, List[Tuple[str, str]]]]:
    """从事实构建出边/入边邻接表。

    Args:
        facts: Fact 行。
        link_types: 允许的谓词；空=全部链接谓词。

    Returns:
        (outgoing, incoming) 映射：node → [(neighbor, link_type), ...]。
    """
    allow = {str(x) for x in (link_types or []) if str(x)}
    outgoing: Dict[str, List[Tuple[str, str]]] = {}
    incoming: Dict[str, List[Tuple[str, str]]] = {}
    for f in facts:
        pred = str(f.get("predicate") or "").strip()
        if not pred:
            continue
        if allow and pred not in allow:
            continue
        obj = f.get("object")
        if not _is_link_object(obj):
            continue
        src = _canon_node(str(f.get("subject") or ""))
        dst = _canon_node(str(obj))
        if not src or not dst:
            continue
        outgoing.setdefault(src, []).append((dst, pred))
        incoming.setdefault(dst, []).append((src, pred))
    return outgoing, incoming


async def traverse_links(
    request: LinkTraverseRequest | Dict[str, Any],
    *,
    tenant_id: str,
    permissions: Optional[List[str]] = None,
    required_permissions: Optional[List[str]] = None,
    role: str = "",
    ledger=None,
) -> Dict[str, Any]:
    """多跳链接遍历（只读；租户 SQL 前置；可选 ABox ACL）。

    Args:
        request: F.2 请求或 dict。
        tenant_id: 租户（必填）。
        permissions: 调用方 scopes。
        required_permissions: 合同级权限，默认 ``["kb:read"]``。
        role: ABox ACL 角色；空则实例 ACL 默认放行。
        ledger: 可选 FactLedger 注入（测试）。

    Returns:
        含 nodes/edges 的回执，或 ``policy_denied`` / ``error``。
    """
    if not tenant_id:
        return {
            "status": "error",
            "reason": "tenant_id_required",
            "start_id": "",
            "nodes": [],
            "edges": [],
            "hops_reached": 0,
        }

    req = (
        request
        if isinstance(request, LinkTraverseRequest)
        else LinkTraverseRequest.model_validate(request)
    )
    need = list(required_permissions if required_permissions is not None else ["kb:read"])
    gate = _permissions_allow(need, permissions)
    if gate["decision"] != "allow":
        return {
            "status": "policy_denied",
            "reason": gate["reason"],
            "policy_gate": gate,
            "start_id": req.start_id,
            "nodes": [],
            "edges": [],
            "hops_reached": 0,
        }

    start = _canon_node(req.start_id, default_type=req.object_type.strip())
    if start is None:
        return {
            "status": "error",
            "reason": "start_id_invalid",
            "start_id": req.start_id,
            "nodes": [],
            "edges": [],
            "hops_reached": 0,
        }

    fl = ledger or get_fact_ledger()
    await fl.initialize()
    domain_id = (req.domain_id or "").strip()
    actor_role = (role or "").strip()
    try:
        facts = await fl.query_facts(
            tenant_id=tenant_id,
            domain_id=domain_id or None,
            limit=2000,
        )
    except FactLedgerError as e:
        return {
            "status": "error",
            "reason": str(e)[:500],
            "start_id": start,
            "nodes": [],
            "edges": [],
            "hops_reached": 0,
        }

    outgoing, incoming = _build_adjacency(facts, link_types=req.link_types)
    direction = req.direction

    cls0, eid0 = _parse_subject(start)
    start_node = {"id": eid0 or start, "object_type": cls0 or "", "ref": start}
    # 为什么：起点被 deny 时不得返回子图（召回前过滤）；attrs 供 H.1 condition
    if not _entity_readable(domain_id, eid0 or "", actor_role, attrs=start_node):
        return {
            "status": "ok",
            "start_id": start,
            "nodes": [],
            "edges": [],
            "hops_reached": 0,
            "max_hops": req.max_hops,
            "domain_id": domain_id,
            "policy_gate": gate,
            "acl_filtered": True,
            "acl_denied_start": True,
        }

    # BFS：(node, hop)
    seen: Set[str] = {start}
    nodes: Dict[str, Dict[str, Any]] = {}
    nodes[start] = _redact_node(domain_id, eid0 or "", start_node, actor_role)
    edges: List[Dict[str, Any]] = []
    q: deque = deque([(start, 0)])
    hops_reached = 0
    acl_dropped = 0

    while q:
        cur, hop = q.popleft()
        if hop >= req.max_hops:
            continue
        neighbors: List[Tuple[str, str, str]] = []
        # (neighbor, link_type, edge_dir)
        if direction in ("outgoing", "both"):
            for nb, lt in outgoing.get(cur, []):
                neighbors.append((nb, lt, "outgoing"))
        if direction in ("incoming", "both"):
            for nb, lt in incoming.get(cur, []):
                neighbors.append((nb, lt, "incoming"))

        for nb, lt, ed in neighbors:
            _cls, eid = _parse_subject(nb)
            nb_attrs = {"id": eid or nb, "object_type": _cls or "", "ref": nb}
            if not _entity_readable(domain_id, eid or "", actor_role, attrs=nb_attrs):
                acl_dropped += 1
                continue
            edges.append(
                {
                    "from": cur,
                    "to": nb,
                    "link_type": lt,
                    "direction": ed,
                    "hop": hop + 1,
                }
            )
            hops_reached = max(hops_reached, hop + 1)
            if nb in seen:
                continue
            seen.add(nb)
            node = {"id": eid or nb, "object_type": _cls or "", "ref": nb}
            nodes[nb] = _redact_node(domain_id, eid or "", node, actor_role)
            q.append((nb, hop + 1))

    return {
        "status": "ok",
        "start_id": start,
        "nodes": list(nodes.values()),
        "edges": edges,
        "hops_reached": hops_reached,
        "max_hops": req.max_hops,
        "domain_id": domain_id,
        "policy_gate": gate,
        "acl_filtered": bool(actor_role and domain_id),
        "acl_dropped": acl_dropped,
    }
