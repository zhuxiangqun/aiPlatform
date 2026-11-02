"""B2-L — dynamic execute: allowlist enqueue (202) or unified deny body.

Honesty:
- API never silently runs forbidden runners (enqueue dual-point #1).
- Worker re-checks allowlist (dual-point #2) via app.worker.allowlist_guard.
- process_split_authorized remains false.
"""
from __future__ import annotations

from typing import Any, Dict, Optional

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from app.auth import require_bearer
from app.errors import runner_forbidden_response, sandbox_required_response
from app.runner_allowlist import classify_runner
from app.store.jobs import enqueue_job


def _db_url(request: Request) -> str:
    cfg = request.app.state.config
    return str(getattr(cfg, "db_url", "") or "")


def _tenant(claims: Dict[str, Any]) -> str:
    return str(claims.get("tenant_id") or "tenant-local")


async def _read_json(request: Request) -> Dict[str, Any]:
    try:
        body = await request.json()
        return body if isinstance(body, dict) else {}
    except Exception:
        return {}


def _enqueue_or_deny(
    request: Request,
    *,
    runner_id: str,
    claims: Dict[str, Any],
    payload: Optional[Dict[str, Any]] = None,
) -> JSONResponse:
    kind = classify_runner(runner_id)
    if kind == "sandbox_required":
        return sandbox_required_response(runner_id=runner_id)
    if kind == "forbidden":
        return runner_forbidden_response(runner_id=runner_id)

    body = payload or {}
    idem = str(body.get("idempotency_key") or body.get("idempotencyKey") or "")
    job = enqueue_job(
        _db_url(request),
        runner_id=runner_id,
        tenant_id=_tenant(claims),
        payload=body,
        idempotency_key=idem,
    )
    return JSONResponse(
        status_code=202,
        content={
            "job_id": job["job_id"],
            "status": job["status"],
            "runner_id": job["runner_id"],
            "tenant_id": job.get("tenant_id") or "",
            "process_split_authorized": False,
            "note": "B2-L enqueued; Worker execute is allowlist-gated (lease slice next).",
        },
    )


async def _stub_skill_run(request: Request, suite_id: str):
    claims = require_bearer(request)
    body = await _read_json(request)
    body = {**body, "suite_id": suite_id}
    return _enqueue_or_deny(request, runner_id="skill_suite", claims=claims, payload=body)


async def _stub_prompt_eval_run(request: Request):
    claims = require_bearer(request)
    body = await _read_json(request)
    return _enqueue_or_deny(request, runner_id="prompt_eval", claims=claims, payload=body)


async def _stub_arena_run(request: Request):
    claims = require_bearer(request)
    body = await _read_json(request)
    return _enqueue_or_deny(request, runner_id="arena", claims=claims, payload=body)


async def _stub_kb_eval_run(request: Request):
    claims = require_bearer(request)
    body = await _read_json(request)
    return _enqueue_or_deny(request, runner_id="kb_rag", claims=claims, payload=body)


async def _stub_http_probe(request: Request):
    claims = require_bearer(request)
    return _enqueue_or_deny(request, runner_id="http_probe", claims=claims)


async def _stub_cli_probe(request: Request):
    claims = require_bearer(request)
    return _enqueue_or_deny(request, runner_id="cli_probe", claims=claims)


async def _stub_replay_run(request: Request):
    claims = require_bearer(request)
    body = await _read_json(request)
    return _enqueue_or_deny(request, runner_id="replay_trace", claims=claims, payload=body)


async def _stub_code_review_run(request: Request):
    claims = require_bearer(request)
    body = await _read_json(request)
    return _enqueue_or_deny(request, runner_id="code_review_gold", claims=claims, payload=body)


async def _get_job(request: Request, job_id: str):
    require_bearer(request)
    from app.store.jobs import get_job

    job = get_job(_db_url(request), job_id)
    if not job:
        return JSONResponse(
            status_code=404,
            content={"error": {"code": "job_not_found", "runner_id": "", "retryable": False, "detail": job_id}},
        )
    return job


def register_execution_stubs(application: FastAPI) -> None:
    prefix = "/api/platform/apps/eval"
    application.add_api_route(
        f"{prefix}/skill-evals/suites/{{suite_id}}/run",
        _stub_skill_run,
        methods=["POST"],
    )
    application.add_api_route(
        f"{prefix}/prompts/eval/runs",
        _stub_prompt_eval_run,
        methods=["POST"],
    )
    application.add_api_route(
        f"{prefix}/arena/run",
        _stub_arena_run,
        methods=["POST"],
    )
    application.add_api_route(
        f"{prefix}/kb-eval/run",
        _stub_kb_eval_run,
        methods=["POST"],
    )
    application.add_api_route(
        f"{prefix}/probes/http",
        _stub_http_probe,
        methods=["POST"],
    )
    application.add_api_route(
        f"{prefix}/probes/cli",
        _stub_cli_probe,
        methods=["POST"],
    )
    application.add_api_route(
        f"{prefix}/replay/run",
        _stub_replay_run,
        methods=["POST"],
    )
    application.add_api_route(
        f"{prefix}/code-review-gold/run",
        _stub_code_review_run,
        methods=["POST"],
    )
    application.add_api_route(
        f"{prefix}/jobs/{{job_id}}",
        _get_job,
        methods=["GET"],
    )


def _wire_execution_stubs(application: FastAPI) -> None:
    """Same-file caller for method_verify."""
    register_execution_stubs(application)
