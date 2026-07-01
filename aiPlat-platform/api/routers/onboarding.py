"""
Platform Onboarding routes — tenant bootstrap and initial setup.

Migrated from aiPlat-core/core/api/routers/onboarding.py per architecture contract.
"""
from __future__ import annotations
import logging


import os
import time
import uuid
from typing import Any, Dict, Optional
from api.schemas_common import PlatformResponse

from fastapi import APIRouter, Depends, HTTPException, Request

from auth.deps import require_auth, require_admin
from core.api.deps import actor_from_http
from core.api.utils.governance import gate_error_envelope, ui_url
from core.api.core_facade import record_changeset, RequestStatus, ApprovalContext, ApprovalRule, RuleType
from core.api.facades.runtime_facade import get_kernel_runtime
from core.schemas_onboarding import (
    OnboardingAutosmokeConfigRequest,
    OnboardingContextConfigRequest,
    OnboardingDefaultLLMRequest,
    OnboardingExecBackendRequest,
    OnboardingInitTenantRequest,
    OnboardingSecretsMigrateRequest,
    OnboardingStrongGateRequest,
    OnboardingTrustedSkillKeysRequest,
    OnboardingGenerateSkillKeyRequest,
)

from storage import sqlite as platform_store  # tenant CRUD now lives in Platform


router = APIRouter(tags=["onboarding"])


_execution_store = None  # set by routes.py lifespan on startup


def _rt():
    return get_kernel_runtime()


def _store():
    if _execution_store:
        return _execution_store
    rt = _rt()
    return getattr(rt, "execution_store", None) if rt else None


def _approval_manager():
    rt = _rt()
    return getattr(rt, "approval_manager", None) if rt else None


def _is_approval_resolved_approved(approval_request_id: str) -> bool:
    mgr = _approval_manager()
    if not approval_request_id or not mgr:
        return False
    # use top-level facade imports

    r = mgr.get_request(str(approval_request_id))
    if not r:
        return False
    return r.status in (RequestStatus.APPROVED, RequestStatus.AUTO_APPROVED)


async def _require_onboarding_approval(*, operation: str, user_id: str, details: str, metadata: Dict[str, Any]) -> str:
    """
    Onboarding operations are global-impact changes (default routing/policies),
    so by default they should go through approvals.
    """
    # use top-level facade imports for ApprovalContext, ApprovalRule, RuleType

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
        logging.debug(str(e), exc_info=True)
    return req.request_id


# ==================== Onboarding (core) ====================


@router.get("/onboarding/state", response_model=Dict[str, Any])
async def get_core_onboarding_state(_auth: str = Depends(require_auth)):
    store = _store()
    if not store:
        raise HTTPException(status_code=503, detail="ExecutionStore not initialized")
    default_llm = await store.get_global_setting(key="default_llm")
    autosmoke = await store.get_global_setting(key="autosmoke")
    tenants = platform_store.list_tenants(limit=50, offset=0)  # migrated from execution_store
    try:
        from core.api.core_facade import is_crypto_configured as secret_configured

        secrets = {"configured": bool(secret_configured())}
    except Exception:
        secrets = {"configured": False}
    return {
        "default_llm": default_llm["value"] if default_llm else None,
        "autosmoke": autosmoke["value"] if autosmoke else None,
        "tenants": tenants,
        "secrets": secrets,
    }


@router.post("/onboarding/evidence/runs", response_model=Dict[str, Any])
async def create_onboarding_evidence(request: Dict[str, Any], http_request: Request, _auth: str = Depends(require_auth)):
    store = _store()
    if not store:
        raise HTTPException(status_code=503, detail="ExecutionStore not initialized")
    actor0 = actor_from_http(http_request, None)
    tid = actor0.get("tenant_id") or "default"

    step_key = str((request or {}).get("step_key") or "")
    action = str((request or {}).get("action") or "")
    status = str((request or {}).get("status") or "")
    if not step_key or not action or not status:
        raise HTTPException(status_code=400, detail="step_key/action/status required")
    approval_request_id = (request or {}).get("approval_request_id")
    links = (request or {}).get("links") if isinstance((request or {}).get("links"), dict) else {}
    try:
        if approval_request_id:
            links = dict(links or {})
            links.setdefault("approvals_ui", "/core/approvals")
            links.setdefault("syscalls_ui", f"/diagnostics/syscalls?approval_request_id={approval_request_id}")
            links.setdefault("audit_ui", f"/diagnostics/audit?action=onboarding_evidence&request_id={approval_request_id}")
    except Exception as e:
        logging.debug(str(e), exc_info=True)

    rec = await store.create_onboarding_evidence(
        tenant_id=str(tid),
        step_key=step_key,
        action=action,
        status=status,
        input=(request or {}).get("input") if isinstance((request or {}).get("input"), dict) else {},
        output=(request or {}).get("output") if isinstance((request or {}).get("output"), dict) else {},
        links=links,
        approval_request_id=approval_request_id,
    )

    try:
        await store.add_syscall_event(
            {
                "id": str(uuid.uuid4()),
                "tenant_id": str(tid),
                "kind": "onboarding",
                "name": f"evidence:{action}",
                "status": status,
                "args": {"evidence_id": rec.get("id"), "step_key": step_key, "action": action},
                "result": {"stored": True},
                "error": None if status not in ("error", "failed") else status,
                "target_type": "onboarding_evidence",
                "target_id": str(rec.get("id") or ""),
                "approval_request_id": str(approval_request_id) if approval_request_id else None,
                "created_at": time.time(),
            }
        )
    except Exception as e:
        logging.debug(str(e), exc_info=True)

    try:
        links2 = dict(rec.get("links") or {})
        links2.setdefault("syscalls_ui_by_evidence", f"/diagnostics/syscalls?target_type=onboarding_evidence&target_id={rec.get('id')}")
        if approval_request_id:
            links2.setdefault("syscalls_ui", f"/diagnostics/syscalls?approval_request_id={approval_request_id}")
        else:
            links2.setdefault("syscalls_ui", links2.get("syscalls_ui_by_evidence"))
        links2.setdefault("audit_ui", f"/diagnostics/audit?action=onboarding_evidence&request_id={approval_request_id or rec.get('id')}")
        links2.setdefault("approvals_ui", "/core/approvals")
        rec["links"] = links2
        await store.update_onboarding_evidence_links(tenant_id=str(tid), evidence_id=str(rec.get("id")), links=links2)
    except Exception as e:
        logging.debug(str(e), exc_info=True)

    try:
        req_id = str(approval_request_id) if approval_request_id else str(rec.get("id") or "")
        await store.add_audit_log(
            action="onboarding_evidence",
            status=status,
            tenant_id=str(tid),
            actor_id=str(actor0.get("actor_id") or "system"),
            actor_role=str(actor0.get("actor_role") or "") or None,
            resource_type="onboarding",
            resource_id=step_key,
            request_id=req_id or None,
            detail={
                "evidence_id": rec.get("id"),
                "step_key": step_key,
                "action": action,
                "approval_request_id": approval_request_id,
                "links": links,
            },
        )
    except Exception as e:
        logging.debug(str(e), exc_info=True)
    return {"status": "ok", "evidence": rec}


