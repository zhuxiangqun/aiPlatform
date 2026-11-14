# core-routing: allowed (named workspace partition is harness/core capability, not an app module)
"""Named workspace partition API — local + remote profiles; allowlisted remote proxy."""
from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional
from urllib.parse import urlparse

from fastapi import APIRouter, Header, HTTPException, Query, Request, Response
from pydantic import BaseModel, Field

from core.api.deps import actor_from_http
from core.harness.named_workspace.errors import (
    WorkspaceError,
    WorkspaceForbidden,
    WorkspaceNotFound,
    WorkspaceRequired,
)
from core.harness.named_workspace.registry import (
    create_local_workspace,
    create_remote_workspace,
    ensure_registry,
    get_registry_entry,
    list_registry_entries,
)
from core.harness.named_workspace.remote_proxy import RemoteProxyError, proxy_request
from core.harness.named_workspace.resolve import (
    HEADER_NAME,
    resolve_from_http,
    resolve_named_workspace,
)

logger = logging.getLogger(__name__)
router = APIRouter(tags=["named-workspaces"])

REMOTE_BOUNDARY = (
    "远程 Core = 换 API 目标；≠ 本机分区；≠ 外部拉模式 Agent。"
    " 本机一期仍只隔离 Agent 与评测结果；traces/缓存/附件/其它 DB 仍共享。"
)


def _http_err(exc: WorkspaceError) -> HTTPException:
    return HTTPException(
        status_code=int(exc.http_status),
        detail={"error": exc.code, "message": str(exc) or exc.code},
    )


def _actor_bits(request: Request) -> Dict[str, Optional[str]]:
    try:
        actor = actor_from_http(request, {})
        return {
            "tenant_id": str(actor.get("tenant_id") or "") or None,
            "actor_id": str(actor.get("actor_id") or "") or None,
        }
    except Exception:
        return {"tenant_id": None, "actor_id": None}


class CreateWorkspaceBody(BaseModel):
    """CreateWorkspaceBody。"""
    workspace_id: str = Field(..., min_length=1, max_length=64)
    label: str = ""
    kind: str = "local"
    base_url: str = ""
    auth_secret_env: str = ""
    allowed_routes: List[str] = Field(default_factory=list)


@router.get("/workspaces")
async def list_named_workspaces(request: Request) -> Dict[str, Any]:
    """List local + remote profiles visible to caller.

    Args:
        request: request 参数。
    """
    try:
        ensure_registry()
        bits = _actor_bits(request)
        headers = {k: v for k, v in request.headers.items()}
        try:
            current = resolve_from_http(
                method="GET",
                headers=headers,
                query=dict(request.query_params),
                tenant_id=bits["tenant_id"],
                actor_id=bits["actor_id"],
            )
            current_id = current.workspace_id
        except WorkspaceError:
            current_id = "default"

        items = []
        for row in list_registry_entries():
            try:
                resolve_named_workspace(
                    row["id"],
                    method="GET",
                    tenant_id=bits["tenant_id"],
                    actor_id=bits["actor_id"],
                )
            except (WorkspaceForbidden, WorkspaceNotFound):
                continue
            except WorkspaceError:
                continue
            kind = str(row.get("kind") or "local")
            host = None
            if kind == "remote" and row.get("base_url"):
                host = urlparse(str(row["base_url"])).hostname
            items.append(
                {
                    "id": row["id"],
                    "label": row["label"],
                    "kind": kind,
                    "base_url_host": host,
                    "active": row["id"] == current_id,
                }
            )
        return {
            "ok": True,
            "items": items,
            "current_workspace_id": current_id,
            "phase1_boundary": (
                "本工作区一期只隔离 Agent 与评测结果；traces/缓存/附件/其它 DB 仍共享。"
            ),
            "remote_boundary": REMOTE_BOUNDARY,
            "header": HEADER_NAME,
            "accuracy_claim": False,
        }
    except WorkspaceError as e:
        raise _http_err(e) from e
    except Exception as e:
        logger.exception("list_named_workspaces failed")
        raise HTTPException(status_code=500, detail=str(e)[:200]) from e


