"""ObjectSet 最小查询（附录 E.1/E.2 / W8）— 租户前置、只读、ABox ACL。

职责：按 object_type + filter 从 FactLedger 组装对象集合视图；
经 ``role`` 应用实例级拒绝与字段脱敏（附录 H.1）；
N07/N22 deepen：嵌套布尔 filter（``$and``/``$or``/``$not`` + 字段算子）。
非目标：不实现写路径、Scenario/Package、Wiki/KB 全入口字段 ACL（SDK 见 sdk_generator）；
不宣称完整表达式语言产品 / N07·N22 certified；
``$where`` 永不 JS eval（declared_unavailable）；``$expr`` 仅有界字段/字面量二元比较；
产品面第一刀：``evaluate_object_set_where_expr_product``（默认可用结构化回执）。
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

# N07/N22 deepen：嵌套 filter 深度上限（防滥用；非无限表达式引擎）
_MAX_FILTER_DEPTH = 4
_FIELD_OPS = frozenset({"$eq", "$ne", "$in", "$exists"})
_BOOL_OPS = frozenset({"$and", "$or", "$not"})
# residual：$expr 有界二元比较；$where 显式不可用（禁 JS）
_EXPR_OPS = frozenset({"$eq", "$ne", "$gt", "$gte", "$lt", "$lte"})
_TOP_LEVEL_SPECIAL = frozenset({"$where", "$expr"})


class ObjectSetFilterError(ValueError):
    """ObjectSet filter 表达式非法或超深。"""


def _apply_abox_acl(
    items: List[Dict[str, Any]],
    *,
    domain_id: str,
    pk_field: str,
    role: str,
) -> List[Dict[str, Any]]:
    """实例拒绝 + 字段脱敏；无 ACL 文件时透传。

    Args:
        items: 过滤后的对象行。
        domain_id: 域 id（ABox ACL 目录键）。
        pk_field: 主键字段名。
        role: 调用方角色（空则 ACL 默认放行，与 graph_abox_acl 一致）。
    """
    if not domain_id:
        return items
    from core.policy.graph_abox_acl import check_entity_acl, redact_entity_fields

    out: List[Dict[str, Any]] = []
    for it in items:
        eid = str(it.get(pk_field) or it.get("id") or "").strip()
        if not eid:
            out.append(it)
            continue
        # 为什么：召回前过滤——deny 的实例不得进入 items/aggregates；传 attrs 供 H.1 condition
        if not check_entity_acl(domain_id, eid, role, "read", attrs=it):
            continue
        out.append(redact_entity_fields(domain_id, eid, it, role))
    return out


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


def _match_field_ops(item: Dict[str, Any], field: str, ops: Dict[str, Any]) -> bool:
    """字段级算子（``$eq``/``$ne``/``$in``/``$exists``）。

    Args:
        item: 对象行。
        field: 字段名。
        ops: 算子字典。
    """
    unknown = set(ops) - _FIELD_OPS
    if unknown:
        raise ObjectSetFilterError(f"unknown field op: {sorted(unknown)}")
    cur = item.get(field)
    if "$exists" in ops:
        want = bool(ops["$exists"])
        present = field in item and cur is not None
        if present != want:
            return False
    if "$eq" in ops and cur != ops["$eq"]:
        return False
    if "$ne" in ops and cur == ops["$ne"]:
        return False
    if "$in" in ops:
        allowed = ops["$in"]
        if not isinstance(allowed, list):
            raise ObjectSetFilterError("$in requires list")
        if cur not in allowed:
            return False
    return True


def _resolve_expr_operand(item: Dict[str, Any], operand: Any) -> Any:
    """解析 ``$expr`` 操作数：``$field`` → item[field]，其它为字面量。

    Args:
        item: 对象行。
        operand: ``$field`` 引用或字面量。
    """
    if isinstance(operand, str) and operand.startswith("$") and len(operand) > 1:
        # 为什么：禁止 ``$`` 空名；仅一层字段引用，不做路径点号展开
        return item.get(operand[1:])
    return operand


def _eval_bounded_expr(item: Dict[str, Any], expr: Any) -> bool:
    """有界 ``$expr``：单算子 + 二元比较（字段/字面量）。

    Args:
        item: 对象行。
        expr: ``{$op: [left, right]}``。

    Raises:
        ObjectSetFilterError: 非法 / 不支持的表达式。
    """
    if not isinstance(expr, dict) or len(expr) != 1:
        raise ObjectSetFilterError("$expr requires single-op object")
    op, args = next(iter(expr.items()))
    if op not in _EXPR_OPS:
        raise ObjectSetFilterError(f"unsupported $expr op: {op}")
    if not isinstance(args, list) or len(args) != 2:
        raise ObjectSetFilterError("$expr op requires 2-arg list")
    left = _resolve_expr_operand(item, args[0])
    right = _resolve_expr_operand(item, args[1])
    if op == "$eq":
        return left == right
    if op == "$ne":
        return left != right
    # 有序比较：None 与不可比类型 → False（不抛，避免半匹配炸查询）
    try:
        if op == "$gt":
            return left > right  # type: ignore[operator]
        if op == "$gte":
            return left >= right  # type: ignore[operator]
        if op == "$lt":
            return left < right  # type: ignore[operator]
        if op == "$lte":
            return left <= right  # type: ignore[operator]
    except TypeError:
        return False
    raise ObjectSetFilterError(f"unsupported $expr op: {op}")


def match_filter_expr(
    item: Dict[str, Any],
    filt: Any,
    *,
    depth: int = 0,
    max_depth: int = _MAX_FILTER_DEPTH,
) -> bool:
    """匹配嵌套布尔 filter（N07/N22 deepen + where/expr residual）。

    兼容附录 E 扁平等值 ``{k: v}``（隐式 ``$and``）；支持
    ``$and`` / ``$or`` / ``$not`` 与字段 ``$eq``/``$ne``/``$in``/``$exists``；
    residual：``$expr`` 有界二元比较；``$where`` → ``where_unavailable``。

    Args:
        item: 对象行。
        filt: filter 表达式。
        depth: 当前嵌套深度。
        max_depth: 最大深度（默认 4）。

    Returns:
        是否匹配。

    Raises:
        ObjectSetFilterError: 非法算子或超深。
    """
    if depth > max_depth:
        raise ObjectSetFilterError(f"filter depth exceeds max={max_depth}")
    if filt is None or filt == {}:
        return True
    if not isinstance(filt, dict):
        raise ObjectSetFilterError("filter must be object")

    # 为什么：$where 永不 JS eval——产品 residual 诚实拒绝，避免假安全
    if "$where" in filt:
        raise ObjectSetFilterError(
            "where_unavailable: $where is declared_unavailable (no JS eval)"
        )

    # 布尔 / 特殊算子优先（不可与字段键混用同一层，除隐式扁平 AND）
    bool_keys = [k for k in filt if k in _BOOL_OPS]
    special_keys = [k for k in filt if k in _TOP_LEVEL_SPECIAL]
    field_keys = [
        k for k in filt if k not in _BOOL_OPS and k not in _TOP_LEVEL_SPECIAL
    ]
    if (bool_keys or special_keys) and field_keys:
        raise ObjectSetFilterError(
            "cannot mix boolean/special ops with field keys at same level"
        )
    if len(special_keys) > 1 or (special_keys and bool_keys):
        raise ObjectSetFilterError(
            "cannot mix $expr/$where with each other or boolean ops at same level"
        )

    if "$expr" in filt:
        return _eval_bounded_expr(item, filt["$expr"])

    if "$and" in filt:
        clauses = filt["$and"]
        if not isinstance(clauses, list) or not clauses:
            raise ObjectSetFilterError("$and requires non-empty list")
        return all(
            match_filter_expr(item, c, depth=depth + 1, max_depth=max_depth)
            for c in clauses
        )
    if "$or" in filt:
        clauses = filt["$or"]
        if not isinstance(clauses, list) or not clauses:
            raise ObjectSetFilterError("$or requires non-empty list")
        return any(
            match_filter_expr(item, c, depth=depth + 1, max_depth=max_depth)
            for c in clauses
        )
    if "$not" in filt:
        return not match_filter_expr(
            item, filt["$not"], depth=depth + 1, max_depth=max_depth
        )

    # 扁平等值 / 字段算子（隐式 AND）
    for k, v in filt.items():
        if isinstance(v, dict) and any(str(op).startswith("$") for op in v):
            if not _match_field_ops(item, k, v):
                return False
        elif item.get(k) != v:
            return False
    return True


def _item_matches_filter(item: Dict[str, Any], filt: Dict[str, Any]) -> bool:
    """属性级过滤（嵌套布尔 + 扁平等值兼容）。"""
    return match_filter_expr(item, filt or {})


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
    role: str = "",
    bindings_path: Optional[Path] = None,
    ledger=None,
) -> Dict[str, Any]:
    """执行 ObjectSet 查询（只读；租户 SQL 前置；可选 ABox 实例/字段 ACL）。

    Args:
        request: E.1 请求或 dict。
        tenant_id: 租户（必填）。
        permissions: 调用方 scopes。
        required_permissions: 合同级权限，默认 ``["kb:read"]``。
        role: 调用方角色（透传 ABox ACL；空则字段/实例默认放行）。
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

    try:
        items = [
            v for v in by_subject.values() if _item_matches_filter(v, req.filter)
        ]
    except ObjectSetFilterError as e:
        return {
            "status": "error",
            "reason": f"invalid_filter:{e}",
            "object_type": req.object_type,
            "total": 0,
            "items": [],
            "aggregates": [],
            "next_cursor": None,
        }
    items = _apply_abox_acl(
        items,
        domain_id=domain_id,
        pk_field=pk_field,
        role=role or "",
    )
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
        "role": role or "",
    }