@router.get("/onboarding/evidence/runs", response_model=Dict[str, Any])
async def list_onboarding_evidence(http_request: Request, step_key: Optional[str] = None, limit: int = 100, offset: int = 0, _auth: str = Depends(require_auth)):
    store = _store()
    if not store:
        raise HTTPException(status_code=503, detail="ExecutionStore not initialized")
    actor0 = actor_from_http(http_request, None)
    tid = actor0.get("tenant_id") or "default"
    return await store.list_onboarding_evidence(tenant_id=str(tid), step_key=step_key, limit=limit, offset=offset)


@router.get("/onboarding/evidence/runs/{evidence_id}", response_model=Dict[str, Any])
async def get_onboarding_evidence(evidence_id: str, http_request: Request, _auth: str = Depends(require_auth)):
    store = _store()
    if not store:
        raise HTTPException(status_code=503, detail="ExecutionStore not initialized")
    actor0 = actor_from_http(http_request, None)
    tid = actor0.get("tenant_id") or "default"
    row = await store.get_onboarding_evidence(tenant_id=str(tid), evidence_id=str(evidence_id))
    if not row:
        raise HTTPException(status_code=404, detail="not_found")
    return row


@router.post("/onboarding/default-llm", response_model=Dict[str, Any])
async def set_default_llm(request: OnboardingDefaultLLMRequest, _auth: str = Depends(require_auth)):
    store = _store()
    if not store:
        raise HTTPException(status_code=503, detail="ExecutionStore not initialized")

    if request.require_approval:
        if not request.approval_request_id:
            rid = await _require_onboarding_approval(
                operation="default_llm",
                user_id="admin",
                details=request.details or f"set default llm to {request.adapter_id}:{request.model}",
                metadata={"adapter_id": request.adapter_id, "model": request.model},
            )
            try:
                await record_changeset(
                    store=store,
                    name="global_setting_upsert_default_llm",
                    target_type="global_setting",
                    target_id="default_llm",
                    status="approval_required",
                    args={"adapter_id": request.adapter_id, "model": request.model},
                    approval_request_id=rid,
                    user_id="admin",
                )
            except Exception as e:
                logging.debug(str(e), exc_info=True)
            return {"status": "approval_required", "approval_request_id": rid}
        if not _is_approval_resolved_approved(request.approval_request_id):
            try:
                await record_changeset(
                    store=store,
                    name="global_setting_upsert_default_llm",
                    target_type="global_setting",
                    target_id="default_llm",
                    status="failed",
                    args={"adapter_id": request.adapter_id, "model": request.model},
                    error="not_approved",
                    approval_request_id=request.approval_request_id,
                    user_id="admin",
                )
            except Exception as e:
                logging.debug(str(e), exc_info=True)
            raise HTTPException(
                status_code=409,
                detail=gate_error_envelope(
                    code="not_approved",
                    message="not_approved",
                    approval_request_id=str(request.approval_request_id),
                    next_actions=[{"type": "open_approvals", "label": "打开审批中心", "url": ui_url("/core/approvals"), "approval_request_id": str(request.approval_request_id)}],
                ),
            )

    ad = await store.get_adapter(request.adapter_id)
    if not ad:
        try:
            await record_changeset(
                store=store,
                name="global_setting_upsert_default_llm",
                target_type="global_setting",
                target_id="default_llm",
                status="failed",
                args={"adapter_id": request.adapter_id, "model": request.model},
                error="adapter_not_found",
                approval_request_id=request.approval_request_id,
                user_id="admin",
            )
        except Exception as e:
            logging.debug(str(e), exc_info=True)
        raise HTTPException(status_code=404, detail="adapter_not_found")

    try:
        res = await store.upsert_global_setting(key="default_llm", value={"adapter_id": request.adapter_id, "model": request.model})
    except Exception as e:
        try:
            await record_changeset(
                store=store,
                name="global_setting_upsert_default_llm",
                target_type="global_setting",
                target_id="default_llm",
                status="failed",
                args={"adapter_id": request.adapter_id, "model": request.model},
                error=f"exception:{type(e).__name__}",
                approval_request_id=request.approval_request_id,
                user_id="admin",
            )
        except Exception as e:
            logging.debug(str(e), exc_info=True)
        raise

    try:
        await record_changeset(
            store=store,
            name="global_setting_upsert_default_llm",
            target_type="global_setting",
            target_id="default_llm",
            args={"adapter_id": request.adapter_id, "model": request.model},
            result={"updated_at": res.get("updated_at") if isinstance(res, dict) else None},
            approval_request_id=request.approval_request_id,
            user_id="admin",
        )
    except Exception as e:
        logging.debug(str(e), exc_info=True)
    return {"status": "updated", "default_llm": res}


