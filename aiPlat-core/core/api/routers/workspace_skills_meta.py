from __future__ import annotations

import json
import os
import time as _time
import uuid
from typing import Any, Dict, Optional

from fastapi import APIRouter, Depends, HTTPException, Request

from core.api.deps.rbac import actor_from_http, rbac_guard
from core.api.utils.governance import gate_error_envelope, governance_links, ui_url
from core.api.utils.skills_meta import (
    load_skill_spec_v2_schema,
    permission_catalog,
    req_tenant_channel,
    schema_version,
    skill_governance_preview,
)
from core.harness.integration import KernelRuntime
from core.harness.kernel.runtime import get_kernel_runtime
from core.schemas import SkillInstallerInstallRequest, SkillInstallerUpdateRequest

router = APIRouter()


def _store(rt: Optional[KernelRuntime]):
    return getattr(rt, "execution_store", None) if rt else None


def _approval_manager(rt: Optional[KernelRuntime]):
    return getattr(rt, "approval_manager", None) if rt else None


def _ws_skill_manager(rt: Optional[KernelRuntime]):
    return getattr(rt, "workspace_skill_manager", None) if rt else None


RuntimeDep = Optional[KernelRuntime]


@router.post("/workspace/skills/governance-preview")
async def preview_workspace_skill_governance(request: Dict[str, Any], http_request: Request, rt: RuntimeDep = Depends(get_kernel_runtime)):
    """Preview governance/risk/approval hints for wizard UX (workspace scope)."""
    deny = await rbac_guard(
        http_request=http_request,
        payload=request or {},
        action="create",
        resource_type="skill",
        resource_id=str((request or {}).get("skill_id") or (request or {}).get("name") or "") or None,
    )
    if deny:
        return deny
    req = dict(request or {})
    req.setdefault("actor_id", "admin")
    req.setdefault("tenant_id", "ops")
    return skill_governance_preview(scope="workspace", payload=req, approval_manager=_approval_manager(rt))


@router.get("/workspace/skills/meta/permissions-catalog")
async def workspace_permissions_catalog(http_request: Request, tenant_id: Optional[str] = None, channel: Optional[str] = None):
    """Permissions catalog for UI (workspace scope)."""
    deny = await rbac_guard(
        http_request=http_request,
        payload={},
        action="create",
        resource_type="skill",
        resource_id=None,
    )
    if deny:
        return deny
    from core.services.config_registry_store import ConfigRegistryKey, get_config_registry_store

    ctx = req_tenant_channel(http_request, tenant_id=tenant_id, channel=channel)
    store = get_config_registry_store()
    key = ConfigRegistryKey(asset_type="permissions_catalog", scope="workspace", tenant_id=ctx["tenant_id"], channel=ctx["channel"])
    published = await store.get_published(key=key)
    if published:
        ver, payload = published
        if isinstance(payload, dict) and "items" in payload:
            out = dict(payload)
            out["source"] = "published"
            out["version"] = ver
            out["tenant_id"] = ctx["tenant_id"]
            out["channel"] = ctx["channel"]
            return out
    out = permission_catalog(scope="workspace")
    out.update({"source": "default", "tenant_id": ctx["tenant_id"], "channel": ctx["channel"], "version": "default"})
    return out


@router.get("/workspace/skills/meta/skill-spec-v2-schema")
async def workspace_skill_spec_v2_schema(http_request: Request, tenant_id: Optional[str] = None, channel: Optional[str] = None):
    """SkillSpec v2 schema registry endpoint (workspace scope)."""
    deny = await rbac_guard(
        http_request=http_request,
        payload={},
        action="create",
        resource_type="skill",
        resource_id=None,
    )
    if deny:
        return deny
    from core.services.config_registry_store import ConfigRegistryKey, get_config_registry_store

    ctx = req_tenant_channel(http_request, tenant_id=tenant_id, channel=channel)
    store = get_config_registry_store()
    key = ConfigRegistryKey(asset_type="skill_spec_v2_schema", scope="workspace", tenant_id=ctx["tenant_id"], channel=ctx["channel"])
    published = await store.get_published(key=key)
    if published:
        ver, payload = published
        if isinstance(payload, dict) and "properties" in payload:
            return {"schema": payload, "version": ver, "source": "published", **ctx}
    s = load_skill_spec_v2_schema()
    return {"schema": s, "version": schema_version(s), "source": "default", **ctx}


@router.post("/workspace/skills/meta/skill-spec-v2-schema/publish")
async def workspace_publish_skill_spec_v2_schema(request: Dict[str, Any], http_request: Request, tenant_id: Optional[str] = None, channel: Optional[str] = None):
    """Publish a new SkillSpec v2 schema for a tenant/channel (workspace scope)."""
    deny = await rbac_guard(
        http_request=http_request,
        payload=request or {},
        action="update",
        resource_type="skill",
        resource_id="meta:skill-spec-v2-schema",
    )
    if deny:
        return deny
    from core.services.config_registry_store import ConfigRegistryKey, get_config_registry_store

    ctx = req_tenant_channel(http_request, tenant_id=tenant_id, channel=channel)
    schema_obj = request.get("schema") if isinstance(request, dict) else None
    if not isinstance(schema_obj, dict):
        schema_obj = load_skill_spec_v2_schema()
    actor = str(http_request.headers.get("X-AIPLAT-ACTOR-ID") or "admin")
    note = str(request.get("note") or "") if isinstance(request, dict) else ""
    store = get_config_registry_store()
    key = ConfigRegistryKey(asset_type="skill_spec_v2_schema", scope="workspace", tenant_id=ctx["tenant_id"], channel=ctx["channel"])
    ver = await store.publish(key=key, payload=schema_obj, actor=actor, note=note or None)
    return {"status": "published", "version": ver, **ctx}


@router.post("/workspace/skills/meta/skill-spec-v2-schema/rollback")
async def workspace_rollback_skill_spec_v2_schema(http_request: Request, tenant_id: Optional[str] = None, channel: Optional[str] = None):
    """Rollback to previous published SkillSpec v2 schema (workspace scope)."""
    deny = await rbac_guard(
        http_request=http_request,
        payload={},
        action="update",
        resource_type="skill",
        resource_id="meta:skill-spec-v2-schema",
    )
    if deny:
        return deny
    from core.services.config_registry_store import ConfigRegistryKey, get_config_registry_store

    ctx = req_tenant_channel(http_request, tenant_id=tenant_id, channel=channel)
    actor = str(http_request.headers.get("X-AIPLAT-ACTOR-ID") or "admin")
    store = get_config_registry_store()
    key = ConfigRegistryKey(asset_type="skill_spec_v2_schema", scope="workspace", tenant_id=ctx["tenant_id"], channel=ctx["channel"])
    ver = await store.rollback(key=key, actor=actor, note="rollback")
    return {"status": "rolled_back", "version": ver, **ctx}


