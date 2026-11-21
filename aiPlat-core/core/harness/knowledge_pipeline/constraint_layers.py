"""知识面 L1/L2/L3 约束分层（附录 N N20 deepen）。

职责：
  - 按标准分层评估约束：L1 硬门 / L2 软约束 / L3 审计
  - 强制 ``L1 > L2 > L3``：高风险无 L1 拒绝；L2 不得单独作安全边界
  - unified_query_gateway / put_fact / query_facts_gateway / MaterialsChat /
    GraphRAG / Wiki-KB 热路径 best-effort 挂 ``n20_constraint``（可 env 关闭）
  - 套件/门槛门：``certified`` / ``n20_full`` 恒 false

非目标：
  - 不重写 ActionRegistry / PolicyGate 全路径
  - 不宣称知识面全域（裸 list retrieve 全入口等）已完整分层强制
  - 不并入 N08 Lv4 误报门
  - 不宣称 N20 certified
"""
from __future__ import annotations

import logging
import os
import time
from typing import Any, Dict, List, Optional, Sequence

logger = logging.getLogger(__name__)

_SUITE_CASES = (
    "l1_blocks_missing_permission",
    "l2_warn_not_block",
    "l2_alone_high_risk_denied",
    "l3_audit_required_flag",
    "layer_order_l1_gt_l2_gt_l3",
    "honesty_certified_false",
    "hotpath_helper_attaches",
    "gateway_hotpath_entry",
    "put_fact_hotpath_entry",
    "query_facts_gateway_hotpath_entry",
    "materials_chat_hotpath_entry",
    "graphrag_hotpath_entry",
    "wiki_kb_hotpath_entry",
)

_LAYERS = ("L1", "L2", "L3")
_HIGH_RISK = frozenset({"high", "critical"})


class ConstraintLayersError(ValueError):
    """约束分层契约错误。"""


def classify_layer(layer: str) -> Dict[str, Any]:
    """校验并返回层元数据。

    Args:
        layer: ``L1`` / ``L2`` / ``L3``。
    """
    ly = (layer or "").strip().upper()
    if ly not in _LAYERS:
        raise ConstraintLayersError("layer_must_be_L1_L2_L3")
    meta = {
        "L1": {
            "name": "hard_gate",
            "role": "block_illegal",
            "security_boundary": True,
        },
        "L2": {
            "name": "soft_constraint",
            "role": "reduce_error",
            "security_boundary": False,
        },
        "L3": {
            "name": "audit",
            "role": "accountability",
            "security_boundary": False,
        },
    }[ly]
    return {"ok": True, "layer": ly, **meta, "certified": False}


