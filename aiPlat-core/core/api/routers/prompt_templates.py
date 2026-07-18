from __future__ import annotations

import difflib
import hashlib
import json
import time
import uuid
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException, Request

from core.api.deps import actor_from_http
from core.api.utils.governance import gate_error_envelope, governance_links, ui_url
from core.governance.changeset import record_changeset
from core.harness.kernel.runtime import get_kernel_runtime
from core.schemas_prompts import PromptTemplateRollbackRequest, PromptTemplateUpsertRequest
import logging

router = APIRouter()


def _rt():
    return get_kernel_runtime()


def _store():
    rt = _rt()
    return getattr(rt, "execution_store", None) if rt else None


def _approval_manager():
    rt = _rt()
    return getattr(rt, "approval_manager", None) if rt else None


def _job_scheduler():
    rt = _rt()
    return getattr(rt, "job_scheduler", None) if rt else None


def _new_change_id() -> str:
    return f"chg-{uuid.uuid4().hex[:12]}"


def _parse_prompt_metadata(tpl: Dict[str, Any]) -> Dict[str, Any]:
    md: Dict[str, Any] = {}
    if isinstance(tpl.get("metadata"), dict):
        md = tpl.get("metadata")  # type: ignore[assignment]
    elif isinstance(tpl.get("metadata_json"), str) and tpl.get("metadata_json"):
        try:
            import json as _json

            md2 = _json.loads(str(tpl.get("metadata_json") or "{}"))
            md = md2 if isinstance(md2, dict) else {}
        except Exception:
            md = {}
    return md if isinstance(md, dict) else {}


