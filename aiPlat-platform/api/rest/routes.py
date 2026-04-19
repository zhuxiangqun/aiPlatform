"""
aiPlat-platform HTTP API (Phase 1/2)

What this file provides:
- PR-01: 身份解析（JWT/API key）+ 标准 Header 透传 + request_id 生成 + /whoami
- PR-02: platform 代理执行：/platform/gateway/execute 与 /api/v1/agents/{id}/execute → 转发 aiPlat-core /api/core/gateway/execute
- Minimal CRUD for management pages: /platform/gateway/routes, /platform/auth/users, /platform/tenants (in-memory)
"""

from __future__ import annotations

import base64
import json
import os
from dataclasses import dataclass
from typing import Any, Dict, Optional, List

from fastapi import FastAPI, Header, HTTPException, Request
from pydantic import BaseModel

import httpx

# NOTE: repo folder name contains '-', so do NOT import via top-level package name.
# Use subpackages directly (auth/, utils/, etc).
from utils.ids import new_prefixed_id as _new_prefixed_id  # type: ignore
from auth.authenticator import authenticator as _authenticator  # type: ignore
from storage import sqlite as platform_store  # type: ignore


app = FastAPI(title="aiPlat-platform", version="0.1.0")


@dataclass
class Identity:
    request_id: str
    tenant_id: str
    actor_id: str
    scopes: List[str]
    actor_role: Optional[str] = None
    auth_type: str = "anonymous"  # jwt|api_key|header|anonymous


def _b64url_json_decode(part: str) -> Dict[str, Any]:
    pad = "=" * (-len(part) % 4)
    raw = base64.urlsafe_b64decode((part + pad).encode("utf-8"))
    return json.loads(raw.decode("utf-8"))


def _decode_jwt_claims(token: str) -> Dict[str, Any]:
    """
    Best-effort JWT decode.
    - If PyJWT is installed and AIPLAT_JWT_SECRET is set, you can enable verification.
    - Otherwise decode without verification (dev-only).
    """
    verify = os.getenv("AIPLAT_PLATFORM_JWT_VERIFY", "false").lower() in ("1", "true", "yes", "y")
    secret = os.getenv("AIPLAT_JWT_SECRET")
    if verify and secret:
        try:
            import jwt  # type: ignore

            return jwt.decode(token, secret, algorithms=["HS256", "RS256"], options={"verify_aud": False})
        except Exception:
            # fallback to unverified decode
            pass
    parts = token.split(".")
    if len(parts) < 2:
        return {}
    return _b64url_json_decode(parts[1])


def _parse_scopes(v: Any) -> List[str]:
    if v is None:
        return []
    if isinstance(v, list):
        return [str(x) for x in v if str(x).strip()]
    if isinstance(v, str):
        # allow comma or space
        raw = v.replace(" ", ",")
        return [x.strip() for x in raw.split(",") if x.strip()]
    return [str(v)]


def _get_or_create_request_id(request: Request) -> str:
    rid = request.headers.get("X-AIPLAT-REQUEST-ID")
    if isinstance(rid, str) and rid.strip():
        return rid.strip()
    return _new_prefixed_id("req")


def _resolve_identity(request: Request) -> Identity:
    request_id = _get_or_create_request_id(request)

    # 1) Explicit headers (debug / internal calls)
    tenant_id = request.headers.get("X-AIPLAT-TENANT-ID")
    actor_id = request.headers.get("X-AIPLAT-ACTOR-ID")
    scopes = _parse_scopes(request.headers.get("X-AIPLAT-SCOPES"))
    actor_role = request.headers.get("X-AIPLAT-ACTOR-ROLE")
    if tenant_id and actor_id:
        return Identity(
            request_id=request_id,
            tenant_id=str(tenant_id),
            actor_id=str(actor_id),
            scopes=scopes,
            actor_role=str(actor_role) if actor_role else None,
            auth_type="header",
        )

    # 2) Authorization: Bearer <token> (JWT or API key)
    authz = request.headers.get("Authorization")
    token = None
    if isinstance(authz, str) and authz.lower().startswith("bearer "):
        token = authz.split(" ", 1)[1].strip()
    # also allow explicit api key header
    api_key = request.headers.get("X-AIPLAT-API-KEY") or token
    if isinstance(api_key, str) and api_key.startswith("apl_"):
        ar = _authenticator.verify_api_key(api_key)
        if ar.success and ar.tenant_id and ar.user_id:
            return Identity(
                request_id=request_id,
                tenant_id=str(ar.tenant_id),
                actor_id=str(ar.user_id),
                scopes=_authenticator.get_permissions(api_key),
                actor_role="service",
                auth_type="api_key",
            )

    if isinstance(token, str) and token.count(".") >= 2:
        claims = _decode_jwt_claims(token)
        tid = claims.get("tid") or claims.get("tenant_id") or "default"
        sub = claims.get("sub") or claims.get("actor_id") or "anonymous"
        roles = claims.get("roles")
        scopes2 = claims.get("scopes")
        role0 = None
        if isinstance(roles, list) and roles:
            role0 = str(roles[0])
        return Identity(
            request_id=request_id,
            tenant_id=str(tid),
            actor_id=str(sub),
            scopes=_parse_scopes(scopes2),
            actor_role=role0,
            auth_type="jwt",
        )

    # 3) default fallback
    return Identity(request_id=request_id, tenant_id="default", actor_id="anonymous", scopes=[], auth_type="anonymous")


