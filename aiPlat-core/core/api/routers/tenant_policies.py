from __future__ import annotations

import json
import os
import uuid
from typing import Annotated, Optional

from fastapi import APIRouter, Depends, HTTPException, Request

from core.api.deps.rbac import actor_from_http, rbac_guard
from core.api.utils.governance import governance_links
from core.harness.integration import KernelRuntime
from core.harness.kernel.runtime import get_kernel_runtime
from core.policy.engine import evaluate_tool_policy_snapshot

router = APIRouter()

RuntimeDep = Annotated[Optional[KernelRuntime], Depends(get_kernel_runtime)]


def _store(rt: Optional[KernelRuntime]):
    return getattr(rt, "execution_store", None) if rt else None


def _new_change_id() -> str:
    return f"chg-{uuid.uuid4().hex[:12]}"


@router.get("/policies/tenants")
async def list_tenant_policies(limit: int = 100, offset: int = 0, rt: RuntimeDep = None):
    store = _store(rt)
    if not store:
        raise HTTPException(status_code=503, detail="ExecutionStore not initialized")
    return await store.list_tenant_policies(limit=limit, offset=offset)


@router.get("/policies/tenants/{tenant_id}")
async def get_tenant_policy(tenant_id: str, rt: RuntimeDep = None):
    store = _store(rt)
    if not store:
        raise HTTPException(status_code=503, detail="ExecutionStore not initialized")
    item = await store.get_tenant_policy(tenant_id=str(tenant_id))
    if not item:
        raise HTTPException(status_code=404, detail="tenant_policy_not_found")
    return item