def evaluate_constraint_stack(
    *,
    risk_level: str = "medium",
    required_permissions: Optional[Sequence[str]] = None,
    actor_permissions: Optional[Sequence[str]] = None,
    soft_constraints: Optional[Sequence[Dict[str, Any]]] = None,
    require_audit: bool = True,
    l1_present: Optional = True,
) -> Dict[str, Any]:
    """评估知识面约束栈（L1→L2→L3）。

    Args:
        risk_level: 风险等级（low/medium/high/critical）。
        required_permissions: L1 所需权限。
        actor_permissions: 调用方已有权限。
        soft_constraints: L2 软约束列表 ``[{id, message}]``。
        require_audit: 是否要求 L3 审计标记。
        l1_present: 是否声明存在 L1 门（高风险必须 True）。
    """
    risk = (risk_level or "medium").strip().lower() or "medium"
    req = [str(p).strip() for p in (required_permissions or []) if str(p).strip()]
    have = {str(p).strip() for p in (actor_permissions or []) if str(p).strip()}
    soft = list(soft_constraints or [])
    layers_fired: List[str] = []
    warnings: List[str] = []
    blocked = False
    block_reason = ""

    # 为什么：白皮书 L1>L2>L3 — 高风险无 L1 不得进入生产
    if risk in _HIGH_RISK and not l1_present:
        blocked = True
        block_reason = "high_risk_requires_l1"
        layers_fired.append("L1")
    elif risk in _HIGH_RISK and not req and l1_present:
        # L1 声明存在但无 required_permissions → 仍视为缺硬门
        blocked = True
        block_reason = "high_risk_l1_empty_permissions"
        layers_fired.append("L1")
    else:
        # L1 权限硬门
        if req:
            layers_fired.append("L1")
            missing = [p for p in req if p not in have and "*" not in have]
            if missing:
                blocked = True
                block_reason = f"l1_policy_denied:{','.join(missing)}"

    # L2 软约束：仅警告，不得单独作安全边界
    if soft and not blocked:
        layers_fired.append("L2")
        for sc in soft:
            if isinstance(sc, dict):
                warnings.append(str(sc.get("message") or sc.get("id") or "soft"))
            else:
                warnings.append(str(sc))
    elif soft and blocked:
        # 仍记录 L2 曾评估（可观测）但不改裁决
        layers_fired.append("L2")
        for sc in soft:
            if isinstance(sc, dict):
                warnings.append(str(sc.get("message") or sc.get("id") or "soft"))

    # 为什么：L2 不得单独作为高风险安全边界
    if (
        risk in _HIGH_RISK
        and soft
        and not req
        and not l1_present
        and block_reason == "high_risk_requires_l1"
    ):
        # already blocked
        pass

    # L3 审计标记（不替代 L1）
    audit = {
        "required": bool(require_audit),
        "recorded": False if blocked else bool(require_audit),
        "layer": "L3",
    }
    if require_audit:
        layers_fired.append("L3")

    # 去重保序
    seen = set()
    ordered = []
    for ly in layers_fired:
        if ly not in seen:
            seen.add(ly)
            ordered.append(ly)

    # 为什么：classify_layer 须有生产调用者（method_verify）；栈评估时物化层元数据
    layer_meta = {ly: classify_layer(ly) for ly in _LAYERS}

    return {
        "ok": not blocked,
        "blocked": blocked,
        "block_reason": block_reason,
        "risk_level": risk,
        "layers_fired": ordered,
        "warnings": warnings,
        "audit": audit,
        "layer_meta": layer_meta,
        "l1_security_boundary": bool(
            (layer_meta.get("L1") or {}).get("security_boundary")
        ),
        "l2_security_boundary": bool(
            (layer_meta.get("L2") or {}).get("security_boundary")
        ),
        "certified": False,
        "n20_full_conformance": False,
        "note": "Constraint stack deepen; not full knowledge-surface / not certified",
    }


def hotpath_constraint_enabled() -> bool:
    """Gateway 热路径挂约束栈开关（默认开；``AIPLAT_CONSTRAINT_LAYERS_HOTPATH=0`` 关）。"""
    raw = (os.environ.get("AIPLAT_CONSTRAINT_LAYERS_HOTPATH") or "1").strip().lower()
    return raw not in ("0", "false", "off", "no")


def maybe_attach_constraint_stack_hotpath(
    response: Optional[Dict[str, Any]],
    *,
    route: str = "",
    actor_permissions: Optional[Sequence[str]] = None,
    risk_level: str = "medium",
) -> Dict[str, Any]:
    """统一 Gateway 热路径 best-effort 挂 ``n20_constraint``；不改 F.1 裁决。

    Args:
        response: F.1 信封。
        route: Gateway 路由名。
        actor_permissions: 调用方权限（缺省视为可读）。
        risk_level: 风险等级。
    """
    resp = dict(response) if isinstance(response, dict) else {}
    if not hotpath_constraint_enabled():
        return resp
    try:
        perms = [str(p).strip() for p in (actor_permissions or []) if str(p).strip()]
        if not perms:
            perms = ["kb:read"]
        stack = evaluate_constraint_stack(
            risk_level=risk_level or "medium",
            required_permissions=["kb:read"],
            actor_permissions=perms,
            soft_constraints=[
                {
                    "id": "gateway_prefer_citations",
                    "message": "prefer citations on knowledge hits",
                }
            ],
            require_audit=True,
            l1_present=True,
        )
        # 为什么：本切片只挂观测信封，不阻断 Gateway 主响应（非全域强制）
        resp["n20_constraint"] = {
            "ok": stack.get("ok"),
            "blocked": stack.get("blocked"),
            "block_reason": stack.get("block_reason") or "",
            "layers_fired": list(stack.get("layers_fired") or []),
            "warnings": list(stack.get("warnings") or []),
            "audit": stack.get("audit") or {},
            "route": (route or "").strip(),
            "op": "unified_query_gateway",
            "hotpath": True,
            "enforced": False,
            "certified": False,
            "n20_full_conformance": False,
        }
        return resp
    except Exception as exc:
        logger.warning(
            "constraint_layers gateway hotpath failed: %s", exc, exc_info=True
        )
        return resp


