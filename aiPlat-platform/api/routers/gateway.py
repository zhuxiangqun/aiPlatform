"""
Platform Gateway routes — unified execution entry, pairing/token management, DLQ.

Migrated from aiPlat-core/core/api/routers/gateway.py per architecture contract:
API gateway management belongs in platform layer (docs/index.md §Layer 2).
"""

from __future__ import annotations
import logging

import os
from typing import Any, Dict, Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import JSONResponse

from core.api.deps import actor_from_http, rbac_guard
from core.api.utils.run_contract import normalize_run_status_v2
from core.api.facades.runtime_facade import KernelRuntime, ExecutionRequest, get_kernel_runtime
from core.schemas_gateway import GatewayExecuteRequest
from core.schemas_run import RunStatus
from core.utils.ids import new_prefixed_id

router = APIRouter(prefix="/platform/gateway", tags=["gateway"])

RuntimeDep = Optional[KernelRuntime]


def _store(rt: RuntimeDep):
    return getattr(rt, "execution_store", None) if rt else None


def _harness(rt: RuntimeDep):
    # Prefer runtime-provided harness (makes tests + multi-runtime setups deterministic).
    if rt is not None and getattr(rt, "harness", None) is not None:
        return getattr(rt, "harness")
    from core.api.core_facade import get_harness
    return get_harness()


def _require_gateway_admin(http_request: Request) -> None:
    """
    Optional admin guard for gateway management endpoints.
    If AIPLAT_GATEWAY_ADMIN_TOKEN is set, callers must provide X-AiPlat-Admin-Token.
    """
    admin = os.environ.get("AIPLAT_GATEWAY_ADMIN_TOKEN")
    if not admin:
        return
    got = http_request.headers.get("x-aiplat-admin-token") or http_request.headers.get("X-AiPlat-Admin-Token")
    if not got or got != admin:
        raise HTTPException(status_code=403, detail="admin token required")


