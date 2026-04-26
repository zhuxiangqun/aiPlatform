from __future__ import annotations

import hashlib
import json
import os
import time
from typing import Annotated, Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Request

from core.api.deps.rbac import rbac_guard
from core.api.utils.governance import gate_error_envelope, governance_links
from core.governance.changeset import record_changeset
from core.governance.gating import new_change_id
from core.harness.integration import KernelRuntime
from core.harness.kernel.runtime import get_kernel_runtime

router = APIRouter()

RuntimeDep = Annotated[Optional[KernelRuntime], Depends(get_kernel_runtime)]


def _store(rt: Optional[KernelRuntime]):
    return getattr(rt, "execution_store", None) if rt else None


def _approval_mgr(rt: Optional[KernelRuntime]):
    return getattr(rt, "approval_manager", None) if rt else None


SETTING_KEY = "gate_policies"


def _normalize_policy_id(v: str) -> str:
    v = str(v or "").strip()
    if not v:
        raise ValueError("empty_policy_id")
    return v


def _normalize_policy_obj(obj: Dict[str, Any]) -> Dict[str, Any]:
    """
    Keep this intentionally permissive (productization phase): validate only top-level shape.
    """
    if not isinstance(obj, dict):
        raise ValueError("policy must be object")
    out = dict(obj)
    out.setdefault("name", out.get("policy_id") or "")
    out.setdefault("description", "")
    out.setdefault("config", {})
    if not isinstance(out.get("config"), dict):
        out["config"] = {}
    out.setdefault("version", 1)
    out.setdefault("revisions", [])
    return out


async def _load_all(store) -> Dict[str, Any]:
    rec = await store.get_global_setting(key=SETTING_KEY)
    if not rec:
        return {"default_id": "default", "items": []}
    v = rec.get("value") if isinstance(rec, dict) else None
    return v if isinstance(v, dict) else {"default_id": "default", "items": []}


async def _save_all(store, value: Dict[str, Any]) -> Dict[str, Any]:
    return await store.upsert_global_setting(key=SETTING_KEY, value=value)

