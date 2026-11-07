"""Bind FastAPI Request → NamedWorkspaceContext for a call scope."""
from __future__ import annotations

from contextlib import contextmanager
from typing import Any, Dict, Iterator, Optional

from fastapi import HTTPException, Request

from core.api.deps import actor_from_http
from core.harness.named_workspace.errors import WorkspaceError
from core.harness.named_workspace.resolve import (
    NamedWorkspaceContext,
    reset_active_named_workspace,
    resolve_from_http,
    set_active_named_workspace,
)


def resolve_request_workspace(request: Request, *, method: Optional[str] = None) -> NamedWorkspaceContext:
    try:
        actor = actor_from_http(request, {})
    except Exception:
        actor = {}
    try:
        return resolve_from_http(
            method=(method or request.method or "GET"),
            headers={k: v for k, v in request.headers.items()},
            query=dict(request.query_params),
            tenant_id=str(actor.get("tenant_id") or "") or None,
            actor_id=str(actor.get("actor_id") or "") or None,
        )
    except WorkspaceError as e:
        raise HTTPException(
            status_code=int(e.http_status),
            detail={"error": e.code, "message": str(e) or e.code},
        ) from e


def require_local_disk(ctx: NamedWorkspaceContext) -> None:
    """Local agents/eval_results APIs must not run under a remote profile header."""
    if getattr(ctx, "is_remote", False):
        raise HTTPException(
            status_code=400,
            detail={
                "error": "remote_local_disk_forbidden",
                "message": (
                    "remote profile has no local disk partition — "
                    "use /core/workspace-proxy/{profile_id}/…"
                ),
            },
        )


@contextmanager
def named_workspace_scope(
    request: Request,
    *,
    method: Optional[str] = None,
    require_local: bool = False,
) -> Iterator[NamedWorkspaceContext]:
    ctx = resolve_request_workspace(request, method=method)
    if require_local:
        require_local_disk(ctx)
    token = set_active_named_workspace(ctx)
    try:
        yield ctx
    finally:
        reset_active_named_workspace(token)


def workspace_meta(ctx: NamedWorkspaceContext) -> Dict[str, Any]:
    out: Dict[str, Any] = {
        "named_workspace_id": ctx.workspace_id,
        "named_workspace_kind": ctx.kind,
        "phase1_boundary": (
            "本工作区一期只隔离 Agent 与评测结果；traces/缓存/附件/其它 DB 仍共享。"
        ),
    }
    if getattr(ctx, "is_remote", False):
        out["remote_boundary"] = (
            "远程 Core = 换 API 目标；≠ 本机分区；≠ 外部拉模式 Agent。"
        )
        out["base_url_host"] = None
        try:
            from urllib.parse import urlparse

            out["base_url_host"] = urlparse(str(ctx.base_url or "")).hostname
        except Exception:
            pass  # noqa: optional-dependency
    return out