@router.get("/policies/tenants/{tenant_id}/effective")
async def get_effective_tenant_policy(tenant_id: str, rt: RuntimeDep = None):
    """
    Return the effective policy view (env defaults merged with tenant snapshot).
    This endpoint is read-only and intended for debugging/ops transparency.
    """
    store = _store(rt)
    if not store:
        raise HTTPException(status_code=503, detail="ExecutionStore not initialized")
    item = await store.get_tenant_policy(tenant_id=str(tenant_id))
    if not item:
        raise HTTPException(status_code=404, detail="tenant_policy_not_found")
    pol = item.get("policy") if isinstance(item, dict) else {}
    pol = pol if isinstance(pol, dict) else {}

    # ---- env defaults ----
    env_run_wait = {
        "enabled": os.getenv("AIPLAT_RUN_WAIT_AUTO_RESUME_ENABLED", "false").lower() in {"1", "true", "yes", "y"},
        "default": os.getenv("AIPLAT_RUN_WAIT_AUTO_RESUME_DEFAULT", "false").lower() in {"1", "true", "yes", "y"},
        "allowlist": str(os.getenv("AIPLAT_RUN_WAIT_AUTO_RESUME_ALLOWLIST", "*") or "*").strip() or "*",
    }
    env_approval_layering = {
        "policy": str(os.getenv("AIPLAT_APPROVAL_LAYER_POLICY", "both") or "both").strip().lower() or "both",
        "tool_force_list": str(os.getenv("AIPLAT_APPROVAL_TOOL_FORCE_LIST", "") or "").strip(),
    }
    try:
        env_sample_rate = float(os.getenv("AIPLAT_APPROVAL_SAMPLE_RATE", "0") or "0")
    except Exception:
        env_sample_rate = 0.0
    env_approval_review = {
        "mode": str(os.getenv("AIPLAT_APPROVAL_REVIEW_MODE", "always") or "always").strip().lower() or "always",
        "sample_rate": float(env_sample_rate),
        "high_risk_always": os.getenv("AIPLAT_APPROVAL_HIGH_RISK_ALWAYS", "true").lower() in {"1", "true", "yes", "y"},
        "force_list": str(os.getenv("AIPLAT_APPROVAL_FORCE_LIST", "") or "").strip(),
        "bypass_list": str(os.getenv("AIPLAT_APPROVAL_BYPASS_LIST", "") or "").strip(),
        "seed": str(os.getenv("AIPLAT_APPROVAL_SAMPLE_SEED", "") or "").strip(),
    }
    env_persona_routing = {
        "routes": [],
        "default_persona_template_id": "",
        "default_risk_level": "",
        "defaults_by_kind": {},
        "default_risk_by_kind": {},
    }

    # ---- tenant overrides ----
    run_wait = dict(env_run_wait)
    t_run_wait = pol.get("run_wait_auto_resume") if isinstance(pol.get("run_wait_auto_resume"), dict) else None
    if isinstance(t_run_wait, dict):
        if isinstance(t_run_wait.get("enabled"), bool):
            run_wait["enabled"] = bool(t_run_wait.get("enabled"))
        if isinstance(t_run_wait.get("default"), bool):
            run_wait["default"] = bool(t_run_wait.get("default"))
        if isinstance(t_run_wait.get("allowlist"), str) and str(t_run_wait.get("allowlist")).strip():
            run_wait["allowlist"] = str(t_run_wait.get("allowlist")).strip()

    approval_layering = dict(env_approval_layering)
    t_layer = pol.get("approval_layering") if isinstance(pol.get("approval_layering"), dict) else None
    if isinstance(t_layer, dict):
        if isinstance(t_layer.get("policy"), str) and str(t_layer.get("policy")).strip():
            approval_layering["policy"] = str(t_layer.get("policy")).strip().lower()
        if isinstance(t_layer.get("tool_force_list"), str):
            approval_layering["tool_force_list"] = str(t_layer.get("tool_force_list")).strip()

    approval_review = dict(env_approval_review)
    t_review = pol.get("approval_review") if isinstance(pol.get("approval_review"), dict) else None
    if isinstance(t_review, dict):
        if isinstance(t_review.get("mode"), str) and str(t_review.get("mode")).strip():
            approval_review["mode"] = str(t_review.get("mode")).strip().lower()
        if t_review.get("sample_rate") is not None:
            try:
                approval_review["sample_rate"] = float(t_review.get("sample_rate"))
            except Exception:
                pass
        if isinstance(t_review.get("high_risk_always"), bool):
            approval_review["high_risk_always"] = bool(t_review.get("high_risk_always"))
        if isinstance(t_review.get("force_list"), str):
            approval_review["force_list"] = str(t_review.get("force_list")).strip()
        if isinstance(t_review.get("bypass_list"), str):
            approval_review["bypass_list"] = str(t_review.get("bypass_list")).strip()
        if isinstance(t_review.get("seed"), str):
            approval_review["seed"] = str(t_review.get("seed")).strip()

    persona_routing = dict(env_persona_routing)
    t_pr = pol.get("persona_routing") if isinstance(pol.get("persona_routing"), dict) else None
    if isinstance(t_pr, dict):
        if isinstance(t_pr.get("routes"), list):
            persona_routing["routes"] = t_pr.get("routes")
        if isinstance(t_pr.get("default_persona_template_id"), str):
            persona_routing["default_persona_template_id"] = str(t_pr.get("default_persona_template_id")).strip()
        if isinstance(t_pr.get("default_risk_level"), str):
            persona_routing["default_risk_level"] = str(t_pr.get("default_risk_level")).strip().lower()
        if isinstance(t_pr.get("defaults_by_kind"), dict):
            persona_routing["defaults_by_kind"] = t_pr.get("defaults_by_kind")
        if isinstance(t_pr.get("default_risk_by_kind"), dict):
            persona_routing["default_risk_by_kind"] = t_pr.get("default_risk_by_kind")

    return {
        "tenant_id": str(tenant_id),
        "stored_version": item.get("version") if isinstance(item, dict) else None,
        "stored_updated_at": item.get("updated_at") if isinstance(item, dict) else None,
        "effective": {
            "run_wait_auto_resume": run_wait,
            "approval_layering": approval_layering,
            "approval_review": approval_review,
            "persona_routing": persona_routing,
        },
        "env_defaults": {
            "run_wait_auto_resume": env_run_wait,
            "approval_layering": env_approval_layering,
            "approval_review": env_approval_review,
            "persona_routing": env_persona_routing,
        },
    }


