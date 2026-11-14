"""Resolve + ACL → NamedWorkspaceContext (explicit; ContextVar is convenience only)."""
from __future__ import annotations

import logging
import os
from contextvars import ContextVar
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from core.harness.named_workspace.errors import (
    WorkspaceForbidden,
    WorkspaceNotFound,
    WorkspaceRequired,
)
from core.harness.named_workspace.registry import (
    ensure_registry,
    get_registry_entry,
    validate_workspace_id,
)
from core.utils.paths import get_aiplat_home

logger = logging.getLogger(__name__)

HEADER_NAME = "X-Aiplat-Workspace-Id"
QUERY_NAME = "workspace_id"


@dataclass(frozen=True)
class NamedWorkspaceContext:
    """Validated named workspace — pass explicitly into services/workers."""

    workspace_id: str
    kind: str
    label: str
    agents_dir: str
    eval_results_dir: str
    root_dir: str
    tenant_id: Optional[str] = None
    actor_id: Optional[str] = None
    allowed_tenants: Tuple[str, ...] = field(default_factory=lambda: ("*",))
    base_url: str = ""
    auth_secret_env: str = ""
    allowed_routes: Tuple[str, ...] = field(default_factory=tuple)

    @property
    def is_remote(self) -> bool:
        """is_remote。
        """
        return str(self.kind or "") == "remote"

    def to_dict(self) -> Dict[str, Any]:
        """to_dict。
        """
        return {
            "workspace_id": self.workspace_id,
            "kind": self.kind,
            "label": self.label,
            "agents_dir": self.agents_dir,
            "eval_results_dir": self.eval_results_dir,
            "root_dir": self.root_dir,
            "tenant_id": self.tenant_id,
            "actor_id": self.actor_id,
            "allowed_tenants": list(self.allowed_tenants),
            "base_url": self.base_url or None,
            "auth_secret_configured": bool(self.auth_secret_env),
            "is_remote": self.is_remote,
        }


_active: ContextVar[Optional[NamedWorkspaceContext]] = ContextVar(
    "named_workspace_ctx", default=None
)


def set_active_named_workspace(ctx: Optional[NamedWorkspaceContext]):
    """set_active_named_workspace。

    Args:
        ctx: ctx 参数。
    """
    return _active.set(ctx)


def reset_active_named_workspace(token) -> None:
    """reset_active_named_workspace。

    Args:
        token: token 参数。
    """
    _active.reset(token)


def get_active_named_workspace() -> Optional[NamedWorkspaceContext]:
    """获取 active_named_workspace。
    """
    return _active.get()


def extract_workspace_id_from_request(
    headers: Optional[Dict[str, str]] = None,
    query: Optional[Dict[str, Any]] = None,
) -> Optional[str]:
    """Header wins over query. Returns None if absent.

    Args:
        headers: headers 参数。
        query: 查询。
    """
    hid = None
    if headers:
        # case-insensitive
        for k, v in headers.items():
            if k.lower() == HEADER_NAME.lower():
                hid = str(v or "").strip()
                break
    if hid:
        return hid
    if query and query.get(QUERY_NAME) is not None:
        return str(query.get(QUERY_NAME) or "").strip() or None
    return None


def _home_realpath() -> Path:
    return Path(get_aiplat_home()).expanduser().resolve()


def _paths_for_entry(entry: Dict[str, Any]) -> Tuple[str, str, str]:
    home = _home_realpath()
    wid = str(entry["id"])
    kind = str(entry.get("kind") or "local")
    if kind == "remote":
        # Remote profiles have no local disk partition.
        return "", "", ""
    if kind != "local":
        raise WorkspaceNotFound(f"workspace kind={kind} not available")

    if wid == "default" or not str(entry.get("root") or "").strip():
        agents = (home / "agents").resolve()
        evals = (home / "eval_results").resolve()
        root = str(home)
        return root, str(agents), str(evals)

    raw_root = str(entry.get("root") or f"workspaces/{wid}").strip()
    root_path = Path(raw_root).expanduser()
    if not root_path.is_absolute():
        root_path = (home / root_path).resolve()
    else:
        root_path = root_path.resolve()

    # Must stay under AIPLAT_HOME
    try:
        root_path.relative_to(home)
    except ValueError as e:
        raise WorkspaceNotFound(f"workspace root escapes AIPLAT_HOME: {wid}") from e

    agents = (root_path / "agents").resolve()
    evals = (root_path / "eval_results").resolve()
    for p in (agents, evals):
        try:
            p.relative_to(home)
        except ValueError as e:
            raise WorkspaceNotFound(f"workspace path escapes AIPLAT_HOME: {wid}") from e
    return str(root_path), str(agents), str(evals)


