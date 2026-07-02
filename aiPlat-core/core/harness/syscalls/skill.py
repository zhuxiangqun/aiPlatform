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
from typing import Any, AsyncGenerator, Dict, Optional

from ..interfaces import SkillContext, SkillResult
from core.harness.infrastructure.gates import TraceGate, ContextGate, ResilienceGate, PolicyGate, PolicyDecision
from core.harness.kernel.runtime import get_kernel_runtime
import time
from core.harness.kernel.execution_context import get_active_release_context, get_active_request_context
from core.harness.kernel.execution_context import set_active_approval_request_id, reset_active_approval_request_id
from core.harness.kernel.execution_context import get_active_tenant_policy_context
# DI: resolve_executable_skill_permission via SkillPermissionResolver


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
    # Config-driven: which coding profiles require contract gate enforcement.
    strict_profiles = set(
        os.getenv("AIPLAT_STRICT_CODING_PROFILES", "karpathy_v1").split(",")
    )
    # Approval layering policy: tenant policy override -> env fallback
    approval_layer_policy = str(os.getenv("AIPLAT_APPROVAL_LAYER_POLICY", "both") or "both").strip().lower()
    if os.getenv("AIPLAT_APPROVALS_DISABLED", "").lower() in ("1", "true", "yes"):
        approval_layer_policy = "none"
    try:
        tpol = get_active_tenant_policy_context()
        pol0 = getattr(tpol, "policy", None) if tpol else None
        layer = pol0.get("approval_layering") if isinstance(pol0, dict) else None
        if isinstance(layer, dict) and isinstance(layer.get("policy"), str) and layer.get("policy").strip():
            approval_layer_policy = str(layer.get("policy")).strip().lower()
    except Exception as e:
        logging.warning(str(e), exc_info=True)

    # §5.93: Crisis gate — check skill params for crisis signals before execution
    try:
        from core.harness.security.crisis_gate import get_crisis_gate
        gate = get_crisis_gate()
        param_text = " ".join(str(v) for v in (params or {}).values() if isinstance(v, str))[:2000]
        if param_text:
            gate_result = gate.check(param_text, session_id=session_id, user_id=user_id)
            if gate_result.decision.value in ("block", "escalate"):
                _log = logging.getLogger("aiplat.skill")
                _log.warning(
                    "Skill %s blocked by crisis gate: severity=%s, decision=%s",
                    skill_name,
                    gate_result.crisis_result.severity.value if gate_result.crisis_result else "unknown",
                    gate_result.decision.value,
                )
                from core.harness.security.crisis_detector import CrisisEscalation
                raise CrisisEscalation(gate_result.crisis_result)
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
                    "parent_span_id": (trace_context or {}).get("parent_span_id") if isinstance(trace_context, dict) else None,
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
                    "parent_span_id": (trace_context or {}).get("parent_span_id") if isinstance(trace_context, dict) else None,
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
                        "parent_span_id": (trace_context or {}).get("parent_span_id") if isinstance(trace_context, dict) else None,
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
            except Exception as e:
                logging.warning(str(e), exc_info=True)
        raise RuntimeError("Skill is not executable")

    ctx = context or SkillContext(session_id=session_id, user_id=user_id, variables=params or {})
    prepared_params = ctx_gate.prepare_tool_args(params or {}, context=trace_context or {})
    if coding_profile and coding_profile not in ("off", "none", "0", "false"):
        # Provide profile hint to skill implementations (e.g., _GenericSkill).
        try:
            if isinstance(prepared_params, dict):
                prepared_params.setdefault("_coding_policy_profile", coding_profile)
        except Exception as e:
            logging.warning(str(e), exc_info=True)

    # routing stage: selected for invocation (before policy gate)
    await _emit_routing_event("selected")
    # candidates snapshot might be emitted at the router/loop layer; avoid double counting.
    try:
        if not (isinstance(trace_context, dict) and trace_context.get("routing_candidates_emitted") is True):
            await _emit_candidates_event(skill_name or "<unknown>", prepared_params or {})
    except Exception as e:
        logging.warning(str(e), exc_info=True)

    # ---- P1: executable skill governance (deny/ask/allow + approval) ----
    try:
        if os.getenv("AIPLAT_ENFORCE_EXECUTABLE_SKILL_POLICY", "true").lower() in ("1", "true", "yes", "y"):
            # propagate identity/run
            args = dict(prepared_params or {})
            args.setdefault("_user_id", user_id)
            args.setdefault("_session_id", session_id)
            # Inject caller Agent identity
            try:
                if isinstance(trace_context, dict) and trace_context.get("agent_id"):
                    args.setdefault("_agent_id", str(trace_context["agent_id"]))
                elif isinstance(session_id, str) and "agent" in session_id.lower():
                    args.setdefault("_agent_id", str(session_id))
            except Exception as e:
                logging.warning(str(e), exc_info=True)
            # Inject graph context for Skill awareness
            try:
                if "_graph_context" not in args:
                    gc = {}
                    try:
                        from core.harness.syscalls.code_intel_syscall import sys_code_intel_context
                        task_hint = str(args.get("task", args.get("question", "")))
                        if task_hint:
                            gc["code_graph"] = sys_code_intel_context(task_hint)
                    except Exception as e:
                        logging.warning(str(e), exc_info=True)
                    try:
                        from core.harness.knowledge.wiki_engine import search_pages
                        kbs = (trace_context or {}).get("knowledge_bases") or []
                        first_cid = kbs[0] if kbs else "default"
                        wiki_pages = search_pages(limit=1, collection_id=first_cid)
                        if wiki_pages:
                            gc["wiki_available"] = True
                            total = 0
                            for cid in (kbs or ["default"]):
                                total += len(search_pages(limit=500, collection_id=cid))
                            gc["wiki_pages"] = total
                            if kbs:
                                gc["wiki_collections"] = kbs
                    except Exception as e:
                        logging.warning(str(e), exc_info=True)
                    try:
                        from core.harness.knowledge.knowledge_ontology import CLASSES
                        gc["ontology_classes"] = [
                            {"label": c.label, "uri": c.uri, "categories": c.allowed_categories}
                            for c in CLASSES if c.allowed_categories
                        ]
                    except Exception as e:
                        logging.warning(str(e), exc_info=True)
                    if gc:
                        args["_graph_context"] = gc
            except Exception as e:
                logging.warning(str(e), exc_info=True)
            # Best-effort: bind run_id for approval replay/linkage. For skill executions,
            # session_id is typically the execution id (run_*), so we use it as fallback.
            if "_run_id" not in args:
                try:
                    if isinstance(trace_context, dict) and trace_context.get("run_id"):
                        args["_run_id"] = str(trace_context.get("run_id"))
                    elif isinstance(session_id, str) and session_id.startswith(("run_", "run-")):
                        args["_run_id"] = str(session_id)
                except Exception as e:
                    logging.warning(str(e), exc_info=True)
            try:
                if isinstance(trace_context, dict) and trace_context.get("tenant_id") and "_tenant_id" not in args:
                    args["_tenant_id"] = trace_context.get("tenant_id")
            except Exception as e:
                logging.warning(str(e), exc_info=True)
            # Fallback tenant propagation from active request context.
            try:
                if "_tenant_id" not in args:
                    arq = get_active_request_context()
                    if arq and getattr(arq, "tenant_id", None):
                        args["_tenant_id"] = getattr(arq, "tenant_id")
            except Exception as e:
                logging.warning(str(e), exc_info=True)
            # Resume semantics: allow passing approval_request_id via trace_context
            try:
                if isinstance(trace_context, dict):
                    arid = trace_context.get("approval_request_id") or trace_context.get("_approval_request_id")
                    if arid and "_approval_request_id" not in args:
                        args["_approval_request_id"] = str(arid)
            except Exception as e:
                logging.warning(str(e), exc_info=True)
            try:
                arq = get_active_request_context()
                if arq and getattr(arq, "actor_role", None):
                    args.setdefault("_actor_role", getattr(arq, "actor_role"))
            except Exception as e:
                logging.warning(str(e), exc_info=True)

            # ---- Coding policy (karpathy_v1) contract gate (Phase-2) ----
            # Goal: enforce Surgical + Goal-driven by requiring stable output contract.
            try:
                require_contract = os.getenv("AIPLAT_CODING_POLICY_REQUIRE_CONTRACT", "true").lower() in ("1", "true", "yes", "y")
                if require_contract and coding_profile in strict_profiles:
                    cfg = getattr(skill, "_config", None)
                    meta = getattr(cfg, "metadata", None) if cfg else None
                    meta = meta if isinstance(meta, dict) else {}
                    is_coding = bool(meta.get("uses_file_output"))
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
            except Exception as e:
                logging.warning("Output schema enforcement check failed: %s", e, exc_info=True)

            # Basic permission posture for executable skills
            resolver = None; di = None
            try:
                from core.harness.integration import _ensure_di
                di = _ensure_di()
                if di: resolver = di.resolve("SkillPermissionResolver")
            except Exception:
                logging.warning("DI resolution failed for SkillPermissionResolver, using direct import fallback", exc_info=True)
            if resolver and isinstance(resolver, dict):
                decision = resolver["resolve_exec"](skill_name)
            else:
                from core.harness.integration import get_exec_skill_permission_resolver
                decision = get_exec_skill_permission_resolver()(skill_name)
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
                    except Exception as e:
                        logging.warning(str(e), exc_info=True)
                # Return a structured result instead of raising (so loop can handle it).
                from core.harness.interfaces import SkillResult

                await _emit_routing_event("policy_denied", extra={"reason": "exec_skill_denied"})
                return SkillResult(success=False, output=None, error="policy_denied", metadata={"reason": "exec_skill_denied", "skill": skill_name})
            if decision == "ask":
                args["_approval_required"] = True

            # Require explicit permissions declaration unless disabled or pre-governance
            require_perm = os.getenv("AIPLAT_EXEC_SKILL_REQUIRE_PERMISSIONS", "true").lower() in ("1", "true", "yes", "y")
            if require_perm:
                try:
                    cfg = getattr(skill, "_config", None)
                    meta = getattr(cfg, "metadata", None) if cfg else None
                    # Pre-governance: skills without a signature haven't been through governance —
                    # don't require permissions for development-phase skills
                    prov = (meta or {}).get("provenance") if isinstance(meta, dict) and isinstance((meta or {}).get("provenance"), dict) else {}
                    has_sig = bool(prov.get("signature"))
                    if not has_sig:
                        require_perm = False  # pre-governance, skip permissions check
                    else:
                        perms = []
                        if isinstance(meta, dict):
                            perms = meta.get("permissions") or meta.get("permission") or []
                        if isinstance(perms, str):
                            perms = [perms]
                        if not isinstance(perms, list) or not [p for p in perms if str(p).strip()]:
                            args["_approval_required"] = True  # fail-safe: require approval if permissions are missing
                            args.setdefault("_policy_reason", "missing_permissions")
                except Exception:
                    if require_perm:
                        args["_approval_required"] = True
                        args.setdefault("_policy_reason", "missing_permissions")

            # P0/P1: honor Skill Contract governance hints
            try:
                cfg = getattr(skill, "_config", None)
                meta = getattr(cfg, "metadata", None) if cfg else None
                meta = meta if isinstance(meta, dict) else {}
                if approval_layer_policy != "tool_only" and meta.get("requires_approval") is True:
                    args["_approval_required"] = True
            except Exception as e:
                logging.warning(str(e), exc_info=True)

            # SandboxGate — pre-execution safety validation
            try:
                from core.harness.infrastructure.gates.sandbox_gate import get_sandbox, Verdict
                sb = get_sandbox()
                sb_result = await sb.check(kind="skill", tool_name=f"skill:{skill_name or ''}", tool_args=args)
                if sb_result.verdict == Verdict.REJECT:
                    return SkillResult(ok=False, error=f"Sandbox rejected: {sb_result.reason}",
                                      error_code="SANDBOX_REJECT")
            except Exception as e:
                logging.warning(str(e), exc_info=True)

            # PolicyGate approval flow (mirrors sys_tool_call behavior)
            # tool_only: bypass skill-level approvals entirely (let tools request approvals).
            if approval_layer_policy == "tool_only":
                try:
                    args.pop("_approval_required", None)
                except Exception as e:
                    logging.warning(str(e), exc_info=True)
                pr = None
            else:
                pr = await policy_gate.check_skill(user_id=user_id, skill_name=skill_name or "<unknown>", skill_args=args)
            # Mark gate coverage (Phase 3 GateTracer)
            try:
                from core.harness.kernel.execution_context import mark_gate_passed
                mark_gate_passed("policy_gate_skill")
            except Exception as e:
                logging.warning(str(e), exc_info=True)
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
                except Exception as e:
                    logging.warning(str(e), exc_info=True)

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
                            except Exception as e:
                                logging.warning(str(e), exc_info=True)
                    except Exception as e:
                        logging.warning(str(e), exc_info=True)

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

    # ── Phase R2: Toolset gate for skills (shared check_workspace_gate) ──
    try:
        from core.harness.tools.toolsets import check_workspace_gate
        allowed, reason, active_toolset = check_workspace_gate("skill", skill_name or "<unknown>")
        if not allowed:
            from core.harness.interfaces import SkillResult
            await _emit_routing_event("toolset_denied", extra={"reason": reason})
            return SkillResult(
                success=False, output=None,
                error=f"toolset_denied: {reason}",
                metadata={"toolset": active_toolset, "skill": skill_name},
            )
    except Exception:
        import logging as _logging
        _logging.getLogger("aiplat.syscall.skill").warning("Workspace gate check skipped", exc_info=True)

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
            # Inject span_id so child syscall events can reference parent
            if ctx and hasattr(ctx, 'metadata') and isinstance(ctx.metadata, dict):
                ctx.metadata["_span_id"] = getattr(span, "span_id", None)
            # Set ActiveTraceContext for downstream event emission (handlers, tools, etc.)
            from core.harness.kernel.execution_context import ActiveTraceContext, set_active_trace_context, reset_active_trace_context
            run_id_val = (trace_context or {}).get("run_id") if isinstance(trace_context, dict) else ""
            span_id_val = getattr(span, "span_id", "")
            trace_token = set_active_trace_context(ActiveTraceContext(
                run_id=str(run_id_val),
                span_id=str(span_id_val),
                parent_span_id=str((trace_context or {}).get("parent_span_id") or "") if isinstance(trace_context, dict) else "",
            )) if run_id_val else None
            try:
                # Check for skill_chain: execute dependencies first
                chain = _get_skill_chain(skill)
                if chain:
                    from core.harness.integration import get_skill_registry
                    reg = get_skill_registry()
                    for dep_name in chain:
                        dep = reg.get(dep_name)
                        if dep and hasattr(dep, 'execute'):
                            await dep.execute(ctx, prepared_params)
                return await skill.execute(ctx, prepared_params)  # type: ignore[misc]
            finally:
                if trace_token is not None:
                    try:
                        reset_active_trace_context(trace_token)
                    except Exception as e:
                        logging.warning(str(e), exc_info=True)
        finally:
            if tok is not None:
                try:
                    reset_active_approval_request_id(tok)
                except Exception as e:
                    logging.warning(str(e), exc_info=True)

    # (span already started above)
    try:
        # §5.31: Ensure skill has a usable LLM model before execution
        if not getattr(skill, "_model", None):
            try:
                from core.harness.utils.model_injection import ensure_skill_model, best_model_for_purpose
                ensure_skill_model(skill, model_name=best_model_for_purpose("skill_execution"), force=False)
            except Exception as e:
                logging.warning(str(e), exc_info=True)

        # §5.19: refuse retry on non-idempotent write skills
        cfg = getattr(skill, "_config", None)
        is_idempotent = bool(getattr(cfg, "idempotent", True))
        retries = int(os.getenv("AIPLAT_SKILL_RETRIES", "0") or "0")
        if retries > 0 and not is_idempotent:
            skill_name = getattr(cfg, "name", None) or getattr(skill, "name", "unknown")
            raise RuntimeError(
                f"Skill '{skill_name}' has idempotent=false but AIPLAT_SKILL_RETRIES={retries}. "
                f"Cannot safely retry a non-idempotent skill. Set idempotent=true or AIPLAT_SKILL_RETRIES=0."
            )
        result = await res_gate.run(_run, retries=retries, timeout_seconds=timeout_seconds)
        end_ts = time.time()
        await trace_gate.end(span, success=bool(getattr(result, "success", True)))

        # ---- Diff Gate helper: capture change contract from coding skill output (best-effort) ----
        try:
            if coding_profile in strict_profiles and bool(getattr(result, "success", True)):
                cfg = getattr(skill, "_config", None)
                meta = getattr(cfg, "metadata", None) if cfg else None
                meta = meta if isinstance(meta, dict) else {}
                is_coding = bool(meta.get("uses_file_output"))
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
        except Exception as e:
            logging.warning(str(e), exc_info=True)

        runtime = get_kernel_runtime()
        store = getattr(runtime, "execution_store", None) if runtime else None
        if store is not None:
            try:
                await store.add_syscall_event(
                    {
                        "trace_id": span.trace_id,
                        "span_id": getattr(span, "span_id", None),
                        "parent_span_id": (trace_context or {}).get("parent_span_id") if isinstance(trace_context, dict) else None,
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
            except Exception as e:
                logging.warning(str(e), exc_info=True)
        # Audit: record execution realness when AIPLAT_EXECUTION_AUDIT is enabled
        if os.getenv("AIPLAT_EXECUTION_AUDIT", "false").lower() in ("1", "true", "yes"):
            try:
                runtime = get_kernel_runtime()
                store = getattr(runtime, "execution_store", None) if runtime else None
                if store:
                    is_ok = bool(getattr(result, "success", True))
                    err = getattr(result, "error", None)
                    exec_type = (getattr(getattr(skill, "_config", None), "metadata", {}) or {}).get("execution_type", "")
                    actual_mode = "handler" if exec_type == "handler" else ("mock" if err and "mock" in str(err).lower() else "prompt")
                    await store.add_audit_log(
                        action="skill_executed",
                        kind="execution_realness",
                        payload={
                            "skill_name": str(skill_name),
                            "execution_type": str(exec_type),
                            "actual_mode": actual_mode,
                            "success": is_ok,
                            "trace_id": span.trace_id,
                        },
                    )
            except Exception as e:
                logging.warning("Execution audit recording failed: %s", e, exc_info=True)
        # Curator: record call for frequency tracking + lifecycle management
        try:
            curator = None
            try:
                from core.harness.integration import _ensure_di
                di = _ensure_di()
                if di: curator = di.resolve("SkillCurator")
            except Exception:
                logging.warning("DI resolution failed for SkillCurator, using direct import fallback", exc_info=True)
            if curator is None:
                from core.harness.integration import get_skill_curator
                curator = get_skill_curator()
            curator.record_call(skill_name) if skill_name else None
        except Exception as e:
            logging.warning("Skill curator call recording failed: %s", e, exc_info=True)
        # SchemaGate — JSON Schema enforcement
        if bool(getattr(result, "success", True)):
            try:
                from core.harness.infrastructure.gates.schema_gate import get_schema_gate, SchemaVerdict
                cfg = getattr(skill, "_config", None)
                output_schema = getattr(cfg, "output_schema", None) if cfg else None
                if not output_schema:
                    meta = getattr(cfg, "metadata", None) if cfg else None
                    output_schema = meta.get("output_schema") if isinstance(meta, dict) else None
                if output_schema:
                    sg = get_schema_gate()
                    s_result = sg.validate(getattr(result, "output", None), output_schema)
                    if s_result.verdict == SchemaVerdict.FAIL:
                        setattr(result, "success", False)
                        setattr(result, "error", f"schema_validation_failed{': ' + s_result.retry_hint[:200] if s_result.retry_hint else ''}")
            except Exception as e:
                logging.warning("SchemaGate validation failed: %s", e, exc_info=True)

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
                        "parent_span_id": (trace_context or {}).get("parent_span_id") if isinstance(trace_context, dict) else None,
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
            except Exception as e:
                logging.warning(str(e), exc_info=True)
        raise


async def sys_skill_call_stream(
    skill: Any,
    params: Dict[str, Any],
    *,
    context: Optional[SkillContext] = None,
    user_id: str = "system",
    session_id: str = "default",
    timeout_seconds: Optional[float] = None,
    trace_context: Optional[Dict[str, Any]] = None,
) -> AsyncGenerator[SkillStreamEvent, None]:
    """Execute a skill call with streaming output."""
    from ..interfaces import SkillStreamEvent

    trace_gate = TraceGate()
    ctx_gate = ContextGate()

    skill_name = str(getattr(skill, "name", "") or getattr(getattr(skill, "_config", None), "name", "") or "unknown")
    span = await trace_gate.start(
        "sys.skill.call_stream",
        attributes={
            "skill": skill_name,
            "trace_id": (trace_context or {}).get("trace_id") if isinstance(trace_context, dict) else None,
        },
    )

    try:
        ctx = (
            context
            if context is not None
            else SkillContext(session_id=session_id, user_id=user_id)
        )
        ctx = await ctx_gate.check(ctx)
        cfg = getattr(skill, "_config", None)
        is_idempotent = bool(getattr(cfg, "idempotent", True))
        if not is_idempotent:
            yield SkillStreamEvent(event_type="status", data=None, progress=0.1, message=f"non-idempotent:{skill_name}")

        async for event in skill.execute_stream(ctx, params):
            yield event

    except asyncio.TimeoutError:
        yield SkillStreamEvent(event_type="done", data=SkillResult(success=False, error=f"timeout: {timeout_seconds}s"), progress=1.0)
    except Exception as e:
        yield SkillStreamEvent(event_type="done", data=SkillResult(success=False, error=str(e)), progress=1.0)
    finally:
        await trace_gate.end(span, success=True)


def _get_skill_chain(skill: Any) -> List[str]:
    u"""Extract skill_chain from skill metadata (SKILL.md frontmatter).
    Returns ordered list of skill names to execute as prerequisites.
    """
    try:
        cfg = getattr(skill, "_config", None)
        meta = getattr(cfg, "metadata", None) if cfg else None
        if isinstance(meta, dict):
            chain = meta.get("skill_chain", [])
            return [str(s) for s in chain] if chain else []
    except Exception as e:
        logging.warning(str(e), exc_info=True)
    return []
