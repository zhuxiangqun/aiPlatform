from __future__ import annotations

import os
import uuid
from typing import Any, Dict, List, Optional, Tuple

from fastapi import HTTPException

from core.api.utils.governance import api_url, gate_error_envelope, ui_url
from core.governance.changeset import record_changeset


def new_change_id() -> str:
    return f"chg-{uuid.uuid4().hex[:12]}"


def autosmoke_enforce(*, store: Any) -> bool:
    # Env override has highest priority.
    v = (os.getenv("AIPLAT_AUTOSMOKE_ENFORCE", "") or "").strip().lower()
    if v:
        return v in {"1", "true", "yes", "y", "on"}
    try:
        if not store or not hasattr(store, "get_global_setting_sync"):
            return False
        row = store.get_global_setting_sync(key="autosmoke")
        cfg = (row or {}).get("value") if isinstance(row, dict) else None
        return bool((cfg or {}).get("enforce")) is True
    except Exception:
        return False


def _is_verified_meta(meta: Optional[Dict[str, Any]]) -> bool:
    if not isinstance(meta, dict):
        return False
    v = meta.get("verification")
    if isinstance(v, dict):
        return str(v.get("status") or "") == "verified"
    return False


async def require_targets_verified(
    *,
    store: Any,
    targets: List[Tuple[str, str]],
    workspace_agent_manager: Any = None,
    workspace_skill_manager: Any = None,
    skill_manager: Any = None,
    workspace_mcp_manager: Any = None,
    mcp_manager: Any = None,
) -> None:
    """Gate publish/enable actions by autosmoke verification status."""
    if not autosmoke_enforce(store=store):
        return

    missing: List[Dict[str, Any]] = []
    for ttype, tid in targets:
        ttype = str(ttype or "").strip().lower()
        tid = str(tid or "").strip()
        if not ttype or not tid:
            continue
        if ttype == "agent":
            if not workspace_agent_manager:
                missing.append({"type": ttype, "id": tid, "reason": "agent_manager_unavailable"})
                continue
            a = await workspace_agent_manager.get_agent(tid)
            meta = getattr(a, "metadata", None) if a else None
            ver = meta.get("verification") if isinstance(meta, dict) else None
            if not a or not _is_verified_meta(meta):
                item = {"type": ttype, "id": tid, "reason": "unverified", "verification": ver or {}}
                jr = (ver or {}).get("job_run_id") if isinstance(ver, dict) else None
                jid = (ver or {}).get("job_id") if isinstance(ver, dict) else None
                if isinstance(jr, str) and jr:
                    item["diagnostics_url"] = ui_url(f"/diagnostics/runs?run_id={jr}")
                    if store:
                        try:
                            item["job_run"] = await store.get_job_run(jr)
                        except Exception:
                            pass
                if isinstance(jid, str) and jid:
                    item["retry"] = {"method": "POST", "api_url": api_url(f"/api/core/jobs/{jid}/run"), "job_id": jid}
                missing.append(item)
        elif ttype == "skill":
            s = None
            mgr_kind = "workspace"
            if workspace_skill_manager:
                s = await workspace_skill_manager.get_skill(tid)
            if not s and skill_manager:
                mgr_kind = "engine"
                s = await skill_manager.get_skill(tid)
            meta = getattr(s, "metadata", None) if s else None
            ver = meta.get("verification") if isinstance(meta, dict) else None
            if not s or not _is_verified_meta(meta):
                item = {"type": ttype, "id": tid, "reason": "unverified", "verification": ver or {}, "scope": mgr_kind}
                jr = (ver or {}).get("job_run_id") if isinstance(ver, dict) else None
                jid = (ver or {}).get("job_id") if isinstance(ver, dict) else None
                if isinstance(jr, str) and jr:
                    item["diagnostics_url"] = ui_url(f"/diagnostics/runs?run_id={jr}")
                    if store:
                        try:
                            item["job_run"] = await store.get_job_run(jr)
                        except Exception:
                            pass
                if isinstance(jid, str) and jid:
                    item["retry"] = {"method": "POST", "api_url": api_url(f"/api/core/jobs/{jid}/run"), "job_id": jid}
                missing.append(item)
        elif ttype == "mcp":
            m = None
            mgr_kind = "workspace"
            if workspace_mcp_manager:
                m = workspace_mcp_manager.get_server(tid)
            if not m and mcp_manager:
                mgr_kind = "engine"
                m = mcp_manager.get_server(tid)
            meta = getattr(m, "metadata", None) if m else None
            ver = meta.get("verification") if isinstance(meta, dict) else None
            if not m or not _is_verified_meta(meta):
                item = {"type": ttype, "id": tid, "reason": "unverified", "verification": ver or {}, "scope": mgr_kind}
                jr = (ver or {}).get("job_run_id") if isinstance(ver, dict) else None
                jid = (ver or {}).get("job_id") if isinstance(ver, dict) else None
                if isinstance(jr, str) and jr:
                    item["diagnostics_url"] = ui_url(f"/diagnostics/runs?run_id={jr}")
                    if store:
                        try:
                            item["job_run"] = await store.get_job_run(jr)
                        except Exception:
                            pass
                if isinstance(jid, str) and jid:
                    item["retry"] = {"method": "POST", "api_url": api_url(f"/api/core/jobs/{jid}/run"), "job_id": jid}
                missing.append(item)
        else:
            continue

    if missing:
        raise HTTPException(
            status_code=403,
            detail={
                "code": "unverified",
                "message": "autosmoke must pass before publish/enable",
                "hint": "查看 targets[*].diagnostics_url 获取失败原因；或等待 autosmoke 完成后再重试",
                "targets": missing,
            },
        )


