"""Skill Eval API — thin HTTP over CoreFacade skill_eval_* (ARCH v1.1c)."""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, HTTPException, Request

from core.api.deps import actor_from_http, rbac_guard
from apps.common_schemas import StatusResponse, ItemResponse

router = APIRouter()


def _map_ops_errors(exc: BaseException) -> HTTPException:
    if isinstance(exc, LookupError):
        msg = str(exc)
        if msg.startswith("skill_md_not_found:"):
            sid = msg.split(":", 1)[1]
            return HTTPException(
                status_code=404,
                detail={"code": "skill_md_not_found", "skill_id": sid},
            )
        return HTTPException(status_code=404, detail=msg)
    if isinstance(exc, ValueError):
        return HTTPException(status_code=400, detail=str(exc))
    if isinstance(exc, RuntimeError):
        return HTTPException(status_code=503, detail=str(exc))
    return HTTPException(status_code=500, detail=str(exc))


@router.post("/skill-evals/suites", response_model=StatusResponse)
async def upsert_skill_eval_suite(request: dict, http_request: Request):
    body = dict(request or {}) if isinstance(request, dict) else {}
    actor = actor_from_http(http_request, body)
    deny = await rbac_guard(
        http_request=http_request,
        payload=body,
        action="update",
        resource_type="skill_eval",
        resource_id=str(body.get("suite_id") or "suite"),
        run_id=None,
    )
    if deny:
        return deny
    from core.api.core_facade import skill_eval_upsert_suite

    try:
        return await skill_eval_upsert_suite(body=body, actor=actor)
    except Exception as exc:
        raise _map_ops_errors(exc) from exc


@router.post("/skill-evals/suites/ensure-builtin", response_model=ItemResponse)
async def ensure_builtin_skill_eval_suites(
    request: dict, http_request: Request
):
    """Idempotent seed: builtin_trigger_demo for Eval Skills empty-state."""
    body = dict(request or {}) if isinstance(request, dict) else {}
    actor = actor_from_http(http_request, body)
    deny = await rbac_guard(
        http_request=http_request,
        payload=body,
        action="update",
        resource_type="skill_eval",
        resource_id="builtin_trigger_demo",
        run_id=None,
    )
    if deny:
        return deny
    from core.api.core_facade import skill_eval_ensure_builtin_suites

    tenant_id = str(body.get("tenant_id") or actor.get("tenant_id") or "eval-v1")
    try:
        out = await skill_eval_ensure_builtin_suites(tenant_id=tenant_id)
        return {"data": out if isinstance(out, dict) else {"value": out}}
    except Exception as exc:
        raise _map_ops_errors(exc) from exc


@router.get("/skill-evals/preflight", response_model=ItemResponse)
async def skill_eval_preflight_api(
    tenant_id: Optional[str] = None,
    eval_kind: str = "trigger",
    mode: str = "heuristic",
):
    """Pre-run readiness: store / builtin / skill_manager|store_direct."""
    from core.api.core_facade import skill_eval_preflight

    try:
        out = await skill_eval_preflight(
            tenant_id=tenant_id or "eval-v1",
            eval_kind=eval_kind,
            mode=mode,
        )
        return {"data": out if isinstance(out, dict) else {"value": out}}
    except Exception as exc:
        raise _map_ops_errors(exc) from exc


@router.get("/skill-evals/suites", response_model=ItemResponse)
async def list_skill_eval_suites(
    limit: int = 50, offset: int = 0, tenant_id: Optional[str] = None
):
    from core.api.core_facade import skill_eval_list_suites

    try:
        out = await skill_eval_list_suites(
            limit=limit, offset=offset, tenant_id=tenant_id
        )
        # ItemResponse expects {data: ...}; facade returns {items,total,...}.
        return {"data": out if isinstance(out, dict) else {"value": out}}
    except Exception as exc:
        raise _map_ops_errors(exc) from exc


@router.get("/skill-evals/suites/{suite_id}", response_model=ItemResponse)
async def get_skill_eval_suite(suite_id: str):
    from core.api.core_facade import skill_eval_get_suite

    try:
        out = await skill_eval_get_suite(suite_id=suite_id)
        return {"data": out if isinstance(out, dict) else {"value": out}}
    except Exception as exc:
        raise _map_ops_errors(exc) from exc


@router.delete("/skill-evals/suites/{suite_id}", response_model=StatusResponse)
async def delete_skill_eval_suite(suite_id: str, http_request: Request):
    deny = await rbac_guard(
        http_request=http_request,
        payload={},
        action="delete",
        resource_type="skill_eval",
        resource_id=str(suite_id),
        run_id=None,
    )
    if deny:
        return deny
    from core.api.core_facade import skill_eval_delete_suite

    try:
        return await skill_eval_delete_suite(suite_id=suite_id)
    except Exception as exc:
        raise _map_ops_errors(exc) from exc