@router.post("/gateway/execute", response_model=StatusResponse)
async def gateway_execute(request: GatewayExecuteRequest, http_request: Request, rt: RuntimeDep = Depends(get_kernel_runtime)):
    """
    Unified external entry for multi-channel integrations.

    This endpoint is intentionally thin: it reuses HarnessIntegration.execute()
    so that toolset / approvals / tracing policies apply consistently.
    """
    harness = _harness(rt)
    store = _store(rt)

    payload = dict(request.payload or {})
    if request.options is not None:
        try:
            payload.setdefault("options", request.options)
        except Exception as e:
            logging.warning(str(e), exc_info=True)

    # Inject channel context for observability.
    try:
        ctx = payload.get("context") if isinstance(payload.get("context"), dict) else {}
        ctx = dict(ctx) if isinstance(ctx, dict) else {}
        ctx.setdefault("source", "gateway")
        ctx.setdefault("entrypoint", "gateway")
        ctx.setdefault("channel", request.channel)
        if request.tenant_id:
            ctx.setdefault("tenant_id", str(request.tenant_id))
        else:
            # Allow tenant_id to come from header when client doesn't send it in body.
            h_tenant = http_request.headers.get("X-AIPLAT-TENANT-ID") or http_request.headers.get("x-aiplat-tenant-id")
            if h_tenant:
                ctx.setdefault("tenant_id", str(h_tenant))
        # platform identity passthrough (optional)
        try:
            actor_id = http_request.headers.get("X-AIPLAT-ACTOR-ID") or http_request.headers.get("x-aiplat-actor-id")
            actor_role = http_request.headers.get("X-AIPLAT-ACTOR-ROLE") or http_request.headers.get("x-aiplat-actor-role")
            if actor_id:
                ctx.setdefault("actor_id", str(actor_id))
            if actor_role:
                ctx.setdefault("actor_role", str(actor_role))
        except Exception as e:
            logging.warning(str(e), exc_info=True)
        # preserve external identity if present
        if request.channel_user_id:
            ctx.setdefault("channel_user_id", request.channel_user_id)
        payload["context"] = ctx
    except Exception as e:
        logging.warning(str(e), exc_info=True)

    deny = await rbac_guard(http_request=http_request, payload=payload, action="execute", resource_type="gateway", resource_id=str(request.target_id))
    if deny:
        return deny

    # Optional auth (Roadmap-3): require token when configured.
    if os.getenv("AIPLAT_GATEWAY_REQUIRE_AUTH", "false").lower() in ("1", "true", "yes", "y"):
        token = http_request.headers.get("x-aiplat-gateway-token") or http_request.headers.get("X-AiPlat-Gateway-Token")
        if not token:
            raise HTTPException(status_code=401, detail="missing gateway token")
        ok = False
        if os.getenv("AIPLAT_GATEWAY_TOKEN") and token == os.getenv("AIPLAT_GATEWAY_TOKEN"):
            ok = True
        elif store:
            try:
                ok = (await store.validate_gateway_token(token=token)) is not None
            except Exception:
                ok = False
        if not ok:
            raise HTTPException(status_code=403, detail="invalid gateway token")

    # Pairing resolution: if user_id/session_id not provided, resolve using (channel, channel_user_id).
    resolved_user = request.user_id
    resolved_session = request.session_id
    resolved_tenant = request.tenant_id
    channel_user_id = (
        request.channel_user_id
        or (payload.get("channel_user_id") if isinstance(payload, dict) else None)
        or (payload.get("sender_id") if isinstance(payload, dict) else None)
        or ((payload.get("context") or {}).get("channel_user_id") if isinstance(payload.get("context"), dict) else None)
    )
    if store and (not resolved_user or not resolved_session) and channel_user_id:
        try:
            pairing = await store.resolve_gateway_pairing(channel=request.channel, channel_user_id=str(channel_user_id))
        except Exception:
            pairing = None
        if pairing:
            resolved_user = resolved_user or pairing.get("user_id")
            resolved_session = resolved_session or pairing.get("session_id")
            resolved_tenant = resolved_tenant or pairing.get("tenant_id")
            # enrich context for observability
            try:
                ctx = payload.get("context") if isinstance(payload.get("context"), dict) else {}
                ctx = dict(ctx) if isinstance(ctx, dict) else {}
                ctx.setdefault("pairing_id", pairing.get("id"))
                if pairing.get("tenant_id"):
                    ctx.setdefault("tenant_id", pairing.get("tenant_id"))
                payload["context"] = ctx
            except Exception as e:
                logging.warning(str(e), exc_info=True)

    # Platform contract: idempotency key from platform (recommended).
    request_id = (
        http_request.headers.get("x-aiplat-request-id")
        or http_request.headers.get("X-AiPlat-Request-Id")
        or http_request.headers.get("X-AIPLAT-REQUEST-ID")
    )
    request_id = str(request_id).strip() if isinstance(request_id, str) else None
    if not request_id:
        request_id = new_prefixed_id("req")
    # surface request_id into payload.context for downstream syscalls/audit
    try:
        if isinstance(payload, dict):
            ctx = payload.get("context") if isinstance(payload.get("context"), dict) else {}
            ctx = dict(ctx) if isinstance(ctx, dict) else {}
            ctx.setdefault("request_id", str(request_id))
            payload["context"] = ctx
    except Exception as e:
        logging.warning(str(e), exc_info=True)

    reserved_run_id = None
    if store and request_id:
        try:
            existing_run_id = await store.get_run_id_for_request(
                request_id=request_id, tenant_id=str(resolved_tenant) if resolved_tenant else None
            )
        except Exception:
            existing_run_id = None
        if existing_run_id:
            run = await store.get_run_summary(run_id=str(existing_run_id))
            try:
                await store.add_audit_log(
                    action="gateway_execute_dedup",
                    status="ok",
                    tenant_id=str(resolved_tenant) if resolved_tenant else None,
                    actor_id=str(resolved_user) if resolved_user else None,
                    resource_type="run",
                    resource_id=str(existing_run_id),
                    request_id=request_id,
                    run_id=str(existing_run_id),
                    trace_id=(run or {}).get("trace_id"),
                    detail={"channel": request.channel, "kind": request.kind, "target_id": request.target_id},
                )
            except Exception as e:
                logging.warning(str(e), exc_info=True)
            return {
                "ok": True,
                "status": RunStatus.completed.value,
                "legacy_status": "deduped",
                "request_id": request_id,
                "run_id": str(existing_run_id),
                "trace_id": (run or {}).get("trace_id"),
                "run": run,
            }
        # Reserve a run_id so upstream retries can dedupe immediately.
        reserved_run_id = new_prefixed_id("run")
        try:
            await store.remember_request_run_id(
                request_id=request_id,
                run_id=reserved_run_id,
                tenant_id=str(resolved_tenant) if resolved_tenant else None,
            )
        except Exception as e:
            logging.warning(str(e), exc_info=True)

    exec_req = ExecutionRequest(
        kind=str(request.kind) if request.kind else "agent",  # type: ignore[arg-type]
        target_id=str(request.target_id),
        payload=payload,
        user_id=str(resolved_user or "system"),
        session_id=str(resolved_session or "default"),
        request_id=request_id,
        run_id=reserved_run_id,
    )
    result = await harness.execute(exec_req)
    # Best-effort ensure request_id mapping exists even if reservation was skipped.
    if store and request_id and result.run_id:
        try:
            await store.remember_request_run_id(
                request_id=request_id,
                run_id=str(result.run_id),
                tenant_id=str(resolved_tenant) if resolved_tenant else None,
            )
        except Exception as e:
            logging.warning(str(e), exc_info=True)

    # Audit (best-effort)
    try:
        actor0 = actor_from_http(http_request, payload)
        if store:
            await store.add_audit_log(
                action="gateway_execute",
                status="ok" if result.ok else "failed",
                tenant_id=str(resolved_tenant) if resolved_tenant else (str(actor0.get("tenant_id") or "") or None),
                actor_id=str(resolved_user) if resolved_user else (str(actor0.get("actor_id") or "") or None),
                actor_role=str(actor0.get("actor_role") or "") or None,
                resource_type=str(request.kind or "agent"),
                resource_id=str(request.target_id),
                request_id=request_id,
                run_id=str(result.run_id) if result.run_id else reserved_run_id,
                trace_id=str(result.trace_id) if result.trace_id else None,
                detail={"channel": request.channel, "channel_user_id": request.channel_user_id},
            )
    except Exception as e:
        logging.warning(str(e), exc_info=True)

    # Normalize: always include trace_id/run_id.
    resp = dict(result.payload or {})
    # Prefer payload status for ok semantics (agent/skill often return ok=True but status=failed).
    status = resp.get("status")
    if isinstance(status, str) and status.lower() == "failed":
        resp.setdefault("ok", False)
    else:
        resp.setdefault("ok", bool(result.ok))

    # Normalize error contract:
    if resp.get("ok") is False:
        resp.setdefault("status", "failed")
        if "error_detail" not in resp:
            resp["error_detail"] = getattr(result, "error_detail", None)
        if isinstance(resp.get("error"), str):
            resp.setdefault("error_message", resp.get("error"))
            resp["error"] = resp.get("error_detail") or {
                "code": "EXECUTION_FAILED",
                "message": str(resp.get("error_message") or "Execution failed"),
            }
        else:
            if "error_message" not in resp:
                try:
                    resp["error_message"] = str((resp.get("error") or {}).get("message") or result.error or "")
                except Exception:
                    resp["error_message"] = result.error or ""
        if not isinstance(resp.get("error"), dict):
            resp["error"] = resp.get("error_detail") or {
                "code": "EXECUTION_FAILED",
                "message": str(resp.get("error_message") or result.error or "Execution failed"),
            }
        resp.setdefault("error_detail", resp.get("error"))

    resp.setdefault("trace_id", result.trace_id)
    resp.setdefault("run_id", result.run_id)
    resp.setdefault("request_id", request_id)
    # normalize run status machine while preserving legacy status string.
    try:
        legacy_status = resp.get("status")
        err_code = None
        if isinstance(resp.get("error"), dict):
            err_code = (resp.get("error") or {}).get("code")
        err_code = err_code or resp.get("error_code")
        resp["legacy_status"] = legacy_status
        resp["status"] = normalize_run_status_v2(ok=bool(resp.get("ok")), legacy_status=legacy_status, error_code=err_code)
        resp.setdefault("output", resp.get("output"))
    except Exception as e:
        logging.warning(str(e), exc_info=True)
    return resp