@router.post("/workspace/skills/meta/permissions-catalog/publish")
async def workspace_publish_permissions_catalog(request: Dict[str, Any], http_request: Request, tenant_id: Optional[str] = None, channel: Optional[str] = None):
    """Publish a new permissions catalog for a tenant/channel (workspace scope)."""
    deny = await rbac_guard(
        http_request=http_request,
        payload=request or {},
        action="update",
        resource_type="skill",
        resource_id="meta:permissions-catalog",
    )
    if deny:
        return deny
    from core.services.config_registry_store import ConfigRegistryKey, get_config_registry_store

    ctx = req_tenant_channel(http_request, tenant_id=tenant_id, channel=channel)
    payload = request.get("catalog") if isinstance(request, dict) else None
    if not isinstance(payload, dict) or "items" not in payload:
        payload = permission_catalog(scope="workspace")
    actor = str(http_request.headers.get("X-AIPLAT-ACTOR-ID") or "admin")
    note = str(request.get("note") or "") if isinstance(request, dict) else ""
    store = get_config_registry_store()
    key = ConfigRegistryKey(asset_type="permissions_catalog", scope="workspace", tenant_id=ctx["tenant_id"], channel=ctx["channel"])
    ver = await store.publish(key=key, payload=payload, actor=actor, note=note or None)
    return {"status": "published", "version": ver, **ctx}


@router.post("/workspace/skills/meta/permissions-catalog/rollback")
async def workspace_rollback_permissions_catalog(http_request: Request, tenant_id: Optional[str] = None, channel: Optional[str] = None):
    """Rollback to previous published permissions catalog (workspace scope)."""
    deny = await rbac_guard(
        http_request=http_request,
        payload={},
        action="update",
        resource_type="skill",
        resource_id="meta:permissions-catalog",
    )
    if deny:
        return deny
    from core.services.config_registry_store import ConfigRegistryKey, get_config_registry_store

    ctx = req_tenant_channel(http_request, tenant_id=tenant_id, channel=channel)
    actor = str(http_request.headers.get("X-AIPLAT-ACTOR-ID") or "admin")
    store = get_config_registry_store()
    key = ConfigRegistryKey(asset_type="permissions_catalog", scope="workspace", tenant_id=ctx["tenant_id"], channel=ctx["channel"])
    ver = await store.rollback(key=key, actor=actor, note="rollback")
    return {"status": "rolled_back", "version": ver, **ctx}


def _unified_diff_text(a: Any, b: Any) -> str:
    try:
        aa = json.dumps(a, ensure_ascii=False, indent=2, sort_keys=True).splitlines()
        bb = json.dumps(b, ensure_ascii=False, indent=2, sort_keys=True).splitlines()
    except Exception:
        aa = str(a).splitlines()
        bb = str(b).splitlines()
    import difflib

    return "\n".join(difflib.unified_diff(aa, bb, fromfile="current", tofile="proposed", lineterm=""))