def _sha(obj: Any) -> str:
    try:
        return hashlib.sha256(json.dumps(obj, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode("utf-8")).hexdigest()
    except Exception:
        return ""

def _default_templates() -> Dict[str, Any]:
    now = float(time.time())
    return {
        "default_id": "dev",
        "items": [
            {
                "policy_id": "dev",
                "name": "dev",
                "description": "开发环境（宽松）",
                "version": 1,
                "revisions": [],
                "config": {"apply_gate": {"gate_policy": "any", "require_autosmoke": False, "require_approval": False}, "eval_gate": {"mode": "off"}, "security_gate": {"mode": "off"}},
                "created_at": now,
                "updated_at": now,
            },
            {
                "policy_id": "staging",
                "name": "staging",
                "description": "预发环境（推荐）",
                "version": 1,
                "revisions": [],
                "config": {"apply_gate": {"gate_policy": "autosmoke", "require_autosmoke": True, "require_approval": False}, "eval_gate": {"mode": "trigger"}, "security_gate": {"mode": "scan_warn"}},
                "created_at": now,
                "updated_at": now,
            },
            {
                "policy_id": "prod",
                "name": "prod",
                "description": "生产环境（严格）",
                "version": 1,
                "revisions": [],
                "config": {"apply_gate": {"gate_policy": "all", "require_autosmoke": True, "require_approval": True}, "eval_gate": {"mode": "trigger+quality"}, "security_gate": {"mode": "scan_block"}},
                "created_at": now,
                "updated_at": now,
            },
        ],
    }


def _approval_required_for_policy(policy_id: str, override: Optional[bool] = None) -> bool:
    """
    Default behavior:
    - prod_only: require approval only when policy_id == "prod" (default)
    - true: require approval for all changes
    - false: require approval for none
    """
    if override is True:
        return True
    if override is False:
        return False
    mode = (os.getenv("AIPLAT_GATE_POLICY_REQUIRE_APPROVAL", "prod_only") or "prod_only").strip().lower()
    if mode in {"1", "true", "yes", "y", "all"}:
        return True
    if mode in {"0", "false", "no", "n", "none"}:
        return False
    return str(policy_id) == "prod"


async def _create_gate_policy_approval_request(
    *,
    approval_manager: Any,
    user_id: str,
    policy_id: str,
    change_id: str,
    tenant_id: Optional[str],
    actor_id: Optional[str],
    actor_role: Optional[str],
    operation_context: Dict[str, Any],
) -> str:
    from core.harness.infrastructure.approval.types import ApprovalContext, ApprovalRule, RuleType

    if not approval_manager:
        raise HTTPException(status_code=503, detail="Approval manager not available")
    op = "gate_policy:apply"
    rule = ApprovalRule(
        rule_id="gate_policy_apply",
        rule_type=RuleType.SENSITIVE_OPERATION,
        name="Gate Policy 变更审批",
        description="Gate Policy 的变更需要审批后才能应用（产品化：propose→approve→apply）",
        priority=1,
        metadata={"sensitive_operations": ["gate_policy"]},
    )
    approval_manager.register_rule(rule)
    ctx = ApprovalContext(
        user_id=user_id or "admin",
        operation=op,
        operation_context={"details": f"apply gate policy {policy_id} (change_id={change_id})"},
        metadata={
            "tenant_id": tenant_id,
            "actor_id": actor_id,
            "actor_role": actor_role,
            "change_id": change_id,
            "policy_id": policy_id,
            "operation_context": operation_context,
        },
    )
    req = approval_manager.create_request(ctx, rule=rule)
    try:
        await approval_manager._persist(req)  # type: ignore[attr-defined]
    except Exception:
        pass
    return str(req.request_id)


@router.post("/governance/gate-policies/bootstrap")
async def bootstrap_gate_policies(http_request: Request, force: bool = False, rt: RuntimeDep = None):
    """
    Seed built-in templates: dev/staging/prod.
    - force=false: only seed when empty/missing
    - force=true: overwrite entirely
    """
    store = _store(rt)
    if not store:
        raise HTTPException(status_code=503, detail="ExecutionStore not initialized")
    cur = await store.get_global_setting(key=SETTING_KEY)
    has_any = False
    if cur and isinstance(cur.get("value"), dict):
        items = cur["value"].get("items")
        has_any = isinstance(items, list) and len(items) > 0
    if has_any and not force:
        return {"status": "ok", "seeded": False, "reason": "already_initialized"}
    await _save_all(store, _default_templates())
    # governance (best-effort)
    try:
        cid = new_change_id()
        await record_changeset(
            store=store,
            name="gate_policy.bootstrap",
            target_type="change",
            target_id=str(cid),
            status="success",
            args={"force": bool(force)},
            result={"default_id": "dev", "items": ["dev", "staging", "prod"]},
            user_id=str((http_request.headers.get("X-AIPLAT-ACTOR-ID") if http_request else None) or "admin"),
            tenant_id=str((http_request.headers.get("X-AIPLAT-TENANT-ID") if http_request else None) or "") or None,
        )
    except Exception:
        cid = None
    return {"status": "ok", "seeded": True, "default_id": "dev", "items": ["dev", "staging", "prod"], "links": governance_links(change_id=cid) if cid else {}}


@router.get("/governance/gate-policies")
async def list_gate_policies(rt: RuntimeDep = None):
    store = _store(rt)
    if not store:
        raise HTTPException(status_code=503, detail="ExecutionStore not initialized")
    data = await _load_all(store)
    items = data.get("items") if isinstance(data.get("items"), list) else []
    return {"status": "ok", "default_id": data.get("default_id"), "items": items}


@router.get("/governance/gate-policies/{policy_id}")
async def get_gate_policy(policy_id: str, rt: RuntimeDep = None):
    store = _store(rt)
    if not store:
        raise HTTPException(status_code=503, detail="ExecutionStore not initialized")
    pid = _normalize_policy_id(policy_id)
    data = await _load_all(store)
    for it in (data.get("items") or []):
        if isinstance(it, dict) and str(it.get("policy_id") or "") == pid:
            return {"status": "ok", "item": it, "default_id": data.get("default_id")}
    raise HTTPException(status_code=404, detail="policy_not_found")


@router.put("/governance/gate-policies/{policy_id}")
async def upsert_gate_policy(policy_id: str, request: dict, http_request: Request, rt: RuntimeDep = None):
    store = _store(rt)
    if not store:
        raise HTTPException(status_code=503, detail="ExecutionStore not initialized")
    pid = _normalize_policy_id(policy_id)
    body = request if isinstance(request, dict) else {}
    deny = await rbac_guard(http_request=http_request, payload=body or {}, action="update", resource_type="policy", resource_id=f"gate_policy:{pid}")
    if deny:
        return deny
    item = body.get("item") if isinstance(body.get("item"), dict) else body
    item = _normalize_policy_obj(item)
    item["policy_id"] = pid
    item["updated_at"] = float(time.time())

    data = await _load_all(store)
    items: List[Dict[str, Any]] = [x for x in (data.get("items") or []) if isinstance(x, dict)]
    found = False
    prev_sha = ""
    new_sha = _sha(item.get("config") or {})
    cid = new_change_id()
    for i, it in enumerate(items):
        if str(it.get("policy_id") or "") == pid:
            # versioning: append old snapshot to revisions
            try:
                prev = dict(it)
                prev_sha = _sha(prev.get("config") or {})
                revs = it.get("revisions") if isinstance(it.get("revisions"), list) else []
                revs = [x for x in revs if isinstance(x, dict)]
                revs.append(
                    {
                        "version": int(it.get("version") or 1),
                        "updated_at": float(it.get("updated_at") or 0),
                        "config": prev.get("config") if isinstance(prev.get("config"), dict) else {},
                        "sha256": prev_sha,
                    }
                )
                # cap history
                if len(revs) > 20:
                    revs = revs[-20:]
                item["revisions"] = revs
                item["version"] = int(it.get("version") or 1) + 1
            except Exception:
                item["version"] = int(it.get("version") or 1) + 1
            items[i] = {**it, **item}
            found = True
            break
    if not found:
        item.setdefault("created_at", float(time.time()))
        items.append(item)
    data["items"] = items
    if isinstance(body.get("set_default"), bool) and body.get("set_default"):
        data["default_id"] = pid
    await _save_all(store, data)
    # governance changeset (best-effort)
    try:
        await record_changeset(
            store=store,
            name="gate_policy.upsert",
            target_type="change",
            target_id=str(cid),
            status="success",
            args={"policy_id": pid, "set_default": bool(body.get("set_default")), "prev_sha256": prev_sha},
            result={"new_sha256": new_sha, "version": int(item.get("version") or 1)},
            user_id=str(http_request.headers.get("X-AIPLAT-ACTOR-ID") or "admin"),
            tenant_id=str(http_request.headers.get("X-AIPLAT-TENANT-ID") or "") or None,
        )
    except Exception:
        pass
    return {"status": "ok", "item": item, "default_id": data.get("default_id"), "change_id": str(cid), "links": governance_links(change_id=str(cid))}


@router.delete("/governance/gate-policies/{policy_id}")
async def delete_gate_policy(policy_id: str, http_request: Request, rt: RuntimeDep = None):
    store = _store(rt)
    if not store:
        raise HTTPException(status_code=503, detail="ExecutionStore not initialized")
    pid = _normalize_policy_id(policy_id)
    deny = await rbac_guard(http_request=http_request, payload=None, action="delete", resource_type="policy", resource_id=f"gate_policy:{pid}")
    if deny:
        return deny
    data = await _load_all(store)
    items: List[Dict[str, Any]] = [x for x in (data.get("items") or []) if isinstance(x, dict)]
    items2 = [x for x in items if str(x.get("policy_id") or "") != pid]
    if len(items2) == len(items):
        raise HTTPException(status_code=404, detail="policy_not_found")
    data["items"] = items2
    if str(data.get("default_id") or "") == pid:
        data["default_id"] = items2[0].get("policy_id") if items2 else "default"
    await _save_all(store, data)
    cid = new_change_id()
    try:
        await record_changeset(
            store=store,
            name="gate_policy.delete",
            target_type="change",
            target_id=str(cid),
            status="success",
            args={"policy_id": pid},
            result={"default_id": data.get("default_id")},
            user_id=str(http_request.headers.get("X-AIPLAT-ACTOR-ID") or "admin"),
            tenant_id=str(http_request.headers.get("X-AIPLAT-TENANT-ID") or "") or None,
        )
    except Exception:
        pass
    return {"status": "ok", "deleted": pid, "default_id": data.get("default_id"), "change_id": str(cid), "links": governance_links(change_id=str(cid))}


@router.post("/governance/gate-policies/{policy_id}/set-default")
async def set_default_gate_policy(policy_id: str, http_request: Request, rt: RuntimeDep = None):
    store = _store(rt)
    if not store:
        raise HTTPException(status_code=503, detail="ExecutionStore not initialized")
    pid = _normalize_policy_id(policy_id)
    deny = await rbac_guard(http_request=http_request, payload=None, action="update", resource_type="policy", resource_id=f"gate_policy:{pid}")
    if deny:
        return deny
    data = await _load_all(store)
    ok = any(isinstance(x, dict) and str(x.get("policy_id") or "") == pid for x in (data.get("items") or []))
    if not ok:
        raise HTTPException(status_code=404, detail="policy_not_found")
    data["default_id"] = pid
    await _save_all(store, data)
    cid = new_change_id()
    try:
        await record_changeset(
            store=store,
            name="gate_policy.set_default",
            target_type="change",
            target_id=str(cid),
            status="success",
            args={"default_id": pid},
            user_id=str(http_request.headers.get("X-AIPLAT-ACTOR-ID") or "admin"),
            tenant_id=str(http_request.headers.get("X-AIPLAT-TENANT-ID") or "") or None,
        )
    except Exception:
        pass
    return {"status": "ok", "default_id": pid, "change_id": str(cid), "links": governance_links(change_id=str(cid))}


@router.get("/governance/gate-policies/{policy_id}/versions")
async def list_gate_policy_versions(policy_id: str, rt: RuntimeDep = None):
    store = _store(rt)
    if not store:
        raise HTTPException(status_code=503, detail="ExecutionStore not initialized")
    pid = _normalize_policy_id(policy_id)
    data = await _load_all(store)
    for it in (data.get("items") or []):
        if isinstance(it, dict) and str(it.get("policy_id") or "") == pid:
            revs = it.get("revisions") if isinstance(it.get("revisions"), list) else []
            revs = [x for x in revs if isinstance(x, dict)]
            return {"status": "ok", "policy_id": pid, "current_version": int(it.get("version") or 1), "revisions": list(reversed(revs))}
    raise HTTPException(status_code=404, detail="policy_not_found")


@router.post("/governance/gate-policies/{policy_id}/rollback")
async def rollback_gate_policy(policy_id: str, request: dict, http_request: Request, rt: RuntimeDep = None):
    """
    Rollback policy config to a previous version from revisions.
    Body: { "version": 3 }
    """
    store = _store(rt)
    if not store:
        raise HTTPException(status_code=503, detail="ExecutionStore not initialized")
    pid = _normalize_policy_id(policy_id)
    try:
        ver = int((request or {}).get("version"))
    except Exception:
        raise HTTPException(status_code=400, detail="version is required (int)")
    data = await _load_all(store)
    items: List[Dict[str, Any]] = [x for x in (data.get("items") or []) if isinstance(x, dict)]
    for i, it in enumerate(items):
        if str(it.get("policy_id") or "") != pid:
            continue
        revs = it.get("revisions") if isinstance(it.get("revisions"), list) else []
        revs = [x for x in revs if isinstance(x, dict)]
        found = None
        for r in revs:
            if int(r.get("version") or 0) == ver:
                found = r
                break
        if not found:
            raise HTTPException(status_code=404, detail="version_not_found")
        # append current snapshot
        cur_sha = _sha(it.get("config") or {})
        revs.append({"version": int(it.get("version") or 1), "updated_at": float(it.get("updated_at") or 0), "config": it.get("config") or {}, "sha256": cur_sha})
        if len(revs) > 20:
            revs = revs[-20:]
        it["config"] = found.get("config") if isinstance(found.get("config"), dict) else {}
        it["revisions"] = revs
        it["version"] = int(it.get("version") or 1) + 1
        it["updated_at"] = float(time.time())
        items[i] = it
        data["items"] = items
        await _save_all(store, data)
        cid = new_change_id()
        try:
            await record_changeset(
                store=store,
                name="gate_policy.rollback",
                target_type="change",
                target_id=str(cid),
                status="success",
                args={"policy_id": pid, "rollback_to_version": ver},
                result={"new_version": int(it.get("version") or 1), "sha256": _sha(it.get("config") or {})},
                user_id=str(http_request.headers.get("X-AIPLAT-ACTOR-ID") or "admin"),
                tenant_id=str(http_request.headers.get("X-AIPLAT-TENANT-ID") or "") or None,
            )
        except Exception:
            pass
        return {"status": "ok", "item": it, "change_id": str(cid), "links": governance_links(change_id=str(cid))}
    raise HTTPException(status_code=404, detail="policy_not_found")


@router.post("/governance/gate-policies/{policy_id}/propose")
async def propose_gate_policy_change(policy_id: str, request: dict, http_request: Request, rt: RuntimeDep = None):
    """
    Productized workflow: propose → approve → apply.
    Creates a change_id (ChangeControl) and optionally an approval_request_id.

    Body:
      {
        "config": {...},
        "name": "optional",
        "description": "optional",
        "set_default": false,
        "require_approval": true|false (optional override)
      }
    """
    store = _store(rt)
    if not store:
        raise HTTPException(status_code=503, detail="ExecutionStore not initialized")
    pid = _normalize_policy_id(policy_id)
    body = request if isinstance(request, dict) else {}
    deny = await rbac_guard(http_request=http_request, payload=body or {}, action="update", resource_type="policy", resource_id=f"gate_policy:{pid}")
    if deny:
        return deny

    data = await _load_all(store)
    cur = None
    for it in (data.get("items") or []):
        if isinstance(it, dict) and str(it.get("policy_id") or "") == pid:
            cur = it
            break
    cur_cfg = cur.get("config") if isinstance(cur, dict) and isinstance(cur.get("config"), dict) else {}
    cur_ver = int(cur.get("version") or 1) if isinstance(cur, dict) else 0

    new_cfg = body.get("config") if isinstance(body.get("config"), dict) else None
    if new_cfg is None:
        raise HTTPException(status_code=400, detail="config is required")
    change_id = new_change_id()
    set_default = bool(body.get("set_default")) if isinstance(body.get("set_default"), bool) else False
    override = body.get("require_approval") if isinstance(body.get("require_approval"), bool) else None
    require_approval = _approval_required_for_policy(pid, override=override)

    opctx = {
        "change_id": str(change_id),
        "policy_id": pid,
        "name": body.get("name"),
        "description": body.get("description"),
        "set_default": set_default,
        "config": new_cfg,
    }
    approval_request_id = None
    if require_approval:
        mgr = _approval_mgr(rt)
        actor_id = http_request.headers.get("X-AIPLAT-ACTOR-ID") or "admin"
        tenant_id = http_request.headers.get("X-AIPLAT-TENANT-ID")
        actor_role = http_request.headers.get("X-AIPLAT-ACTOR-ROLE")
        approval_request_id = await _create_gate_policy_approval_request(
            approval_manager=mgr,
            user_id=str(actor_id),
            policy_id=pid,
            change_id=str(change_id),
            tenant_id=str(tenant_id) if tenant_id else None,
            actor_id=str(actor_id) if actor_id else None,
            actor_role=str(actor_role) if actor_role else None,
            operation_context=opctx,
        )

    links = governance_links(change_id=str(change_id), approval_request_id=str(approval_request_id) if approval_request_id else None)
    await record_changeset(
        store=store,
        name="gate_policy.proposed",
        target_type="change",
        target_id=str(change_id),
        status="approval_required" if approval_request_id else "pending",
        args={"policy_id": pid, "set_default": set_default, "approval_request_id": approval_request_id, "current_version": cur_ver},
        result={"current": {"version": cur_ver, "sha256": _sha(cur_cfg), "config": cur_cfg}, "next": {"sha256": _sha(new_cfg), "config": new_cfg}, "links": links},
        user_id=str(http_request.headers.get("X-AIPLAT-ACTOR-ID") or "admin"),
        tenant_id=str(http_request.headers.get("X-AIPLAT-TENANT-ID") or "") or None,
        approval_request_id=str(approval_request_id) if approval_request_id else None,
    )
    return {"status": "ok", "change_id": str(change_id), "approval_request_id": approval_request_id, "links": links}


@router.post("/governance/gate-policies/changes/{change_id}/apply")
async def apply_gate_policy_change(change_id: str, request: dict, http_request: Request, rt: RuntimeDep = None):
    """
    Apply a previously proposed gate policy change.
    Body: { "approval_request_id": "optional" }
    """
    store = _store(rt)
    if not store:
        raise HTTPException(status_code=503, detail="ExecutionStore not initialized")
    body = request if isinstance(request, dict) else {}

    cc = await store.get_change_control(change_id=str(change_id), limit=200, offset=0, tenant_id=http_request.headers.get("X-AIPLAT-TENANT-ID"))
    events = (cc.get("events") or {}).get("items") if isinstance(cc.get("events"), dict) else []
    prop = None
    for e in (events or []):
        if isinstance(e, dict) and str(e.get("name") or "") == "gate_policy.proposed":
            prop = e
            break
    if not prop:
        raise HTTPException(status_code=404, detail="proposal_not_found")
    args = prop.get("args") if isinstance(prop.get("args"), dict) else {}
    res = prop.get("result") if isinstance(prop.get("result"), dict) else {}
    pid = str(args.get("policy_id") or "")
    if not pid:
        raise HTTPException(status_code=400, detail="invalid_proposal")

    deny = await rbac_guard(http_request=http_request, payload=body or {}, action="update", resource_type="policy", resource_id=f"gate_policy:{pid}")
    if deny:
        return deny

    approval_request_id = str(body.get("approval_request_id") or args.get("approval_request_id") or "").strip() or None
    require_approval = bool(approval_request_id)
    if require_approval:
        # Ensure approved
        mgr = _approval_mgr(rt)
        from core.security.skill_signature_gate import is_approval_resolved_approved

        if not is_approval_resolved_approved(mgr, str(approval_request_id)):
            links = governance_links(change_id=str(change_id), approval_request_id=str(approval_request_id))
            next_actions = [
                {"type": "open_ui", "label": "打开审批中心", "ui": links.get("approvals_ui"), "recommended": True},
                {"type": "open_ui", "label": "打开变更详情", "ui": links.get("change_control_ui")},
                {"type": "retry", "label": "重试应用", "api": {"method": "POST", "path": f"/api/core/governance/gate-policies/changes/{str(change_id)}/apply"}},
            ]
            raise HTTPException(
                status_code=409,
                detail=gate_error_envelope(
                    code="approval_required",
                    message="approval_required",
                    change_id=str(change_id),
                    approval_request_id=str(approval_request_id),
                    links=links,
                    next_actions=next_actions,
                ),
            )

    next_cfg = None
    try:
        next_cfg = (res.get("next") or {}).get("config")
    except Exception:
        next_cfg = None
    if not isinstance(next_cfg, dict):
        raise HTTPException(status_code=400, detail="invalid_next_config")
    set_default = bool(args.get("set_default"))

    # Apply as a normal upsert, preserving version history.
    data = await _load_all(store)
    items: List[Dict[str, Any]] = [x for x in (data.get("items") or []) if isinstance(x, dict)]
    updated = None
    prev_sha = ""
    for i, it in enumerate(items):
        if str(it.get("policy_id") or "") != pid:
            continue
        prev_sha = _sha(it.get("config") or {})
        revs = it.get("revisions") if isinstance(it.get("revisions"), list) else []
        revs = [x for x in revs if isinstance(x, dict)]
        revs.append({"version": int(it.get("version") or 1), "updated_at": float(it.get("updated_at") or 0), "config": it.get("config") or {}, "sha256": prev_sha})
        if len(revs) > 20:
            revs = revs[-20:]
        it["config"] = next_cfg
        it["revisions"] = revs
        it["version"] = int(it.get("version") or 1) + 1
        it["updated_at"] = float(time.time())
        updated = it
        items[i] = it
        break
    if updated is None:
        updated = _normalize_policy_obj({"policy_id": pid, "config": next_cfg, "name": pid, "description": ""})
        updated["created_at"] = float(time.time())
        updated["updated_at"] = float(time.time())
        items.append(updated)
    data["items"] = items
    if set_default:
        data["default_id"] = pid
    await _save_all(store, data)

    links = governance_links(change_id=str(change_id), approval_request_id=str(approval_request_id) if approval_request_id else None)
    await record_changeset(
        store=store,
        name="gate_policy.applied",
        target_type="change",
        target_id=str(change_id),
        status="success",
        args={"policy_id": pid, "set_default": set_default, "approval_request_id": approval_request_id, "prev_sha256": prev_sha},
        result={"new_sha256": _sha(next_cfg), "version": int(updated.get("version") or 1), "links": links},
        user_id=str(http_request.headers.get("X-AIPLAT-ACTOR-ID") or "admin"),
        tenant_id=str(http_request.headers.get("X-AIPLAT-TENANT-ID") or "") or None,
        approval_request_id=str(approval_request_id) if approval_request_id else None,
    )
    return {"status": "ok", "change_id": str(change_id), "item": updated, "default_id": data.get("default_id"), "links": links}