@router.post("/gateway/webhook/message", response_model=StatusResponse)
async def gateway_webhook_message(http_request: Request, body: Dict[str, Any], rt: RuntimeDep = Depends(get_kernel_runtime)):
    """
    Minimal webhook adapter (Roadmap-3):
    - Accept a generic incoming message event
    - Convert to GatewayExecuteRequest
    - Reuse /gateway/execute so pairing/auth/toolset/tracing stay consistent
    """
    payload = body.get("payload") if isinstance(body.get("payload"), dict) else None
    if payload is None:
        payload = {"input": {"message": body.get("text") or "", "text": body.get("text") or ""}}
    # merge additional context
    try:
        ctx = payload.get("context") if isinstance(payload.get("context"), dict) else {}
        ctx = dict(ctx) if isinstance(ctx, dict) else {}
        extra_ctx = body.get("context") if isinstance(body.get("context"), dict) else {}
        ctx.update(extra_ctx or {})
        if body.get("channel_user_id"):
            ctx.setdefault("channel_user_id", body.get("channel_user_id"))
        payload["context"] = ctx
    except Exception as e:
        logging.warning(str(e), exc_info=True)

    req = GatewayExecuteRequest(
        channel=str(body.get("channel") or "webhook"),
        kind=str(body.get("kind") or "agent"),
        target_id=str(body.get("target_id") or ""),
        user_id=str(body.get("user_id")) if body.get("user_id") else None,
        session_id=str(body.get("session_id")) if body.get("session_id") else None,
        channel_user_id=str(body.get("channel_user_id")) if body.get("channel_user_id") else None,
        tenant_id=str(body.get("tenant_id")) if body.get("tenant_id") else None,
        payload=payload,
        options=body.get("options") if isinstance(body.get("options"), dict) else None,
    )
    if not req.target_id:
        raise HTTPException(status_code=400, detail="target_id is required")
    return await gateway_execute(req, http_request, rt)


