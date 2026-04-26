from __future__ import annotations

import time
from typing import Annotated, Any, Dict, Optional

from fastapi import APIRouter, Depends, HTTPException, Request

from core.api.deps.rbac import actor_from_http, rbac_guard
from core.api.utils.governance import governance_links
from core.governance.changeset import record_changeset
from core.governance.gating import autosmoke_enforce, gate_with_change_control, new_change_id
from core.harness.integration import KernelRuntime
from core.harness.kernel.runtime import get_kernel_runtime
from core.schemas import UpsertEvaluationPolicyRequest, UpsertProjectEvaluationPolicyRequest

router = APIRouter()

RuntimeDep = Annotated[Optional[KernelRuntime], Depends(get_kernel_runtime)]


def _store(rt: Optional[KernelRuntime]):
    return getattr(rt, "execution_store", None) if rt else None


def _runtime_env() -> str:
    from core.mcp.prod_policy import runtime_env

    return runtime_env()


@router.get("/evaluation/policy/latest")
async def get_latest_evaluation_policy(rt: RuntimeDep = None):
    """
    Returns the latest evaluation_policy (global default).
    """
    store = _store(rt)
    if not store:
        raise HTTPException(status_code=503, detail="ExecutionStore not initialized")
    res = await store.list_learning_artifacts(
        target_type="system",
        target_id="default",
        kind="evaluation_policy",
        limit=20,
        offset=0,
    )
    items = (res or {}).get("items") if isinstance(res, dict) else None
    if not isinstance(items, list) or not items:
        from core.harness.evaluation.policy import DEFAULT_POLICY

        return {"status": "ok", "item": {"payload": DEFAULT_POLICY, "artifact_id": None}}
    items2 = sorted(items, key=lambda x: float((x or {}).get("created_at") or 0), reverse=True)
    return {"status": "ok", "item": items2[0]}


@router.get("/projects/{project_id}/evaluation/policy/latest")
async def get_latest_project_evaluation_policy(project_id: str, rt: RuntimeDep = None):
    """
    Returns:
      - item: latest project policy (may be None)
      - merged: system/default merged with project override
    """
    store = _store(rt)
    if not store:
        raise HTTPException(status_code=503, detail="ExecutionStore not initialized")
    pid = str(project_id)
    # project
    proj = await store.list_learning_artifacts(target_type="project", target_id=pid, kind="evaluation_policy", limit=10, offset=0)
    items = (proj or {}).get("items") if isinstance(proj, dict) else None
    proj_item = None
    proj_payload = None
    if isinstance(items, list) and items:
        items2 = sorted(items, key=lambda x: float((x or {}).get("created_at") or 0), reverse=True)
        proj_item = items2[0]
        proj_payload = (proj_item or {}).get("payload") if isinstance(proj_item, dict) else None

    # system
    sys_res = await store.list_learning_artifacts(target_type="system", target_id="default", kind="evaluation_policy", limit=10, offset=0)
    sitems = (sys_res or {}).get("items") if isinstance(sys_res, dict) else None
    sys_payload = None
    if isinstance(sitems, list) and sitems:
        sitems2 = sorted(sitems, key=lambda x: float((x or {}).get("created_at") or 0), reverse=True)
        sys_payload = (sitems2[0] or {}).get("payload") if isinstance(sitems2[0], dict) else None

    from core.harness.evaluation.policy import DEFAULT_POLICY, EvaluationPolicy, merge_policy

    merged_obj = merge_policy(sys_payload if isinstance(sys_payload, dict) else DEFAULT_POLICY, proj_payload if isinstance(proj_payload, dict) else {})
    merged = EvaluationPolicy.from_dict(merged_obj).to_dict()
    return {"status": "ok", "item": proj_item, "merged": merged}


