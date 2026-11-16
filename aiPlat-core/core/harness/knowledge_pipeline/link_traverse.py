"""Link traverse 最小实现（附录 F.2 link.traverse）— 租户前置、只读。

从 FactLedger 三元组构造边（object 形如 ``Type:id`` 视为链接目标），BFS 多跳。
非目标：不写 Fact；不实现 SDK / action.execute / 字段级 ACL；不直连 GraphIndex 写路径。
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
    ledger=None,
) -> Dict[str, Any]:
    """多跳链接遍历（只读；租户 SQL 前置）。

    Args:
        request: F.2 请求或 dict。
        tenant_id: 租户（必填）。
        permissions: 调用方 scopes。
        required_permissions: 合同级权限，默认 ``["kb:read"]``。
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

    # BFS：(node, hop)
    seen: Set[str] = {start}
    nodes: Dict[str, Dict[str, Any]] = {}
    cls0, eid0 = _parse_subject(start)
    nodes[start] = {"id": eid0 or start, "object_type": cls0 or "", "ref": start}
    edges: List[Dict[str, Any]] = []
    q: deque = deque([(start, 0)])
    hops_reached = 0

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
            cls, eid = _parse_subject(nb)
            nodes[nb] = {"id": eid or nb, "object_type": cls or "", "ref": nb}
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
    }