@router.get("/gateway/pairings", response_model=StatusResponse)
async def list_gateway_pairings(
    http_request: Request,
    channel: Optional[str] = None,
    user_id: Optional[str] = None,
    limit: int = 100,
    offset: int = 0,
    rt: RuntimeDep = Depends(get_kernel_runtime),
):
    store = _store(rt)
    if not store:
        raise HTTPException(status_code=503, detail="ExecutionStore not initialized")
    _require_gateway_admin(http_request)
    return await store.list_gateway_pairings(channel=channel, user_id=user_id, limit=limit, offset=offset)


@router.post("/gateway/pairings", response_model=StatusResponse)
async def upsert_gateway_pairing(http_request: Request, body: Dict[str, Any], rt: RuntimeDep = Depends(get_kernel_runtime)):
    store = _store(rt)
    if not store:
        raise HTTPException(status_code=503, detail="ExecutionStore not initialized")
    _require_gateway_admin(http_request)
    channel = str(body.get("channel") or "default")
    channel_user_id = str(body.get("channel_user_id") or "").strip()
    user_id = str(body.get("user_id") or "").strip()
    if not channel_user_id or not user_id:
        raise HTTPException(status_code=400, detail="channel_user_id and user_id are required")
    return await store.upsert_gateway_pairing(
        channel=channel,
        channel_user_id=channel_user_id,
        user_id=user_id,
        session_id=body.get("session_id"),
        tenant_id=body.get("tenant_id"),
        metadata=body.get("metadata") if isinstance(body.get("metadata"), dict) else {},
    )


@router.delete("/gateway/pairings", response_model=StatusResponse)
async def delete_gateway_pairing(http_request: Request, channel: str, channel_user_id: str, rt: RuntimeDep = Depends(get_kernel_runtime)):
    store = _store(rt)
    if not store:
        raise HTTPException(status_code=503, detail="ExecutionStore not initialized")
    _require_gateway_admin(http_request)
    ok = await store.delete_gateway_pairing(channel=channel, channel_user_id=channel_user_id)
    if not ok:
        raise HTTPException(status_code=404, detail="pairing not found")
    return {"status": "deleted", "channel": channel, "channel_user_id": channel_user_id}


