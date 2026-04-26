from __future__ import annotations

import json
import time
import uuid
from typing import Any, Dict, Optional

from core.utils.ids import new_prefixed_id


def unified_diff_text(a: Any, b: Any) -> str:
    try:
        aa = json.dumps(a, ensure_ascii=False, indent=2, sort_keys=True).splitlines()
        bb = json.dumps(b, ensure_ascii=False, indent=2, sort_keys=True).splitlines()
    except Exception:
        aa = str(a).splitlines()
        bb = str(b).splitlines()
    import difflib

    return "\n".join(difflib.unified_diff(aa, bb, fromfile="current", tofile="proposed", lineterm=""))


def assess_schema_change(current: Optional[Dict[str, Any]], proposed: Optional[Dict[str, Any]]) -> Dict[str, Any]:
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


def assess_permissions_catalog_change(current: Optional[Dict[str, Any]], proposed: Optional[Dict[str, Any]]) -> Dict[str, Any]:
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


def assess_config_change(*, asset_type: str, current: Any, proposed: Any) -> Dict[str, Any]:
    at = str(asset_type)
    if at == "skill_spec_v2_schema":
        base = assess_schema_change(current if isinstance(current, dict) else None, proposed if isinstance(proposed, dict) else None)
    elif at == "permissions_catalog":
        base = assess_permissions_catalog_change(
            current if isinstance(current, dict) else None, proposed if isinstance(proposed, dict) else None
        )
    else:
        base = {"risk_level": "medium", "breaking_changes": [], "warnings": [{"type": "unknown_asset_type"}]}

    # NOTE: channel-specific gates are decided by caller (stable -> approval; canary -> confirm phrase).
    requires_confirmation = base.get("risk_level") == "high"
    confirm_phrase = f"PUBLISH {at} HIGH-RISK" if requires_confirmation else None
    base.update({"requires_confirmation": requires_confirmation, "confirm_phrase": confirm_phrase, "requires_approval": False})
    return base


async def create_config_publish_approval_request(
    *,
    execution_store: Any | None,
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
    if not execution_store:
        return None
    try:
        now = time.time()
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
        await execution_store.upsert_approval_request(record)

        # Emit a change control event to link approval_request -> change_id.
        try:
            await execution_store.add_syscall_event(
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


async def create_config_rollback_approval_request(
    *,
    execution_store: Any | None,
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
    if not execution_store:
        return None
    try:
        now = time.time()
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
        await execution_store.upsert_approval_request(record)

        # changeset pending event (links to change control)
        try:
            await execution_store.add_syscall_event(
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