def _core_base_url() -> str:
    return os.getenv("AIPLAT_CORE_ENDPOINT", "http://localhost:8002").rstrip("/")


async def _call_core_gateway_execute(identity: Identity, body: Dict[str, Any]) -> Dict[str, Any]:
    """
    Forward to core /api/core/gateway/execute and inject standardized headers.
    """
    headers = {
        "Content-Type": "application/json",
        "X-AIPLAT-REQUEST-ID": identity.request_id,
        "X-AIPLAT-TENANT-ID": identity.tenant_id,
        "X-AIPLAT-ACTOR-ID": identity.actor_id,
    }
    if identity.scopes:
        headers["X-AIPLAT-SCOPES"] = ",".join(identity.scopes)
    if identity.actor_role:
        headers["X-AIPLAT-ACTOR-ROLE"] = identity.actor_role

    # Force core identity to be platform-authoritative
    body = dict(body or {})
    body["tenant_id"] = identity.tenant_id
    body["user_id"] = identity.actor_id
    # session_id: preserve caller if provided
    if not body.get("session_id"):
        body["session_id"] = body.get("payload", {}).get("session_id") if isinstance(body.get("payload"), dict) else None

    return await _core_request("POST", "/api/core/gateway/execute", identity=identity, json_body=body, extra_headers=headers)


async def _core_request(
    method: str,
    path: str,
    *,
    identity: Identity,
    params: Optional[Dict[str, Any]] = None,
    json_body: Optional[Dict[str, Any]] = None,
    extra_headers: Optional[Dict[str, str]] = None,
) -> Dict[str, Any]:
    headers = {
        "Content-Type": "application/json",
        "X-AIPLAT-REQUEST-ID": identity.request_id,
        "X-AIPLAT-TENANT-ID": identity.tenant_id,
        "X-AIPLAT-ACTOR-ID": identity.actor_id,
    }
    if identity.scopes:
        headers["X-AIPLAT-SCOPES"] = ",".join(identity.scopes)
    if identity.actor_role:
        headers["X-AIPLAT-ACTOR-ROLE"] = identity.actor_role
    if extra_headers:
        headers.update(extra_headers)
    async with httpx.AsyncClient(timeout=60.0) as client:
        resp = await client.request(method.upper(), f"{_core_base_url()}{path}", headers=headers, params=params, json=json_body)
        resp.raise_for_status()
        return resp.json()


# -------------------- Health & Debug --------------------


@app.get("/health")
async def health_check(request: Request):
    identity = _resolve_identity(request)
    return {"status": "healthy", "tenant_id": identity.tenant_id}


@app.get("/whoami")
async def whoami(request: Request):
    identity = _resolve_identity(request)
    return {
        "request_id": identity.request_id,
        "tenant_id": identity.tenant_id,
        "actor_id": identity.actor_id,
        "actor_role": identity.actor_role,
        "scopes": identity.scopes,
        "auth_type": identity.auth_type,
    }


# -------------------- Platform proxy execute (PR-02) --------------------


@app.post("/platform/gateway/execute")
async def platform_gateway_execute(request: Request):
    identity = _resolve_identity(request)
    body = await request.json()
    if not isinstance(body, dict):
        raise HTTPException(status_code=400, detail="body must be json object")
    return await _call_core_gateway_execute(identity, body)


# -------------------- API v1 (compat for aiPlat-app client / docs) --------------------


class AgentExecuteRequest(BaseModel):
    input: Any
    session_id: Optional[str] = None
    context: Optional[Dict[str, Any]] = None


