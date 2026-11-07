"""Named workspace error types (HTTP mapping in routers)."""
from __future__ import annotations


class WorkspaceError(Exception):
    code: str = "workspace_error"
    http_status: int = 500

    def __init__(self, message: str = "", *, code: str | None = None):
        super().__init__(message or self.code)
        if code:
            self.code = code


class WorkspaceRequired(WorkspaceError):
    code = "workspace_required"
    http_status = 400


class WorkspaceNotFound(WorkspaceError):
    code = "workspace_not_found"
    http_status = 404


class WorkspaceForbidden(WorkspaceError):
    code = "workspace_forbidden"
    http_status = 403
