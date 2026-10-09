"""Code-review gold eval API — Precision/Recall for autoreview (ReviewBench-style)."""

from __future__ import annotations

from typing import Any, Dict

from fastapi import APIRouter, Depends
from auth.deps import require_auth
from apps.common_schemas import ItemResponse

router = APIRouter(prefix="/code-review-gold", tags=["code-review-gold"])


@router.get("/profiles", response_model=ItemResponse)
async def get_profiles(_auth: str = Depends(require_auth)) -> Dict[str, Any]:
    """List low_noise / balanced / high_coverage → autoreview args."""
    from core.api.core_facade import list_code_review_gold_profiles

    return {"data": {"profiles": list_code_review_gold_profiles()}}


@router.post("/evaluate", response_model=ItemResponse)
async def evaluate_gold(
    body: Dict[str, Any],
    _auth: str = Depends(require_auth),
) -> Dict[str, Any]:
    """Run gold eval.

    body: {profile?, gold_dir?, case_ids?, match_only?, limit?, tenant_id?, persist?, record_novel?}
    match_only=true scores embedded ``predicted`` fixtures (no LLM).
    record_novel 把未匹配 P0/P1 → shared_memory + experience_feedback pending
    （升级确认后 Team Brain；不改黄金集）。默认 True。
    """
    from core.api.core_facade import run_code_review_gold_eval

    case_ids = body.get("case_ids")
    if isinstance(case_ids, str):
        case_ids = [case_ids]
    if case_ids is not None and not isinstance(case_ids, list):
        case_ids = None

    record_novel = body.get("record_novel")
    if record_novel is None:
        record_novel = True

    out = await run_code_review_gold_eval(
        profile=str(body.get("profile") or "balanced"),
        gold_dir=str(body.get("gold_dir") or "") or None,
        case_ids=case_ids,
        match_only=bool(body.get("match_only", False)),
        limit=int(body.get("limit") or 0),
        tenant_id=str(body.get("tenant_id") or ""),
        persist=bool(body.get("persist", True)),
        record_novel=bool(record_novel),
    )
    return {"data": out}


@router.get("/reports", response_model=ItemResponse)
async def get_reports(
    tenant_id: str = "",
    limit: int = 20,
    _auth: str = Depends(require_auth),
) -> Dict[str, Any]:
    from core.api.core_facade import list_code_review_gold_reports

    rows = list_code_review_gold_reports(tenant_id=tenant_id, limit=limit)
    return {"data": {"items": rows, "total": len(rows)}}