@router.post("/projects/{project_id}/evaluation/policy")
async def upsert_project_evaluation_policy(
    project_id: str,
    request: UpsertProjectEvaluationPolicyRequest,
    http_request: Request,
    rt: RuntimeDep = None,
):
    """
    Upsert project evaluation policy (partial or full). Body: { "policy": {...}, "mode": "merge"|"replace" }
    - merge (default): deep-merge into current project policy
    - replace: replace project policy payload entirely
    """
    store = _store(rt)
    if not store:
        raise HTTPException(status_code=503, detail="ExecutionStore not initialized")
    pid = str(project_id)
    body = request.dict(exclude_none=True) if hasattr(request, "dict") else {}
    deny = await rbac_guard(http_request=http_request, payload=body, action="update", resource_type="policy", resource_id=f"evaluation_policy:project:{pid}")
    if deny:
        return deny
    pol = body.get("policy")
    if not isinstance(pol, dict):
        raise HTTPException(status_code=400, detail="missing_policy")
    mode = str(body.get("mode") or "merge").lower()

    from core.harness.evaluation.policy import EvaluationPolicy, merge_policy
    from core.learning.manager import LearningManager
    from core.learning.types import LearningArtifactKind

    actor = actor_from_http(http_request, body or {})
    # Load existing project policy for merge
    cur: Dict[str, Any] = {}
    if mode != "replace":
        try:
            res = await store.list_learning_artifacts(target_type="project", target_id=pid, kind="evaluation_policy", limit=5, offset=0)
            items = (res or {}).get("items") if isinstance(res, dict) else None
            if isinstance(items, list) and items:
                items2 = sorted(items, key=lambda x: float((x or {}).get("created_at") or 0), reverse=True)
                cur = (items2[0] or {}).get("payload") if isinstance(items2[0], dict) else {}
        except Exception:
            cur = {}
    merged_obj = merge_policy(cur if isinstance(cur, dict) else {}, pol) if mode != "replace" else pol
    normalized = EvaluationPolicy.from_dict(merged_obj).to_dict()

    # Optional change-control gating (autosmoke enforce)
    change_id = new_change_id()
    try:
        if autosmoke_enforce(store=store):
            change_id = await gate_with_change_control(
                store=store,
                operation="evaluation_policy.project.upsert",
                targets=[("policy", f"evaluation_policy:project:{pid}")],
                actor={"actor_id": actor.get("actor_id"), "actor_role": actor.get("actor_role")},
            )
    except HTTPException:
        raise
    except Exception:
        pass

    mgr = LearningManager(execution_store=store)
    art = await mgr.create_artifact(
        kind=LearningArtifactKind.EVALUATION_POLICY,
        target_type="project",
        target_id=pid,
        version=f"evaluation_policy:{int(time.time())}",
        status="draft",
        payload=normalized,
        metadata={"source": "manual", "mode": mode, "actor_id": actor.get("actor_id"), "actor_role": actor.get("actor_role"), "change_id": change_id},
        trace_id=None,
        run_id=None,
    )
    # Record governance change event (best-effort)
    try:
        await record_changeset(
            store=store,
            name="evaluation_policy.project.upsert",
            target_type="change",
            target_id=change_id,
            status="success",
            args={"project_id": pid, "mode": mode},
            user_id=str(actor.get("actor_id") or "admin"),
        )
    except Exception:
        pass
    return {
        "status": "ok",
        "artifact_id": art.artifact_id,
        "policy": normalized,
        "project_id": pid,
        "change_id": change_id,
        "links": governance_links(change_id=change_id),
    }


@router.post("/evaluation/policy")
async def upsert_evaluation_policy(request: UpsertEvaluationPolicyRequest, http_request: Request, rt: RuntimeDep = None):
    """
    Upsert global evaluation policy.
    Body: { "policy": {...} }
    """
    store = _store(rt)
    if not store:
        raise HTTPException(status_code=503, detail="ExecutionStore not initialized")
    body = request.dict(exclude_none=True) if hasattr(request, "dict") else {}
    deny = await rbac_guard(http_request=http_request, payload=body or {}, action="update", resource_type="policy", resource_id="evaluation_policy:default")
    if deny:
        return deny
    pol = (body or {}).get("policy")
    if not isinstance(pol, dict):
        raise HTTPException(status_code=400, detail="missing_policy")

    from core.harness.evaluation.policy import EvaluationPolicy
    from core.learning.manager import LearningManager
    from core.learning.types import LearningArtifactKind

    actor = actor_from_http(http_request, body or {})
    policy = EvaluationPolicy.from_dict(pol).to_dict()
    mgr = LearningManager(execution_store=store)
    art = await mgr.create_artifact(
        kind=LearningArtifactKind.EVALUATION_POLICY,
        target_type="system",
        target_id="default",
        version=f"evaluation_policy:{int(time.time())}",
        status="draft",
        payload=policy,
        metadata={"source": "manual", "actor_id": actor.get("actor_id"), "actor_role": actor.get("actor_role")},
        trace_id=None,
        run_id=None,
    )
    return {"status": "ok", "artifact_id": art.artifact_id, "policy": policy}


