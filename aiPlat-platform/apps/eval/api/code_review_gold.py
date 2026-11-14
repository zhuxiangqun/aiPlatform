"""Code-review gold eval API — Precision/Recall for autoreview (ReviewBench-style)."""

from __future__ import annotations

from typing import Any, Dict

from fastapi import APIRouter, Depends
from auth.deps import require_auth
from apps.common_schemas import ItemResponse

router = APIRouter(prefix="/code-review-gold", tags=["code-review-gold"])


@router.get("/profiles", response_model=ItemResponse)
async def get_profiles(_auth: str = Depends(require_auth)) -> Dict[str, Any]:
    """List low_noise / balanced / high_coverage → autoreview args.

    Args:
        _auth: _auth 参数。
    """
    from core.api.core_facade import list_code_review_gold_profiles

    return {"data": {"profiles": list_code_review_gold_profiles()}}


@router.post("/evaluate", response_model=ItemResponse)
async def evaluate_gold(
    body: Dict[str, Any],
    _auth: str = Depends(require_auth),
) -> Dict[str, Any]:
    """Run gold eval.

    Args:
        body: 请求体 dict。
        _auth: _auth 参数。
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

    try:
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
    except ValueError as e:
        return {"data": {"ok": False, "error": str(e)}}
    from core.api.core_facade import attach_eval_protocol, eval_protocol_from_gold

    payload = {"data": out}
    return attach_eval_protocol(
        payload,
        eval_protocol_from_gold(result=out if isinstance(out, dict) else None, profile=str(body.get("profile") or "balanced")),
    )


@router.get("/reports", response_model=ItemResponse)
async def get_reports(
    tenant_id: str = "",
    limit: int = 20,
    _auth: str = Depends(require_auth),
) -> Dict[str, Any]:
    """列出 code_review gold 评测报告。

    Args:
        tenant_id: 租户 ID；空串表示默认/不过滤。
        limit: 返回条数上限。
        _auth: 鉴权依赖注入（未使用）。
    """
    from core.api.core_facade import list_code_review_gold_reports

    rows = list_code_review_gold_reports(tenant_id=tenant_id, limit=limit)
    return {"data": {"items": rows, "total": len(rows)}}


@router.post("/reevaluate", response_model=ItemResponse)
async def reevaluate_gold(
    body: Dict[str, Any],
    _auth: str = Depends(require_auth),
) -> Dict[str, Any]:
    """Re-run the same gold set and return deltas vs the previous report.

    Args:
        body: 请求体 dict。
        _auth: _auth 参数。
    """
    from core.api.core_facade import reevaluate_code_review_gold

    case_ids = body.get("case_ids")
    if isinstance(case_ids, str):
        case_ids = [case_ids]
    if case_ids is not None and not isinstance(case_ids, list):
        case_ids = None
    # Reevaluate is audit/replay: do not write novel→experience unless asked.
    record_novel = body.get("record_novel")
    if record_novel is None:
        record_novel = False
    baseline = body.get("baseline")
    if baseline is not None and not isinstance(baseline, dict):
        baseline = None

    try:
        out = await reevaluate_code_review_gold(
            profile=str(body.get("profile") or "balanced"),
            gold_dir=str(body.get("gold_dir") or "") or None,
            case_ids=case_ids,
            match_only=bool(body.get("match_only", False)),
            limit=int(body.get("limit") or 0),
            tenant_id=str(body.get("tenant_id") or ""),
            persist=bool(body.get("persist", True)),
            record_novel=bool(record_novel),
            baseline=baseline,
        )
    except ValueError as e:
        return {"data": {"ok": False, "error": str(e)}}
    from core.api.core_facade import attach_eval_protocol, eval_protocol_from_gold

    payload = {"data": out}
    return attach_eval_protocol(
        payload,
        eval_protocol_from_gold(result=out if isinstance(out, dict) else None, profile=str(body.get("profile") or "balanced")),
    )