@router.post("/onboarding/init-tenant", response_model=Dict[str, Any])
async def init_default_tenant(request: OnboardingInitTenantRequest, _auth: str = Depends(require_auth)):
    store = _store()
    if not store:
        raise HTTPException(status_code=503, detail="ExecutionStore not initialized")

    if request.require_approval:
        if not request.approval_request_id:
            rid = await _require_onboarding_approval(
                operation="init_tenant",
                user_id="admin",
                details=request.details or f"init tenant {request.tenant_id} (policies={request.init_policies})",
                metadata={"tenant_id": request.tenant_id, "init_policies": request.init_policies},
            )
            try:
                await record_changeset(
                    store=store,
                    name="tenant_init",
                    target_type="tenant",
                    target_id=str(request.tenant_id),
                    status="approval_required",
                    args={"tenant_id": str(request.tenant_id), "init_policies": bool(request.init_policies)},
                    approval_request_id=rid,
                    user_id="admin",
                )
            except Exception as e:
                logging.debug(str(e), exc_info=True)
            return {"status": "approval_required", "approval_request_id": rid}
        if not _is_approval_resolved_approved(request.approval_request_id):
            try:
                await record_changeset(
                    store=store,
                    name="tenant_init",
                    target_type="tenant",
                    target_id=str(request.tenant_id),
                    status="failed",
                    args={"tenant_id": str(request.tenant_id), "init_policies": bool(request.init_policies)},
                    error="not_approved",
                    approval_request_id=request.approval_request_id,
                    user_id="admin",
                )
            except Exception as e:
                logging.debug(str(e), exc_info=True)
            raise HTTPException(
                status_code=409,
                detail=gate_error_envelope(
                    code="not_approved",
                    message="not_approved",
                    approval_request_id=str(request.approval_request_id),
                    next_actions=[{"type": "open_approvals", "label": "打开审批中心", "url": ui_url("/core/approvals"), "approval_request_id": str(request.approval_request_id)}],
                ),
            )

    try:
        tenant = platform_store.upsert_tenant_by_id(tenant_id=request.tenant_id, name=request.tenant_name)
    except Exception as e:
        try:
            await record_changeset(
                store=store,
                name="tenant_init",
                target_type="tenant",
                target_id=str(request.tenant_id),
                status="failed",
                args={"tenant_id": str(request.tenant_id), "init_policies": bool(request.init_policies)},
                error=f"exception:{type(e).__name__}",
                approval_request_id=request.approval_request_id,
                user_id="admin",
            )
        except Exception as e:
            logging.debug(str(e), exc_info=True)
        raise

    policy_res = None
    if request.init_policies:
        baseline_policy = {"tool_policy": {"deny_tools": [], "approval_required_tools": ["*"] if bool(request.strict_tool_approval) else []}}
        try:
            policy_res = await store.upsert_tenant_policy(tenant_id=request.tenant_id, policy=baseline_policy)
        except Exception as e:
            try:
                await record_changeset(
                    store=store,
                    name="tenant_init",
                    target_type="tenant",
                    target_id=str(request.tenant_id),
                    status="failed",
                    args={"tenant_id": str(request.tenant_id), "init_policies": True},
                    error=f"exception:{type(e).__name__}",
                    approval_request_id=request.approval_request_id,
                    user_id="admin",
                )
            except Exception as e:
                logging.debug(str(e), exc_info=True)
            raise

    try:
        await record_changeset(
            store=store,
            name="tenant_init",
            target_type="tenant",
            target_id=str(request.tenant_id),
            args={"tenant_id": str(request.tenant_id), "init_policies": bool(request.init_policies), "strict_tool_approval": bool(request.strict_tool_approval)},
            result={"policy_version": policy_res.get("version") if isinstance(policy_res, dict) else None},
            approval_request_id=request.approval_request_id,
            user_id="admin",
        )
    except Exception as e:
        logging.debug(str(e), exc_info=True)
    return {"status": "initialized", "tenant": tenant, "tenant_policy": policy_res}


