"""EVAL UI-1 — package-plane job proxy (poll/cancel + B2 enqueue).

When AIPLAT_EVAL_SERVICE_URL is set, forward to standalone :8010.
Otherwise return execution_not_migrated (cohost sync evaluate stays on other routes).
process_split_authorized stays false.
"""
from __future__ import annotations

from typing import Any, Dict, Union

from fastapi import APIRouter, Depends, Request, Response
from fastapi.responses import JSONResponse

from auth.deps import require_auth
from apps.common_schemas import ItemResponse, StatusResponse
from apps.eval.api.eval_upstream import proxy_eval_store


router = APIRouter(tags=["eval-jobs"])


def _not_migrated(*, runner_id: str, detail: str) -> JSONResponse:
    return JSONResponse(
        status_code=503,
        content={
            "error": {
                "code": "execution_not_migrated",
                "runner_id": runner_id,
                "retryable": False,
                "detail": detail,
            },
            "process_split_authorized": False,
        },
    )


@router.get("/jobs/{job_id}", response_model=ItemResponse)
async def get_eval_job(
    request: Request,
    job_id: str,
    _auth: str = Depends(require_auth),
) -> Union[Dict[str, Any], Response]:
    proxied = await proxy_eval_store(request, path=f"/jobs/{job_id}")
    if proxied is not None:
        return proxied
    return _not_migrated(
        runner_id="",
        detail="set AIPLAT_EVAL_SERVICE_URL to poll package-plane jobs",
    )


@router.post("/jobs/{job_id}/cancel", response_model=StatusResponse)
async def cancel_eval_job(
    request: Request,
    job_id: str,
    _auth: str = Depends(require_auth),
) -> Union[Dict[str, Any], Response]:
    proxied = await proxy_eval_store(request, path=f"/jobs/{job_id}/cancel")
    if proxied is not None:
        return proxied
    return _not_migrated(
        runner_id="",
        detail="set AIPLAT_EVAL_SERVICE_URL to cancel package-plane jobs",
    )


@router.post("/package/code-review-gold/run", response_model=StatusResponse)
async def package_code_review_run(
    request: Request,
    _auth: str = Depends(require_auth),
) -> Union[Dict[str, Any], Response]:
    """Enqueue B2 code_review_gold (≠ cohost POST …/evaluate)."""
    proxied = await proxy_eval_store(request, path="/code-review-gold/run")
    if proxied is not None:
        return proxied
    return _not_migrated(
        runner_id="code_review_gold",
        detail="package enqueue requires AIPLAT_EVAL_SERVICE_URL; use …/evaluate match_only on cohost",
    )


@router.post("/package/prompts/eval/runs", response_model=StatusResponse)
async def package_prompt_eval_run(
    request: Request,
    _auth: str = Depends(require_auth),
) -> Union[Dict[str, Any], Response]:
    """Enqueue B2 prompt_eval (≠ cohost POST …/prompts/eval/runs sync)."""
    proxied = await proxy_eval_store(request, path="/prompts/eval/runs")
    if proxied is not None:
        return proxied
    return _not_migrated(
        runner_id="prompt_eval",
        detail="package enqueue requires AIPLAT_EVAL_SERVICE_URL; use cohost prompts/eval/runs sync",
    )


@router.post("/package/kb-eval/run", response_model=StatusResponse)
async def package_kb_eval_run(
    request: Request,
    _auth: str = Depends(require_auth),
) -> Union[Dict[str, Any], Response]:
    """Enqueue B2 kb_rag (≠ cohost POST …/kb-eval/run sync)."""
    proxied = await proxy_eval_store(request, path="/kb-eval/run")
    if proxied is not None:
        return proxied
    return _not_migrated(
        runner_id="kb_rag",
        detail="package enqueue requires AIPLAT_EVAL_SERVICE_URL; use cohost kb-eval/run sync",
    )