@router.get("/gateway/tokens", response_model=StatusResponse)
async def list_gateway_tokens(http_request: Request, enabled: Optional[bool] = None, limit: int = 100, offset: int = 0, rt: RuntimeDep = Depends(get_kernel_runtime)):
    store = _store(rt)
    if not store:
        raise HTTPException(status_code=503, detail="ExecutionStore not initialized")
    _require_gateway_admin(http_request)
    return await store.list_gateway_tokens(limit=limit, offset=offset, enabled=enabled)


@router.post("/gateway/tokens", response_model=StatusResponse)
async def create_gateway_token(http_request: Request, body: Dict[str, Any], rt: RuntimeDep = Depends(get_kernel_runtime)):
    store = _store(rt)
    if not store:
        raise HTTPException(status_code=503, detail="ExecutionStore not initialized")
    _require_gateway_admin(http_request)
    name = str(body.get("name") or "token")
    token = str(body.get("token") or "")
    if not token:
        raise HTTPException(status_code=400, detail="token is required")
    rec = await store.create_gateway_token(
        name=name,
        token=token,
        tenant_id=body.get("tenant_id"),
        enabled=bool(body.get("enabled", True)),
        metadata=body.get("metadata") if isinstance(body.get("metadata"), dict) else {},
    )
    rec.pop("token_sha256", None)
    return rec


@router.delete("/gateway/tokens/{token_id}", response_model=StatusResponse)
async def delete_gateway_token(http_request: Request, token_id: str, rt: RuntimeDep = Depends(get_kernel_runtime)):
    store = _store(rt)
    if not store:
        raise HTTPException(status_code=503, detail="ExecutionStore not initialized")
    _require_gateway_admin(http_request)
    ok = await store.delete_gateway_token(token_id=token_id)
    if not ok:
        raise HTTPException(status_code=404, detail="token not found")
    return {"status": "deleted", "token_id": token_id}


@router.get("/gateway/dlq", response_model=StatusResponse)
async def list_gateway_delivery_dlq(
    http_request: Request,
    status: Optional[str] = "pending",
    connector: Optional[str] = None,
    tenant_id: Optional[str] = None,
    limit: int = 100,
    offset: int = 0,
    rt: RuntimeDep = Depends(get_kernel_runtime),
):
    store = _store(rt)
    if not store:
        raise HTTPException(status_code=503, detail="ExecutionStore not initialized")
    _require_gateway_admin(http_request)
    return await store.list_connector_delivery_dlq(
        status=status,
        tenant_id=tenant_id,
        connector=connector,
        limit=limit,
        offset=offset,
    )


@router.post("/gateway/dlq/{dlq_id}/retry", response_model=StatusResponse)
async def retry_gateway_delivery_dlq(http_request: Request, dlq_id: str, rt: RuntimeDep = Depends(get_kernel_runtime)):
    store = _store(rt)
    if not store:
        raise HTTPException(status_code=503, detail="ExecutionStore not initialized")
    _require_gateway_admin(http_request)
    item = await store.get_connector_delivery_dlq_item(dlq_id)
    if not item:
        raise HTTPException(status_code=404, detail="DLQ item not found")
    if str(item.get("status")) != "pending":
        raise HTTPException(status_code=409, detail="DLQ item not pending")
    from core.api.services import ConnectorDelivery

    out = await ConnectorDelivery(execution_store=store).post_webhook(
        connector=str(item.get("connector") or "gateway"),
        url=str(item.get("url") or ""),
        payload=item.get("payload") if isinstance(item.get("payload"), dict) else {},
        tenant_id=item.get("tenant_id"),
        run_id=item.get("run_id"),
        retries=0,
    )
    if out.get("ok") is True:
        await store.resolve_connector_delivery_dlq_item(dlq_id)
    return {"ok": bool(out.get("ok")), "dlq_id": dlq_id, "result": out}


@router.delete("/gateway/dlq/{dlq_id}", response_model=StatusResponse)
async def delete_gateway_delivery_dlq(http_request: Request, dlq_id: str, rt: RuntimeDep = Depends(get_kernel_runtime)):
    store = _store(rt)
    if not store:
        raise HTTPException(status_code=503, detail="ExecutionStore not initialized")
    _require_gateway_admin(http_request)
    ok = await store.delete_connector_delivery_dlq_item(dlq_id)
    if not ok:
        raise HTTPException(status_code=404, detail="DLQ item not found")
    return {"status": "deleted", "dlq_id": dlq_id}