@router.post("/policies/evaluate")
async def evaluate_policy_debug(request: dict, http_request: Request, rt: RuntimeDep = None):
    """
    调试接口：评估 tenant policy + RBAC 对某个“操作”的决策（不产生任何副作用）。
    Body 示例：
      {
        "tenant_id": "t1",
        "actor_id": "admin",
        "actor_role": "operator",
        "kind": "tool",                 # tool | mcp_server
        "tool_name": "file_operations",
        "tool_args": {"path": "/tmp"},
        "server_name": "s1",
        "transport": "stdio",
        "server_metadata": {"prod_allowed": true}
      }
    """
    store = _store(rt)
    if not store:
        raise HTTPException(status_code=503, detail="ExecutionStore not initialized")

    kind = str((request or {}).get("kind") or "tool").strip().lower()
    tenant_id = str((request or {}).get("tenant_id") or "").strip() or None
    actor_id = str((request or {}).get("actor_id") or "").strip() or (http_request.headers.get("X-AIPLAT-ACTOR-ID") or "admin")
    actor_role = str((request or {}).get("actor_role") or "").strip() or (http_request.headers.get("X-AIPLAT-ACTOR-ROLE") or "")

    # RBAC (best-effort): normalize to an allow/deny with reason
    try:
        from core.security.rbac import check_permission, mode as rbac_mode

        if kind == "tool":
            rbac = check_permission(actor_role=actor_role, action="execute", resource_type="tool")
        elif kind == "mcp_server":
            rbac = check_permission(actor_role=actor_role, action="execute", resource_type="gateway")
        else:
            rbac = check_permission(actor_role=actor_role, action="read", resource_type="policy")
        rbac_out = {"allowed": bool(rbac.allowed), "reason": rbac.reason, "mode": rbac_mode()}
    except Exception as e:
        rbac_out = {"allowed": True, "reason": f"rbac_unavailable:{e}", "mode": "unknown"}

    # Policy engine eval
    try:
        from core.policy.engine import evaluate_tool, evaluate_mcp_server

        if kind == "tool":
            tool_name = str((request or {}).get("tool_name") or "").strip()
            if not tool_name:
                raise HTTPException(status_code=400, detail="tool_name is required when kind=tool")
            tool_args = (request or {}).get("tool_args") if isinstance((request or {}).get("tool_args"), dict) else None
            # inject identity fields (policy gate expects these keys)
            if isinstance(tool_args, dict):
                tool_args = dict(tool_args)
            else:
                tool_args = {}
            tool_args.setdefault("_tenant_id", tenant_id)
            tool_args.setdefault("_actor_role", actor_role)
            ev = await evaluate_tool(
                store=store,
                tenant_id=tenant_id,
                actor_id=actor_id,
                actor_role=actor_role,
                tool_name=tool_name,
                tool_args=tool_args,
            )
            policy_out = ev.to_dict() if hasattr(ev, "to_dict") else (ev if isinstance(ev, dict) else {"decision": "allow"})
        elif kind == "mcp_server":
            server_name = str((request or {}).get("server_name") or "").strip()
            transport = str((request or {}).get("transport") or "").strip().lower() or "sse"
            if not server_name:
                raise HTTPException(status_code=400, detail="server_name is required when kind=mcp_server")
            server_meta = (request or {}).get("server_metadata") if isinstance((request or {}).get("server_metadata"), dict) else None
            ev = await evaluate_mcp_server(
                store=store,
                tenant_id=tenant_id,
                actor_id=actor_id,
                actor_role=actor_role,
                server_name=server_name,
                transport=transport,
                server_metadata=server_meta,
            )
            policy_out = ev.to_dict() if hasattr(ev, "to_dict") else (ev if isinstance(ev, dict) else {"decision": "allow"})
        else:
            raise HTTPException(status_code=400, detail="kind must be tool|mcp_server")
    except HTTPException:
        raise
    except Exception as e:
        # prod 默认严格（fail-closed）
        decision = "deny" if _runtime_env() == "prod" else "deny"
        policy_out = {"decision": decision, "reason_code": "EVAL_ERROR", "reason": str(e), "tenant_id": tenant_id}

    # Final decision: RBAC deny > policy deny > approval_required > allow
    final_decision = "allow"
    if not bool(rbac_out.get("allowed", True)):
        final_decision = "deny"
    else:
        pd = str((policy_out or {}).get("decision") or "allow").lower()
        if pd == "deny":
            final_decision = "deny"
        elif pd == "approval_required":
            final_decision = "approval_required"

    return {
        "kind": kind,
        "input": {
            "tenant_id": tenant_id,
            "actor_id": actor_id,
            "actor_role": actor_role,
        },
        "rbac": rbac_out,
        "policy": policy_out,
        "final_decision": final_decision,
    }