def _select_release_version(
    *,
    tpl: Dict[str, Any],
    release: Dict[str, Any],
    tenant_id: Optional[str] = None,
    user_id: Optional[str] = None,
    session_id: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Resolve an "effective" prompt template version based on release semantics:
    - pinned_version: always use this version
    - rollout: weighted list [{version, weight}], deterministic bucketing
    """
    current_version = str(tpl.get("version") or "")
    pinned = release.get("pinned_version")
    if isinstance(pinned, str) and pinned.strip():
        return {"version": pinned.strip(), "strategy": "pinned"}

    rollout = release.get("rollout") if isinstance(release.get("rollout"), list) else []
    items: list[dict[str, Any]] = []
    total = 0
    for it in rollout:
        if not isinstance(it, dict):
            continue
        v = str(it.get("version") or "").strip()
        if not v:
            continue
        try:
            w = int(it.get("weight") or 0)
        except Exception:
            w = 0
        if w <= 0:
            continue
        items.append({"version": v, "weight": w})
        total += w
    if total <= 0 or not items:
        return {"version": current_version, "strategy": "current"}

    key = str(session_id or user_id or tenant_id or "default")
    h = hashlib.sha256(key.encode("utf-8")).hexdigest()
    bucket = int(h[:8], 16) % total
    acc = 0
    for it in items:
        acc += int(it["weight"])
        if bucket < acc:
            return {
                "version": str(it["version"]),
                "strategy": "rollout",
                "bucket": bucket,
                "bucket_total": total,
                "bucket_key": key,
            }
    return {"version": current_version, "strategy": "current"}


def _is_approval_resolved_approved(approval_request_id: str) -> bool:
    mgr = _approval_manager()
    if not approval_request_id or not mgr:
        return False
    from core.harness.infrastructure.approval.types import RequestStatus

    r = mgr.get_request(str(approval_request_id))
    if not r:
        return False
    return r.status in (RequestStatus.APPROVED, RequestStatus.AUTO_APPROVED)


async def _require_onboarding_approval(*, operation: str, user_id: str, details: str, metadata: Dict[str, Any]) -> str:
    """
    Prompt templates release / write operations are global-impact changes, so by default they go through approvals.
    """
    from core.harness.infrastructure.approval.types import ApprovalContext, ApprovalRule, RuleType

    mgr = _approval_manager()
    if not mgr:
        raise HTTPException(status_code=503, detail="Approval manager not available")
    rule = ApprovalRule(
        rule_id=f"onboarding_{operation}",
        rule_type=RuleType.SENSITIVE_OPERATION,
        name=f"Onboarding {operation} 审批",
        description=f"{operation} onboarding 需要审批",
        priority=1,
        metadata={"sensitive_operations": [f"onboarding:{operation}"]},
    )
    mgr.register_rule(rule)
    ctx = ApprovalContext(
        user_id=user_id,
        operation=f"onboarding:{operation}",
        operation_context={"details": details},
        metadata=metadata or {},
    )
    req = mgr.create_request(ctx, rule=rule)
    try:
        await mgr._persist(req)  # type: ignore[attr-defined]
    except Exception as e:
        logging.warning(str(e), exc_info=True)
    return req.request_id


async def _record_changeset(
    *,
    name: str,
    target_type: str,
    target_id: str,
    status: str = "success",
    args: Dict[str, Any] | None = None,
    result: Dict[str, Any] | None = None,
    error: str | None = None,
    trace_id: str | None = None,
    run_id: str | None = None,
    user_id: str = "admin",
    session_id: str | None = None,
    approval_request_id: str | None = None,
    tenant_id: str | None = None,
) -> None:
    store = _store()
    return await record_changeset(
        store=store,
        name=name,
        target_type=target_type,
        target_id=target_id,
        status=status,
        args=args,
        result=result,
        error=error,
        trace_id=trace_id,
        run_id=run_id,
        user_id=user_id,
        session_id=session_id,
        approval_request_id=approval_request_id,
        tenant_id=tenant_id,
    )


@router.delete("/prompts/{template_id}", response_model=Dict[str, Any])
async def delete_prompt_template(
    template_id: str,
    http_request: Request,
    require_approval: bool = True,
    approval_request_id: Optional[str] = None,
    details: Optional[str] = None,
):
    store = _store()
    if not store:
        raise HTTPException(status_code=503, detail="ExecutionStore not initialized")

    change_id = _new_change_id()

    if require_approval:
        if not approval_request_id:
            rid = await _require_onboarding_approval(
                operation="prompt_template_delete",
                user_id="admin",
                details=details or f"delete prompt template {template_id}",
                metadata={"template_id": str(template_id)},
            )
            try:
                await _record_changeset(
                    name="prompt_template_delete",
                    target_type="change",
                    target_id=str(change_id),
                    status="approval_required",
                    args={"operation": "prompt_template_delete", "template_id": str(template_id)},
                    approval_request_id=rid,
                )
            except Exception as e:
                logging.warning(str(e), exc_info=True)
            return {
                "status": "approval_required",
                "approval_request_id": rid,
                "change_id": change_id,
                "links": governance_links(change_id=change_id, approval_request_id=rid),
            }
        if not _is_approval_resolved_approved(str(approval_request_id)):
            try:
                await _record_changeset(
                    name="prompt_template_delete",
                    target_type="change",
                    target_id=str(change_id),
                    status="failed",
                    args={"operation": "prompt_template_delete", "template_id": str(template_id)},
                    error="not_approved",
                    approval_request_id=str(approval_request_id),
                )
            except Exception as e:
                logging.warning(str(e), exc_info=True)
            raise HTTPException(  # noqa: error-structured
                status_code=409,
                detail=gate_error_envelope(
                    code="not_approved",
                    message="not_approved",
                    change_id=change_id,
                    approval_request_id=str(approval_request_id),
                    next_actions=[{"type": "open_approvals", "label": "打开审批中心", "url": ui_url("/core/approvals"), "approval_request_id": str(approval_request_id)}],
                ),
            )

    ok = await store.delete_prompt_template(template_id=str(template_id))
    try:
        await _record_changeset(
            name="prompt_template_delete",
            target_type="change",
            target_id=str(change_id),
            args={"operation": "prompt_template_delete", "template_id": str(template_id)},
            result={"status": "deleted" if ok else "not_found"},
            approval_request_id=str(approval_request_id) if approval_request_id else None,
        )
    except Exception as e:
        logging.warning(str(e), exc_info=True)

    # Verification: enqueue autosmoke (best-effort)
    try:
        js = _job_scheduler()
        if ok and js is not None:
            from core.harness.smoke import enqueue_autosmoke

            tenant_id = http_request.headers.get("X-AIPLAT-TENANT-ID", "ops_smoke")
            actor_id = http_request.headers.get("X-AIPLAT-ACTOR-ID", "admin")

            await enqueue_autosmoke(
                execution_store=store,
                job_scheduler=js,
                resource_type="prompt_template",
                resource_id=str(template_id),
                tenant_id=tenant_id or "ops_smoke",
                actor_id=actor_id or "admin",
                detail={"op": "prompt_template_delete", "template_id": str(template_id), "change_id": str(change_id)},
            )
    except Exception as e:
        logging.warning(str(e), exc_info=True)
    return {
        "status": "deleted" if ok else "not_found",
        "change_id": change_id,
        "approval_request_id": approval_request_id,
        "links": governance_links(change_id=change_id, approval_request_id=str(approval_request_id) if approval_request_id else None),
    }
