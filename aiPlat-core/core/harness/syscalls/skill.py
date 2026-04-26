"""
sys_skill - Skill syscall wrappers (Phase 2).

Centralizes skill invocation so future gates can be enforced here:
- TraceGate (span + audit record)
- ResilienceGate (timeout/retry)
"""

from __future__ import annotations

import asyncio
import os
import re
from core.harness.kernel.execution_context import ActiveChangeContract, set_active_change_contract
from typing import Any, Dict, Optional

from ..interfaces import SkillContext
from core.harness.infrastructure.gates import TraceGate, ContextGate, ResilienceGate, PolicyGate, PolicyDecision
from core.harness.kernel.runtime import get_kernel_runtime
import time
from core.harness.kernel.execution_context import get_active_release_context, get_active_request_context
from core.harness.kernel.execution_context import set_active_approval_request_id, reset_active_approval_request_id
from core.harness.kernel.execution_context import get_active_tenant_policy_context
from core.apps.tools.skill_tools import resolve_executable_skill_permission


async def sys_skill_call(
    skill: Any,
    params: Dict[str, Any],
    *,
    context: Optional[SkillContext] = None,
    user_id: str = "system",
    session_id: str = "default",
    timeout_seconds: Optional[float] = None,
    trace_context: Optional[Dict[str, Any]] = None,
) -> Any:
    """Execute a skill call."""
    trace_gate = TraceGate()
    ctx_gate = ContextGate()
    res_gate = ResilienceGate()
    policy_gate = PolicyGate()

    # Start span early so "fast-fail" (missing skill) is still observable.
    skill_name = str(getattr(skill, "name", None) or getattr(getattr(skill, "_config", None), "name", "") or "")
    span = await trace_gate.start(
        "sys.skill.call",
        attributes={
            "skill": skill_name,
            "trace_id": (trace_context or {}).get("trace_id") if isinstance(trace_context, dict) else None,
        },
    )
    start_ts = time.time()
    _ar = get_active_release_context()
    _pr = get_active_request_context()
    coding_profile = (
        str((trace_context or {}).get("coding_policy_profile") or "off").strip().lower()
        if isinstance(trace_context, dict)
        else "off"
    )
    # Approval layering policy: tenant policy override -> env fallback
    approval_layer_policy = str(os.getenv("AIPLAT_APPROVAL_LAYER_POLICY", "both") or "both").strip().lower()
    try:
        tpol = get_active_tenant_policy_context()
        pol0 = getattr(tpol, "policy", None) if tpol else None
        layer = pol0.get("approval_layering") if isinstance(pol0, dict) else None
        if isinstance(layer, dict) and isinstance(layer.get("policy"), str) and layer.get("policy").strip():
            approval_layer_policy = str(layer.get("policy")).strip().lower()
    except Exception:
        pass

    async def _emit_routing_event(status: str, *, extra: Optional[Dict[str, Any]] = None, approval_request_id: Optional[str] = None) -> None:
        """Emit best-effort routing event for observability/funnel metrics."""
        try:
            runtime = get_kernel_runtime()
            store = getattr(runtime, "execution_store", None) if runtime else None
            if store is None:
                return
            end_ts = time.time()
            await store.add_syscall_event(
                {
                    "trace_id": span.trace_id,
                    "span_id": getattr(span, "span_id", None),
                    "run_id": (trace_context or {}).get("run_id") if isinstance(trace_context, dict) else None,
                    "kind": "routing",
                    "name": "skill_route",
                    "status": str(status),
                    "target_type": _ar.target_type if _ar else None,
                    "target_id": _ar.target_id if _ar else None,
                    "tenant_id": getattr(_pr, "tenant_id", None),
                    "user_id": user_id,
                    "session_id": session_id,
                    "start_time": start_ts,
                    "end_time": end_ts,
                    "duration_ms": (end_ts - start_ts) * 1000.0,
                    "args": {
                        "skill": skill_name,
                        "params_keys": sorted(list((params or {}).keys()))[:50],
                        "routing_decision_id": (trace_context or {}).get("routing_decision_id") if isinstance(trace_context, dict) else None,
                        "coding_policy_profile": coding_profile,
                        **(extra or {}),
                    },
                    "approval_request_id": approval_request_id,
                    "created_at": end_ts,
                }
            )
        except Exception:
            return

    def _extract_query_text(p: Dict[str, Any]) -> str:
        # best-effort: common field names used by skills
        for k in ("prompt", "query", "text", "input", "question", "instruction"):
            v = p.get(k)
            if isinstance(v, str) and v.strip():
                return v.strip()
        # fallback: first string field
        for _, v in (p or {}).items():
            if isinstance(v, str) and v.strip():
                return v.strip()
        return ""

    def _norm(s: str) -> str:
        s0 = str(s or "").lower().strip()
        s0 = re.sub(r"[\s\-\._/]+", " ", s0)
        s0 = re.sub(r"[^\w\u4e00-\u9fff ]+", "", s0)
        return s0.strip()

    def _tokenize(s: str) -> set[str]:
        s0 = _norm(s)
        if not s0:
            return set()
        toks = set()
        for w in s0.split():
            if len(w) >= 2:
                toks.add(w)
        # add simple CJK bigrams (best-effort)
        for seg in re.findall(r"[\u4e00-\u9fff]{2,}", s0):
            for i in range(0, max(0, len(seg) - 1)):
                toks.add(seg[i : i + 2])
        return toks

    async def _emit_candidates_event(selected_skill: str, prepared: Dict[str, Any]) -> None:
        """
        Emit routing candidates snapshot. This is a best-effort, heuristic view:
        candidates are computed from (trigger_conditions + keywords + description) overlap with query text.
        """
        try:
            runtime = get_kernel_runtime()
            if runtime is None:
                return
            store = getattr(runtime, "execution_store", None)
            if store is None:
                return
            from core.harness.routing.skill_routing import compute_skill_candidates, extract_query_text

            q = extract_query_text(prepared or {})
            if not q:
                return

            skills: List[Dict[str, Any]] = []

            async def _scan_mgr(mgr: Any, scope: str) -> None:
                if mgr is None:
                    return
                try:
                    items = await mgr.list_skills(None, None, 400, 0)
                except Exception:
                    items = []
                for s in items or []:
                    try:
                        meta = getattr(s, "metadata", None)
                        meta = meta if isinstance(meta, dict) else {}
                        skills.append(
                            {
                                "skill_id": str(getattr(s, "id", "") or ""),
                                "name": str(getattr(s, "name", "") or ""),
                                "description": str(getattr(s, "description", "") or ""),
                                "scope": scope,
                                "trigger_conditions": meta.get("trigger_conditions") or meta.get("trigger_keywords") or [],
                                "keywords": meta.get("keywords") if isinstance(meta.get("keywords"), dict) else {},
                            }
                        )
                    except Exception:
                        continue

            await _scan_mgr(getattr(runtime, "workspace_skill_manager", None), "workspace")
            await _scan_mgr(getattr(runtime, "skill_manager", None), "engine")

            top = compute_skill_candidates(query_text=q, skills=skills, top_k=8)
            top = [{"skill_id": c.skill_id, "name": c.name, "scope": c.scope, "score": c.score, "overlap": c.overlap} for c in top]
            end_ts = time.time()
            await store.add_syscall_event(
                {
                    "trace_id": span.trace_id,
                    "span_id": getattr(span, "span_id", None),
                    "run_id": (trace_context or {}).get("run_id") if isinstance(trace_context, dict) else None,
                    "kind": "routing",
                    "name": "skill_candidates",
                    "status": "candidates",
                    "tenant_id": getattr(_pr, "tenant_id", None),
                    "user_id": user_id,
                    "session_id": session_id,
                    "start_time": start_ts,
                    "end_time": end_ts,
                    "duration_ms": (end_ts - start_ts) * 1000.0,
                    "args": {
                        "selected_skill": selected_skill,
                        "query_excerpt": q[:220],
                        "candidates": top,
                        "routing_decision_id": (trace_context or {}).get("routing_decision_id") if isinstance(trace_context, dict) else None,
                        "coding_policy_profile": coding_profile,
                    },
                    "created_at": end_ts,
                }
            )
        except Exception:
            return

    if skill is None or not hasattr(skill, "execute"):
        end_ts = time.time()
        await trace_gate.end(span, success=False)
        runtime = get_kernel_runtime()
        store = getattr(runtime, "execution_store", None) if runtime else None
        if store is not None:
            try:
                await store.add_syscall_event(
                    {
                        "trace_id": span.trace_id,
                        "span_id": getattr(span, "span_id", None),
                        "run_id": (trace_context or {}).get("run_id") if isinstance(trace_context, dict) else None,
                        "kind": "skill",
                        "name": skill_name or "<unknown>",
                        "status": "failed",
                        "target_type": _ar.target_type if _ar else None,
                        "target_id": _ar.target_id if _ar else None,
                        "tenant_id": getattr(_pr, "tenant_id", None),
                        "user_id": user_id,
                        "session_id": session_id,
                        "start_time": start_ts,
                        "end_time": end_ts,
                        "duration_ms": (end_ts - start_ts) * 1000.0,
                        "args": {"params": params or {}},
                        "error": "skill_not_executable",
                        "error_code": "SKILL_NOT_EXECUTABLE",
                    }
                )
            except Exception:
                pass
        raise RuntimeError("Skill is not executable")

    ctx = context or SkillContext(session_id=session_id, user_id=user_id, variables=params or {})
    prepared_params = ctx_gate.prepare_tool_args(params or {}, context=trace_context or {})
    if coding_profile and coding_profile not in ("off", "none", "0", "false"):
        # Provide profile hint to skill implementations (e.g., _GenericSkill).
        try:
            if isinstance(prepared_params, dict):
                prepared_params.setdefault("_coding_policy_profile", coding_profile)
        except Exception:
            pass

    # routing stage: selected for invocation (before policy gate)
    await _emit_routing_event("selected")
    # candidates snapshot might be emitted at the router/loop layer; avoid double counting.
    try:
        if not (isinstance(trace_context, dict) and trace_context.get("routing_candidates_emitted") is True):
            await _emit_candidates_event(skill_name or "<unknown>", prepared_params or {})
    except Exception:
        pass

    # ---- P1: executable skill governance (deny/ask/allow + approval) ----
    try:
        if os.getenv("AIPLAT_ENFORCE_EXECUTABLE_SKILL_POLICY", "true").lower() in ("1", "true", "yes", "y"):
            # propagate identity/run
            args = dict(prepared_params or {})
            args.setdefault("_user_id", user_id)
            args.setdefault("_session_id", session_id)
            # Best-effort: bind run_id for approval replay/linkage. For skill executions,
            # session_id is typically the execution id (run_*), so we use it as fallback.
            if "_run_id" not in args:
                try:
                    if isinstance(trace_context, dict) and trace_context.get("run_id"):
                        args["_run_id"] = str(trace_context.get("run_id"))
                    elif isinstance(session_id, str) and session_id.startswith(("run_", "run-")):
                        args["_run_id"] = str(session_id)
                except Exception:
                    pass
            try:
                if isinstance(trace_context, dict) and trace_context.get("tenant_id") and "_tenant_id" not in args:
                    args["_tenant_id"] = trace_context.get("tenant_id")
            except Exception:
                pass
            # Fallback tenant propagation from active request context.
            try:
                if "_tenant_id" not in args:
                    arq = get_active_request_context()
                    if arq and getattr(arq, "tenant_id", None):
                        args["_tenant_id"] = getattr(arq, "tenant_id")
            except Exception:
                pass
            # Resume semantics: allow passing approval_request_id via trace_context
            try:
                if isinstance(trace_context, dict):
                    arid = trace_context.get("approval_request_id") or trace_context.get("_approval_request_id")
                    if arid and "_approval_request_id" not in args:
                        args["_approval_request_id"] = str(arid)
            except Exception:
                pass
            try:
                arq = get_active_request_context()
                if arq and getattr(arq, "actor_role", None):
                    args.setdefault("_actor_role", getattr(arq, "actor_role"))
            except Exception:
                pass

            # ---- Coding policy (karpathy_v1) contract gate (Phase-2) ----
            # Goal: enforce Surgical + Goal-driven by requiring stable output contract.
            try:
                require_contract = os.getenv("AIPLAT_CODING_POLICY_REQUIRE_CONTRACT", "true").lower() in ("1", "true", "yes", "y")
                if require_contract and coding_profile == "karpathy_v1":
                    cfg = getattr(skill, "_config", None)
                    meta = getattr(cfg, "metadata", None) if cfg else None
                    meta = meta if isinstance(meta, dict) else {}
                    cat = str(meta.get("category") or "").strip().lower()
                    tags = meta.get("tags") or []
                    tags = [str(t).strip().lower() for t in tags] if isinstance(tags, list) else []
                    is_coding = (cat == "coding") or ("coding" in tags) or ("code" in tags)
                    if is_coding:
                        out_schema = {}
                        try:
                            out_schema = getattr(cfg, "output_schema", None) or {}
                        except Exception:
                            out_schema = {}
                        out_schema = out_schema if isinstance(out_schema, dict) else {}
                        required_keys = ["change_plan", "changed_files", "unrelated_changes", "acceptance_criteria", "rollback_plan"]
                        missing = [k for k in required_keys if k not in out_schema]
                        if missing:
                            args["_approval_required"] = True
                            args["_policy_reason"] = "missing_change_contract"
                            args["_missing_change_contract_keys"] = missing[:10]
            except Exception:
                pass

            # Basic permission posture for executable skills
            decision = resolve_executable_skill_permission(skill_name)
            if decision == "deny":
                end_ts = time.time()
                await trace_gate.end(span, success=False)
                runtime = get_kernel_runtime()
                store = getattr(runtime, "execution_store", None) if runtime else None
                if store is not None:
                    try:
                        await store.add_syscall_event(
                            {
                                "trace_id": span.trace_id,
                                "span_id": getattr(span, "span_id", None),
                                "run_id": (trace_context or {}).get("run_id") if isinstance(trace_context, dict) else None,
                                "kind": "skill",
                                "name": skill_name or "<unknown>",
                                "status": "policy_denied",
                                "target_type": _ar.target_type if _ar else None,
                                "target_id": _ar.target_id if _ar else None,
                                "tenant_id": getattr(_pr, "tenant_id", None),
                                "user_id": user_id,
                                "session_id": session_id,
                                "start_time": start_ts,
                                "end_time": end_ts,
                                "duration_ms": (end_ts - start_ts) * 1000.0,
                                "args": {"params": args},
                                "error": f"executable_skill_denied:{skill_name}",
                                "error_code": "EXEC_SKILL_DENIED",
                            }
                        )
                    except Exception:
                        pass
                # Return a structured result instead of raising (so loop can handle it).
                from core.harness.interfaces import SkillResult

                await _emit_routing_event("policy_denied", extra={"reason": "exec_skill_denied"})
                return SkillResult(success=False, output=None, error="policy_denied", metadata={"reason": "exec_skill_denied", "skill": skill_name})
            if decision == "ask":
                args["_approval_required"] = True

            # Require explicit permissions declaration unless disabled
            require_perm = os.getenv("AIPLAT_EXEC_SKILL_REQUIRE_PERMISSIONS", "true").lower() in ("1", "true", "yes", "y")
            if require_perm:
                try:
                    cfg = getattr(skill, "_config", None)
                    meta = getattr(cfg, "metadata", None) if cfg else None
                    perms = []
                    if isinstance(meta, dict):
                        perms = meta.get("permissions") or meta.get("permission") or []
                    if isinstance(perms, str):
                        perms = [perms]
                    if not isinstance(perms, list) or not [p for p in perms if str(p).strip()]:
                        args["_approval_required"] = True  # fail-safe: require approval if permissions are missing
                        args.setdefault("_policy_reason", "missing_permissions")
                except Exception:
                    args["_approval_required"] = True
                    args.setdefault("_policy_reason", "missing_permissions")

            # P0/P1: honor Skill Contract governance hints
            try:
                cfg = getattr(skill, "_config", None)
                meta = getattr(cfg, "metadata", None) if cfg else None
                meta = meta if isinstance(meta, dict) else {}
                if approval_layer_policy != "tool_only" and meta.get("requires_approval") is True:
                    args["_approval_required"] = True
            except Exception:
                pass

            # PolicyGate approval flow (mirrors sys_tool_call behavior)
            # tool_only: bypass skill-level approvals entirely (let tools request approvals).
            if approval_layer_policy == "tool_only":
                try:
                    args.pop("_approval_required", None)
                except Exception:
                    pass
                pr = None
            else:
                pr = await policy_gate.check_skill(user_id=user_id, skill_name=skill_name or "<unknown>", skill_args=args)
            if pr is not None and pr.decision == PolicyDecision.DENY:
                from core.harness.interfaces import SkillResult
                # Emit syscall event for observability (deny)
                try:
                    runtime = get_kernel_runtime()
                    store = getattr(runtime, "execution_store", None) if runtime else None
                    if store is not None:
                        end_ts = time.time()
                        await store.add_syscall_event(
                            {
                                "trace_id": span.trace_id,
                                "span_id": getattr(span, "span_id", None),
                                "run_id": (trace_context or {}).get("run_id") if isinstance(trace_context, dict) else None,
                                "kind": "skill",
                                "name": skill_name or "<unknown>",
                                "status": "policy_denied",
                                "target_type": _ar.target_type if _ar else None,
                                "target_id": _ar.target_id if _ar else None,
                                "tenant_id": getattr(_pr, "tenant_id", None),
                                "user_id": user_id,
                                "session_id": session_id,
                                "start_time": start_ts,
                                "end_time": end_ts,
                                "duration_ms": (end_ts - start_ts) * 1000.0,
                                "args": {
                                    "params": args,
                                    "routing_decision_id": (trace_context or {}).get("routing_decision_id") if isinstance(trace_context, dict) else None,
                                    "coding_policy_profile": coding_profile,
                                },
                                "error": f"policy_denied:{pr.reason}",
                                "error_code": "SKILL_POLICY_DENIED",
                            }
                        )
                except Exception:
                    pass

                await _emit_routing_event("policy_denied", extra={"reason": pr.reason})
                return SkillResult(success=False, output=None, error="policy_denied", metadata={"reason": pr.reason, "skill": skill_name})
            if pr is not None and pr.decision == PolicyDecision.APPROVAL_REQUIRED:
                from core.harness.interfaces import SkillResult
                if approval_layer_policy == "tool_only":
                    prepared_params = args
                    await _emit_routing_event("approval_bypassed", extra={"reason": pr.reason, "policy": "tool_only"}, approval_request_id=pr.approval_request_id)
                else:
                    # Emit syscall event for observability (approval required)
                    try:
                        runtime = get_kernel_runtime()
                        store = getattr(runtime, "execution_store", None) if runtime else None
                        if store is not None:
                            end_ts = time.time()
                            await store.add_syscall_event(
                                {
                                    "trace_id": span.trace_id,
                                    "span_id": getattr(span, "span_id", None),
                                    "run_id": (trace_context or {}).get("run_id") if isinstance(trace_context, dict) else None,
                                    "kind": "skill",
                                    "name": skill_name or "<unknown>",
                                    "status": "approval_required",
                                    "target_type": _ar.target_type if _ar else None,
                                    "target_id": _ar.target_id if _ar else None,
                                    "tenant_id": getattr(_pr, "tenant_id", None),
                                    "user_id": user_id,
                                    "session_id": session_id,
                                    "start_time": start_ts,
                                    "end_time": end_ts,
                                    "duration_ms": (end_ts - start_ts) * 1000.0,
                                    "args": {
                                        "params": args,
                                        "routing_decision_id": (trace_context or {}).get("routing_decision_id") if isinstance(trace_context, dict) else None,
                                        "coding_policy_profile": coding_profile,
                                    },
                                    "result": {"approval_request_id": pr.approval_request_id, "reason": pr.reason},
                                    "approval_request_id": pr.approval_request_id,
                                    "error": f"approval_required:{pr.reason}",
                                    "error_code": "SKILL_APPROVAL_REQUIRED",
                                }
                            )
                            # PR-08 parity: emit run event so /runs/{run_id}/wait can surface approval_request_id.
                            try:
                                _run_id = args.get("_run_id")
                                if _run_id:
                                    await store.append_run_event(
                                        run_id=str(_run_id),
                                        event_type="approval_requested",
                                        trace_id=span.trace_id,
                                        tenant_id=str(getattr(_pr, "tenant_id", None)) if getattr(_pr, "tenant_id", None) else None,
                                        payload={
                                            "kind": "skill",
                                            "skill": skill_name or "<unknown>",
                                            "approval_request_id": pr.approval_request_id,
                                            "reason": pr.reason,
                                        },
                                    )
                            except Exception:
                                pass
                    except Exception:
                        pass

                    await _emit_routing_event("approval_required", extra={"reason": pr.reason}, approval_request_id=pr.approval_request_id)
                    return SkillResult(
                        success=False,
                        output=None,
                        error="approval_required",
                        metadata={"approval_request_id": pr.approval_request_id, "reason": pr.reason, "skill": skill_name},
                    )

            prepared_params = args
    except Exception:
        # Fail-open for compatibility
        pass

    async def _run():
        # P4: propagate approval_request_id across nested tool calls (when present).
        tok = None
        try:
            arid = None
            if isinstance(prepared_params, dict):
                arid = prepared_params.get("_approval_request_id")
            if isinstance(arid, str) and arid:
                tok = set_active_approval_request_id(str(arid))
        except Exception:
            tok = None
        try:
            return await skill.execute(ctx, prepared_params)  # type: ignore[misc]
        finally:
            if tok is not None:
                try:
                    reset_active_approval_request_id(tok)
                except Exception:
                    pass

    # (span already started above)
    try:
        retries = int(os.getenv("AIPLAT_SKILL_RETRIES", "0") or "0")
        result = await res_gate.run(_run, retries=retries, timeout_seconds=timeout_seconds)
        end_ts = time.time()
        await trace_gate.end(span, success=bool(getattr(result, "success", True)))

        # ---- Diff Gate helper: capture change contract from coding skill output (best-effort) ----
        try:
            if coding_profile == "karpathy_v1" and bool(getattr(result, "success", True)):
                cfg = getattr(skill, "_config", None)
                meta = getattr(cfg, "metadata", None) if cfg else None
                meta = meta if isinstance(meta, dict) else {}
                cat = str(meta.get("category") or "").strip().lower()
                tags = meta.get("tags") or []
                tags = [str(t).strip().lower() for t in tags] if isinstance(tags, list) else []
                is_coding = (cat == "coding") or ("coding" in tags) or ("code" in tags)
                out = getattr(result, "output", None)
                if is_coding and isinstance(out, dict):
                    cf = out.get("changed_files")
                    ac = out.get("acceptance_criteria")
                    if isinstance(cf, list) or isinstance(ac, list) or ("unrelated_changes" in out):
                        contract = ActiveChangeContract(
                            source_skill=str(skill_name or ""),
                            changed_files=[str(x) for x in (cf or []) if str(x).strip()][:200] if isinstance(cf, list) else [],
                            unrelated_changes=out.get("unrelated_changes") if isinstance(out.get("unrelated_changes"), bool) else None,
                            acceptance_criteria=[str(x) for x in (ac or []) if str(x).strip()][:50] if isinstance(ac, list) else [],
                            change_plan=str(out.get("change_plan") or "")[:2000],
                            rollback_plan=str(out.get("rollback_plan") or "")[:2000],
                            updated_at=end_ts,
                        )
                        set_active_change_contract(contract)
        except Exception:
            pass

        runtime = get_kernel_runtime()
        store = getattr(runtime, "execution_store", None) if runtime else None
        if store is not None:
            try:
                await store.add_syscall_event(
                    {
                        "trace_id": span.trace_id,
                        "span_id": getattr(span, "span_id", None),
                        "run_id": (trace_context or {}).get("run_id") if isinstance(trace_context, dict) else None,
                        "kind": "skill",
                        "name": skill_name or "<unknown>",
                        "status": "success" if bool(getattr(result, "success", True)) else "failed",
                        "target_type": _ar.target_type if _ar else None,
                        "target_id": _ar.target_id if _ar else None,
                        "tenant_id": getattr(_pr, "tenant_id", None),
                        "user_id": user_id,
                        "session_id": session_id,
                        "start_time": start_ts,
                        "end_time": end_ts,
                        "duration_ms": (end_ts - start_ts) * 1000.0,
                        "args": {
                            "params": prepared_params,
                            "routing_decision_id": (trace_context or {}).get("routing_decision_id") if isinstance(trace_context, dict) else None,
                            "coding_policy_profile": coding_profile,
                        },
                        "result": {"output": getattr(result, "output", None), "error": getattr(result, "error", None)},
                        "error_code": "SKILL_FAILED" if not bool(getattr(result, "success", True)) else None,
                    }
                )
            except Exception:
                pass
        return result
    except Exception:
        end_ts = time.time()
        await trace_gate.end(span, success=False)
        runtime = get_kernel_runtime()
        store = getattr(runtime, "execution_store", None) if runtime else None
        if store is not None:
            try:
                await store.add_syscall_event(
                    {
                        "trace_id": span.trace_id,
                        "span_id": getattr(span, "span_id", None),
                        "run_id": (trace_context or {}).get("run_id") if isinstance(trace_context, dict) else None,
                        "kind": "skill",
                        "name": skill_name or "<unknown>",
                        "status": "failed",
                        "target_type": _ar.target_type if _ar else None,
                        "target_id": _ar.target_id if _ar else None,
                        "tenant_id": getattr(_pr, "tenant_id", None),
                        "user_id": user_id,
                        "session_id": session_id,
                        "start_time": start_ts,
                        "end_time": end_ts,
                        "duration_ms": (end_ts - start_ts) * 1000.0,
                        "args": {
                            "params": prepared_params,
                            "routing_decision_id": (trace_context or {}).get("routing_decision_id") if isinstance(trace_context, dict) else None,
                            "coding_policy_profile": coding_profile,
                        },
                        "error": "skill_error",
                        "error_code": "SKILL_ERROR",
                    }
                )
            except Exception:
                pass
        raise