async def gate_with_change_control(
    *,
    store: Any,
    operation: str,
    targets: List[Tuple[str, str]],
    actor: Optional[Dict[str, Any]] = None,
    approval_request_id: Optional[str] = None,
    workspace_agent_manager: Any = None,
    workspace_skill_manager: Any = None,
    skill_manager: Any = None,
    workspace_mcp_manager: Any = None,
    mcp_manager: Any = None,
) -> str:
    """Wrap require_targets_verified with a stable change_id and consistent error envelope."""
    change_id = new_change_id()
    actor0 = actor or {}
    try:
        await require_targets_verified(
            store=store,
            targets=targets,
            workspace_agent_manager=workspace_agent_manager,
            workspace_skill_manager=workspace_skill_manager,
            skill_manager=skill_manager,
            workspace_mcp_manager=workspace_mcp_manager,
            mcp_manager=mcp_manager,
        )
        return change_id
    except HTTPException as e:
        if isinstance(e.detail, dict):
            detail0 = dict(e.detail)
        else:
            detail0 = {"code": "blocked", "message": str(e.detail)}
        code = str(detail0.get("code") or "blocked")
        msg = str(detail0.get("message") or "blocked by gate")

        detail = gate_error_envelope(
            code=code,
            message=msg,
            change_id=change_id,
            approval_request_id=approval_request_id,
            links=detail0.get("links") if isinstance(detail0.get("links"), dict) else None,
            next_actions=[
                {"type": "open_change_control", "label": "打开变更控制台", "url": ui_url(f"/diagnostics/change-control/{change_id}")},
                {"type": "open_syscalls", "label": "打开 Syscalls", "url": ui_url(f"/diagnostics/syscalls?kind=changeset&target_type=change&target_id={change_id}")},
                {"type": "open_audit", "label": "打开 Audit", "url": ui_url(f"/diagnostics/audit?change_id={change_id}")},
                {"type": "download_evidence", "label": "导出证据包（zip）", "url": ui_url(f"/diagnostics/change-control/{change_id}")},
                {"type": "retry_autosmoke", "label": "重试 autosmoke", "method": "POST", "api_url": f"/api/core/change-control/changes/{change_id}/autosmoke"},
                *(
                    [{"type": "open_approvals", "label": "打开审批中心", "url": ui_url("/core/approvals"), "approval_request_id": str(approval_request_id)}]
                    if approval_request_id
                    else []
                ),
            ],
            detail={"operation": operation, "targets": [{"type": t[0], "id": t[1]} for t in targets]},
        )

        # record blocked change event (best-effort)
        await record_changeset(
            store=store,
            name=f"gate:{operation}",
            target_type="change",
            target_id=change_id,
            status="blocked",
            args={"operation": operation, "targets": [{"type": t[0], "id": t[1]} for t in targets], "gate": detail},
            user_id=str(actor0.get("actor_id") or "admin"),
            session_id=str(actor0.get("session_id") or "") or None,
            tenant_id=str(actor0.get("tenant_id") or "") or None,
            approval_request_id=approval_request_id,
        )
        # audit (best-effort)
        try:
            if store:
                await store.add_audit_log(
                    action="gate_blocked",
                    status="failed",
                    tenant_id=str(actor0.get("tenant_id") or "") or None,
                    actor_id=str(actor0.get("actor_id") or "admin"),
                    actor_role=str(actor0.get("actor_role") or "") or None,
                    resource_type="change",
                    resource_id=str(change_id),
                    change_id=str(change_id),
                    request_id=str(approval_request_id) if approval_request_id else None,
                    detail={"operation": operation, "targets": [{"type": t[0], "id": t[1]} for t in targets], "gate": detail},
                )
        except Exception:
            pass
        raise HTTPException(status_code=e.status_code, detail=detail)