def maybe_attach_put_fact_constraint_hotpath(
    record: Optional[Dict[str, Any]],
    *,
    actor_permissions: Optional[Sequence[str]] = None,
    risk_level: str = "medium",
) -> Dict[str, Any]:
    """put_fact 热路径 best-effort 挂 ``n20_constraint``；不阻断写入。

    Args:
        record: Fact 写入回执。
        actor_permissions: 调用方权限（缺省视为可写）。
        risk_level: 风险等级。
    """
    out = dict(record) if isinstance(record, dict) else {}
    if not hotpath_constraint_enabled():
        return out
    try:
        perms = [str(p).strip() for p in (actor_permissions or []) if str(p).strip()]
        if not perms:
            perms = ["kb:write"]
        stack = evaluate_constraint_stack(
            risk_level=risk_level or "medium",
            required_permissions=["kb:write"],
            actor_permissions=perms,
            soft_constraints=[
                {
                    "id": "prefer_draft_then_publish",
                    "message": "prefer draft then transition publish",
                }
            ],
            require_audit=True,
            l1_present=True,
        )
        # 为什么：写入已完成；信封仅观测，禁止用 blocked 回滚 put_fact
        out["n20_constraint"] = {
            "ok": stack.get("ok"),
            "blocked": stack.get("blocked"),
            "block_reason": stack.get("block_reason") or "",
            "layers_fired": list(stack.get("layers_fired") or []),
            "warnings": list(stack.get("warnings") or []),
            "audit": stack.get("audit") or {},
            "route": "put_fact",
            "op": "put_fact",
            "hotpath": True,
            "enforced": False,
            "certified": False,
            "n20_full_conformance": False,
        }
        return out
    except Exception as exc:
        logger.warning(
            "constraint_layers put_fact hotpath failed: %s", exc, exc_info=True
        )
        return out


def maybe_attach_query_facts_gateway_constraint_hotpath(
    response: Optional[Dict[str, Any]],
    *,
    actor_permissions: Optional[Sequence[str]] = None,
    risk_level: str = "medium",
) -> Dict[str, Any]:
    """query_facts_gateway 旁路热路径 best-effort 挂 ``n20_constraint``。

    Args:
        response: Fact Gateway 查询回执。
        actor_permissions: 调用方权限（缺省视为可读）。
        risk_level: 风险等级。
    """
    resp = dict(response) if isinstance(response, dict) else {}
    if not hotpath_constraint_enabled():
        return resp
    try:
        perms = [str(p).strip() for p in (actor_permissions or []) if str(p).strip()]
        if not perms:
            perms = ["kb:read"]
        stack = evaluate_constraint_stack(
            risk_level=risk_level or "medium",
            required_permissions=["kb:read"],
            actor_permissions=perms,
            soft_constraints=[
                {
                    "id": "fact_gateway_prefer_citations",
                    "message": "prefer citations on fact gateway hits",
                }
            ],
            require_audit=True,
            l1_present=True,
        )
        # 为什么：旁路查询已完成；信封仅观测，不改 abstain/citations 裁决
        resp["n20_constraint"] = {
            "ok": stack.get("ok"),
            "blocked": stack.get("blocked"),
            "block_reason": stack.get("block_reason") or "",
            "layers_fired": list(stack.get("layers_fired") or []),
            "warnings": list(stack.get("warnings") or []),
            "audit": stack.get("audit") or {},
            "route": "fact",
            "op": "query_facts_gateway",
            "hotpath": True,
            "enforced": False,
            "certified": False,
            "n20_full_conformance": False,
        }
        return resp
    except Exception as exc:
        logger.warning(
            "constraint_layers query_facts_gateway hotpath failed: %s",
            exc,
            exc_info=True,
        )
        return resp