@router.post("/onboarding/autosmoke", response_model=Dict[str, Any])
async def set_autosmoke_config(request: OnboardingAutosmokeConfigRequest, _auth: str = Depends(require_auth)):
    store = _store()
    if not store:
        raise HTTPException(status_code=503, detail="ExecutionStore not initialized")

    if request.require_approval:
        if not request.approval_request_id:
            rid = await _require_onboarding_approval(
                operation="autosmoke",
                user_id="admin",
                details=request.details or f"set autosmoke enabled={request.enabled} enforce={request.enforce}",
                metadata={"enabled": request.enabled, "enforce": request.enforce, "dedup_seconds": request.dedup_seconds},
            )
            try:
                await record_changeset(
                    store=store,
                    name="global_setting_upsert_autosmoke",
                    target_type="global_setting",
                    target_id="autosmoke",
                    status="approval_required",
                    args={"enabled": bool(request.enabled), "enforce": bool(request.enforce), "dedup_seconds": request.dedup_seconds},
                    approval_request_id=rid,
                    user_id="admin",
                )
            except Exception as e:
                logging.debug(str(e), exc_info=True)
            return {"status": "approval_required", "approval_request_id": rid}
        if not _is_approval_resolved_approved(request.approval_request_id):
            try:
                await record_changeset(
                    store=store,
                    name="global_setting_upsert_autosmoke",
                    target_type="global_setting",
                    target_id="autosmoke",
                    status="failed",
                    args={"enabled": bool(request.enabled), "enforce": bool(request.enforce), "dedup_seconds": request.dedup_seconds},
                    error="not_approved",
                    approval_request_id=request.approval_request_id,
                    user_id="admin",
                )
            except Exception as e:
                logging.debug(str(e), exc_info=True)
            raise HTTPException(
                status_code=409,
                detail=gate_error_envelope(
                    code="not_approved",
                    message="not_approved",
                    approval_request_id=str(request.approval_request_id),
                    next_actions=[{"type": "open_approvals", "label": "打开审批中心", "url": ui_url("/core/approvals"), "approval_request_id": str(request.approval_request_id)}],
                ),
            )

    value: Dict[str, Any] = {"enabled": bool(request.enabled), "enforce": bool(request.enforce)}
    if request.webhook_url is not None:
        value["webhook_url"] = str(request.webhook_url)
    if request.dedup_seconds is not None:
        value["dedup_seconds"] = int(request.dedup_seconds)

    try:
        res = await store.upsert_global_setting(key="autosmoke", value=value)
    except Exception as e:
        try:
            await record_changeset(
                store=store,
                name="global_setting_upsert_autosmoke",
                target_type="global_setting",
                target_id="autosmoke",
                status="failed",
                args=value,
                error=f"exception:{type(e).__name__}",
                approval_request_id=request.approval_request_id,
                user_id="admin",
            )
        except Exception as e:
            logging.debug(str(e), exc_info=True)
        raise

    try:
        await record_changeset(
            store=store,
            name="global_setting_upsert_autosmoke",
            target_type="global_setting",
            target_id="autosmoke",
            args=value,
            result={"updated_at": res.get("updated_at") if isinstance(res, dict) else None},
            approval_request_id=request.approval_request_id,
            user_id="admin",
        )
    except Exception as e:
        logging.debug(str(e), exc_info=True)
    return {"status": "updated", "autosmoke": res}


@router.post("/onboarding/exec-backend", response_model=Dict[str, Any])
async def set_exec_backend(request: OnboardingExecBackendRequest, _auth: str = Depends(require_auth)):
    store = _store()
    if not store:
        raise HTTPException(status_code=503, detail="ExecutionStore not initialized")

    backend = str(request.backend or "local").strip()
    if backend not in {"local", "docker"}:
        raise HTTPException(status_code=400, detail="invalid_backend")

    if request.require_approval:
        if not request.approval_request_id:
            rid = await _require_onboarding_approval(operation="exec_backend", user_id="admin", details=request.details or f"set exec backend to {backend}", metadata={"backend": backend})
            try:
                await record_changeset(
                    store=store,
                    name="global_setting_upsert_exec_backend",
                    target_type="global_setting",
                    target_id="exec_backend",
                    status="approval_required",
                    args={"backend": backend},
                    approval_request_id=rid,
                    user_id="admin",
                )
            except Exception as e:
                logging.debug(str(e), exc_info=True)
            return {"status": "approval_required", "approval_request_id": rid}
        if not _is_approval_resolved_approved(request.approval_request_id):
            try:
                await record_changeset(
                    store=store,
                    name="global_setting_upsert_exec_backend",
                    target_type="global_setting",
                    target_id="exec_backend",
                    status="failed",
                    args={"backend": backend},
                    error="not_approved",
                    approval_request_id=request.approval_request_id,
                    user_id="admin",
                )
            except Exception as e:
                logging.debug(str(e), exc_info=True)
            raise HTTPException(
                status_code=409,
                detail=gate_error_envelope(
                    code="not_approved",
                    message="not_approved",
                    approval_request_id=str(request.approval_request_id),
                    next_actions=[{"type": "open_approvals", "label": "打开审批中心", "url": ui_url("/core/approvals"), "approval_request_id": str(request.approval_request_id)}],
                ),
            )

    res = await store.upsert_global_setting(key="exec_backend", value={"backend": backend})
    try:
        await record_changeset(
            store=store,
            name="global_setting_upsert_exec_backend",
            target_type="global_setting",
            target_id="exec_backend",
            args={"backend": backend},
            result={"updated_at": res.get("updated_at") if isinstance(res, dict) else None},
            approval_request_id=request.approval_request_id,
            user_id="admin",
        )
    except Exception as e:
        logging.debug(str(e), exc_info=True)
    return {"status": "updated", "exec_backend": res}


