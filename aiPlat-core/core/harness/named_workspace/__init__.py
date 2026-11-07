"""Named workspace partition (local Agent + eval_results isolation).

Distinct from ActiveWorkspaceContext (repo/coding metadata).
Contract: docs/architecture/plans/workspace-isolation-contract.md
"""
from __future__ import annotations

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
    list_registry_entries,
    load_registry,
)
from core.harness.named_workspace.resolve import (
    NamedWorkspaceContext,
    get_active_named_workspace,
    reset_active_named_workspace,
    resolve_named_workspace,
    set_active_named_workspace,
)

__all__ = [
    "NamedWorkspaceContext",
    "WorkspaceError",
    "WorkspaceForbidden",
    "WorkspaceNotFound",
    "WorkspaceRequired",
    "create_local_workspace",
    "create_remote_workspace",
    "ensure_registry",
    "get_active_named_workspace",
    "list_registry_entries",
    "load_registry",
    "reset_active_named_workspace",
    "resolve_named_workspace",
    "set_active_named_workspace",
]