def maybe_attach_materials_chat_constraint_hotpath(
    output: Optional[Dict[str, Any]],
    *,
    exit_kind: str = "rag",
    actor_permissions: Optional[Sequence[str]] = None,
    risk_level: str = "medium",
) -> Dict[str, Any]:
    """MaterialsChat 直出旁路热路径 best-effort 挂 ``n20_constraint``。

    Args:
        output: N21 enforce 后的 Agent 输出。
        exit_kind: ``rag`` / ``shortcut`` / ``cache_hit``。
        actor_permissions: 调用方权限（缺省视为可读）。
        risk_level: 风险等级。
    """
    out = dict(output) if isinstance(output, dict) else {}
    if not hotpath_constraint_enabled():
        return out
    try:
        perms = [str(p).strip() for p in (actor_permissions or []) if str(p).strip()]
        if not perms:
            perms = ["kb:read"]
        kind = (exit_kind or "rag").strip() or "rag"
        stack = evaluate_constraint_stack(
            risk_level=risk_level or "medium",
            required_permissions=["kb:read"],
            actor_permissions=perms,
            soft_constraints=[
                {
                    "id": "materials_prefer_citations",
                    "message": "prefer citations on materials knowledge hits",
                }
            ],
            require_audit=True,
            l1_present=True,
        )
        # 为什么：直出已完成；信封仅观测，不改 N21 abstain/citations 或 gateway_f1
        out["n20_constraint"] = {
            "ok": stack.get("ok"),
            "blocked": stack.get("blocked"),
            "block_reason": stack.get("block_reason") or "",
            "layers_fired": list(stack.get("layers_fired") or []),
            "warnings": list(stack.get("warnings") or []),
            "audit": stack.get("audit") or {},
            "route": "materials_chat",
            "op": "materials_chat",
            "exit": kind,
            "hotpath": True,
            "enforced": False,
            "certified": False,
            "n20_full_conformance": False,
        }
        return out
    except Exception as exc:
        logger.warning(
            "constraint_layers materials_chat hotpath failed: %s",
            exc,
            exc_info=True,
        )
        return out


def maybe_attach_graphrag_constraint_hotpath(
    result: Optional[Dict[str, Any]],
    *,
    actor_permissions: Optional[Sequence[str]] = None,
    risk_level: str = "medium",
) -> Dict[str, Any]:
    """GraphRAG 旁路热路径 best-effort 挂 ``n20_constraint``。

    Args:
        result: GraphRAG retrieve / N21 信封后的回执。
        actor_permissions: 调用方权限（缺省视为可读）。
        risk_level: 风险等级。
    """
    out = dict(result) if isinstance(result, dict) else {}
    if not hotpath_constraint_enabled():
        return out
    try:
        perms = [str(p).strip() for p in (actor_permissions or []) if str(p).strip()]
        if not perms:
            perms = ["kb:read"]
        stack = evaluate_constraint_stack(
            risk_level=risk_level or "medium",
            required_permissions=["kb:read"],
            actor_permissions=perms,
            soft_constraints=[
                {
                    "id": "graphrag_prefer_citations",
                    "message": "prefer citations on graphrag hits",
                }
            ],
            require_audit=True,
            l1_present=True,
        )
        # 为什么：检索已完成；信封仅观测，不改 n21_query / gateway_f1 裁决
        out["n20_constraint"] = {
            "ok": stack.get("ok"),
            "blocked": stack.get("blocked"),
            "block_reason": stack.get("block_reason") or "",
            "layers_fired": list(stack.get("layers_fired") or []),
            "warnings": list(stack.get("warnings") or []),
            "audit": stack.get("audit") or {},
            "route": "graphrag",
            "op": "graphrag_retrieve",
            "hotpath": True,
            "enforced": False,
            "certified": False,
            "n20_full_conformance": False,
        }
        return out
    except Exception as exc:
        logger.warning(
            "constraint_layers graphrag hotpath failed: %s",
            exc,
            exc_info=True,
        )
        return out


def maybe_attach_wiki_kb_constraint_hotpath(
    response: Optional[Dict[str, Any]],
    *,
    channel: str = "wiki",
    actor_permissions: Optional[Sequence[str]] = None,
    risk_level: str = "medium",
) -> Dict[str, Any]:
    """Wiki/KB 查询形与 list 信封热路径 best-effort 挂 ``n20_constraint``。

    Args:
        response: Wiki/KB 查询形或 list 信封 dict。
        channel: ``wiki`` / ``kb`` / ``wiki_context`` 等。
        actor_permissions: 调用方权限（缺省视为可读）。
        risk_level: 风险等级。
    """
    out = dict(response) if isinstance(response, dict) else {}
    if not hotpath_constraint_enabled():
        return out
    try:
        perms = [str(p).strip() for p in (actor_permissions or []) if str(p).strip()]
        if not perms:
            perms = ["kb:read"]
        ch = (channel or "wiki").strip() or "wiki"
        stack = evaluate_constraint_stack(
            risk_level=risk_level or "medium",
            required_permissions=["kb:read"],
            actor_permissions=perms,
            soft_constraints=[
                {
                    "id": "wiki_kb_prefer_citations",
                    "message": "prefer citations on wiki/kb hits",
                }
            ],
            require_audit=True,
            l1_present=True,
        )
        # 为什么：检索已完成；信封仅观测，不改 n21_query / abstain 裁决
        out["n20_constraint"] = {
            "ok": stack.get("ok"),
            "blocked": stack.get("blocked"),
            "block_reason": stack.get("block_reason") or "",
            "layers_fired": list(stack.get("layers_fired") or []),
            "warnings": list(stack.get("warnings") or []),
            "audit": stack.get("audit") or {},
            "route": ch,
            "op": "wiki_kb",
            "channel": ch,
            "hotpath": True,
            "enforced": False,
            "certified": False,
            "n20_full_conformance": False,
        }
        return out
    except Exception as exc:
        logger.warning(
            "constraint_layers wiki_kb hotpath failed: %s",
            exc,
            exc_info=True,
        )
        return out