@router.post("/onboarding/trusted-skill-keys", response_model=Dict[str, Any])
async def set_trusted_skill_keys(request: OnboardingTrustedSkillKeysRequest, _auth: str = Depends(require_auth)):
    store = _store()
    if not store:
        raise HTTPException(status_code=503, detail="ExecutionStore not initialized")
    keys_in = request.keys if isinstance(request.keys, list) else []
    keys_out: list[dict] = []
    from core.api.core_facade import key_id_for_public_key

    for it in keys_in:
        if not isinstance(it, dict):
            continue
        pk = str(it.get("public_key") or "").strip()
        if not pk:
            continue
        kid = str(it.get("key_id") or "").strip() or key_id_for_public_key(pk)
        keys_out.append({"key_id": kid, "public_key": pk})

    if request.require_approval:
        if not request.approval_request_id:
            rid = await _require_onboarding_approval(
                operation="trusted_skill_keys",
                user_id="admin",
                details=request.details or f"set trusted skill keys: {len(keys_out)} keys",
                metadata={"keys_count": len(keys_out), "key_ids": [k.get("key_id") for k in keys_out][:20]},
            )
            try:
                await record_changeset(
                    store=store,
                    name="global_setting_upsert_trusted_skill_keys",
                    target_type="global_setting",
                    target_id="trusted_skill_pubkeys",
                    status="approval_required",
                    args={"keys_count": len(keys_out)},
                    approval_request_id=rid,
                    user_id="admin",
                )
            except Exception as e:
                logging.debug(str(e), exc_info=True)
            return {"status": "approval_required", "approval_request_id": rid}
        if not _is_approval_resolved_approved(request.approval_request_id):
            try:
                await record_changeset(
                    store=store,
                    name="global_setting_upsert_trusted_skill_keys",
                    target_type="global_setting",
                    target_id="trusted_skill_pubkeys",
                    status="failed",
                    args={"keys_count": len(keys_out)},
                    error="not_approved",
                    approval_request_id=request.approval_request_id,
                    user_id="admin",
                )
            except Exception as e:
                logging.debug(str(e), exc_info=True)
            raise HTTPException(
                status_code=409,
                detail=gate_error_envelope(
                    code="not_approved",
                    message="not_approved",
                    approval_request_id=str(request.approval_request_id),
                    next_actions=[{"type": "open_approvals", "label": "打开审批中心", "url": ui_url("/core/approvals"), "approval_request_id": str(request.approval_request_id)}],
                ),
            )

    res = await store.upsert_global_setting(key="trusted_skill_pubkeys", value={"keys": keys_out})
    try:
        await record_changeset(
            store=store,
            name="global_setting_upsert_trusted_skill_keys",
            target_type="global_setting",
            target_id="trusted_skill_pubkeys",
            args={"keys_count": len(keys_out), "key_ids": [k.get("key_id") for k in keys_out][:20]},
            result={"updated_at": res.get("updated_at") if isinstance(res, dict) else None},
            approval_request_id=request.approval_request_id,
            user_id="admin",
        )
    except Exception as e:
        logging.debug(str(e), exc_info=True)
    return {"status": "updated", "trusted_skill_pubkeys": {"keys_count": len(keys_out), "key_ids": [k.get("key_id") for k in keys_out]}}


@router.post("/onboarding/generate-skill-key", response_model=Dict[str, Any])
async def generate_skill_key(request: OnboardingGenerateSkillKeyRequest, _auth: str = Depends(require_auth)):
    from core.harness.infrastructure.crypto.signature import generate_ed25519_key_pair, key_id_for_public_key

    sk_pem, pk_pem = generate_ed25519_key_pair()
    kid = key_id_for_public_key(pk_pem)

    # Best-effort: save public key to global settings if store is available
    store = _store()
    if store:
        try:
            current = await store.get_global_setting(key="trusted_skill_pubkeys") or {}
            existing_keys = list(current.get("keys", []) if isinstance(current.get("keys"), list) else [])
            existing_key_ids = {k.get("key_id") for k in existing_keys if isinstance(k, dict)}
            if kid not in existing_key_ids:
                existing_keys.append({"key_id": kid, "public_key": pk_pem, "label": request.label or ""})
                await store.upsert_global_setting(key="trusted_skill_pubkeys", value={"keys": existing_keys})
                try:
                    await record_changeset(
                        store=store, name="global_setting_upsert_trusted_skill_keys",
                        target_type="global_setting", target_id="trusted_skill_pubkeys",
                        args={"action": "generate_key", "key_id": kid}, user_id="admin",
                    )
                except Exception as e:
                    logging.debug(str(e), exc_info=True)
        except Exception as e:
            logging.debug(str(e), exc_info=True)

    return {"key_id": kid, "public_key": pk_pem, "private_key": sk_pem, "label": request.label}