@router.put("/policies/tenants/{tenant_id}")
async def upsert_tenant_policy(tenant_id: str, request: dict, http_request: Request, rt: RuntimeDep = None):
    store = _store(rt)
    if not store:
        raise HTTPException(status_code=503, detail="ExecutionStore not initialized")
    deny = await rbac_guard(
        http_request=http_request,
        payload=request if isinstance(request, dict) else None,
        action="policy_upsert",
        resource_type="tenant_policy",
        resource_id=str(tenant_id),
    )
    if deny:
        return deny
    policy = (request or {}).get("policy")
    if not isinstance(policy, dict):
        raise HTTPException(status_code=400, detail="policy must be an object")
    version = (request or {}).get("version")
    if version is not None:
        try:
            version = int(version)
        except Exception:
            raise HTTPException(status_code=400, detail="invalid version")
    try:
        saved = await store.upsert_tenant_policy(tenant_id=str(tenant_id), policy=policy, version=version)
    except ValueError as e:
        if str(e) == "version_conflict":
            raise HTTPException(status_code=409, detail="version_conflict")
        raise

    change_id = _new_change_id()
    # Audit (best-effort)
    try:
        actor0 = actor_from_http(http_request, request if isinstance(request, dict) else None)
        await store.add_audit_log(
            action="tenant_policy_upsert",
            status="ok",
            tenant_id=str(tenant_id),
            actor_id=str((request or {}).get("actor_id") or actor0.get("actor_id") or "admin"),
            actor_role=str(actor0.get("actor_role") or "") or None,
            resource_type="tenant_policy",
            resource_id=str(tenant_id),
            detail={"version": saved.get("version")},
        )
    except Exception:
        pass
    # Changeset (best-effort): store only hash + version
    try:
        import hashlib

        from core.governance.changeset import record_changeset

        await record_changeset(
            store=store,
            name="tenant_policy_upsert",
            target_type="change",
            target_id=str(change_id),
            args={
                "operation": "tenant_policy_upsert",
                "tenant_id": str(tenant_id),
                "prev_version": int(version) if isinstance(version, int) else None,
            },
            result={
                "version": saved.get("version") if isinstance(saved, dict) else None,
                "policy_sha256": hashlib.sha256(json.dumps(policy, sort_keys=True).encode("utf-8")).hexdigest(),
            },
            user_id=str((request or {}).get("actor_id") or "admin"),
            tenant_id=str(tenant_id),
        )
    except Exception:
        pass
    # Attach change control links for UI
    out = dict(saved or {}) if isinstance(saved, dict) else {"tenant_id": str(tenant_id), "policy": policy}
    out["change_id"] = str(change_id)
    out["links"] = governance_links(change_id=str(change_id))
    return out


@router.get("/policies/tenants/{tenant_id}/evaluate-tool")
async def evaluate_tenant_tool_policy(tenant_id: str, tool_name: str, http_request: Request, rt: RuntimeDep = None):
    """
    Evaluate a single tool against tenant policy (best-effort).
    Returns: allow | deny | approval_required with policy_version and matched rule.
    """
    store = _store(rt)
    if not store:
        raise HTTPException(status_code=503, detail="ExecutionStore not initialized")
    item = await store.get_tenant_policy(tenant_id=str(tenant_id))
    if not item:
        raise HTTPException(status_code=404, detail="tenant_policy_not_found")
    policy = item.get("policy") if isinstance(item, dict) else {}
    actor = actor_from_http(http_request, None)
    ev = evaluate_tool_policy_snapshot(
        policy=policy if isinstance(policy, dict) else None,
        policy_version=item.get("version") if isinstance(item, dict) else None,
        tenant_id=str(tenant_id),
        actor_id=actor.get("actor_id"),
        actor_role=actor.get("actor_role"),
        tool_name=str(tool_name),
        tool_args=None,
    )
    return {
        "tenant_id": str(tenant_id),
        "tool_name": str(tool_name),
        "decision": ev.decision.value,
        "policy_version": ev.policy_version,
        "matched_rule": ev.matched_rule,
    }