def evaluate_constraint_layers_gate(
    suite: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """N20 deepen 门槛门（certified / n20_full 恒 false）。

    Args:
        suite: ``run_constraint_layers_suite`` 回执。
    """
    s = suite or {}
    issues: List[str] = []
    # 为什么：禁止套件自签 certified（分层 deepen ≠ N20 全量认证）
    if s.get("certified") is True:
        issues.append("honesty_certified_flag_forbidden")
    if s.get("n20_full_conformance") is True:
        issues.append("honesty_n20_full_flag_forbidden")
    cases = s.get("cases") or []
    if cases:
        failed = [c for c in cases if isinstance(c, dict) and not c.get("ok")]
        if failed:
            issues.append(f"suite_cases_failed:{len(failed)}")
        ids = {str(c.get("id") or "") for c in cases if isinstance(c, dict)}
        missing = [x for x in _SUITE_CASES if x not in ids]
        if missing:
            issues.append(f"suite_cases_missing:{','.join(missing)}")
    elif not s.get("ok"):
        issues.append("suite_not_ok")
    return {
        "ok": not issues and bool(s.get("ok", True)),
        "passed": int(s.get("passed") or 0),
        "total": int(s.get("total") or 0),
        "required": True,
        "issues": issues,
        "certified": False,
        "n20_full_conformance": False,
        "note": (
            "Constraint layers + Gateway/put_fact/query_facts_gateway/"
            "MaterialsChat/GraphRAG/Wiki-KB hotpath deepen; not N20 "
            "certified / not full surface / not Lv4 redesign"
        ),
    }


def run_constraint_layers_suite() -> Dict[str, Any]:
    """N20 deepen：L1/L2/L3 分层套件（含 Gateway 热路径；certified 恒 false）。"""
    import inspect

    from core.harness.knowledge_pipeline import fact_ledger as fl

    cases: List[Dict[str, Any]] = []

    denied = evaluate_constraint_stack(
        risk_level="medium",
        required_permissions=["kb:write"],
        actor_permissions=["kb:read"],
        soft_constraints=[{"id": "hint", "message": "prefer draft"}],
        require_audit=True,
    )
    cases.append(
        {
            "id": "l1_blocks_missing_permission",
            "ok": denied.get("blocked") is True
            and "l1_policy_denied" in str(denied.get("block_reason") or ""),
            "detail": denied.get("block_reason") or "",
        }
    )

    soft_ok = evaluate_constraint_stack(
        risk_level="low",
        required_permissions=[],
        actor_permissions=[],
        soft_constraints=[{"id": "style", "message": "prefer citations"}],
        require_audit=True,
        l1_present=True,
    )
    cases.append(
        {
            "id": "l2_warn_not_block",
            "ok": soft_ok.get("blocked") is False
            and soft_ok.get("ok") is True
            and len(soft_ok.get("warnings") or []) >= 1
            and soft_ok.get("l2_security_boundary") is False,
            "detail": "",
        }
    )

    alone = evaluate_constraint_stack(
        risk_level="high",
        required_permissions=[],
        actor_permissions=[],
        soft_constraints=[{"id": "prompt", "message": "be careful"}],
        require_audit=True,
        l1_present=False,
    )
    cases.append(
        {
            "id": "l2_alone_high_risk_denied",
            "ok": alone.get("blocked") is True
            and alone.get("block_reason") == "high_risk_requires_l1",
            "detail": "",
        }
    )

    aud = evaluate_constraint_stack(
        risk_level="medium",
        required_permissions=["kb:read"],
        actor_permissions=["kb:read"],
        require_audit=True,
    )
    cases.append(
        {
            "id": "l3_audit_required_flag",
            "ok": aud.get("audit", {}).get("required") is True
            and aud.get("audit", {}).get("recorded") is True
            and "L3" in (aud.get("layers_fired") or []),
            "detail": "",
        }
    )

    # 层序：L1 先于 L2 先于 L3
    order = evaluate_constraint_stack(
        risk_level="medium",
        required_permissions=["kb:write"],
        actor_permissions=["kb:write"],
        soft_constraints=[{"id": "x", "message": "y"}],
        require_audit=True,
    )
    fired = order.get("layers_fired") or []
    cases.append(
        {
            "id": "layer_order_l1_gt_l2_gt_l3",
            "ok": fired == ["L1", "L2", "L3"],
            "detail": str(fired),
        }
    )

    cases.append(
        {
            "id": "honesty_certified_false",
            "ok": order.get("certified") is False
            and order.get("n20_full_conformance") is False,
            "detail": "",
        }
    )

    attached = maybe_attach_constraint_stack_hotpath(
        {"answer": "x", "abstained": False, "citations": [{"source_id": "s1"}]},
        route="fact",
        actor_permissions=["kb:read"],
    )
    n20 = attached.get("n20_constraint") if isinstance(attached, dict) else None
    cases.append(
        {
            "id": "hotpath_helper_attaches",
            "ok": isinstance(n20, dict)
            and n20.get("hotpath") is True
            and n20.get("certified") is False
            and "L1" in (n20.get("layers_fired") or []),
            "detail": "",
        }
    )

    ug_src = inspect.getsource(fl.unified_query_gateway)
    put_src = inspect.getsource(fl.FactLedger.put_fact)
    cases.append(
        {
            "id": "gateway_hotpath_entry",
            "ok": "maybe_attach_constraint_stack_hotpath" in ug_src,
            "detail": "",
        }
    )
    cases.append(
        {
            "id": "put_fact_hotpath_entry",
            "ok": "maybe_attach_put_fact_constraint_hotpath" in put_src,
            "detail": "",
        }
    )

    qfg_src = inspect.getsource(fl.FactLedger.query_facts_gateway)
    cases.append(
        {
            "id": "query_facts_gateway_hotpath_entry",
            "ok": "maybe_attach_query_facts_gateway_constraint_hotpath" in qfg_src,
            "detail": "",
        }
    )

    from core.apps.agents import materials_chat as mc

    mc_src = (
        inspect.getsource(mc._n21_enforce_rag_output)
        + inspect.getsource(mc._n21_enforce_shortcut_output)
        + inspect.getsource(mc._n21_enforce_cache_hit_output)
    )
    cases.append(
        {
            "id": "materials_chat_hotpath_entry",
            "ok": "maybe_attach_materials_chat_constraint_hotpath" in mc_src,
            "detail": "",
        }
    )

    from core.harness.knowledge_pipeline import query_abstain_citations as qac

    gr_src = inspect.getsource(qac.attach_graphrag_n21_envelope)
    cases.append(
        {
            "id": "graphrag_hotpath_entry",
            "ok": "maybe_attach_graphrag_constraint_hotpath" in gr_src,
            "detail": "",
        }
    )

    wk_src = (
        inspect.getsource(qac.attach_list_retrieve_n21_envelope)
        + inspect.getsource(qac.query_wiki_with_abstain)
        + inspect.getsource(qac.query_kb_with_abstain)
    )
    cases.append(
        {
            "id": "wiki_kb_hotpath_entry",
            "ok": "maybe_attach_wiki_kb_constraint_hotpath" in wk_src,
            "detail": "",
        }
    )

    passed = sum(1 for c in cases if c.get("ok"))
    return {
        "ok": passed == len(_SUITE_CASES),
        "passed": passed,
        "total": len(_SUITE_CASES),
        "cases": cases,
        "certified": False,
        "n20_full_conformance": False,
        "measured_at": time.time(),
        "note": (
            "Constraint layers + Gateway/put_fact/query_facts_gateway/"
            "MaterialsChat/GraphRAG/Wiki-KB hotpath deepen; not full "
            "surface / not certified"
        ),
    }