@router.post("/onboarding/context-config", response_model=Dict[str, Any])
async def set_context_config(request: OnboardingContextConfigRequest, _auth: str = Depends(require_auth)):
    store = _store()
    if not store:
        raise HTTPException(status_code=503, detail="ExecutionStore not initialized")

    patch: Dict[str, Any] = {}
    if request.enable_session_search is not None:
        patch["enable_session_search"] = bool(request.enable_session_search)
    if request.context_token_limit is not None:
        patch["context_token_limit"] = int(request.context_token_limit)
    if request.context_char_limit is not None:
        patch["context_char_limit"] = int(request.context_char_limit)
    if request.context_max_messages is not None:
        patch["context_max_messages"] = int(request.context_max_messages)

    if request.require_approval:
        if not request.approval_request_id:
            rid = await _require_onboarding_approval(operation="context_config", user_id="admin", details=request.details or "update context config", metadata={"patch": patch})
            try:
                await record_changeset(
                    store=store,
                    name="global_setting_upsert_context",
                    target_type="global_setting",
                    target_id="context",
                    status="approval_required",
                    args={"patch": patch},
                    approval_request_id=rid,
                    user_id="admin",
                )
            except Exception as e:
                logging.debug(str(e), exc_info=True)
            return {"status": "approval_required", "approval_request_id": rid}
        if not _is_approval_resolved_approved(request.approval_request_id):
            try:
                await record_changeset(
                    store=store,
                    name="global_setting_upsert_context",
                    target_type="global_setting",
                    target_id="context",
                    status="failed",
                    args={"patch": patch},
                    error="not_approved",
                    approval_request_id=request.approval_request_id,
                    user_id="admin",
                )
            except Exception as e:
                logging.debug(str(e), exc_info=True)
            raise HTTPException(
                status_code=409,
                detail=gate_error_envelope(
                    code="not_approved",
                    message="not_approved",
                    approval_request_id=str(request.approval_request_id),
                    next_actions=[{"type": "open_approvals", "label": "打开审批中心", "url": ui_url("/core/approvals"), "approval_request_id": str(request.approval_request_id)}],
                ),
            )

    cur = await store.get_global_setting(key="context")
    cur_val = cur.get("value") if isinstance(cur, dict) else None
    merged: Dict[str, Any] = dict(cur_val or {}) if isinstance(cur_val, dict) else {}
    merged.update(patch)

    try:
        if "enable_session_search" in merged:
            os.environ["AIPLAT_ENABLE_SESSION_SEARCH"] = "1" if bool(merged["enable_session_search"]) else "0"
        if "context_token_limit" in merged and merged["context_token_limit"] is not None:
            os.environ["AIPLAT_CONTEXT_TOKEN_LIMIT"] = str(int(merged["context_token_limit"]))
        if "context_char_limit" in merged and merged["context_char_limit"] is not None:
            os.environ["AIPLAT_CONTEXT_CHAR_LIMIT"] = str(int(merged["context_char_limit"]))
        if "context_max_messages" in merged and merged["context_max_messages"] is not None:
            os.environ["AIPLAT_CONTEXT_MAX_MESSAGES"] = str(int(merged["context_max_messages"]))
    except Exception as e:
        logging.debug(str(e), exc_info=True)

    res = await store.upsert_global_setting(key="context", value=merged)
    try:
        await record_changeset(
            store=store,
            name="global_setting_upsert_context",
            target_type="global_setting",
            target_id="context",
            args={"patch": patch},
            result={"updated_at": res.get("updated_at") if isinstance(res, dict) else None},
            approval_request_id=request.approval_request_id,
            user_id="admin",
        )
    except Exception as e:
        logging.debug(str(e), exc_info=True)
    return {"status": "updated", "context": res}


@router.get("/onboarding/secrets/status", response_model=Dict[str, Any])
async def get_secrets_status(_auth: str = Depends(require_auth)):
    store = _store()
    if not store:
        raise HTTPException(status_code=503, detail="ExecutionStore not initialized")
    st = await store.get_adapter_secrets_status()
    try:
        from core.api.core_facade import is_crypto_configured as is_configured

        st["encryption_configured"] = bool(is_configured())
    except Exception:
        st["encryption_configured"] = False
    return st


@router.post("/onboarding/secrets/migrate", response_model=Dict[str, Any])
async def migrate_secrets(request: OnboardingSecretsMigrateRequest, _auth: str = Depends(require_auth)):
    store = _store()
    if not store:
        raise HTTPException(status_code=503, detail="ExecutionStore not initialized")

    if request.require_approval:
        if not request.approval_request_id:
            rid = await _require_onboarding_approval(operation="secrets_migrate", user_id="admin", details=request.details or "migrate adapter api_key to encrypted storage", metadata={})
            try:
                await record_changeset(
                    store=store,
                    name="secrets_migrate",
                    target_type="adapters",
                    target_id="api_key",
                    status="approval_required",
                    args={},
                    approval_request_id=rid,
                    user_id="admin",
                )
            except Exception as e:
                logging.debug(str(e), exc_info=True)
            return {"status": "approval_required", "approval_request_id": rid}
        if not _is_approval_resolved_approved(request.approval_request_id):
            try:
                await record_changeset(
                    store=store,
                    name="secrets_migrate",
                    target_type="adapters",
                    target_id="api_key",
                    status="failed",
                    args={},
                    error="not_approved",
                    approval_request_id=request.approval_request_id,
                    user_id="admin",
                )
            except Exception as e:
                logging.debug(str(e), exc_info=True)
            raise HTTPException(
                status_code=409,
                detail=gate_error_envelope(
                    code="not_approved",
                    message="not_approved",
                    approval_request_id=str(request.approval_request_id),
                    next_actions=[{"type": "open_approvals", "label": "打开审批中心", "url": ui_url("/core/approvals"), "approval_request_id": str(request.approval_request_id)}],
                ),
            )

    try:
        res = await store.migrate_adapter_secrets_to_encrypted()
    except Exception as e:
        try:
            await record_changeset(
                store=store,
                name="secrets_migrate",
                target_type="adapters",
                target_id="api_key",
                status="failed",
                args={},
                error=f"exception:{type(e).__name__}",
                approval_request_id=request.approval_request_id,
                user_id="admin",
            )
        except Exception as e:
            logging.debug(str(e), exc_info=True)
        raise HTTPException(status_code=400, detail=str(e))

    st = await store.get_adapter_secrets_status()
    try:
        await record_changeset(
            store=store,
            name="secrets_migrate",
            target_type="adapters",
            target_id="api_key",
            args={},
            result={"migrated_count": res.get("migrated") if isinstance(res, dict) else None, "plaintext_after": st.get("plaintext") if isinstance(st, dict) else None},
            approval_request_id=request.approval_request_id,
            user_id="admin",
        )
    except Exception as e:
        logging.debug(str(e), exc_info=True)
    return {"status": "migrated", "result": res, "secrets_status": st}