@app.post("/api/v1/agents/{agent_id}/execute")
async def api_v1_agent_execute(agent_id: str, req: AgentExecuteRequest, request: Request):
    identity = _resolve_identity(request)
    payload_ctx = dict(req.context or {})
    payload_ctx.setdefault("source", "app")
    payload_ctx.setdefault("tenant_id", identity.tenant_id)
    payload_ctx.setdefault("session_id", req.session_id or "default")
    # Execute workspace agent via core workspace agent endpoint (not gateway/execute),
    # because /api/v1/agents CRUD is backed by core /workspace/agents.
    body = {
        "input": {"text": req.input},
        "context": payload_ctx,
        "user_id": identity.actor_id,
        "session_id": req.session_id or "default",
    }
    return await _core_request(
        "POST",
        f"/api/core/workspace/agents/{agent_id}/execute",
        identity=identity,
        json_body=body,
    )


@app.get("/api/v1/agents")
async def api_v1_agents_list(request: Request, limit: int = 100, offset: int = 0):
    identity = _resolve_identity(request)
    data = await _core_request(
        "GET",
        "/api/core/workspace/agents",
        identity=identity,
        params={"limit": int(limit), "offset": int(offset)},
    )
    # core already returns {agents,total,limit,offset}
    return data


@app.post("/api/v1/agents")
async def api_v1_agents_create(request: Request, body: Dict[str, Any]):
    identity = _resolve_identity(request)
    if not isinstance(body, dict):
        raise HTTPException(status_code=400, detail="body must be json object")
    name = body.get("name")
    if not name:
        raise HTTPException(status_code=400, detail="name is required")
    metadata = body.get("metadata") if isinstance(body.get("metadata"), dict) else {}
    if body.get("description"):
        metadata = dict(metadata)
        metadata.setdefault("description", str(body.get("description")))
    payload = {
        "name": str(name),
        "agent_type": str(body.get("agent_type") or "base"),
        "config": body.get("config") if isinstance(body.get("config"), dict) else {},
        "skills": body.get("skills") if isinstance(body.get("skills"), list) else [],
        "tools": body.get("tools") if isinstance(body.get("tools"), list) else [],
        "memory_config": body.get("memory_config") if isinstance(body.get("memory_config"), dict) else None,
        "metadata": metadata or None,
    }
    return await _core_request("POST", "/api/core/workspace/agents", identity=identity, json_body=payload)


@app.get("/api/v1/agents/{agent_id}")
async def api_v1_agents_get(agent_id: str, request: Request):
    identity = _resolve_identity(request)
    agent = await _core_request("GET", f"/api/core/workspace/agents/{agent_id}", identity=identity)
    return {"agent": agent}


@app.put("/api/v1/agents/{agent_id}")
async def api_v1_agents_update(agent_id: str, request: Request, body: Dict[str, Any]):
    identity = _resolve_identity(request)
    if not isinstance(body, dict):
        raise HTTPException(status_code=400, detail="body must be json object")
    payload: Dict[str, Any] = {}
    for k in ("name", "config", "skills", "tools", "memory_config", "metadata"):
        if k in body:
            payload[k] = body.get(k)
    if "description" in body:
        md = payload.get("metadata") if isinstance(payload.get("metadata"), dict) else {}
        md = dict(md)
        md["description"] = str(body.get("description") or "")
        payload["metadata"] = md
    return await _core_request("PUT", f"/api/core/workspace/agents/{agent_id}", identity=identity, json_body=payload)


@app.delete("/api/v1/agents/{agent_id}")
async def api_v1_agents_delete(agent_id: str, request: Request):
    identity = _resolve_identity(request)
    try:
        await _core_request("DELETE", f"/api/core/workspace/agents/{agent_id}", identity=identity)
        return {"ok": True, "id": agent_id}
    except httpx.HTTPStatusError as e:
        if e.response is not None and e.response.status_code == 404:
            return {"ok": False, "id": agent_id}
        raise


# -------------------- Management-facing platform resources (minimal, in-memory) --------------------


@app.get("/platform/gateway/routes")
async def list_gateway_routes(enabled: Optional[bool] = None):
    routes = platform_store.list_gateway_routes(enabled=enabled)
    return {"routes": routes, "total": len(routes)}


@app.post("/platform/gateway/routes")
async def create_gateway_route(body: Dict[str, Any]):
    rid = str(body.get("id") or _new_prefixed_id("route"))
    route = {
        "id": rid,
        "name": body.get("name") or rid,
        "path": body.get("path") or "/",
        "backend": body.get("backend") or "core",
        "methods": body.get("methods") or ["POST"],
        "enabled": bool(body.get("enabled", True)),
        "rate_limit": int(body.get("rate_limit", 100)),
        "timeout": int(body.get("timeout", 30)),
        "created_at": body.get("created_at") or "",
        "updated_at": body.get("updated_at") or "",
    }
    return platform_store.upsert_gateway_route(route)


