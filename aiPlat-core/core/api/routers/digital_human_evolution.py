# core-routing: allowed (digital-human harness status/decide/rollback — core capability, not an app module)
"""小朱/五域自进化状态与纠偏 HTTP 入口。

GET  /api/core/digital-human/evolution/status
POST /api/core/digital-human/evolution/proposals/{id}/decide
POST /api/core/digital-human/evolution/proposals/{id}/rollback
"""
from __future__ import annotations

from typing import Any, Dict, Optional

from fastapi import APIRouter, Body, Query, Request

from core.api.deps import actor_from_http

router = APIRouter(tags=["digital-human-evolution"])


@router.get("/digital-human/evolution/status", response_model=Dict[str, Any])
async def evolution_status(limit: int = Query(50, ge=1, le=200)):
    """聚合五域目标进度、提案列表与时间线。

    Args:
        limit: 提案/时间线条数上限。
    """
    from core.api.core_facade import get_digital_human_evolution_status

    return get_digital_human_evolution_status(limit=limit)


@router.post(
    "/digital-human/evolution/proposals/{proposal_id}/decide",
    response_model=Dict[str, Any],
)
async def evolution_decide(
    proposal_id: str,
    http_request: Request,
    body: Optional[Dict[str, Any]] = Body(default=None),
):
    """批准或拒绝待批进化提案。

    Args:
        proposal_id: 提案 id。
        http_request: HTTP 请求（身份门）。
        body: decision=approve|reject；可选 reason/apply。
    """
    from core.api.core_facade import decide_digital_human_evolution_proposal

    payload = body if isinstance(body, dict) else {}
    actor0 = actor_from_http(http_request, payload)
    actor = str(actor0.get("actor_id") or payload.get("actor") or "user")
    decision = str(payload.get("decision") or "").strip().lower()
    apply = payload.get("apply", True)
    if isinstance(apply, str):
        apply = apply.strip().lower() in ("1", "true", "yes", "on")
    return decide_digital_human_evolution_proposal(
        decision=decision,
        proposal_id=proposal_id,
        actor=actor,
        apply=bool(apply),
    )


@router.post(
    "/digital-human/evolution/proposals/{proposal_id}/rollback",
    response_model=Dict[str, Any],
)
async def evolution_rollback(
    proposal_id: str,
    http_request: Request,
    body: Optional[Dict[str, Any]] = Body(default=None),
):
    """回滚已应用/已批准提案（有界撤销）。

    Args:
        proposal_id: 提案 id。
        http_request: HTTP 请求（身份门）。
        body: 可选 reason/actor。
    """
    from core.api.core_facade import rollback_digital_human_evolution_proposal

    payload = body if isinstance(body, dict) else {}
    actor0 = actor_from_http(http_request, payload)
    actor = str(actor0.get("actor_id") or payload.get("actor") or "user")
    reason = str(payload.get("reason") or "")
    return rollback_digital_human_evolution_proposal(
        proposal_id=proposal_id,
        actor=actor,
        reason=reason,
    )