@router.post("/skill-evals/suites/{suite_id}/run", response_model=ItemResponse)
async def run_skill_eval_suite(suite_id: str, request: dict, http_request: Request):
    body = dict(request or {}) if isinstance(request, dict) else {}
    actor = actor_from_http(http_request, body)
    deny = await rbac_guard(
        http_request=http_request,
        payload=body,
        action="execute",
        resource_type="skill_eval",
        resource_id=str(suite_id),
        run_id=None,
    )
    if deny:
        return deny
    from core.api.core_facade import skill_eval_run_suite

    try:
        out = await skill_eval_run_suite(
            suite_id=suite_id, body=body, actor=actor
        )
        # Preserve run_id / runtime_tier (StatusResponse would strip extras).
        return {"data": out if isinstance(out, dict) else {"value": out}}
    except Exception as exc:
        raise _map_ops_errors(exc) from exc


@router.get("/skill-evals/runs/{run_id}", response_model=ItemResponse)
async def get_skill_eval_run(run_id: str):
    from core.api.core_facade import skill_eval_get_run

    try:
        return await skill_eval_get_run(run_id=run_id)
    except Exception as exc:
        raise _map_ops_errors(exc) from exc


@router.get("/skill-evals/runs/{run_id}/results", response_model=ItemResponse)
async def list_skill_eval_results(run_id: str, limit: int = 200, offset: int = 0):
    from core.api.core_facade import skill_eval_list_results

    try:
        return await skill_eval_list_results(
            run_id=run_id, limit=limit, offset=offset
        )
    except Exception as exc:
        raise _map_ops_errors(exc) from exc


@router.post("/skill-evals/runs/{run_id}/suggest", response_model=StatusResponse)
async def suggest_trigger_improvements(
    run_id: str, request: dict, http_request: Request
):
    body = dict(request or {}) if isinstance(request, dict) else {}
    deny = await rbac_guard(
        http_request=http_request,
        payload=body,
        action="read",
        resource_type="skill_eval",
        resource_id=str(run_id),
        run_id=None,
    )
    if deny:
        return deny
    from core.api.core_facade import skill_eval_suggest

    try:
        return await skill_eval_suggest(run_id=run_id, body=body)
    except Exception as exc:
        raise _map_ops_errors(exc) from exc


@router.post(
    "/skill-evals/suites/{suite_id}/apply-suggestion", response_model=StatusResponse
)
async def apply_skill_eval_suggestion(
    suite_id: str, request: dict, http_request: Request
):
    body = dict(request or {}) if isinstance(request, dict) else {}
    deny = await rbac_guard(
        http_request=http_request,
        payload=body,
        action="update",
        resource_type="skill_eval",
        resource_id=str(suite_id),
        run_id=None,
    )
    if deny:
        return deny
    from core.api.core_facade import skill_eval_apply_suggestion

    try:
        return await skill_eval_apply_suggestion(suite_id=suite_id, body=body)
    except Exception as exc:
        raise _map_ops_errors(exc) from exc


@router.post(
    "/skill-evals/suites/{suite_id}/apply-skill-suggestion",
    response_model=StatusResponse,
)
async def apply_skill_md_suggestion(
    suite_id: str, request: dict, http_request: Request
):
    body = dict(request or {}) if isinstance(request, dict) else {}
    actor = actor_from_http(http_request, body)
    deny = await rbac_guard(
        http_request=http_request,
        payload=body,
        action="update",
        resource_type="skill_eval",
        resource_id=str(suite_id),
        run_id=None,
    )
    if deny:
        return deny
    from core.api.core_facade import skill_eval_apply_skill_md

    try:
        return await skill_eval_apply_skill_md(
            suite_id=suite_id, body=body, actor=actor
        )
    except Exception as exc:
        raise _map_ops_errors(exc) from exc


@router.post("/skill-evals/compare", response_model=StatusResponse)
async def compare_skill_eval_runs(request: dict, http_request: Request):
    body = dict(request or {}) if isinstance(request, dict) else {}
    deny = await rbac_guard(
        http_request=http_request,
        payload=body,
        action="read",
        resource_type="skill_eval",
        resource_id="compare",
        run_id=None,
    )
    if deny:
        return deny
    from core.api.core_facade import skill_eval_compare

    try:
        return await skill_eval_compare(body=body)
    except Exception as exc:
        raise _map_ops_errors(exc) from exc


@router.post(
    "/skill-evals/suites/{suite_id}/jobs/create", response_model=StatusResponse
)
async def create_skill_eval_job(
    suite_id: str, request: dict, http_request: Request
):
    body = dict(request or {}) if isinstance(request, dict) else {}
    actor = actor_from_http(http_request, body)
    deny = await rbac_guard(
        http_request=http_request,
        payload=body,
        action="update",
        resource_type="job",
        resource_id=f"skill_eval:{suite_id}",
        run_id=None,
    )
    if deny:
        return deny
    from core.api.core_facade import skill_eval_create_job

    try:
        return await skill_eval_create_job(
            suite_id=suite_id, body=body, actor=actor
        )
    except Exception as exc:
        raise _map_ops_errors(exc) from exc


__all__ = ["router"]
