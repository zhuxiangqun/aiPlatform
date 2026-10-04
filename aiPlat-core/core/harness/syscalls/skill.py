"""

sys_skill - Skill syscall wrappers (Phase 2).



Centralizes skill invocation so future gates can be enforced here:

- TraceGate (span + audit record)

- ResilienceGate (timeout/retry)

"""



from __future__ import annotations



import asyncio

import logging

import os

import re

from core.harness.kernel.execution_context import ActiveChangeContract, set_active_change_contract

from typing import Any, AsyncGenerator, Dict, List, Optional



from core.harness.interfaces.skill import SkillStreamEvent

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

    from ._trace import trace_syscall_entry

    trace_syscall_entry("sys_skill_call")

    """Execute a skill call."""

    trace_gate = TraceGate()

    ctx_gate = ContextGate()

    res_gate = ResilienceGate()

    policy_gate = PolicyGate()



    # Start span early so "fast-fail" (missing skill) is still observable.

    skill_name = str(getattr(skill, "name", None) or getattr(getattr(skill, "_config", None), "name", "") or "")

    try:
        import asyncio as _aio_span

        span = await _aio_span.wait_for(
            trace_gate.start(
                "sys.skill.call",
                attributes={
                    "skill": skill_name,
                    "trace_id": (trace_context or {}).get("trace_id") if isinstance(trace_context, dict) else None,
                },
            ),
            timeout=3.0,
        )
    except Exception:
        span = None
    if span is None:
        from core.harness.infrastructure.gates.trace_gate import TraceSpan as _TraceSpan

        span = _TraceSpan(
            trace_id=(trace_context or {}).get("trace_id") if isinstance(trace_context, dict) else None,
            span_id=None,
            name="sys.skill.call",
        )

    start_ts = time.time()

    _ar = get_active_release_context()

    _pr = get_active_request_context()

    coding_profile = (

        str((trace_context or {}).get("coding_policy_profile") or "off").strip().lower()

        if isinstance(trace_context, dict)

        else "off"

    )

    # B0–B2: lite/full/ultra (+ karpathy_v1 alias) keep contract gates; env can override list
    try:
        from core.harness.utils.coding_intensity import is_strict_coding_profile
        _profile_is_strict = is_strict_coding_profile(coding_profile)
    except Exception:
        strict_profiles = {
            x.strip().lower()
            for x in os.getenv(
                "AIPLAT_STRICT_CODING_PROFILES", "karpathy_v1,full,lite,ultra"
            ).split(",")
            if x.strip()
        }
        _profile_is_strict = coding_profile in strict_profiles

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

        logging.getLogger(__name__).debug('sys_skill_call failed', exc_info=True)


    async def _emit_routing_event(status: str, *, extra: Optional[Dict[str, Any]] = None, approval_request_id: Optional[str] = None) -> None:

        """Emit best-effort routing event for observability/funnel metrics."""

        try:

            runtime = get_kernel_runtime()

            store = getattr(runtime, "execution_store", None) if runtime else None

            if store is None:

                return

            end_ts = time.time()

            # Never reuse the skill TraceGate span_id — that overwrites the Skill
            # canvas card with「路由 · 选技能」(run-2e8529 / run-eec14e).
            _skill_span = getattr(span, "span_id", None)
            _route_span = (
                f"routing:skill_route:{_skill_span}"
                if _skill_span
                else f"routing:skill_route:{skill_name or 'unknown'}:{int(end_ts * 1000)}"
            )
            _parent = None
            if isinstance(trace_context, dict):
                _parent = trace_context.get("parent_span_id") or _skill_span
            else:
                _parent = _skill_span

            await store.add_syscall_event(

                {

                    "trace_id": span.trace_id,

                    "span_id": _route_span,

                    "parent_span_id": _parent,

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

    # P0-1: 注入当前 skill 名称，供 MemoryManager 检测审计模式

    if skill_name:

        ctx.variables["_active_skill"] = skill_name

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

    # Close agent pre_llm_prep + emit in-flight skill row NOW. Completion-only
    # skill rows left orphan_watchdog blind: skill_route selected → 60s later
    # false pre_llm_prep_stalled killed live code_generation (run-320e4de31f66).
    _run_id_skill = (
        str((trace_context or {}).get("run_id") or "").strip()
        if isinstance(trace_context, dict)
        else ""
    )
    _skill_evt_id = (
        f"{_run_id_skill}:skill:{skill_name}:{start_ts}"
        if _run_id_skill and skill_name
        else None
    )
    try:
        runtime_early = get_kernel_runtime()
        store_early = getattr(runtime_early, "execution_store", None) if runtime_early else None
        if store_early is not None and _run_id_skill:
            try:
                from core.harness.utils.execute_session import emit_pre_llm_prep_close

                _tc = trace_context if isinstance(trace_context, dict) else {}
                await emit_pre_llm_prep_close(
                    store_early,
                    _run_id_skill,
                    status="ok",
                    step_count=_tc.get("step_count"),
                    parent_span_id=str(_tc.get("parent_span_id") or ""),
                    reason="before_skill_call",
                    extra_args={"skill": skill_name},
                )
            except Exception:
                logging.debug("pre_llm_prep close before skill skipped", exc_info=True)
            if _skill_evt_id:
                try:
                    await store_early.add_syscall_event(
                        {
                            "id": _skill_evt_id,
                            "trace_id": span.trace_id,
                            "span_id": getattr(span, "span_id", None),
                            "parent_span_id": (
                                (trace_context or {}).get("parent_span_id")
                                if isinstance(trace_context, dict)
                                else None
                            ),
                            "run_id": _run_id_skill,
                            "kind": "skill",
                            "name": skill_name or "<unknown>",
                            "status": "running",
                            "target_type": _ar.target_type if _ar else None,
                            "target_id": _ar.target_id if _ar else None,
                            "tenant_id": getattr(_pr, "tenant_id", None),
                            "user_id": user_id,
                            "session_id": session_id,
                            "start_time": start_ts,
                            "args": {
                                "params_keys": sorted(list((params or {}).keys()))[:50],
                                "routing_decision_id": (
                                    (trace_context or {}).get("routing_decision_id")
                                    if isinstance(trace_context, dict)
                                    else None
                                ),
                                "coding_policy_profile": coding_profile,
                                "phase": "selected",
                            },
                            "created_at": time.time(),
                        }
                    )
                except Exception:
                    logging.debug("skill running span emit skipped", exc_info=True)
    except Exception:
        logging.debug("skill early progress emit skipped", exc_info=True)

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

            # Agent required_skills: carry into args so PolicyGate can waive second HITL
            # (loop may put them on params and/or trace_context).
            try:
                bound = args.get("_bound_skill_ids")
                if not (isinstance(bound, list) and bound) and isinstance(trace_context, dict):
                    tc_bound = trace_context.get("_bound_skill_ids")
                    if isinstance(tc_bound, list) and tc_bound:
                        args["_bound_skill_ids"] = [
                            str(x).strip() for x in tc_bound if str(x).strip()
                        ]
            except Exception as e:
                logging.debug(str(e), exc_info=True)

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

                            gc["wiki_pages"] = 1

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

            # Keep SkillContext.variables in sync — handlers (code_generation) read
            # run_id / parent span from context.variables, not only prepared_params.
            try:
                _rid_sync = str(args.get("_run_id") or "").strip()
                if _rid_sync and isinstance(getattr(ctx, "variables", None), dict):
                    ctx.variables.setdefault("_run_id", _rid_sync)
                _psp_sync = ""
                if isinstance(trace_context, dict):
                    _psp_sync = str(trace_context.get("parent_span_id") or "").strip()
                if not _psp_sync:
                    _psp_sync = str(args.get("_parent_span_id") or "").strip()
                if _psp_sync and isinstance(getattr(ctx, "variables", None), dict):
                    ctx.variables.setdefault("_parent_span_id", _psp_sync)
                    args.setdefault("_parent_span_id", _psp_sync)
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

                if require_contract and _profile_is_strict:

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
                # Agent-bound required_skills: already authorized by Agent execute.
                try:
                    from core.apps.tools.skill_tools import is_agent_bound_required_skill

                    if is_agent_bound_required_skill(skill_name, args):
                        decision = "allow"
                    else:
                        args["_approval_required"] = True
                except Exception:
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
                    try:
                        from core.apps.tools.skill_tools import is_agent_bound_required_skill

                        if not is_agent_bound_required_skill(skill_name, args):
                            args["_approval_required"] = True
                    except Exception:
                        args["_approval_required"] = True

            except Exception as e:

                logging.warning(str(e), exc_info=True)

            # Final bound-skill waiver: clear any prior force-approval flags when
            # the skill is listed on this Agent's required_skills.
            try:
                from core.apps.tools.skill_tools import is_agent_bound_required_skill

                if (
                    isinstance(args, dict)
                    and args.get("_approval_required")
                    and is_agent_bound_required_skill(skill_name, args)
                ):
                    args.pop("_approval_required", None)
                    args["_approval_waived"] = "agent_bound_required_skill"
            except Exception as e:
                logging.debug(str(e), exc_info=True)



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
                # Bound required_skills were already authorized by Agent execute.
                try:
                    from core.apps.tools.skill_tools import is_agent_bound_required_skill

                    if is_agent_bound_required_skill(skill_name, args):
                        await _emit_routing_event(
                            "approval_bypassed",
                            extra={"reason": "agent_bound_required_skill", "orig": getattr(pr, "reason", "")},
                            approval_request_id=getattr(pr, "approval_request_id", None),
                        )
                        pr = None
                except Exception:
                    logging.debug("bound-skill approval waiver skipped", exc_info=True)

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
        logging.getLogger(__name__).debug('Parameter validation fail-open for compatibility', exc_info=True)



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



    # Phase 41: Decision Lineage — capture skill selection (best-effort)
    _skill_decision_id = None
    try:
        from core.harness.infrastructure.decision_capture import capture_skill_decision
        _skill_decision_id = await capture_skill_decision(
            skill_name, prepared_params, trace_context,
            reason='',
        )
    except Exception:
        logging.getLogger(__name__).debug("swallowing non-critical exception", exc_info=True)

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

                from core.harness.execution.skill_side_effect_gate import (
                    skill_result_if_unrealized_side_effects,
                )

                refused = skill_result_if_unrealized_side_effects(skill)

                if refused is not None:

                    return refused

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

        # Agent ReAct often calls without timeout_seconds — then ResilienceGate
        # awaits forever (test_executor run-49fc6a85db3c: skill stuck 2443s).
        # Honor SKILL.md / metadata.timeout, else same default as SkillExecutor.
        if timeout_seconds is None:
            try:
                meta = getattr(cfg, "metadata", None) if cfg is not None else None
                if isinstance(meta, dict) and meta.get("timeout") is not None:
                    timeout_seconds = float(meta.get("timeout"))
            except Exception:
                timeout_seconds = None
        if timeout_seconds is None:
            try:
                timeout_seconds = float(
                    os.getenv("AIPLAT_SKILL_DEFAULT_TIMEOUT", "180") or "180"
                )
            except Exception:
                timeout_seconds = 180.0

        async def _run_with_model():
            # Model inject must sit inside the skill timeout budget — sync
            # ModelManager / Ollama scan outside wait_for wedged ReAct for 40min.
            if not getattr(skill, "_model", None):
                try:
                    from core.harness.utils.model_injection import (
                        ensure_skill_model,
                        best_model_for_purpose,
                    )
                    from core.harness.utils.execute_session import (
                        resolve_skill_model_purpose,
                    )

                    _purpose = resolve_skill_model_purpose(
                        skill, default="skill_execution"
                    )
                    ensure_skill_model(
                        skill,
                        model_name=best_model_for_purpose(_purpose),
                        force=False,
                    )
                except Exception as e:
                    logging.warning(str(e), exc_info=True)
            return await _run()

        result = await res_gate.run(
            _run_with_model, retries=retries, timeout_seconds=timeout_seconds
        )

        end_ts = time.time()

        # Phase 41: Update skill decision outcome (best-effort)
        if _skill_decision_id:
            try:
                from core.harness.infrastructure.decision_capture import update_decision_outcome
                success = bool(getattr(result, "success", True))
                await update_decision_outcome(
                    _skill_decision_id,
                    outcome_status="success" if success else "failed",
                    outcome_summary=str(getattr(result, "output", ""))[:200] if success else str(getattr(result, "error", ""))[:200],
                )
            except Exception:
                logging.getLogger(__name__).debug("swallowing non-critical exception", exc_info=True)

        # Phase 44: Operation Recording (best-effort, zero-cost when not recording)
        try:
            from core.harness.learning.operation_recorder import OperationRecorder
            recorder = OperationRecorder.get()
            if recorder.is_recording():
                recorder.record_step(
                    tool_name=skill_name or '<unknown>',
                    tool_args=prepared_params if 'prepared_params' in dir() else {},
                    result_type='success' if bool(getattr(result, 'success', True)) else 'failed',
                    result_summary=str(getattr(result, 'output', ''))[:200] if bool(getattr(result, 'success', True)) else str(getattr(result, 'error', ''))[:200],
                    duration_ms=(end_ts - start_ts) * 1000 if 'start_ts' in dir() and 'end_ts' in dir() else 0,
                )
        except Exception:
            logging.getLogger(__name__).debug("swallowing non-critical exception", exc_info=True)

        await trace_gate.end(span, success=bool(getattr(result, "success", True)))



        # ---- Diff Gate helper: capture change contract from coding skill output (best-effort) ----

        try:

            if _profile_is_strict and bool(getattr(result, "success", True)):

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

        if os.getenv("AIPLAT_EXECUTION_AUDIT", "true").lower() in ("1", "true", "yes"):

            try:

                runtime = get_kernel_runtime()

                store = getattr(runtime, "execution_store", None) if runtime else None

                if store:

                    is_ok = bool(getattr(result, "success", True))

                    err = getattr(result, "error", None)

                    exec_type = (getattr(getattr(skill, "_config", None), "metadata", {}) or {}).get("execution_type", "")

                    meta = (getattr(getattr(skill, "_config", None), "metadata", {}) or {})

                    action_type = meta.get("action_type", "")

                    audit_level = meta.get("audit_level", "normal")

                    actual_mode = "handler" if exec_type == "handler" else ("mock" if err and "mock" in str(err).lower() else "prompt")

                    # AuditMixin.add_audit_log takes detail= (not kind=/payload=);
                    # wrong kwargs made Execution audit recording fail every skill
                    # (run-58363c7935f6 WARNING spam).
                    await store.add_audit_log(
                        action="skill_executed",
                        status="ok" if is_ok else "failed",
                        resource_type="skill",
                        resource_id=str(skill_name),
                        run_id=str(
                            (getattr(context, "variables", None) or {}).get("_run_id")
                            or ""
                        )
                        or None,
                        trace_id=span.trace_id,
                        detail={
                            "kind": "execution_realness",
                            "skill_name": str(skill_name),
                            "execution_type": str(exec_type),
                            "action_type": action_type,
                            "audit_level": audit_level,
                            "actual_mode": actual_mode,
                            "success": is_ok,
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



        # ── Write skill execution record for domain maturity tracking (Phase B2, 2026-07) ──

        try:

            from core.apps.skills.skill_execution_record import SkillExecutionRecord, SkillExecutionStore

            cfg = getattr(skill, "_config", None)

            meta = getattr(cfg, "metadata", None) if cfg else None

            domain_id = str((meta or {}).get("domain_id", ""))

            record = SkillExecutionRecord(

                execution_id=span.trace_id or f"skill_{int(start_ts)}",

                skill_name=skill_name,

                domain_id=domain_id,

                success=getattr(result, "success", True) if result else True,

                adopted=False,

                execution_time_ms=(time.time() - start_ts) * 1000.0,

            )

            store_path = os.path.expanduser(os.getenv("AIPLAT_HOME", "~/.aiplat")) + "/data/execution_store.db"

            os.makedirs(os.path.dirname(store_path), exist_ok=True)

            SkillExecutionStore.ensure_table(store_path)

            SkillExecutionStore.insert(store_path, record)

        except Exception:

            logging.getLogger(__name__).debug('code failed', exc_info=True)


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

