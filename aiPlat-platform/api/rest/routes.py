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

    async with httpx.AsyncClient(timeout=60.0) as client:
        resp = await client.post(f"{_core_base_url()}/api/core/gateway/execute", headers=headers, json=body)
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
    body = {
        "channel": "api_v1",
        "kind": "agent",
        "target_id": agent_id,
        "session_id": req.session_id or "default",
        "payload": {"input": {"text": req.input}, "context": payload_ctx},
    }
    return await _call_core_gateway_execute(identity, body)


@app.get("/api/v1/agents")
async def api_v1_agents_list(limit: int = 100):
    # minimal placeholder; can be expanded to proxy core /agents later
    return {"agents": [], "total": 0, "limit": limit}


# -------------------- Management-facing platform resources (minimal, in-memory) --------------------


_gateway_routes: Dict[str, Dict[str, Any]] = {}
_auth_users: Dict[str, Dict[str, Any]] = {}
_tenants: Dict[str, Dict[str, Any]] = {}


@app.get("/platform/gateway/routes")
async def list_gateway_routes(enabled: Optional[bool] = None):
    routes = list(_gateway_routes.values())
    if enabled is not None:
        routes = [r for r in routes if bool(r.get("enabled")) == bool(enabled)]
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
    _gateway_routes[rid] = route
    return route


@app.get("/platform/gateway/routes/{route_id}")
async def get_gateway_route(route_id: str):
    r = _gateway_routes.get(route_id)
    if not r:
        raise HTTPException(status_code=404, detail="route_not_found")
    return r


@app.put("/platform/gateway/routes/{route_id}")
async def update_gateway_route(route_id: str, patch: Dict[str, Any]):
    r = _gateway_routes.get(route_id)
    if not r:
        raise HTTPException(status_code=404, detail="route_not_found")
    r.update({k: v for k, v in (patch or {}).items() if v is not None})
    _gateway_routes[route_id] = r
    return r


@app.delete("/platform/gateway/routes/{route_id}")
async def delete_gateway_route(route_id: str):
    _gateway_routes.pop(route_id, None)
    return {"status": "ok"}


@app.get("/platform/gateway/metrics")
async def gateway_metrics():
    # stubbed metrics
    return {"total_requests": 0, "success_rate": 1.0, "avg_latency_ms": 0, "active_routes": len(_gateway_routes)}


@app.get("/platform/auth/users")
async def list_auth_users(role: Optional[str] = None, status: Optional[str] = None):
    users = list(_auth_users.values())
    if role:
        users = [u for u in users if str(u.get("role")) == str(role)]
    if status:
        users = [u for u in users if str(u.get("status")) == str(status)]
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
    _auth_users[uid] = user
    return user


@app.put("/platform/auth/users/{user_id}")
async def update_auth_user(user_id: str, patch: Dict[str, Any]):
    u = _auth_users.get(user_id)
    if not u:
        raise HTTPException(status_code=404, detail="user_not_found")
    u.update({k: v for k, v in (patch or {}).items() if v is not None})
    _auth_users[user_id] = u
    return u


@app.delete("/platform/auth/users/{user_id}")
async def delete_auth_user(user_id: str):
    _auth_users.pop(user_id, None)
    return {"status": "ok"}


@app.get("/platform/tenants")
async def list_tenants(status: Optional[str] = None):
    tenants = list(_tenants.values())
    if status:
        tenants = [t for t in tenants if str(t.get("status")) == str(status)]
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
    _tenants[tid] = t
    return t


@app.put("/platform/tenants/{tenant_id}")
async def update_tenant(tenant_id: str, patch: Dict[str, Any]):
    t = _tenants.get(tenant_id)
    if not t:
        raise HTTPException(status_code=404, detail="tenant_not_found")
    t.update({k: v for k, v in (patch or {}).items() if v is not None})
    _tenants[tenant_id] = t
    return t


@app.delete("/platform/tenants/{tenant_id}")
async def delete_tenant(tenant_id: str):
    _tenants.pop(tenant_id, None)
    return {"status": "ok"}


@app.post("/platform/tenants/{tenant_id}/suspend")
async def suspend_tenant(tenant_id: str):
    t = _tenants.get(tenant_id)
    if not t:
        raise HTTPException(status_code=404, detail="tenant_not_found")
    t["status"] = "suspended"
    return {"status": "ok"}


@app.post("/platform/tenants/{tenant_id}/resume")
async def resume_tenant(tenant_id: str):
    t = _tenants.get(tenant_id)
    if not t:
        raise HTTPException(status_code=404, detail="tenant_not_found")
    t["status"] = "active"
    return {"status": "ok"}


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=int(os.getenv("AIPLAT_PLATFORM_PORT", "8003")))