def _acl_allows(entry: Dict[str, Any], tenant_id: Optional[str]) -> bool:
    allowed = entry.get("allowed_tenants") or ["*"]
    if not isinstance(allowed, list):
        allowed = ["*"]
    if "*" in allowed:
        return True
    tid = (tenant_id or "").strip()
    if not tid:
        # No tenant on request: only default with * would have passed; deny others.
        return False
    return tid in {str(x) for x in allowed}


def resolve_named_workspace(
    workspace_id: Optional[str],
    *,
    method: str = "GET",
    tenant_id: Optional[str] = None,
    actor_id: Optional[str] = None,
    require_explicit_write: bool = True,
) -> NamedWorkspaceContext:
    """Resolve registry entry + ACL → context.

    Args:
        workspace_id: 工作区 ID。
        method: method 参数。
        tenant_id: 租户 ID。
        actor_id: actor 标识。
        require_explicit_write: require_explicit_write 参数。
    """
    ensure_registry()
    m = (method or "GET").upper()
    is_write = m not in ("GET", "HEAD", "OPTIONS")
    raw = (workspace_id or "").strip() if workspace_id is not None else ""

    if not raw:
        if is_write and require_explicit_write:
            compat = os.environ.get("AIPLAT_WORKSPACE_WRITE_DEFAULT_COMPAT", "").strip() in (
                "1",
                "true",
                "TRUE",
                "yes",
            )
            if compat:
                logger.warning(
                    "workspace_write_default_compat: missing workspace_id on %s; "
                    "falling back to default (audit)",
                    m,
                )
                raw = "default"
            else:
                raise WorkspaceRequired("write requires X-Aiplat-Workspace-Id")
        else:
            raw = "default"

    try:
        wid = validate_workspace_id(raw)
    except ValueError as e:
        raise WorkspaceNotFound(str(e)) from e

    entry = get_registry_entry(wid)
    if not entry:
        raise WorkspaceNotFound(f"workspace not found: {wid}")

    if not _acl_allows(entry, tenant_id):
        raise WorkspaceForbidden(f"workspace forbidden: {wid}")

    kind = str(entry.get("kind") or "local")
    root, agents, evals = _paths_for_entry(entry)
    if kind == "local":
        Path(agents).mkdir(parents=True, exist_ok=True)
        Path(evals).mkdir(parents=True, exist_ok=True)
    elif kind == "remote":
        if not str(entry.get("base_url") or "").strip():
            raise WorkspaceNotFound(f"remote profile missing base_url: {wid}")
        # Local disk writes against a remote profile are forbidden.
        if is_write:
            # Allow resolve for proxy/list; services that write local disks must check is_remote.
            pass

    routes = entry.get("allowed_routes") or []
    if not isinstance(routes, list):
        routes = []

    return NamedWorkspaceContext(
        workspace_id=wid,
        kind=kind,
        label=str(entry.get("label") or wid),
        agents_dir=agents,
        eval_results_dir=evals,
        root_dir=root,
        tenant_id=tenant_id,
        actor_id=actor_id,
        allowed_tenants=tuple(str(x) for x in (entry.get("allowed_tenants") or ["*"])),
        base_url=str(entry.get("base_url") or ""),
        auth_secret_env=str(entry.get("auth_secret_env") or ""),
        allowed_routes=tuple(str(x) for x in routes if str(x).strip()),
    )


def resolve_from_http(
    *,
    method: str,
    headers: Dict[str, str],
    query: Optional[Dict[str, Any]] = None,
    tenant_id: Optional[str] = None,
    actor_id: Optional[str] = None,
) -> NamedWorkspaceContext:
    """resolve_from_http。

    Args:
        method: method 参数。
        headers: headers 参数。
        query: 查询。
        tenant_id: 租户 ID。
        actor_id: actor 标识。
    """
    wid = extract_workspace_id_from_request(headers, query)
    return resolve_named_workspace(
        wid,
        method=method,
        tenant_id=tenant_id,
        actor_id=actor_id,
    )