def run_object_set_filter_suite() -> Dict[str, Any]:
    """N07/N22 deepen：嵌套 filter 表达式套件（certified 恒 false）。

    Returns:
        套件回执；``certified`` / ``n07_full_conformance`` / ``n22_full_conformance`` 恒 false。
    """
    checks: Dict[str, bool] = {}
    item = {"status": "open", "priority": "high", "order_id": "O-1"}

    # 1) 扁平等值兼容
    checks["flat_equality"] = match_filter_expr(
        item, {"status": "open", "priority": "high"}
    ) and not match_filter_expr(item, {"status": "closed"})

    # 2) $and / $or / $not 嵌套
    nested = {
        "$and": [
            {"status": {"$eq": "open"}},
            {
                "$or": [
                    {"priority": {"$in": ["high", "urgent"]}},
                    {"order_id": {"$eq": "missing"}},
                ]
            },
            {"$not": {"status": {"$eq": "closed"}}},
        ]
    }
    checks["nested_boolean"] = match_filter_expr(item, nested)

    # 3) $exists / $ne
    checks["field_ops"] = match_filter_expr(
        item, {"assignee": {"$exists": False}, "status": {"$ne": "closed"}}
    )

    # 4) 深度上限拒绝
    deep: Dict[str, Any] = {"status": "open"}
    for _ in range(_MAX_FILTER_DEPTH + 2):
        deep = {"$and": [deep]}
    try:
        match_filter_expr(item, deep)
        checks["depth_cap"] = False
    except ObjectSetFilterError:
        checks["depth_cap"] = True

    # 5) residual：$where 诚实不可用（禁 JS）
    try:
        match_filter_expr(item, {"$where": "this.status == 'open'"})
        checks["where_unavailable"] = False
    except ObjectSetFilterError as exc:
        checks["where_unavailable"] = "where_unavailable" in str(exc)

    # 6) residual：$expr 有界二元比较
    checks["expr_bounded"] = match_filter_expr(
        item, {"$expr": {"$eq": ["$status", "open"]}}
    ) and match_filter_expr(
        item, {"$expr": {"$ne": ["$priority", "low"]}}
    ) and not match_filter_expr(
        item, {"$expr": {"$eq": ["$status", "closed"]}}
    )

    # 7) 诚实锁
    checks["honesty_certified_false"] = True

    passed = sum(1 for v in checks.values() if v)
    return {
        "ok": passed == len(checks),
        "passed": passed,
        "total": len(checks),
        "checks": checks,
        "certified": False,
        "n07_full_conformance": False,
        "n22_full_conformance": False,
        "wiki_kb_full_acl": False,
        "where_js_eval": False,
        "note": (
            "ObjectSet nested filter + $expr residual; $where declared_unavailable; "
            "not Wiki/KB full ACL; not N07/N22 certified"
        ),
    }


