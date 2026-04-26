from __future__ import annotations

from typing import Any, Dict, Optional

from core.schemas import RunStatus
from core.utils.ids import new_prefixed_id


def normalize_run_status_v2(*, ok: bool, legacy_status: Optional[str], error_code: Optional[str]) -> str:
    s = str(legacy_status or "").lower().strip()
    c = str(error_code or "").upper().strip()
    if s in {"accepted", "queued"}:
        return RunStatus.accepted.value
    if s in {"running"}:
        return RunStatus.running.value
    if s in {"approval_required", "waiting_approval"} or c == "APPROVAL_REQUIRED":
        return RunStatus.waiting_approval.value
    if s in {"timeout"} or c == "TIMEOUT":
        return RunStatus.timeout.value
    if ok:
        return RunStatus.completed.value
    if s in {"publish_required", "blocked"} or c == "PUBLISH_REQUIRED":
        return RunStatus.aborted.value
    if s in {"aborted"}:
        return RunStatus.aborted.value
    return RunStatus.failed.value


def normalize_run_error(*, code: Optional[str], message: Optional[str], detail: Optional[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    if not code and not message and not detail:
        return None
    return {"code": str(code or "EXECUTION_FAILED"), "message": str(message or "Execution failed"), "detail": detail or None}


def wrap_execution_result_as_run_summary(result: Any) -> Dict[str, Any]:
    """
    PR-02: Run Contract v2
    Return: {ok, run_id, trace_id, status, output, error{code,message,detail}, ...legacy fields...}
    """
    payload = dict(getattr(result, "payload", None) or {}) if isinstance(getattr(result, "payload", None), dict) else {}
    ok0 = bool(getattr(result, "ok", False))
    if payload.get("ok") is False:
        ok0 = False
    legacy_status = payload.get("status")
    # Backward compatibility: some execution paths always return ok=True but use status to signal failure.
    try:
        if isinstance(legacy_status, str) and legacy_status.lower().strip() in {
            "failed",
            "waiting_approval",
            "approval_required",
            "policy_denied",
            "aborted",
            "timeout",
        }:
            ok0 = False
    except Exception:
        pass
    run_id = (
        getattr(result, "run_id", None)
        or payload.get("run_id")
        or payload.get("execution_id")
        or payload.get("executionId")
        or new_prefixed_id("run")
    )
    trace_id = getattr(result, "trace_id", None) or payload.get("trace_id")

    err_detail = getattr(result, "error_detail", None) if isinstance(getattr(result, "error_detail", None), dict) else None
    err_obj = payload.get("error") if isinstance(payload.get("error"), dict) else None
    err_code = None
    err_msg = None
    if isinstance(err_obj, dict):
        err_code = err_obj.get("code")
        err_msg = err_obj.get("message")
        err_detail = err_obj.get("detail") if isinstance(err_obj.get("detail"), dict) else (err_detail or None)
    else:
        err_code = payload.get("error_code") or (err_detail or {}).get("code") if isinstance(err_detail, dict) else None
        err_msg = payload.get("error_message") or (err_detail or {}).get("message") if isinstance(err_detail, dict) else None
        if not err_msg:
            err_msg = getattr(result, "error", None)

    run_status = normalize_run_status_v2(ok=ok0, legacy_status=legacy_status, error_code=err_code)
    out = dict(payload)
    out.setdefault("legacy_status", legacy_status)
    out["ok"] = ok0
    out["run_id"] = str(run_id)
    out["trace_id"] = trace_id
    out["status"] = run_status
    out["output"] = payload.get("output")
    out["error"] = None if ok0 else normalize_run_error(code=err_code, message=err_msg, detail=err_detail)
    if not ok0:
        out.setdefault("error_detail", out.get("error"))
        out.setdefault("error_message", (out.get("error") or {}).get("message") if isinstance(out.get("error"), dict) else None)
        out.setdefault("error_code", (out.get("error") or {}).get("code") if isinstance(out.get("error"), dict) else None)
    return out
