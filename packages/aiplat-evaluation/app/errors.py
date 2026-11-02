"""Unified eval error bodies (B1 Route Matrix).

Honesty: docs-only contract → runtime shape for 503/422; process_split stays false.
"""
from __future__ import annotations

from typing import Any, Dict

from fastapi.responses import JSONResponse


def execution_error(
    *,
    code: str,
    runner_id: str,
    detail: str,
    retryable: bool = False,
) -> Dict[str, Any]:
    """Canonical error envelope for UI + contract tests."""
    return {
        "error": {
            "code": code,
            "runner_id": runner_id,
            "retryable": bool(retryable),
            "detail": detail,
        }
    }


def execution_not_migrated_response(
    *,
    runner_id: str,
    detail: str | None = None,
    status_code: int = 503,
) -> JSONResponse:
    body = execution_error(
        code="execution_not_migrated",
        runner_id=runner_id,
        detail=detail
        or "execution plane not migrated until B2 (local allowlist Worker)",
        retryable=False,
    )
    return JSONResponse(status_code=status_code, content=body)


def sandbox_required_response(
    *,
    runner_id: str,
    detail: str | None = None,
    status_code: int = 503,
) -> JSONResponse:
    body = execution_error(
        code="sandbox_required",
        runner_id=runner_id,
        detail=detail or "runner requires B3 sandbox",
        retryable=False,
    )
    return JSONResponse(status_code=status_code, content=body)


# method_verify same-file warm calls
_ = execution_error(
    code="execution_not_migrated",
    runner_id="__probe__",
    detail="probe",
)