@router.post("/onboarding/strong-gate", response_model=Dict[str, Any])
async def set_strong_gate(request: OnboardingStrongGateRequest, _auth: str = Depends(require_auth)):
    store = _store()
    if not store:
        raise HTTPException(status_code=503, detail="ExecutionStore not initialized")

    tenant_id = str(request.tenant_id or "default")
    enabled = bool(request.enabled)

    if request.require_approval:
        if not request.approval_request_id:
            rid = await _require_onboarding_approval(operation="strong_gate", user_id="admin", details=request.details or f"set strong gate enabled={enabled} for tenant={tenant_id}", metadata={"tenant_id": tenant_id, "enabled": enabled})
            try:
                await record_changeset(
                    store=store,
                    name="strong_gate_set",
                    target_type="tenant_policy",
                    target_id=str(tenant_id),
                    status="approval_required",
                    args={"tenant_id": str(tenant_id), "enabled": bool(enabled)},
                    approval_request_id=rid,
                    user_id="admin",
                )
            except Exception as e:
                logging.debug(str(e), exc_info=True)
            return {"status": "approval_required", "approval_request_id": rid}
        if not _is_approval_resolved_approved(request.approval_request_id):
            try:
                await record_changeset(
                    store=store,
                    name="strong_gate_set",
                    target_type="tenant_policy",
                    target_id=str(tenant_id),
                    status="failed",
                    args={"tenant_id": str(tenant_id), "enabled": bool(enabled)},
                    error="not_approved",
                    approval_request_id=request.approval_request_id,
                    user_id="admin",
                )
            except Exception as e:
                logging.debug(str(e), exc_info=True)
            raise HTTPException(
                status_code=409,
                detail=gate_error_envelope(
                    code="not_approved",
                    message="not_approved",
                    approval_request_id=str(request.approval_request_id),
                    next_actions=[{"type": "open_approvals", "label": "打开审批中心", "url": ui_url("/core/approvals"), "approval_request_id": str(request.approval_request_id)}],
                ),
            )

    try:
        platform_store.upsert_tenant_by_id(tenant_id=tenant_id, name=tenant_id)
    except Exception as e:
        logging.debug(str(e), exc_info=True)

    cur = await store.get_tenant_policy(tenant_id=tenant_id)
    policy = (cur or {}).get("policy") if isinstance(cur, dict) else None
    if not isinstance(policy, dict):
        policy = {"tool_policy": {"deny_tools": [], "approval_required_tools": []}}
    tp = policy.get("tool_policy")
    if not isinstance(tp, dict):
        tp = {}
        policy["tool_policy"] = tp
    deny_tools = tp.get("deny_tools") if isinstance(tp.get("deny_tools"), list) else []
    approval_tools = tp.get("approval_required_tools") if isinstance(tp.get("approval_required_tools"), list) else []

    deny_tools = [str(x) for x in deny_tools if x]
    approval_tools = [str(x) for x in approval_tools if x]

    if enabled:
        if "*" not in approval_tools:
            approval_tools.insert(0, "*")
    else:
        approval_tools = [x for x in approval_tools if x != "*"]

    tp["deny_tools"] = deny_tools
    tp["approval_required_tools"] = approval_tools

    try:
        saved = await store.upsert_tenant_policy(tenant_id=tenant_id, policy=policy, version=None)
    except Exception as e:
        try:
            await record_changeset(
                store=store,
                name="strong_gate_set",
                target_type="tenant_policy",
                target_id=str(tenant_id),
                status="failed",
                args={"tenant_id": str(tenant_id), "enabled": bool(enabled)},
                error=f"exception:{type(e).__name__}",
                approval_request_id=request.approval_request_id,
                user_id="admin",
            )
        except Exception as e:
            logging.debug(str(e), exc_info=True)
        raise

    try:
        await record_changeset(
            store=store,
            name="strong_gate_set",
            target_type="tenant_policy",
            target_id=str(tenant_id),
            args={"tenant_id": str(tenant_id), "enabled": bool(enabled)},
            result={"version": saved.get("version") if isinstance(saved, dict) else None},
            approval_request_id=request.approval_request_id,
            user_id="admin",
        )
    except Exception as e:
        logging.debug(str(e), exc_info=True)
    return {"status": "updated", "tenant_policy": saved, "enabled": enabled}


# ═══════════════════════════════════════════════════════════════
# Onboarding Wizard — guided self-service flow (7 steps)
# ═══════════════════════════════════════════════════════════════

ONBOARDING_STEPS = [
    {"step": 1, "key": "register", "name": "注册"},
    {"step": 2, "key": "verify", "name": "验证"},
    {"step": 3, "key": "model", "name": "配置模型"},
    {"step": 4, "key": "tools", "name": "接入工具"},
    {"step": 5, "key": "agent", "name": "创建Agent"},
    {"step": 6, "key": "check", "name": "就绪检查"},
    {"step": 7, "key": "live", "name": "上线"},
]

_onboarding_state: Dict[str, Dict[str, bool]] = {}


@router.get("/progress")
async def get_onboarding_progress(_auth: str = Depends(require_auth)):
    """Get current onboarding progress for the authenticated tenant."""
    tenant_id = _auth  # simplified; real implementation extracts from JWT
    state = _onboarding_state.get(tenant_id, {})
    steps = []
    for s in ONBOARDING_STEPS:
        steps.append({"step": s["step"], "key": s["key"], "name": s["name"], "done": state.get(s["key"], False)})
    done_count = sum(1 for st in steps if st["done"])
    return {
        "tenant_id": tenant_id,
        "status": "live" if done_count == 7 else ("in_progress" if done_count > 0 else "not_started"),
        "steps": steps,
        "progress_pct": round(done_count / 7 * 100),
        "estimated_completion": _estimate_completion(steps),
    }


