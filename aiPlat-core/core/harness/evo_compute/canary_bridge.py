"""Evo 候选 ↔ SkillRouter Canary 桥（生产加深 D3）。

默认使用**进程内本地** SkillRouter（沙箱），不触达全局单例。
``use_global_router=True`` 时才接全局路由器，并标记 ``production_write=true``。
非目标：不宣称 G1/E2 完成；状态机与 Platform Skill 灰度对齐为最小切片。
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from core.harness.deployment.canary import SkillRouter, get_skill_router
from core.harness.evo_compute.status import advance_candidate_status


def _honesty(*, production_write: bool = False) -> Dict[str, Any]:
    return {
        "g1_foundation": True,
        "g1_complete": False,
        "g3_complete": False,
        "certified": False,
        "e2_claimed": False,
        "production_write": bool(production_write),
    }


def _resolve_router(
    *,
    router: Optional[SkillRouter] = None,
    use_global_router: bool = False,
) -> tuple:
    """解析路由器与是否生产写。

    Returns:
        (router, production_write, source)
    """
    if router is not None:
        return router, False, "injected"
    if use_global_router:
        return get_skill_router(), True, "global"
    return SkillRouter(), False, "sandbox_local"


def request_evo_canary_cutover(
    *,
    candidate_id: str,
    skill_name: str,
    version: str = "evo-cand",
    rollout_percentage: int = 5,
    actor: str = "evo-canary",
    evidence_ref: str = "d3-canary",
    from_status: str = "approved",
    router: Optional[SkillRouter] = None,
    use_global_router: bool = False,
    canary_tenants: Optional[List[str]] = None,
) -> Dict[str, Any]:
    """申请 Canary：注册 Skill 灰度 + 候选 ``approved→canary``。

    Args:
        candidate_id: 候选 id。
        skill_name: Skill 名（路由键）。
        version: 灰度版本标签。
        rollout_percentage: 灰度百分比。
        actor: 操作者。
        evidence_ref: 证据前缀。
        from_status: 起始状态（须可迁至 canary，默认 approved）。
        router: 可选注入路由器。
        use_global_router: 是否用全局 SkillRouter（生产写）。
        canary_tenants: 金丝雀租户。
    """
    cid = str(candidate_id or "").strip()
    skill = str(skill_name or "").strip()
    if not cid or not skill:
        return {
            "ok": False,
            "error": "candidate_id_and_skill_required",
            "cutover": False,
            **_honesty(),
        }
    rtr, prod_write, src = _resolve_router(router=router, use_global_router=use_global_router)
    pct = max(0, min(100, int(rollout_percentage)))
    ver = str(version or "evo-cand").strip() or "evo-cand"
    rtr.register_version(
        skill,
        ver,
        rollout_percentage=pct,
        canary_tenants=list(canary_tenants or []),
        shadow_mode=False,
        auto_rollback={"metric": "error_rate", "threshold": 0.05, "window_minutes": 10},
    )
    step = advance_candidate_status(
        candidate_id=cid,
        from_status=from_status,
        to_status="canary",
        actor=str(actor or "evo-canary"),
        evidence_ref=f"{evidence_ref}:cutover",
    )
    if not step.get("ok"):
        # 状态机失败则撤回刚注册的灰度，避免悬挂
        rtr.remove_version(skill)
        return {
            "ok": False,
            "error": step.get("error") or "status_transition_failed",
            "status_step": step,
            "cutover": False,
            "router_source": src,
            **_honesty(production_write=prod_write),
        }
    return {
        "ok": True,
        "candidate_id": cid,
        "skill_name": skill,
        "version": ver,
        "rollout_percentage": pct,
        "status": "canary",
        "status_step": step,
        "cutover": True,
        "router_source": src,
        "note": "canary cutover registered; sandbox unless use_global_router"
        if not prod_write
        else "canary cutover on global SkillRouter",
        **_honesty(production_write=prod_write),
    }


def observe_evo_canary(
    *,
    skill_name: str = "",
    router: Optional[SkillRouter] = None,
    use_global_router: bool = False,
) -> Dict[str, Any]:
    """观察 Canary rollout 状态（只读摘要）。

    Args:
        skill_name: 可选过滤 Skill。
        router: 可选注入。
        use_global_router: 是否用全局路由器。
    """
    rtr, prod_write, src = _resolve_router(router=router, use_global_router=use_global_router)
    rows = rtr.get_rollout_status()
    skill = str(skill_name or "").strip()
    if skill:
        # SkillRouter.get_rollout_status 行键为 ``skill``（非 skill_name）
        rows = [
            r
            for r in rows
            if str(r.get("skill") or r.get("skill_name") or "") == skill
        ]
    return {
        "ok": True,
        "available": True,
        "rows": rows,
        "count": len(rows),
        "skill_filter": skill or None,
        "router_source": src,
        "cutover": False,
        "note": "observe-only canary rollout rows",
        **_honesty(production_write=prod_write),
    }


def rollback_evo_canary(
    *,
    candidate_id: str,
    skill_name: str,
    actor: str = "evo-canary",
    evidence_ref: str = "d3-canary",
    from_status: str = "canary",
    router: Optional[SkillRouter] = None,
    use_global_router: bool = False,
    force_remove: bool = True,
) -> Dict[str, Any]:
    """回滚 Canary：移除 Skill 灰度 + 候选 ``canary→rolled_back``。

    Args:
        candidate_id: 候选 id。
        skill_name: Skill 名。
        actor: 操作者。
        evidence_ref: 证据前缀。
        from_status: 当前状态。
        router: 可选注入。
        use_global_router: 是否全局路由器。
        force_remove: True 则直接 remove_version；否则先 check_auto_rollback。
    """
    cid = str(candidate_id or "").strip()
    skill = str(skill_name or "").strip()
    if not cid or not skill:
        return {
            "ok": False,
            "error": "candidate_id_and_skill_required",
            "rollback_ok": False,
            **_honesty(),
        }
    rtr, prod_write, src = _resolve_router(router=router, use_global_router=use_global_router)
    reason = None
    if force_remove:
        rtr.remove_version(skill)
        reason = "manual_remove_version"
    else:
        reason = rtr.check_auto_rollback(skill) or "no_auto_rollback_trigger"
        if reason == "no_auto_rollback_trigger":
            rtr.remove_version(skill)
            reason = "forced_after_no_auto_trigger"

    step = advance_candidate_status(
        candidate_id=cid,
        from_status=from_status,
        to_status="rolled_back",
        actor=str(actor or "evo-canary"),
        evidence_ref=f"{evidence_ref}:rollback",
    )
    return {
        "ok": bool(step.get("ok")),
        "candidate_id": cid,
        "skill_name": skill,
        "rollback_ok": bool(step.get("ok")),
        "rollback_reason": reason,
        "status": str(step.get("status") or ("rolled_back" if step.get("ok") else from_status)),
        "status_step": step,
        "router_source": src,
        "error": "" if step.get("ok") else (step.get("error") or "status_transition_failed"),
        "note": "canary rollback + candidate status rolled_back",
        **_honesty(production_write=prod_write),
    }


def run_evo_canary_cutover_rollback_cycle(
    *,
    candidate_id: str,
    skill_name: str,
    version: str = "evo-cand",
    rollout_percentage: int = 5,
    actor: str = "evo-canary",
    evidence_ref: str = "d3-canary",
    router: Optional[SkillRouter] = None,
    use_global_router: bool = False,
) -> Dict[str, Any]:
    """一次完整切流→观察→回滚循环（默认沙箱路由器）。

    Args:
        candidate_id: 候选。
        skill_name: Skill。
        version: 版本标签。
        rollout_percentage: 灰度%。
        actor: 操作者。
        evidence_ref: 证据。
        router: 可选注入（同实例贯穿）。
        use_global_router: 全局路由器（慎用）。
    """
    rtr, prod_write, src = _resolve_router(router=router, use_global_router=use_global_router)
    cut = request_evo_canary_cutover(
        candidate_id=candidate_id,
        skill_name=skill_name,
        version=version,
        rollout_percentage=rollout_percentage,
        actor=actor,
        evidence_ref=evidence_ref,
        router=rtr,
        use_global_router=False,
    )
    obs = observe_evo_canary(skill_name=skill_name, router=rtr, use_global_router=False)
    rb = rollback_evo_canary(
        candidate_id=candidate_id,
        skill_name=skill_name,
        actor=actor,
        evidence_ref=evidence_ref,
        router=rtr,
        use_global_router=False,
    )
    ok = bool(cut.get("ok") and rb.get("ok"))
    return {
        "ok": ok,
        "cutover": cut,
        "observe": obs,
        "rollback": rb,
        "router_source": src,
        "cycle_complete": ok and rb.get("rollback_ok") is True,
        "note": "sandbox canary cutover↔rollback cycle; ≠ production traffic claim"
        if not prod_write
        else "global router cycle; production_write=true",
        **_honesty(production_write=prod_write),
    }
