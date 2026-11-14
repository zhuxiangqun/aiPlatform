"""Run Eval API — thin HTTP over CoreFacade runs_eval_* (ARCH v1.1c)."""
from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request

from core.api.deps import actor_from_http, rbac_guard
from core.schemas_eval import EvidenceDiffRequest
from apps.common_schemas import StatusResponse, ItemResponse

router = APIRouter()


def _map_ops_errors(exc: BaseException) -> HTTPException:
    from core.api.core_facade import RunsEvalGateFailed

    if isinstance(exc, RunsEvalGateFailed):
        return HTTPException(
            status_code=409,
            detail={
                "code": "evaluation_failed",
                "artifact_id": exc.artifact_id,
                "report": exc.report,
            },
        )
    if isinstance(exc, LookupError):
        return HTTPException(status_code=404, detail=str(exc))
    if isinstance(exc, ValueError):
        return HTTPException(status_code=400, detail=str(exc))
    if isinstance(exc, RuntimeError):
        return HTTPException(status_code=503, detail=str(exc))
    return HTTPException(status_code=500, detail=str(exc))


@router.post("/runs/{run_id}/evaluate", response_model=StatusResponse)
async def submit_run_evaluation(run_id: str, request: dict, http_request: Request):
    """submit_run_evaluation。

    Args:
        run_id: 运行 ID。
        request: request 参数。
        http_request: http_request 参数。
    """
    deny = await rbac_guard(
        http_request=http_request,
        payload=request or {},
        action="update",
        resource_type="run",
        resource_id=str(run_id),
    )
    if deny:
        return deny
    from core.api.core_facade import runs_eval_submit

    actor = actor_from_http(http_request, request or {})
    try:
        return await runs_eval_submit(
            run_id=run_id, body=request or {}, actor=actor
        )
    except Exception as exc:
        raise _map_ops_errors(exc) from exc


@router.post("/runs/{run_id}/evaluate/auto", response_model=StatusResponse)
async def auto_evaluate_run(run_id: str, http_request: Request):
    """auto_evaluate_run。

    Args:
        run_id: 运行 ID。
        http_request: http_request 参数。
    """
    deny = await rbac_guard(
        http_request=http_request,
        payload={"run_id": str(run_id)},
        action="read",
        resource_type="run",
        resource_id=str(run_id),
    )
    if deny:
        return deny
    from core.api.core_facade import runs_eval_auto

    try:
        return await runs_eval_auto(run_id=run_id)
    except Exception as exc:
        raise _map_ops_errors(exc) from exc


@router.get("/runs/{run_id}/evaluation/latest", response_model=ItemResponse)
async def get_latest_run_evaluation(run_id: str):
    """获取 latest_run_evaluation。

    Args:
        run_id: 运行 ID。
    """
    from core.api.core_facade import runs_eval_latest

    try:
        return await runs_eval_latest(run_id=run_id)
    except Exception as exc:
        raise _map_ops_errors(exc) from exc


@router.get("/runs/{run_id}/investigate/latest", response_model=ItemResponse)
async def get_latest_investigate_report(run_id: str):
    """获取 latest_investigate_report。

    Args:
        run_id: 运行 ID。
    """
    from core.api.core_facade import runs_eval_investigate_latest

    try:
        return await runs_eval_investigate_latest(run_id=run_id)
    except Exception as exc:
        raise _map_ops_errors(exc) from exc


@router.post("/runs/{run_id}/investigate/auto", response_model=StatusResponse)
async def auto_investigate_run(run_id: str, http_request: Request):
    """auto_investigate_run。

    Args:
        run_id: 运行 ID。
        http_request: http_request 参数。
    """
    deny = await rbac_guard(
        http_request=http_request,
        payload={"run_id": str(run_id)},
        action="read",
        resource_type="run",
        resource_id=str(run_id),
    )
    if deny:
        return deny
    from core.api.core_facade import runs_eval_investigate_auto

    try:
        return await runs_eval_investigate_auto(run_id=run_id)
    except Exception as exc:
        raise _map_ops_errors(exc) from exc


@router.get("/runs/{run_id}/state/latest", response_model=ItemResponse)
async def get_latest_run_state(run_id: str):
    """获取 latest_run_state。

    Args:
        run_id: 运行 ID。
    """
    from core.api.core_facade import runs_eval_state_latest

    try:
        return await runs_eval_state_latest(run_id=run_id)
    except Exception as exc:
        raise _map_ops_errors(exc) from exc


@router.get("/runs/{run_id}/evidence_pack/latest", response_model=ItemResponse)
async def get_latest_evidence_pack(run_id: str):
    """获取 latest_evidence_pack。

    Args:
        run_id: 运行 ID。
    """
    from core.api.core_facade import runs_eval_evidence_pack_latest

    try:
        return await runs_eval_evidence_pack_latest(run_id=run_id)
    except Exception as exc:
        raise _map_ops_errors(exc) from exc


@router.post("/runs/{run_id}/evidence/diff", response_model=StatusResponse)
async def compute_run_evidence_diff(
    run_id: str, request: EvidenceDiffRequest, http_request: Request
):
    """计算 run_evidence_diff。

    Args:
        run_id: 运行 ID。
        request: request 参数。
        http_request: http_request 参数。
    """
    body = request.dict(exclude_none=True) if hasattr(request, "dict") else {}
    deny = await rbac_guard(
        http_request=http_request,
        payload=body or {},
        action="update",
        resource_type="run",
        resource_id=str(run_id),
    )
    if deny:
        return deny
    from core.api.core_facade import runs_eval_evidence_diff

    try:
        return await runs_eval_evidence_diff(
            run_id=run_id,
            base_evidence_pack_id=str((body or {}).get("base_evidence_pack_id") or ""),
            new_evidence_pack_id=str((body or {}).get("new_evidence_pack_id") or ""),
        )
    except Exception as exc:
        raise _map_ops_errors(exc) from exc


@router.post("/runs/{run_id}/state", response_model=StatusResponse)
async def upsert_run_state(run_id: str, request: dict, http_request: Request):
    """upsert_run_state。

    Args:
        run_id: 运行 ID。
        request: request 参数。
        http_request: http_request 参数。
    """
    deny = await rbac_guard(
        http_request=http_request,
        payload=request or {},
        action="update",
        resource_type="run",
        resource_id=str(run_id),
    )
    if deny:
        return deny
    from core.api.core_facade import runs_eval_upsert_state

    actor = actor_from_http(http_request, request or {})
    try:
        return await runs_eval_upsert_state(
            run_id=run_id,
            state=(request or {}).get("state"),
            lock=(request or {}).get("lock"),
            actor=actor,
        )
    except Exception as exc:
        raise _map_ops_errors(exc) from exc


@router.get("/runs/{run_id}/evidence", response_model=ItemResponse)
async def get_run_evidence(run_id: str):
    """获取 run_evidence。

    Args:
        run_id: 运行 ID。
    """
    from core.api.core_facade import runs_eval_evidence

    try:
        return await runs_eval_evidence(run_id=run_id)
    except Exception as exc:
        raise _map_ops_errors(exc) from exc


__all__ = ["router"]