@app.get("/platform/gateway/routes/{route_id}")
async def get_gateway_route(route_id: str):
    r = platform_store.get_gateway_route(route_id)
    if not r:
        raise HTTPException(status_code=404, detail="route_not_found")
    return r


@app.put("/platform/gateway/routes/{route_id}")
async def update_gateway_route(route_id: str, patch: Dict[str, Any]):
    r = platform_store.get_gateway_route(route_id)
    if not r:
        raise HTTPException(status_code=404, detail="route_not_found")
    r.update({k: v for k, v in (patch or {}).items() if v is not None})
    return platform_store.upsert_gateway_route(r)


@app.delete("/platform/gateway/routes/{route_id}")
async def delete_gateway_route(route_id: str):
    platform_store.delete_gateway_route(route_id)
    return {"status": "ok"}


@app.get("/platform/gateway/metrics")
async def gateway_metrics():
    # stubbed metrics
    return {"total_requests": 0, "success_rate": 1.0, "avg_latency_ms": 0, "active_routes": len(platform_store.list_gateway_routes())}


@app.get("/platform/auth/users")
async def list_auth_users(role: Optional[str] = None, status: Optional[str] = None):
    users = platform_store.list_auth_users(role=role, status=status)
    return {"users": users, "total": len(users)}


@app.post("/platform/auth/users")
async def create_auth_user(body: Dict[str, Any]):
    uid = str(body.get("id") or _new_prefixed_id("u"))
    user = {
        "id": uid,
        "username": body.get("username") or uid,
        "email": body.get("email") or "",
        "role": body.get("role") or "user",
        "status": body.get("status") or "active",
        "last_login": None,
        "created_at": "",
    }
    return platform_store.upsert_auth_user(user)


@app.put("/platform/auth/users/{user_id}")
async def update_auth_user(user_id: str, patch: Dict[str, Any]):
    u = platform_store.get_auth_user(user_id)
    if not u:
        raise HTTPException(status_code=404, detail="user_not_found")
    u.update({k: v for k, v in (patch or {}).items() if v is not None})
    return platform_store.upsert_auth_user(u)


@app.delete("/platform/auth/users/{user_id}")
async def delete_auth_user(user_id: str):
    platform_store.delete_auth_user(user_id)
    return {"status": "ok"}


@app.get("/platform/tenants")
async def list_tenants(status: Optional[str] = None):
    tenants = platform_store.list_tenants(status=status)
    return {"tenants": tenants, "total": len(tenants)}


@app.post("/platform/tenants")
async def create_tenant(body: Dict[str, Any]):
    tid = str(body.get("id") or _new_prefixed_id("t"))
    t = {
        "id": tid,
        "name": body.get("name") or tid,
        "description": body.get("description") or "",
        "quota": body.get("quota") or {"gpu_limit": 0, "storage_limit_gb": 0, "max_agents": 0},
        "status": body.get("status") or "active",
        "user_count": 0,
        "created_at": "",
    }
    return platform_store.upsert_tenant(t)


@app.put("/platform/tenants/{tenant_id}")
async def update_tenant(tenant_id: str, patch: Dict[str, Any]):
    t = platform_store.get_tenant(tenant_id)
    if not t:
        raise HTTPException(status_code=404, detail="tenant_not_found")
    t.update({k: v for k, v in (patch or {}).items() if v is not None})
    return platform_store.upsert_tenant(t)


@app.delete("/platform/tenants/{tenant_id}")
async def delete_tenant(tenant_id: str):
    platform_store.delete_tenant(tenant_id)
    return {"status": "ok"}


@app.post("/platform/tenants/{tenant_id}/suspend")
async def suspend_tenant(tenant_id: str):
    t = platform_store.get_tenant(tenant_id)
    if not t:
        raise HTTPException(status_code=404, detail="tenant_not_found")
    t["status"] = "suspended"
    platform_store.upsert_tenant(t)
    return {"status": "ok"}


@app.post("/platform/tenants/{tenant_id}/resume")
async def resume_tenant(tenant_id: str):
    t = platform_store.get_tenant(tenant_id)
    if not t:
        raise HTTPException(status_code=404, detail="tenant_not_found")
    t["status"] = "active"
    platform_store.upsert_tenant(t)
    return {"status": "ok"}


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=int(os.getenv("AIPLAT_PLATFORM_PORT", "8003")))
