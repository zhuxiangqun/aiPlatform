from __future__ import annotations

import os
from typing import Any, Dict, List, Optional


def management_public_url() -> str:
    """Public base URL for management UI (for clickable links in API errors)."""
    return (os.getenv("AIPLAT_MANAGEMENT_PUBLIC_URL") or "").rstrip("/")


def ui_url(path: str) -> str:
    base = management_public_url()
    if not base:
        return path
    if not path.startswith("/"):
        path = "/" + path
    return base + path


def api_url(path: str) -> str:
    # Under the same domain in the current deployment model.
    return ui_url(path)


def governance_links(
    *,
    change_id: Optional[str] = None,
    approval_request_id: Optional[str] = None,
    run_id: Optional[str] = None,
    trace_id: Optional[str] = None,
) -> Dict[str, Any]:
    """Generate consistent UI/API deep links for governance surfaces."""
    try:
        links: Dict[str, Any] = {}
        if change_id:
            links.update(
                {
                    "change_control_ui": ui_url(f"/diagnostics/change-control/{change_id}"),
                    "syscalls_ui": ui_url(f"/diagnostics/syscalls?kind=changeset&target_type=change&target_id={change_id}"),
                    "audit_ui": ui_url(f"/diagnostics/audit?change_id={change_id}"),
                    "evidence_json_api": f"/api/core/change-control/changes/{change_id}/evidence?format=json",
                    "evidence_zip_api": f"/api/core/change-control/changes/{change_id}/evidence?format=zip",
                }
            )
        if approval_request_id:
            links["approvals_ui"] = ui_url("/core/approvals")
            links["audit_request_ui"] = ui_url(f"/diagnostics/audit?request_id={approval_request_id}")
        if run_id:
            links["runs_ui"] = ui_url(f"/diagnostics/runs?run_id={run_id}")
        if trace_id:
            links["traces_ui"] = ui_url(f"/diagnostics/traces?trace_id={trace_id}")
            links["links_ui"] = ui_url(f"/diagnostics/links?trace_id={trace_id}")
        return links
    except Exception:
        # fall back to relative paths (should be rare)
        links: Dict[str, Any] = {}
        if change_id:
            links.update(
                {
                    "change_control_ui": f"/diagnostics/change-control/{change_id}",
                    "syscalls_ui": f"/diagnostics/syscalls?kind=changeset&target_type=change&target_id={change_id}",
                    "audit_ui": f"/diagnostics/audit?change_id={change_id}",
                    "evidence_json_api": f"/api/core/change-control/changes/{change_id}/evidence?format=json",
                    "evidence_zip_api": f"/api/core/change-control/changes/{change_id}/evidence?format=zip",
                }
            )
        if approval_request_id:
            links["approvals_ui"] = "/core/approvals"
            links["audit_request_ui"] = f"/diagnostics/audit?request_id={approval_request_id}"
        if run_id:
            links["runs_ui"] = f"/diagnostics/runs?run_id={run_id}"
        if trace_id:
            links["traces_ui"] = f"/diagnostics/traces?trace_id={trace_id}"
            links["links_ui"] = f"/diagnostics/links?trace_id={trace_id}"
        return links


def change_links(change_id: str) -> Dict[str, Any]:
    """Backward-compatible alias (historically only had syscalls_ui/audit_ui)."""
    return governance_links(change_id=str(change_id))


def gate_error_envelope(
    *,
    code: str,
    message: str,
    change_id: Optional[str] = None,
    approval_request_id: Optional[str] = None,
    links: Optional[Dict[str, Any]] = None,
    next_actions: Optional[List[Dict[str, Any]]] = None,
    detail: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    env: Dict[str, Any] = {"code": str(code), "message": str(message)}
    if change_id:
        env["change_id"] = str(change_id)
    if approval_request_id:
        env["approval_request_id"] = str(approval_request_id)
    lk = dict(links or {})
    if change_id:
        lk.update(governance_links(change_id=str(change_id), approval_request_id=str(approval_request_id) if approval_request_id else None))
    elif approval_request_id:
        lk.update(governance_links(approval_request_id=str(approval_request_id)))
    if lk:
        env["links"] = lk
    if next_actions:
        env["next_actions"] = next_actions
    if detail:
        env["detail"] = detail
    return env

