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
    """获取 eval_job。

    Args:
        request: request 参数。
        job_id: job 标识。
        _auth: _auth 参数。
    """
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
    """cancel_eval_job。

    Args:
        request: request 参数。
        job_id: job 标识。
        _auth: _auth 参数。
    """
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
    """Enqueue B2 code_review_gold (≠ cohost POST …/evaluate).

    Args:
        request: request 参数。
        _auth: _auth 参数。
    """
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
    """Enqueue B2 prompt_eval (≠ cohost POST …/prompts/eval/runs sync).

    Args:
        request: request 参数。
        _auth: _auth 参数。
    """
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
    """Enqueue B2 kb_rag (≠ cohost POST …/kb-eval/run sync).

    Args:
        request: request 参数。
        _auth: _auth 参数。
    """
    proxied = await proxy_eval_store(request, path="/kb-eval/run")
    if proxied is not None:
        return proxied
    return _not_migrated(
        runner_id="kb_rag",
        detail="package enqueue requires AIPLAT_EVAL_SERVICE_URL; use cohost kb-eval/run sync",
    )


@router.post("/package/session-eval/run", response_model=StatusResponse)
async def package_session_eval_run(
    request: Request,
    _auth: str = Depends(require_auth),
) -> Union[Dict[str, Any], Response]:
    """Enqueue B2 session_eval (multi-turn fixture/live).

    Args:
        request: request 参数。
        _auth: _auth 参数。
    """
    proxied = await proxy_eval_store(request, path="/session-eval/run")
    if proxied is not None:
        return proxied
    return _not_migrated(
        runner_id="session_eval",
        detail="package enqueue requires AIPLAT_EVAL_SERVICE_URL",
    )


@router.post("/package/arena/run", response_model=StatusResponse)
async def package_arena_run(
    request: Request,
    _auth: str = Depends(require_auth),
) -> Union[Dict[str, Any], Response]:
    """Enqueue B2 arena length-smoke (≠ quality gate).

    Args:
        request: request 参数。
        _auth: _auth 参数。
    """
    proxied = await proxy_eval_store(request, path="/arena/run")
    if proxied is not None:
        return proxied
    return _not_migrated(
        runner_id="arena",
        detail="package enqueue requires AIPLAT_EVAL_SERVICE_URL",
    )


@router.post("/package/skill-evals/suites/{suite_id}/run", response_model=StatusResponse)
async def package_skill_suite_run(
    request: Request,
    suite_id: str,
    _auth: str = Depends(require_auth),
) -> Union[Dict[str, Any], Response]:
    """Enqueue skill_suite fixture (needs sandbox admit; docker for wrap).

    Args:
        request: request 参数。
        suite_id: 套件 ID。
        _auth: _auth 参数。
    """
    proxied = await proxy_eval_store(
        request, path=f"/skill-evals/suites/{suite_id}/run"
    )
    if proxied is not None:
        return proxied
    return _not_migrated(
        runner_id="skill_suite",
        detail="package enqueue requires AIPLAT_EVAL_SERVICE_URL (+ sandbox for skill_suite)",
    )


@router.post("/package/context-mgmt/run", response_model=StatusResponse)
async def package_context_mgmt_run(
    request: Request,
    _auth: str = Depends(require_auth),
) -> Union[Dict[str, Any], Response]:
    """package_context_mgmt_run。

    Args:
        request: request 参数。
        _auth: _auth 参数。
    """
    proxied = await proxy_eval_store(request, path="/context-mgmt/run")
    if proxied is not None:
        return proxied
    return _not_migrated(
        runner_id="context_mgmt",
        detail="package enqueue requires AIPLAT_EVAL_SERVICE_URL",
    )


@router.post("/package/memory-persist/run", response_model=StatusResponse)
async def package_memory_persist_run(
    request: Request,
    _auth: str = Depends(require_auth),
) -> Union[Dict[str, Any], Response]:
    """package_memory_persist_run。

    Args:
        request: request 参数。
        _auth: _auth 参数。
    """
    proxied = await proxy_eval_store(request, path="/memory-persist/run")
    if proxied is not None:
        return proxied
    return _not_migrated(
        runner_id="memory_persist",
        detail="package enqueue requires AIPLAT_EVAL_SERVICE_URL",
    )


@router.post("/package/self-learn/run", response_model=StatusResponse)
async def package_self_learn_run(
    request: Request,
    _auth: str = Depends(require_auth),
) -> Union[Dict[str, Any], Response]:
    """package_self_learn_run。

    Args:
        request: request 参数。
        _auth: _auth 参数。
    """
    proxied = await proxy_eval_store(request, path="/self-learn/run")
    if proxied is not None:
        return proxied
    return _not_migrated(
        runner_id="self_learn",
        detail="package enqueue requires AIPLAT_EVAL_SERVICE_URL",
    )