def _assess_schema_change(current: Optional[Dict[str, Any]], proposed: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    cur = current or {}
    nxt = proposed or {}
    breaking = []
    warnings = []

    cur_req = set(cur.get("required") or [])
    nxt_req = set(nxt.get("required") or [])
    removed_required = sorted(list(cur_req - nxt_req))
    if removed_required:
        breaking.append({"type": "required_removed", "fields": removed_required})

    cur_props = cur.get("properties") or {}
    nxt_props = nxt.get("properties") or {}
    for k, v in (cur_props or {}).items():
        if k not in nxt_props:
            if k in cur_req:
                breaking.append({"type": "required_field_removed", "field": k})
            else:
                warnings.append({"type": "field_removed", "field": k})
            continue
        t1 = str((v or {}).get("type") or "")
        t2 = str((nxt_props.get(k) or {}).get("type") or "")
        if t1 and t2 and t1 != t2:
            breaking.append({"type": "field_type_changed", "field": k, "from": t1, "to": t2})

    # output_schema markdown invariant
    out = nxt_props.get("output_schema") or {}
    out_def = out.get("default") if isinstance(out, dict) else None
    markdown_ok = False
    try:
        if isinstance(out_def, dict) and "markdown" in out_def:
            markdown_ok = True
    except Exception:
        markdown_ok = False
    if not markdown_ok:
        breaking.append({"type": "markdown_constraint_missing", "field": "output_schema.markdown"})

    risk = "low"
    if breaking:
        risk = "high"
    elif warnings:
        risk = "medium"
    return {"risk_level": risk, "breaking_changes": breaking, "warnings": warnings}


def _assess_permissions_catalog_change(current: Optional[Dict[str, Any]], proposed: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    cur_items = {str(it.get("permission") or it.get("value") or ""): it for it in (current or {}).get("items") or []}
    nxt_items = {str(it.get("permission") or it.get("value") or ""): it for it in (proposed or {}).get("items") or []}
    breaking = []
    warnings = []

    removed = sorted([k for k in cur_items.keys() if k and k not in nxt_items])
    if removed:
        warnings.append({"type": "permission_removed", "permissions": removed})

    for p, it in nxt_items.items():
        if not p:
            continue
        if p not in cur_items:
            # new permission
            if bool(it.get("default_selected")) and str(it.get("risk_level") or "").lower() == "high":
                breaking.append({"type": "high_risk_default_added", "permission": p})
            else:
                warnings.append({"type": "permission_added", "permission": p})
            continue
        # existing - risk label changes
        r1 = str(cur_items[p].get("risk_level") or "").lower()
        r2 = str(it.get("risk_level") or "").lower()
        if r1 and r2 and r1 != r2:
            warnings.append({"type": "risk_level_changed", "permission": p, "from": r1, "to": r2})
        if bool(cur_items[p].get("default_selected")) != bool(it.get("default_selected")):
            # making high-risk default is breaking
            if bool(it.get("default_selected")) and r2 == "high":
                breaking.append({"type": "high_risk_default_enabled", "permission": p})
            else:
                warnings.append(
                    {
                        "type": "default_selected_changed",
                        "permission": p,
                        "from": bool(cur_items[p].get("default_selected")),
                        "to": bool(it.get("default_selected")),
                    }
                )

    risk = "low"
    if breaking:
        risk = "high"
    elif warnings:
        risk = "medium"
    return {"risk_level": risk, "breaking_changes": breaking, "warnings": warnings}


def _assess_config_change(*, asset_type: str, current: Any, proposed: Any) -> Dict[str, Any]:
    at = str(asset_type)
    if at == "skill_spec_v2_schema":
        base = _assess_schema_change(current if isinstance(current, dict) else None, proposed if isinstance(proposed, dict) else None)
    elif at == "permissions_catalog":
        base = _assess_permissions_catalog_change(current if isinstance(current, dict) else None, proposed if isinstance(proposed, dict) else None)
    else:
        base = {"risk_level": "medium", "breaking_changes": [], "warnings": [{"type": "unknown_asset_type"}]}
    # NOTE: channel-specific gates are decided by caller (stable -> approval; canary -> confirm phrase).
    requires_confirmation = base.get("risk_level") == "high"
    confirm_phrase = f"PUBLISH {at} HIGH-RISK" if requires_confirmation else None
    base.update({"requires_confirmation": requires_confirmation, "confirm_phrase": confirm_phrase, "requires_approval": False})
    return base


async def _create_config_publish_approval_request(
    *,
    store: Any,
    actor_id: str,
    actor_role: str,
    tenant_id: str,
    scope: str,
    channel: str,
    asset_type: str,
    version: Optional[str],
    payload: Any,
    note: Optional[str],
    assessment: Optional[Dict[str, Any]] = None,
    diff: Optional[str] = None,
) -> Optional[str]:
    """
    Create a manual approval request for config publishing.
    Stored in execution DB so it shows up in /core/approvals.
    """
    if not store:
        return None
    try:
        from core.utils.ids import new_prefixed_id

        now = _time.time()
        request_id = str(uuid.uuid4())
        change_id = new_prefixed_id("chg")
        # 24h SLA by default (product-level)
        expires_at = now + 24 * 3600
        summary_lines = []
        try:
            if isinstance(assessment, dict):
                summary_lines.append(f"risk_level={assessment.get('risk_level')}")
                bc = assessment.get("breaking_changes") or []
                wn = assessment.get("warnings") or []
                summary_lines.append(f"breaking_changes={len(bc)} warnings={len(wn)}")
                if bc:
                    summary_lines.append(f"breaking={json.dumps(bc[:5], ensure_ascii=False)}")
                if wn:
                    summary_lines.append(f"warnings={json.dumps(wn[:5], ensure_ascii=False)}")
        except Exception:
            pass
        if version:
            summary_lines.append(f"to_version={version}")
        assessment_summary = "\n".join([x for x in summary_lines if x]).strip()
        diff_excerpt = None
        try:
            if isinstance(diff, str) and diff:
                lines = diff.splitlines()
                diff_excerpt = "\n".join(lines[:120])
        except Exception:
            diff_excerpt = None

        record = {
            "request_id": request_id,
            "user_id": actor_id or "admin",
            "operation": "config:publish",
            "details": f"publish {asset_type} to {channel} (scope={scope}, tenant={tenant_id})\n{assessment_summary}",
            "rule_id": "config_publish_high_risk_stable",
            "rule_type": "sensitive_operation",
            "status": "pending",
            "amount": None,
            "batch_size": None,
            "is_first_time": False,
            "created_at": now,
            "updated_at": now,
            "expires_at": expires_at,
            "metadata": {
                "tenant_id": tenant_id,
                "actor_id": actor_id,
                "actor_role": actor_role,
                "change_id": change_id,
                "operation_context": {
                    "action": "config_registry_publish",
                    "asset_type": asset_type,
                    "scope": scope,
                    "tenant_id": tenant_id,
                    "channel": channel,
                    "version": version,
                    "payload": payload,
                    "note": note,
                    "assessment": assessment,
                    "assessment_summary": assessment_summary,
                    "diff_excerpt": diff_excerpt,
                    "change_id": change_id,
                },
            },
            "result": None,
        }
        await store.upsert_approval_request(record)

        # Emit a change control event to link approval_request -> change_id.
        try:
            await store.add_syscall_event(
                {
                    "trace_id": None,
                    "span_id": None,
                    "run_id": None,
                    "tenant_id": tenant_id,
                    "kind": "changeset",
                    "name": "config_publish_pending",
                    "status": "pending",
                    "args": {
                        "asset_type": asset_type,
                        "scope": scope,
                        "channel": channel,
                        "tenant_id": tenant_id,
                        "to_version": version,
                        "note": note,
                        "risk_level": (assessment or {}).get("risk_level") if isinstance(assessment, dict) else None,
                    },
                    "result": {"approval_request_id": request_id},
                    "target_type": "change",
                    "target_id": change_id,
                    "user_id": actor_id,
                    "session_id": None,
                    "approval_request_id": request_id,
                    "created_at": now,
                }
            )
        except Exception:
            pass
        return request_id
    except Exception:
        return None


async def _create_config_rollback_approval_request(
    *,
    store: Any,
    actor_id: str,
    actor_role: str,
    tenant_id: str,
    scope: str,
    channel: str,
    asset_type: str,
    from_version: Optional[str],
    to_version: Optional[str],
    note: Optional[str],
) -> Optional[str]:
    """Create approval request for stable rollback."""
    if not store:
        return None
    try:
        from core.utils.ids import new_prefixed_id

        now = _time.time()
        request_id = str(uuid.uuid4())
        change_id = new_prefixed_id("chg")
        expires_at = now + 24 * 3600
        summary = f"rollback {asset_type} {from_version} -> {to_version} (scope={scope}, tenant={tenant_id}, channel={channel})"

        record = {
            "request_id": request_id,
            "user_id": actor_id or "admin",
            "operation": "config:rollback",
            "details": summary,
            "rule_id": "config_rollback_stable",
            "rule_type": "sensitive_operation",
            "status": "pending",
            "amount": None,
            "batch_size": None,
            "is_first_time": False,
            "created_at": now,
            "updated_at": now,
            "expires_at": expires_at,
            "metadata": {
                "tenant_id": tenant_id,
                "actor_id": actor_id,
                "actor_role": actor_role,
                "change_id": change_id,
                "operation_context": {
                    "action": "config_registry_rollback",
                    "asset_type": asset_type,
                    "scope": scope,
                    "tenant_id": tenant_id,
                    "channel": channel,
                    "from_version": from_version,
                    "to_version": to_version,
                    "note": note,
                    "change_id": change_id,
                },
            },
            "result": None,
        }
        await store.upsert_approval_request(record)

        # changeset pending event (links to change control)
        try:
            await store.add_syscall_event(
                {
                    "trace_id": None,
                    "span_id": None,
                    "run_id": None,
                    "tenant_id": tenant_id,
                    "kind": "changeset",
                    "name": "config_rollback_pending",
                    "status": "pending",
                    "args": {
                        "asset_type": asset_type,
                        "scope": scope,
                        "channel": channel,
                        "tenant_id": tenant_id,
                        "from_version": from_version,
                        "to_version": to_version,
                        "note": note,
                    },
                    "result": {"approval_request_id": request_id},
                    "target_type": "change",
                    "target_id": change_id,
                    "user_id": actor_id,
                    "session_id": None,
                    "approval_request_id": request_id,
                    "created_at": now,
                }
            )
        except Exception:
            pass
        return request_id
    except Exception:
        return None


@router.get("/workspace/skills/meta/config-registry/status")
async def workspace_config_registry_status(
    http_request: Request,
    asset_type: str,
    scope: str = "workspace",
    tenant_id: Optional[str] = None,
    channel: Optional[str] = None,
):
    """UI: get published status (version/prev/updated_by/updated_at)."""
    deny = await rbac_guard(
        http_request=http_request,
        payload={},
        action="read",
        resource_type="skill",
        resource_id=f"meta:{asset_type}",
    )
    if deny:
        return deny
    from core.services.config_registry_store import ConfigRegistryKey, get_config_registry_store

    ctx = req_tenant_channel(http_request, tenant_id=tenant_id, channel=channel)
    sc = (scope or "workspace").strip().lower()
    key = ConfigRegistryKey(asset_type=str(asset_type), scope=sc, tenant_id=ctx["tenant_id"], channel=ctx["channel"])
    store = get_config_registry_store()
    row = await store.get_published_row(key=key)
    return {"status": "ok", "published": row, **ctx, "scope": sc, "asset_type": str(asset_type)}


@router.get("/workspace/skills/meta/config-registry/versions")
async def workspace_config_registry_versions(
    http_request: Request,
    asset_type: str,
    scope: str = "workspace",
    tenant_id: Optional[str] = None,
    limit: int = 50,
    offset: int = 0,
):
    """UI: list versions for an asset."""
    deny = await rbac_guard(
        http_request=http_request,
        payload={},
        action="read",
        resource_type="skill",
        resource_id=f"meta:{asset_type}",
    )
    if deny:
        return deny
    from core.services.config_registry_store import get_config_registry_store

    ctx = req_tenant_channel(http_request, tenant_id=tenant_id, channel="stable")
    sc = (scope or "workspace").strip().lower()
    store = get_config_registry_store()
    out = await store.list_versions(asset_type=str(asset_type), scope=sc, tenant_id=ctx["tenant_id"], limit=limit, offset=offset)
    out.update({"status": "ok", "tenant_id": ctx["tenant_id"], "scope": sc, "asset_type": str(asset_type)})
    return out


@router.get("/workspace/skills/meta/config-registry/asset")
async def workspace_config_registry_asset(
    http_request: Request,
    asset_type: str,
    scope: str = "workspace",
    tenant_id: Optional[str] = None,
    version: str = "",
):
    """UI: fetch one version payload (for preview/diff)."""
    deny = await rbac_guard(
        http_request=http_request,
        payload={},
        action="read",
        resource_type="skill",
        resource_id=f"meta:{asset_type}",
    )
    if deny:
        return deny
    from core.services.config_registry_store import get_config_registry_store

    ctx = req_tenant_channel(http_request, tenant_id=tenant_id, channel="stable")
    sc = (scope or "workspace").strip().lower()
    store = get_config_registry_store()
    item = await store.get_asset(asset_type=str(asset_type), scope=sc, tenant_id=ctx["tenant_id"], version=version)
    return {"status": "ok", "item": item, "tenant_id": ctx["tenant_id"], "scope": sc, "asset_type": str(asset_type)}


@router.post("/workspace/skills/meta/config-registry/publish")
async def workspace_config_registry_publish(
    request: Dict[str, Any],
    http_request: Request,
    asset_type: str,
    scope: str = "workspace",
    tenant_id: Optional[str] = None,
    channel: Optional[str] = None,
    rt: RuntimeDep = Depends(get_kernel_runtime),
):
    """UI: publish a specific version (or provided payload) to stable/canary."""
    deny = await rbac_guard(
        http_request=http_request,
        payload=request or {},
        action="update",
        resource_type="skill",
        resource_id=f"meta:{asset_type}",
    )
    if deny:
        return deny
    from core.services.config_registry_store import ConfigRegistryKey, get_config_registry_store

    ctx = req_tenant_channel(http_request, tenant_id=tenant_id, channel=channel)
    sc = (scope or "workspace").strip().lower()
    actor = str(http_request.headers.get("X-AIPLAT-ACTOR-ID") or "admin")
    note = str((request or {}).get("note") or "") or None
    ver = str((request or {}).get("version") or "").strip() or None
    payload = (request or {}).get("payload")
    confirm_phrase = str((request or {}).get("confirm_phrase") or "").strip()
    approval_request_id = str((request or {}).get("approval_request_id") or "").strip()

    if payload is None:
        # If version is provided, try read existing asset payload
        store0 = get_config_registry_store()
        if ver:
            item = await store0.get_asset(asset_type=str(asset_type), scope=sc, tenant_id=ctx["tenant_id"], version=ver)
            if item:
                payload = item.get("payload")
        if payload is None:
            # fallback: built-in defaults
            payload = load_skill_spec_v2_schema() if str(asset_type) == "skill_spec_v2_schema" else permission_catalog(scope=sc)

    store = get_config_registry_store()
    # Gate high-risk changes:
    # - stable: require approval request (product-level governance)
    # - canary: require confirm phrase (lightweight gate)
    try:
        key0 = ConfigRegistryKey(asset_type=str(asset_type), scope=sc, tenant_id=ctx["tenant_id"], channel=ctx["channel"])
        cur = await store.get_published(key=key0)
        cur_payload = cur[1] if cur else None
        assessment = _assess_config_change(asset_type=str(asset_type), current=cur_payload, proposed=payload)
        risk_high = assessment.get("risk_level") == "high"

        approval_mgr = _approval_manager(rt)
        if risk_high and ctx["channel"] == "stable":
            # If caller provides an approval_request_id, require it to be approved (best-effort).
            if approval_request_id:
                if not approval_mgr:
                    raise HTTPException(status_code=503, detail="ApprovalManager not initialized")
                r = (
                    await approval_mgr.get_request_async(str(approval_request_id))  # type: ignore[attr-defined]
                    if hasattr(approval_mgr, "get_request_async")
                    else approval_mgr.get_request(str(approval_request_id))
                )
                if not r:
                    raise HTTPException(status_code=404, detail="approval_request_not_found")
                from core.harness.infrastructure.approval.types import RequestStatus

                if r.status not in (RequestStatus.APPROVED, RequestStatus.AUTO_APPROVED):
                    raise HTTPException(
                        status_code=409,
                        detail=gate_error_envelope(
                            code="approval_required",
                            message=f"approval_required: status={r.status.value}",
                            approval_request_id=str(approval_request_id),
                            next_actions=[
                                {"type": "open_approvals", "label": "打开审批中心", "url": ui_url("/core/approvals"), "approval_request_id": str(approval_request_id)}
                            ],
                        ),
                    )
            else:
                # Create an approval request and block publishing.
                actor_role = str(http_request.headers.get("X-AIPLAT-ACTOR-ROLE") or "admin")
                diff_text = None
                try:
                    diff_text = _unified_diff_text(cur_payload, payload)
                except Exception:
                    diff_text = None
                rid = await _create_config_publish_approval_request(
                    store=_store(rt),
                    actor_id=actor,
                    actor_role=actor_role,
                    tenant_id=ctx["tenant_id"],
                    scope=sc,
                    channel=ctx["channel"],
                    asset_type=str(asset_type),
                    version=ver,
                    payload=payload,
                    note=note,
                    assessment=assessment if isinstance(assessment, dict) else None,
                    diff=diff_text,
                )
                raise HTTPException(
                    status_code=409,
                    detail=gate_error_envelope(
                        code="approval_required",
                        message="high_risk_publish_requires_approval",
                        approval_request_id=str(rid) if rid else None,
                        next_actions=[
                            {"type": "open_approvals", "label": "打开审批中心", "url": ui_url("/core/approvals"), "approval_request_id": str(rid) if rid else None},
                        ],
                    ),
                )

        if risk_high and ctx["channel"] == "canary":
            expected = str(assessment.get("confirm_phrase") or "").strip()
            if expected and confirm_phrase != expected:
                raise HTTPException(status_code=400, detail={"code": "confirm_phrase_required", "confirm_phrase": expected, "risk_level": assessment.get("risk_level")})
    except HTTPException:
        raise
    except Exception:
        pass

    key = ConfigRegistryKey(asset_type=str(asset_type), scope=sc, tenant_id=ctx["tenant_id"], channel=ctx["channel"])
    v2 = await store.publish(key=key, payload=payload, actor=actor, note=note, version=ver)

    # Emit change control event for direct publish (non-approval flows)
    try:
        from core.utils.ids import new_prefixed_id

        es = _store(rt)
        if es:
            chg = new_prefixed_id("chg")
            await es.add_syscall_event(
                {
                    "trace_id": None,
                    "span_id": None,
                    "run_id": None,
                    "tenant_id": ctx["tenant_id"],
                    "kind": "changeset",
                    "name": "config_publish_direct",
                    "status": "published",
                    "args": {"asset_type": str(asset_type), "scope": sc, "channel": ctx["channel"], "tenant_id": ctx["tenant_id"], "to_version": v2, "note": note},
                    "result": {"version": v2},
                    "target_type": "change",
                    "target_id": chg,
                    "user_id": actor,
                    "session_id": None,
                    "approval_request_id": approval_request_id or None,
                }
            )
    except Exception:
        pass
    return {"status": "published", "version": v2, **ctx, "scope": sc, "asset_type": str(asset_type)}


@router.post("/workspace/skills/meta/config-registry/rollback")
async def workspace_config_registry_rollback(
    http_request: Request,
    asset_type: str,
    scope: str = "workspace",
    tenant_id: Optional[str] = None,
    channel: Optional[str] = None,
    rt: RuntimeDep = Depends(get_kernel_runtime),
):
    """UI: rollback published version."""
    deny = await rbac_guard(
        http_request=http_request,
        payload={},
        action="update",
        resource_type="skill",
        resource_id=f"meta:{asset_type}",
    )
    if deny:
        return deny
    from core.services.config_registry_store import ConfigRegistryKey, get_config_registry_store

    ctx = req_tenant_channel(http_request, tenant_id=tenant_id, channel=channel)
    sc = (scope or "workspace").strip().lower()
    actor = str(http_request.headers.get("X-AIPLAT-ACTOR-ID") or "admin")
    actor_role = str(http_request.headers.get("X-AIPLAT-ACTOR-ROLE") or "admin")
    approval_request_id = str(http_request.headers.get("X-AIPLAT-APPROVAL-REQUEST-ID") or "").strip()
    store = get_config_registry_store()
    key = ConfigRegistryKey(asset_type=str(asset_type), scope=sc, tenant_id=ctx["tenant_id"], channel=ctx["channel"])
    from_v = None
    try:
        row = await store.get_published_row(key=key)
        from_v = row.get("version") if isinstance(row, dict) else None
        prev_v = row.get("prev_version") if isinstance(row, dict) else None
    except Exception:
        from_v = None
        prev_v = None

    approval_mgr = _approval_manager(rt)
    es = _store(rt)

    # Product-level gate: stable rollback of schema requires approval
    if ctx["channel"] == "stable" and str(asset_type) == "skill_spec_v2_schema":
        # If caller provided approval_request_id, require it approved; otherwise create request and block.
        if approval_request_id:
            if not approval_mgr:
                raise HTTPException(status_code=503, detail="ApprovalManager not initialized")
            r = (
                await approval_mgr.get_request_async(str(approval_request_id))  # type: ignore[attr-defined]
                if hasattr(approval_mgr, "get_request_async")
                else approval_mgr.get_request(str(approval_request_id))
            )
            if not r:
                raise HTTPException(status_code=404, detail="approval_request_not_found")
            from core.harness.infrastructure.approval.types import RequestStatus

            if r.status not in (RequestStatus.APPROVED, RequestStatus.AUTO_APPROVED):
                raise HTTPException(
                    status_code=409,
                    detail=gate_error_envelope(
                        code="approval_required",
                        message=f"approval_required: status={r.status.value}",
                        approval_request_id=str(approval_request_id),
                        next_actions=[{"type": "open_approvals", "label": "打开审批中心", "url": ui_url("/core/approvals"), "approval_request_id": str(approval_request_id)}],
                    ),
                )
            # deterministic rollback: publish target to_version if provided in approval request context
            meta = r.metadata if isinstance(getattr(r, "metadata", None), dict) else {}
            opctx = meta.get("operation_context") if isinstance(meta.get("operation_context"), dict) else {}
            to_v = str(opctx.get("to_version") or "") or prev_v
            if to_v:
                item = await store.get_asset(asset_type=str(asset_type), scope=sc, tenant_id=ctx["tenant_id"], version=str(to_v))
                if item and "payload" in item:
                    await store.publish(key=key, payload=item.get("payload"), actor=actor, note="rollback(approved)", version=str(to_v))
                    # changeset applied
                    try:
                        change_id = str(opctx.get("change_id") or meta.get("change_id") or "")
                        if es and change_id:
                            await es.add_syscall_event(
                                {
                                    "tenant_id": ctx["tenant_id"],
                                    "kind": "changeset",
                                    "name": "config_rollback_applied",
                                    "status": "rolled_back",
                                    "args": {"asset_type": str(asset_type), "scope": sc, "channel": ctx["channel"], "tenant_id": ctx["tenant_id"], "from_version": from_v, "to_version": to_v},
                                    "result": {"from_version": from_v, "to_version": to_v},
                                    "target_type": "change",
                                    "target_id": change_id,
                                    "user_id": actor,
                                    "approval_request_id": str(approval_request_id),
                                }
                            )
                    except Exception:
                        pass
                    return {"status": "rolled_back", "version": str(to_v), "from_version": from_v, **ctx, "scope": sc, "asset_type": str(asset_type), "approval_request_id": str(approval_request_id)}
        # create approval request and block
        rid = await _create_config_rollback_approval_request(
            store=es,
            actor_id=actor,
            actor_role=actor_role,
            tenant_id=ctx["tenant_id"],
            scope=sc,
            channel=ctx["channel"],
            asset_type=str(asset_type),
            from_version=str(from_v) if from_v else None,
            to_version=str(prev_v) if prev_v else None,
            note="rollback",
        )
        raise HTTPException(
            status_code=409,
            detail=gate_error_envelope(
                code="approval_required",
                message="stable_schema_rollback_requires_approval",
                approval_request_id=str(rid) if rid else None,
                next_actions=[{"type": "open_approvals", "label": "打开审批中心", "url": ui_url("/core/approvals"), "approval_request_id": str(rid) if rid else None}],
            ),
        )

    ver = await store.rollback(key=key, actor=actor, note="rollback")
    # Emit change control event
    try:
        from core.utils.ids import new_prefixed_id

        if es:
            chg = new_prefixed_id("chg")
            await es.add_syscall_event(
                {
                    "trace_id": None,
                    "span_id": None,
                    "run_id": None,
                    "tenant_id": ctx["tenant_id"],
                    "kind": "changeset",
                    "name": "config_rollback_direct",
                    "status": "rolled_back" if ver and from_v and str(ver) != str(from_v) else "no_op",
                    "args": {
                        "asset_type": str(asset_type),
                        "scope": sc,
                        "channel": ctx["channel"],
                        "tenant_id": ctx["tenant_id"],
                        "from_version": from_v,
                        "to_version": ver,
                        "note": "rollback",
                    },
                    "result": {"from_version": from_v, "to_version": ver},
                    "target_type": "change",
                    "target_id": chg,
                    "user_id": actor,
                    "session_id": None,
                    "approval_request_id": None,
                }
            )
    except Exception:
        pass
    return {"status": "rolled_back", "version": ver, "from_version": from_v, **ctx, "scope": sc, "asset_type": str(asset_type)}


@router.get("/workspace/skills/meta/config-registry/diff")
async def workspace_config_registry_diff(
    http_request: Request,
    asset_type: str,
    scope: str = "workspace",
    tenant_id: Optional[str] = None,
    channel: Optional[str] = None,
    from_ref: str = "published",
    to_version: str = "",
):
    """UI: diff published/current vs a target version (or inline payload in future)."""
    deny = await rbac_guard(
        http_request=http_request,
        payload={},
        action="read",
        resource_type="skill",
        resource_id=f"meta:{asset_type}",
    )
    if deny:
        return deny
    from core.services.config_registry_store import ConfigRegistryKey, get_config_registry_store

    ctx = req_tenant_channel(http_request, tenant_id=tenant_id, channel=channel)
    sc = (scope or "workspace").strip().lower()
    store = get_config_registry_store()

    # current
    cur_payload = None
    cur_version = None
    if from_ref == "published":
        key = ConfigRegistryKey(asset_type=str(asset_type), scope=sc, tenant_id=ctx["tenant_id"], channel=ctx["channel"])
        pub = await store.get_published(key=key)
        if pub:
            cur_version, cur_payload = pub[0], pub[1]
    elif from_ref == "default":
        cur_version, cur_payload = ("default", load_skill_spec_v2_schema() if str(asset_type) == "skill_spec_v2_schema" else permission_catalog(scope=sc))

    # proposed
    item = await store.get_asset(asset_type=str(asset_type), scope=sc, tenant_id=ctx["tenant_id"], version=str(to_version))
    proposed_payload = item.get("payload") if item else None

    assessment = _assess_config_change(asset_type=str(asset_type), current=cur_payload, proposed=proposed_payload)
    # channel-specific gating: stable -> approval; canary -> confirm phrase
    try:
        if assessment.get("risk_level") == "high":
            if ctx["channel"] == "stable":
                assessment["requires_approval"] = True
                assessment["requires_confirmation"] = False
                assessment["confirm_phrase"] = None
            else:
                assessment["requires_approval"] = False
    except Exception:
        pass
    diff_text = _unified_diff_text(cur_payload, proposed_payload)
    return {
        "status": "ok",
        "asset_type": str(asset_type),
        "scope": sc,
        "tenant_id": ctx["tenant_id"],
        "channel": ctx["channel"],
        "from_ref": from_ref,
        "from_version": cur_version,
        "to_version": str(to_version),
        "assessment": assessment,
        "diff": diff_text,
    }


# ====================
# Skills Installer (workspace scope)
# ====================


@router.post("/workspace/skills/installer/install")
async def workspace_skills_installer_install(request: SkillInstallerInstallRequest, http_request: Request, rt: RuntimeDep = Depends(get_kernel_runtime)):
    """
    Install skills from external sources into workspace skills directory.

    Source types:
    - git: url + ref (required)
    - path: local directory path on server
    - zip: local zip file path on server
    """
    ws_mgr = _ws_skill_manager(rt)
    if not ws_mgr:
        raise HTTPException(status_code=503, detail="Workspace skill manager not available")
    if str(request.scope or "workspace").strip().lower() != "workspace":
        raise HTTPException(status_code=400, detail="only_workspace_scope_is_supported")

    deny = await rbac_guard(
        http_request=http_request,
        payload=request.model_dump(),
        action="install",
        resource_type="skill",
        resource_id=str(request.skill_id) if request.skill_id else None,
    )
    if deny:
        return deny

    try:
        # Optional plan_id guard (recommended for production).
        require_plan_id = os.getenv("AIPLAT_SKILL_INSTALL_REQUIRE_PLAN_ID", "false").lower() in ("1", "true", "yes", "y")
        plan = None
        if require_plan_id:
            plan = await ws_mgr.installer_plan(
                source_type=str(request.source_type.value if hasattr(request.source_type, "value") else request.source_type),
                url=request.url,
                ref=request.ref,
                path=request.path,
                skill_id=request.skill_id,
                subdir=request.subdir,
                auto_detect_subdir=bool(getattr(request, "auto_detect_subdir", True)),
                metadata=request.metadata,
            )
            from core.management.skill_install_plan_token import canonical_plan_data, verify_plan_token
            from core.management.skill_install_plan_token import skills_digest as _skills_digest

            digest = _skills_digest((plan or {}).get("skills"))
            expected = canonical_plan_data(
                scope=str(request.scope or "workspace"),
                source_type=str(request.source_type.value if hasattr(request.source_type, "value") else request.source_type),
                url=request.url,
                ref=request.ref,
                path=request.path,
                skill_id=request.skill_id,
                subdir=request.subdir,
                auto_detect_subdir=bool(getattr(request, "auto_detect_subdir", True)),
                allow_overwrite=bool(request.allow_overwrite),
                metadata=request.metadata,
                detected_subdir=str((plan or {}).get("detected_subdir") or ""),
                planned_skills_digest=str(digest or ""),
            )
            if not (request.plan_id or "").strip():
                raise HTTPException(
                    status_code=409,
                    detail={"code": "plan_id_required", "message": "必须先调用 /workspace/skills/installer/plan 获取 plan_id", "plan": plan},
                )
            try:
                verify_plan_token(token=str(request.plan_id), expected_data=expected)
            except Exception as e:
                raise HTTPException(status_code=409, detail={"code": "plan_id_invalid", "message": str(e), "plan": plan})

        # Optional confirm guard (interactive safety). Recommended for production.
        require_confirm = os.getenv("AIPLAT_SKILL_INSTALL_REQUIRE_CONFIRM", "false").lower() in ("1", "true", "yes", "y")
        if require_confirm and not bool(request.confirm):
            if plan is None:
                plan = await ws_mgr.installer_plan(
                    source_type=str(request.source_type.value if hasattr(request.source_type, "value") else request.source_type),
                    url=request.url,
                    ref=request.ref,
                    path=request.path,
                    skill_id=request.skill_id,
                    subdir=request.subdir,
                    auto_detect_subdir=bool(getattr(request, "auto_detect_subdir", True)),
                    metadata=request.metadata,
                )
            raise HTTPException(
                status_code=409,
                detail={"code": "confirm_required", "message": "请先确认安装计划（建议先调用 /workspace/skills/installer/plan）", "plan": plan},
            )

        # Optional approval gate for installer (manual review).
        if bool(getattr(request, "require_approval", False)) or os.getenv("AIPLAT_SKILL_INSTALL_REQUIRE_APPROVAL", "false").lower() in ("1", "true", "yes", "y"):
            approval_id = str(getattr(request, "approval_request_id", None) or "").strip() or None
            approval_mgr = _approval_manager(rt)
            if approval_id:
                try:
                    from core.harness.infrastructure.approval.types import RequestStatus

                    if not approval_mgr:
                        raise HTTPException(status_code=503, detail="Approval manager not available")
                    ar = (
                        await approval_mgr.get_request_async(str(approval_id))  # type: ignore[attr-defined]
                        if hasattr(approval_mgr, "get_request_async")
                        else approval_mgr.get_request(str(approval_id))
                    )
                    if not ar:
                        raise HTTPException(status_code=404, detail=f"Approval request not found: {approval_id}")
                    if ar.status != RequestStatus.APPROVED:
                        raise HTTPException(status_code=409, detail={"code": "approval_required", "approval_request_id": approval_id, "status": str(ar.status)})
                except HTTPException:
                    raise
                except Exception as e:
                    raise HTTPException(status_code=500, detail=f"approval_check_failed:{e}")
            else:
                # create approval request
                from core.harness.infrastructure.approval.types import ApprovalContext, ApprovalRule, RuleType

                if not approval_mgr:
                    raise HTTPException(status_code=503, detail="Approval manager not available")
                rule = ApprovalRule(
                    rule_id="skills_installer_install",
                    rule_type=RuleType.SENSITIVE_OPERATION,
                    name="Skills Installer 安装审批",
                    description="安装第三方开源技能需要审批确认（生产护栏）",
                    priority=1,
                    metadata={"sensitive_operations": ["skills:installer"]},
                )
                approval_mgr.register_rule(rule)
                actor = actor_from_http(http_request, request.model_dump())
                ctx = ApprovalContext(
                    user_id=str(actor.get("actor_id") or "admin"),
                    operation="skills:installer:install",
                    operation_context={"details": str(getattr(request, "details", None) or "install skills"), "payload": request.model_dump()},
                    metadata={"resource_type": "skill", "resource_id": str(request.skill_id) if request.skill_id else None},
                )
                ar = approval_mgr.create_request(ctx, rule=rule)
                try:
                    await approval_mgr._persist(ar)  # type: ignore[attr-defined]
                except Exception:
                    pass
                raise HTTPException(
                    status_code=409,
                    detail={
                        "code": "approval_required",
                        "approval_request_id": ar.request_id,
                        "links": governance_links(approval_request_id=str(ar.request_id)),
                    },
                )

        res = await ws_mgr.installer_install(
            source_type=str(request.source_type.value if hasattr(request.source_type, "value") else request.source_type),
            url=request.url,
            ref=request.ref,
            path=request.path,
            skill_id=request.skill_id,
            subdir=request.subdir,
            auto_detect_subdir=bool(getattr(request, "auto_detect_subdir", True)),
            allow_overwrite=bool(request.allow_overwrite),
            metadata=request.metadata,
        )
        try:
            es = _store(rt)
            if es is not None:
                actor = actor_from_http(http_request, request.model_dump())
                await es.add_audit_log(
                    action="workspace_skill_installer_install",
                    status="ok",
                    tenant_id=str(actor.get("tenant_id") or "") or None,
                    actor_id=str(actor.get("actor_id") or "") or None,
                    actor_role=str(actor.get("actor_role") or "") or None,
                    resource_type="skill",
                    resource_id=str(request.skill_id) if request.skill_id else None,
                    detail={
                        "source_type": str(request.source_type),
                        "url": request.url,
                        "path": request.path,
                        "ref": request.ref,
                        "installed": res.get("installed") if isinstance(res, dict) else None,
                        "skipped": res.get("skipped") if isinstance(res, dict) else None,
                    },
                )
        except Exception:
            pass
        return {"status": "ok", **res}
    except PermissionError as e:
        raise HTTPException(status_code=403, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"installer_failed:{e}")


@router.post("/workspace/skills/installer/plan")
async def workspace_skills_installer_plan(request: SkillInstallerInstallRequest, http_request: Request, rt: RuntimeDep = Depends(get_kernel_runtime)):
    """Dry-run plan for installer. No filesystem write."""
    ws_mgr = _ws_skill_manager(rt)
    if not ws_mgr:
        raise HTTPException(status_code=503, detail="Workspace skill manager not available")
    if str(request.scope or "workspace").strip().lower() != "workspace":
        raise HTTPException(status_code=400, detail="only_workspace_scope_is_supported")

    deny = await rbac_guard(
        http_request=http_request,
        payload=request.model_dump(),
        action="install",
        resource_type="skill",
        resource_id=str(request.skill_id) if request.skill_id else None,
    )
    if deny:
        return deny

    try:
        plan = await ws_mgr.installer_plan(
            source_type=str(request.source_type.value if hasattr(request.source_type, "value") else request.source_type),
            url=request.url,
            ref=request.ref,
            path=request.path,
            skill_id=request.skill_id,
            subdir=request.subdir,
            auto_detect_subdir=bool(getattr(request, "auto_detect_subdir", True)),
            metadata=request.metadata,
        )
        plan_id = None
        expires_at = None
        # When plan secret is configured, emit signed plan_id for drift-proof installs.
        try:
            from core.management.skill_install_plan_token import build_plan_token, canonical_plan_data, skills_digest as _skills_digest

            digest = _skills_digest((plan or {}).get("skills"))
            data = canonical_plan_data(
                scope=str(request.scope or "workspace"),
                source_type=str(request.source_type.value if hasattr(request.source_type, "value") else request.source_type),
                url=request.url,
                ref=request.ref,
                path=request.path,
                skill_id=request.skill_id,
                subdir=request.subdir,
                auto_detect_subdir=bool(getattr(request, "auto_detect_subdir", True)),
                allow_overwrite=bool(request.allow_overwrite),
                metadata=request.metadata,
                detected_subdir=str((plan or {}).get("detected_subdir") or ""),
                planned_skills_digest=str(digest or ""),
            )
            plan_id, expires_at = build_plan_token(data=data)
        except Exception:
            plan_id = None
            expires_at = None
        out = {"status": "ok", **plan}
        try:
            from core.management.skill_install_plan_token import skills_digest as _skills_digest

            out["planned_skills_digest"] = _skills_digest((plan or {}).get("skills"))
        except Exception:
            pass
        if plan_id:
            out["plan_id"] = plan_id
            out["plan_expires_at"] = expires_at
        return out
    except PermissionError as e:
        raise HTTPException(status_code=403, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"installer_plan_failed:{e}")


@router.post("/workspace/skills/installer/resolve-head")
async def workspace_skills_installer_resolve_head(payload: dict, http_request: Request, rt: RuntimeDep = Depends(get_kernel_runtime)):
    """Resolve git remote HEAD SHA for a URL (helper for 'always latest but pinned sha' workflow)."""
    ws_mgr = _ws_skill_manager(rt)
    if not ws_mgr:
        raise HTTPException(status_code=503, detail="Workspace skill manager not available")
    url = str((payload or {}).get("url") or "").strip()
    deny = await rbac_guard(http_request=http_request, payload=payload or {}, action="install", resource_type="skill", resource_id=None)
    if deny:
        return deny
    try:
        res = await ws_mgr.installer_resolve_head(url=url)
        try:
            es = _store(rt)
            if es is not None:
                actor = actor_from_http(http_request, payload or {})
                await es.add_audit_log(
                    action="workspace_skill_installer_resolve_head",
                    status="ok",
                    tenant_id=str(actor.get("tenant_id") or "") or None,
                    actor_id=str(actor.get("actor_id") or "") or None,
                    actor_role=str(actor.get("actor_role") or "") or None,
                    resource_type="skill",
                    resource_id=None,
                    detail={"url": url, "head_sha": (res or {}).get("head_sha") if isinstance(res, dict) else None},
                )
        except Exception:
            pass
        return {"status": "ok", **res}
    except PermissionError as e:
        raise HTTPException(status_code=403, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"installer_resolve_head_failed:{e}")


@router.post("/workspace/skills/installer/update/{skill_id}")
async def workspace_skills_installer_update(skill_id: str, request: SkillInstallerUpdateRequest, http_request: Request, rt: RuntimeDep = Depends(get_kernel_runtime)):
    ws_mgr = _ws_skill_manager(rt)
    if not ws_mgr:
        raise HTTPException(status_code=503, detail="Workspace skill manager not available")
    if str(request.scope or "workspace").strip().lower() != "workspace":
        raise HTTPException(status_code=400, detail="only_workspace_scope_is_supported")

    deny = await rbac_guard(
        http_request=http_request,
        payload=request.model_dump(),
        action="update",
        resource_type="skill",
        resource_id=str(skill_id),
    )
    if deny:
        return deny

    try:
        res = await ws_mgr.installer_update(skill_id=str(skill_id), ref=request.ref, metadata=request.metadata)
        try:
            es = _store(rt)
            if es is not None:
                actor = actor_from_http(http_request, request.model_dump())
                await es.add_audit_log(
                    action="workspace_skill_installer_update",
                    status="ok",
                    tenant_id=str(actor.get("tenant_id") or "") or None,
                    actor_id=str(actor.get("actor_id") or "") or None,
                    actor_role=str(actor.get("actor_role") or "") or None,
                    resource_type="skill",
                    resource_id=str(skill_id),
                    detail={"ref": request.ref, "installed": (res or {}).get("installed") if isinstance(res, dict) else None},
                )
        except Exception:
            pass
        return {"status": "ok", **res}
    except PermissionError as e:
        raise HTTPException(status_code=403, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"installer_update_failed:{e}")


@router.post("/workspace/skills/installer/uninstall/{skill_id}")
async def workspace_skills_installer_uninstall(skill_id: str, http_request: Request, delete_files: bool = True, rt: RuntimeDep = Depends(get_kernel_runtime)):
    ws_mgr = _ws_skill_manager(rt)
    if not ws_mgr:
        raise HTTPException(status_code=503, detail="Workspace skill manager not available")

    deny = await rbac_guard(
        http_request=http_request,
        payload={"delete_files": bool(delete_files)},
        action="delete",
        resource_type="skill",
        resource_id=str(skill_id),
    )
    if deny:
        return deny

    try:
        res = await ws_mgr.installer_uninstall(skill_id=str(skill_id), delete_files=bool(delete_files))
        try:
            es = _store(rt)
            if es is not None:
                actor = actor_from_http(http_request, {"delete_files": bool(delete_files)})
                await es.add_audit_log(
                    action="workspace_skill_installer_uninstall",
                    status="ok",
                    tenant_id=str(actor.get("tenant_id") or "") or None,
                    actor_id=str(actor.get("actor_id") or "") or None,
                    actor_role=str(actor.get("actor_role") or "") or None,
                    resource_type="skill",
                    resource_id=str(skill_id),
                    detail={"delete_files": bool(delete_files), "deleted": (res or {}).get("deleted") if isinstance(res, dict) else None},
                )
        except Exception:
            pass
        return {"status": "ok", **res}
    except PermissionError as e:
        raise HTTPException(status_code=403, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"installer_uninstall_failed:{e}")