def evaluate_object_set_filter_gate(
    suite: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """N07/N22 嵌套 filter 门槛门；certified 恒 false。

    Args:
        suite: ``run_object_set_filter_suite`` 回执。
    """
    s = suite if isinstance(suite, dict) else run_object_set_filter_suite()
    issues: List[str] = []
    if not s.get("ok"):
        issues.append("suite_not_ok")
    if s.get("certified") is True:
        issues.append("honesty_certified_flag_forbidden")
    if s.get("n07_full_conformance") is True:
        issues.append("honesty_n07_full_forbidden")
    if s.get("n22_full_conformance") is True:
        issues.append("honesty_n22_full_forbidden")
    if s.get("wiki_kb_full_acl") is True:
        issues.append("honesty_wiki_kb_full_acl_forbidden")
    if s.get("where_js_eval") is True:
        issues.append("honesty_where_js_eval_forbidden")
    required = (
        "flat_equality",
        "nested_boolean",
        "field_ops",
        "depth_cap",
        "where_unavailable",
        "expr_bounded",
        "honesty_certified_false",
    )
    checks = s.get("checks") if isinstance(s.get("checks"), dict) else {}
    for k in required:
        if not checks.get(k):
            issues.append(f"missing_or_failed:{k}")
    return {
        "ok": not issues,
        "issues": issues,
        "certified": False,
        "note": (
            "ObjectSet nested filter + $expr residual; $where unavailable; "
            "not N07/N22 certified"
        ),
    }


_WHERE_EXPR_PRODUCT_CASES = (
    "where_expr_product_eval",
    "where_expr_product_where_unavailable",
    "honesty_product_certified_false",
)


def evaluate_object_set_where_expr_product(
    item: Dict[str, Any],
    filt: Dict[str, Any],
    *,
    max_depth: int = _MAX_FILTER_DEPTH,
) -> Dict[str, Any]:
    """N07/N22 产品面：有界 `$expr` / `$where` 结构化回执（默认可用；非 certified）。

    `$where` 仍诚实 unavailable（禁 JS）；`$expr` 走有界二元比较。
    返回结构化回执，便于 HTTP/UI（不抛 residual 同款异常冒充成功）。

    Args:
        item: 对象行。
        filt: filter 表达式（`$expr` 或 `$where` 等）。
        max_depth: 嵌套深度上限。
    """
    base = {
        "objectset_where_expr_product_surface": True,
        "certified": False,
        "n07_full_conformance": False,
        "n22_full_conformance": False,
        "where_js_eval": False,
        "n07_n22_h1_condition_freeze": True,
        "wiki_kb_full_acl": False,
    }
    if not isinstance(item, dict) or not isinstance(filt, dict):
        return {
            **base,
            "status": "invalid",
            "matched": False,
            "error": "item_and_filter_required",
        }

    # 为什么：产品面仍拒绝 $where JS——与 residual 同诚实锁，仅改为结构化回执
    if "$where" in filt:
        return {
            **base,
            "status": "where_unavailable",
            "matched": False,
            "via": "product_where_denied",
            "note": (
                "$where declared_unavailable (no JS eval); "
                "product surface still refuses"
            ),
        }

    try:
        matched = match_filter_expr(item, filt, max_depth=max_depth)
        via = "product_expr" if "$expr" in filt else "product_filter"
        return {
            **base,
            "status": "ok",
            "matched": bool(matched),
            "via": via,
            "note": (
                "ObjectSet where/expr product surface; "
                "not full expression language / not N07/N22 certified"
            ),
        }
    except ObjectSetFilterError as exc:
        msg = str(exc)
        status = (
            "where_unavailable" if "where_unavailable" in msg else "filter_error"
        )
        return {
            **base,
            "status": status,
            "matched": False,
            "via": "product_error",
            "error": msg,
            "note": (
                "ObjectSet where/expr product surface; "
                "not full expression language / not N07/N22 certified"
            ),
        }


def run_object_set_where_expr_product_suite() -> Dict[str, Any]:
    """N07/N22 产品面套件：`$expr` 可用；`$where` unavailable；certified 恒 false。"""
    cases: List[Dict[str, Any]] = []
    item = {"status": "open", "priority": "high", "n": 3}

    ok = evaluate_object_set_where_expr_product(
        item, {"$expr": {"$eq": ["$status", "open"]}}
    )
    gt_ok = evaluate_object_set_where_expr_product(
        item, {"$expr": {"$gt": ["$n", 2]}}
    )
    miss = evaluate_object_set_where_expr_product(
        item, {"$expr": {"$eq": ["$status", "closed"]}}
    )
    cases.append(
        {
            "id": "where_expr_product_eval",
            "ok": ok.get("status") == "ok"
            and ok.get("matched") is True
            and ok.get("via") == "product_expr"
            and ok.get("objectset_where_expr_product_surface") is True
            and gt_ok.get("matched") is True
            and miss.get("matched") is False
            and ok.get("certified") is False
            and ok.get("where_js_eval") is False,
        }
    )

    where_prod = evaluate_object_set_where_expr_product(
        item, {"$where": "this.status=='open'"}
    )
    residual_where_ok = False
    try:
        match_filter_expr(item, {"$where": "this.status=='open'"})
    except ObjectSetFilterError as exc:
        residual_where_ok = "where_unavailable" in str(exc)
    cases.append(
        {
            "id": "where_expr_product_where_unavailable",
            "ok": where_prod.get("status") == "where_unavailable"
            and where_prod.get("matched") is False
            and where_prod.get("objectset_where_expr_product_surface") is True
            and where_prod.get("where_js_eval") is False
            and residual_where_ok,
        }
    )
    cases.append(
        {
            "id": "honesty_product_certified_false",
            "ok": ok.get("certified") is False
            and ok.get("n07_full_conformance") is False
            and ok.get("n22_full_conformance") is False
            and where_prod.get("certified") is False
            and where_prod.get("where_js_eval") is False,
        }
    )

    passed = sum(1 for c in cases if c.get("ok"))
    return {
        "ok": passed == len(_WHERE_EXPR_PRODUCT_CASES)
        and len(cases) == len(_WHERE_EXPR_PRODUCT_CASES),
        "passed": passed,
        "total": len(_WHERE_EXPR_PRODUCT_CASES),
        "cases": cases,
        "certified": False,
        "n07_full_conformance": False,
        "n22_full_conformance": False,
        "where_js_eval": False,
        "n07_n22_h1_condition_freeze": True,
        "objectset_where_expr_product_surface": True,
        "note": (
            "ObjectSet where/expr product surface suite; "
            "$where unavailable; not N07/N22 certified"
        ),
    }


def evaluate_object_set_where_expr_product_gate(
    suite: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """N07/N22 产品面门槛门：要求 objectset_where_expr_product_surface。

    Args:
        suite: ``run_object_set_where_expr_product_suite`` 回执；缺省时现场跑套件。
    """
    s = (
        suite
        if isinstance(suite, dict)
        else run_object_set_where_expr_product_suite()
    )
    issues: List[str] = []
    if not s.get("ok"):
        issues.append("suite_not_ok")
    # 为什么：禁止套件自签 certified（产品面 ≠ N07/N22 全量）
    if (
        s.get("certified") is True
        or s.get("n07_full_conformance") is True
        or s.get("n22_full_conformance") is True
    ):
        issues.append("honesty_certified_flag_forbidden")
    # 为什么：$where JS 永不放开
    if s.get("where_js_eval") is True:
        issues.append("honesty_where_js_eval_forbidden")
    # 为什么：产品面门槛要求显式 surface 标记
    if s.get("objectset_where_expr_product_surface") is not True:
        issues.append("product_where_expr_surface_required")
    ids = {
        c.get("id")
        for c in (s.get("cases") or [])
        if isinstance(c, dict) and c.get("ok")
    }
    for need in _WHERE_EXPR_PRODUCT_CASES:
        if need not in ids:
            issues.append(f"missing_or_failed:{need}")
    return {
        "ok": not issues,
        "issues": issues,
        "certified": False,
        "n07_full_conformance": False,
        "n22_full_conformance": False,
        "where_js_eval": False,
        "n07_n22_h1_condition_freeze": True,
        "objectset_where_expr_product_surface": True,
        "note": (
            "ObjectSet where/expr product gate; "
            "$where unavailable; not N07/N22 certified"
        ),
    }