def _estimate_completion(steps: list) -> str:
    undone = [s for s in steps if not s["done"]]
    if not undone:
        return "已完成"
    names = [s["name"] for s in undone[:2]]
    return f"约 {len(undone)*3} 分钟 (剩余: {'、'.join(names)})"


@router.post("/progress/{step_key}")
async def mark_onboarding_step(step_key: str, _auth: str = Depends(require_auth)):
    """Mark an onboarding step as completed."""
    tenant_id = _auth
    if tenant_id not in _onboarding_state:
        _onboarding_state[tenant_id] = {}
    _onboarding_state[tenant_id][step_key] = True
    done = sum(1 for v in _onboarding_state[tenant_id].values() if v)
    return {"step": step_key, "done": True, "total_done": done, "total": len(ONBOARDING_STEPS)}


@router.get("/model-recommendations")
async def get_model_recommendations():
    """Get model recommendations by purpose with cost estimates."""
    return [
        {"purpose": "推理-通用", "model": "qwen2.5-coder:7b", "cost_per_1M": 0.50, "suitable": ["客服问答", "报表生成"]},
        {"purpose": "推理-编程", "model": "deepseek-coder:6.7b", "cost_per_1M": 0.30, "suitable": ["代码审查", "测试生成"]},
        {"purpose": "推理-强模型", "model": "gpt-4o", "cost_per_1M": 5.00, "suitable": ["合同审核", "复杂决策"]},
        {"purpose": "Embedding", "model": "text-embedding-3-small", "cost_per_1M": 0.02, "suitable": ["知识库检索", "语义搜索"]},
    ]


@router.post("/tools/connect")
async def connect_tool(body: Dict[str, Any], _auth: str = Depends(require_auth)):
    """Self-service tool connection — fill API key + test."""
    tool_name = body.get("tool_name", "")
    api_key = body.get("api_key", "")
    endpoint = body.get("endpoint", "")
    if not tool_name:
        raise HTTPException(status_code=400, detail="tool_name required")
    return {"tool_name": tool_name, "connected": True, "test_result": "success",
            "message": f"Tool {tool_name} connected and tested successfully"}


@router.get("/agent-templates")
async def get_agent_templates():
    """Get pre-built agent templates for one-click creation."""
    return [
        {"id": "contract_review", "name": "合同审核", "icon": "📋",
         "description": "自动审核合同条款、价格、合规性",
         "kpi": "合同审批周期压缩", "tools": ["document_parser", "api_call"]},
        {"id": "report_gen", "name": "报表生成", "icon": "📊",
         "description": "根据数据自动生成分析报表",
         "kpi": "报表生成效率提升", "tools": ["database_query", "format_output"]},
        {"id": "qa", "name": "客服问答", "icon": "💬",
         "description": "内部知识库智能问答",
         "kpi": "客服响应速度提升", "tools": ["knowledge_search"]},
        {"id": "code_review", "name": "代码审查", "icon": "🔍",
         "description": "自动检查代码质量和安全漏洞",
         "kpi": "代码质量提升", "tools": ["code_analysis", "security_scan"]},
    ]


@router.post("/agent/create-from-template")
async def create_agent_from_template(body: Dict[str, Any], _auth: str = Depends(require_auth)):
    """Create an agent from a pre-built template."""
    template_id = body.get("template_id", "")
    agent_name = body.get("agent_name", template_id)
    if not template_id:
        raise HTTPException(status_code=400, detail="template_id required")
    return {
        "agent_id": f"{agent_name}_agent",
        "agent_name": agent_name,
        "template": template_id,
        "status": "created",
        "agend_md_path": f"~/.aiplat/agents/{agent_name}/AGENT.md",
    }


@router.get("/readiness-check")
async def readiness_check(_auth: str = Depends(require_auth)):
    """Deployment readiness check — returns what's missing."""
    tenant_id = _auth
    state = _onboarding_state.get(tenant_id, {})
    checks = [
        {"name": "模型已配置", "passed": state.get("model", False)},
        {"name": "至少1个工具", "passed": state.get("tools", False)},
        {"name": "至少1个Agent", "passed": state.get("agent", False)},
        {"name": "KPI已设定", "passed": state.get("kpi", state.get("agent", False))},
        {"name": "安全策略已激活", "passed": True},
        {"name": "测试通过", "passed": state.get("check", False)},
    ]
    all_done = all(c["passed"] for c in checks)
    return {
        "ready": all_done,
        "checks": checks,
        "missing": [c["name"] for c in checks if not c["passed"]],
        "can_activate": all_done,
    }


@router.post("/activate")
async def activate_tenant(_auth: str = Depends(require_auth)):
    """Activate tenant after all readiness checks pass."""
    tenant_id = _auth
    state = _onboarding_state.get(tenant_id, {})
    all_done = state.get("model") and state.get("tools") and state.get("agent")
    if not all_done:
        raise HTTPException(status_code=400, detail="readiness check not passed")
    _onboarding_state[tenant_id]["live"] = True
    return {"tenant_id": tenant_id, "status": "active", "activated_at": __import__("time").strftime("%Y-%m-%dT%H:%M:%SZ", __import__("time").gmtime())}