@router.post("/workspaces")
async def create_named_workspace(
    request: Request,
    body: CreateWorkspaceBody,
    x_aiplat_workspace_id: Optional[str] = Header(None, alias=HEADER_NAME),
) -> Dict[str, Any]:
    """Create local empty workspace or remote Core profile. Write requires workspace header.

    Args:
        request: request 参数。
        body: 请求体 dict。
        x_aiplat_workspace_id: x_aiplat_workspace 标识。
    """
    try:
        bits = _actor_bits(request)
        headers = {k: v for k, v in request.headers.items()}
        resolve_from_http(
            method="POST",
            headers=headers,
            query=dict(request.query_params),
            tenant_id=bits["tenant_id"],
            actor_id=bits["actor_id"],
        )
        kind = (body.kind or "local").strip().lower()
        if kind == "remote":
            entry = create_remote_workspace(
                body.workspace_id,
                label=body.label or "",
                base_url=body.base_url,
                auth_secret_env=body.auth_secret_env or "",
                allowed_routes=list(body.allowed_routes or []),
                allowed_tenants=["*"],
            )
        elif kind == "local":
            entry = create_local_workspace(body.workspace_id, label=body.label or "")
            try:
                from core.harness.named_workspace.agent_mgr import invalidate_agent_manager

                invalidate_agent_manager(str(entry.get("id") or ""))
            except Exception:
                pass  # noqa: optional-dependency
        else:
            raise HTTPException(status_code=400, detail=f"unsupported kind: {kind}")
        # Public view: never return secret values
        pub = {
            "id": entry.get("id"),
            "label": entry.get("label"),
            "kind": entry.get("kind"),
            "base_url": entry.get("base_url"),
            "auth_secret_configured": bool(entry.get("auth_secret_env")),
        }
        return {"ok": True, "workspace": pub, "remote_boundary": REMOTE_BOUNDARY}
    except WorkspaceError as e:
        raise _http_err(e) from e
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)[:200]) from e
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("create_named_workspace failed")
        raise HTTPException(status_code=500, detail=str(e)[:200]) from e


@router.get("/workspaces/resolve")
async def resolve_named_workspace_endpoint(
    request: Request,
    workspace_id: Optional[str] = Query(None),
) -> Dict[str, Any]:
    """Debug/resolve current named workspace (read).

    Args:
        request: request 参数。
        workspace_id: workspace 标识。
    """
    try:
        bits = _actor_bits(request)
        headers = {k: v for k, v in request.headers.items()}
        q = dict(request.query_params)
        if workspace_id:
            q["workspace_id"] = workspace_id
        ctx = resolve_from_http(
            method="GET",
            headers=headers,
            query=q,
            tenant_id=bits["tenant_id"],
            actor_id=bits["actor_id"],
        )
        return {"ok": True, "workspace": ctx.to_dict()}
    except WorkspaceError as e:
        raise _http_err(e) from e


@router.api_route(
    "/workspace-proxy/{profile_id}/{path:path}",
    methods=["GET", "POST"],
)
async def workspace_proxy(
    profile_id: str,
    path: str,
    request: Request,
) -> Response:
    """Allowlisted forward to a remote Core profile. Strips local workspace header.

    Args:
        profile_id: profile 标识。
        path: 文件或目录路径。
        request: request 参数。
    """
    bits = _actor_bits(request)
    try:
        entry = get_registry_entry(profile_id)
        if not entry or str(entry.get("kind") or "") != "remote":
            raise WorkspaceNotFound(f"remote profile not found: {profile_id}")
        # ACL
        resolve_named_workspace(
            profile_id,
            method="GET",
            tenant_id=bits["tenant_id"],
            actor_id=bits["actor_id"],
        )
    except WorkspaceError as e:
        raise _http_err(e) from e

    raw_path = path if path.startswith("/") else f"/{path}"
    if request.url.query:
        raw_path = f"{raw_path}?{request.url.query}"

    body = b""
    if request.method.upper() == "POST":
        body = await request.body()

    try:
        out = proxy_request(
            profile_id=profile_id,
            base_url=str(entry.get("base_url") or ""),
            method=request.method,
            path=raw_path if raw_path.startswith("/core/") else f"/core/{raw_path.lstrip('/')}",
            body=body,
            content_type=request.headers.get("content-type") or "",
            auth_secret_env=str(entry.get("auth_secret_env") or ""),
            allowed_routes=list(entry.get("allowed_routes") or []),
            tenant_id=bits["tenant_id"] or "",
            actor_id=bits["actor_id"] or "",
        )
    except RemoteProxyError as e:
        raise HTTPException(
            status_code=int(e.http_status),
            detail={"error": e.code, "message": str(e)},
        ) from e
    except ValueError as e:
        raise HTTPException(
            status_code=400,
            detail={"error": "remote_proxy_error", "message": str(e)[:300]},
        ) from e

    return Response(
        content=out.get("body") or b"",
        status_code=int(out.get("status_code") or 502),
        media_type=str(out.get("content_type") or "application/json"),
        headers={
            "X-Aiplat-Remote-Profile": profile_id,
            "X-Aiplat-Remote-Stripped-Workspace": "1",
        },
    )
