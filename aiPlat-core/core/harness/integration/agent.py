"""Auto-extracted from integration.py — 2026-07-13"""

from __future__ import annotations

import logging




async def _execute_agent_impl(self, req: ExecutionRequest) -> ExecutionResult:

    agent_reg = _resolve_or_import("AgentRegistry", "core.apps.agents:get_agent_registry")

    agent_reg = agent_reg() if callable(agent_reg) else agent_reg

    skill_reg = _resolve_or_import("SkillRegistry", "core.apps.skills:get_skill_registry")

    skill_reg = skill_reg() if callable(skill_reg) else skill_reg

    tool_reg = _resolve_tool_registry()

    from core.apps.tools.permission import Permission  # noqa: allowed — data type (enum) import

    from core.harness.interfaces import AgentContext

    from core.harness.kernel.types import ExecutionResult



    runtime = self._runtime

    if runtime is None or runtime.agent_manager is None:

        return self._fail(code="NOT_INITIALIZED", message="Kernel runtime not initialized", http_status=503)



    agent_id = req.target_id

    registry = agent_reg

    agent = registry.get(agent_id)

    if not agent:

        return self._fail(code="NOT_FOUND", message=f"Agent {agent_id} not found", http_status=404)



    user_id = req.user_id or (req.payload.get("user_id") if isinstance(req.payload, dict) else None) or "system"

    perm = _resolve_or_import("PermissionManager", "core.apps.tools.permission:get_permission_manager")

    perm_mgr = perm() if callable(perm) else perm

    if not perm_mgr.check_permission(user_id, agent_id, Permission.EXECUTE):

        return self._fail(

            code="PERMISSION_DENIED",

            message=f"User '{user_id}' lacks EXECUTE permission for agent '{agent_id}'",

            http_status=403,

        )



    # Resolve model from env/config (best_model_for_purpose first, config default as fallback)

    agent_info = await runtime.agent_manager.get_agent(agent_id)

    from core.harness.utils.model_injection import best_model_for_purpose

    model_name = best_model_for_purpose("chat") or (agent_info.config.get("model") if agent_info else None)



    # Ensure agent model is usable and consistent (agent + internal loop).

    try:

        from core.harness.utils.model_injection import ensure_agent_model



        force_rebind = False

        try:

            v = (os.getenv("AIPLAT_FORCE_AGENT_MODEL_REBIND") or "").strip().lower()  # noqa: env-legacy

            if v in {"1", "true", "yes", "y"}:

                force_rebind = True

        except Exception:

            force_rebind = False

        ensure_agent_model(agent, model_name=model_name, force=force_rebind)

    except Exception as e:

        logging.debug(str(e), exc_info=True)



    # Wire approval manager into loop (best effort)

    if runtime.approval_manager and hasattr(agent, "_loop") and hasattr(agent._loop, "set_approval_manager"):

        try:

            agent._loop.set_approval_manager(runtime.approval_manager)  # type: ignore[attr-defined]

        except Exception as e:

            logging.debug(str(e), exc_info=True)



    # Bind tools (best effort)

    if agent_info and getattr(agent_info, "tools", None) and hasattr(agent, "add_tool"):

        tool_registry = _resolve_tool_registry()

        for tool_name in agent_info.tools:

            if not perm_mgr.check_permission(user_id, tool_name, Permission.EXECUTE):

                return self._fail(

                    code="PERMISSION_DENIED",

                    message=f"User '{user_id}' lacks EXECUTE permission for tool '{tool_name}'",

                    http_status=403,

                )

            tool = tool_registry.get(tool_name)

            if tool:

                try:

                    agent.add_tool(tool)  # type: ignore[attr-defined]

                except Exception as e:

                    logging.debug(str(e), exc_info=True)



    # Bind skills (best effort)

    if agent_info and getattr(agent_info, "skills", None) and hasattr(agent, "add_skill"):

        skill_registry = _resolve_or_import("SkillRegistry", "core.apps.skills:get_skill_registry")

        skill_registry = skill_registry() if callable(skill_registry) else skill_registry

        for skill_name in agent_info.skills:

            skill = skill_registry.get(skill_name)

            if skill:

                # inject model if needed (env-aware + mock fallback)

                if hasattr(skill, "_model") and getattr(skill, "_model") is None:

                    try:

                        from core.harness.utils.model_injection import ensure_skill_model



                        ensure_skill_model(skill, model_name=model_name)

                    except Exception as e:

                        logging.debug(str(e), exc_info=True)

                try:

                    agent.add_skill(skill)  # type: ignore[attr-defined]

                except Exception as e:

                    logging.debug(str(e), exc_info=True)



    # Platform default: run_id should be time-sortable and stable for tracing/log correlation.

    execution_id = str(getattr(req, "run_id", None) or "") or new_prefixed_id("run")

    start_time = time.time()

    tenant_id = None

    try:

        if isinstance(req.payload, dict):

            ctx0 = req.payload.get("context") if isinstance(req.payload.get("context"), dict) else {}

            tenant_id = ctx0.get("tenant_id") if isinstance(ctx0, dict) else None

    except Exception:

        tenant_id = None



    trace_id = None

    if runtime.trace_service:

        try:

            # Trace attributes: include request_id and job context when present (best-effort).

            attrs = {"run_id": execution_id, "agent_id": agent_id, "user_id": user_id}

            if getattr(req, "request_id", None):

                attrs["request_id"] = req.request_id

            try:

                ctx0 = (req.payload or {}).get("context") if isinstance(req.payload, dict) else None

                if isinstance(ctx0, dict) and ctx0:

                    if ctx0.get("source") == "job":

                        if ctx0.get("job_id"):

                            attrs["job_id"] = ctx0.get("job_id")

                        if ctx0.get("job_run_id"):

                            attrs["job_run_id"] = ctx0.get("job_run_id")

            except Exception as e:

                logging.debug(str(e), exc_info=True)

            trace = await runtime.trace_service.start_trace(

                name=f"agent:{agent_id}",

                attributes=attrs,

            )

            trace_id = trace.trace_id

        except Exception:

            trace_id = None



    # Run events (best-effort): start

    if runtime.execution_store:

        try:

            exec_backend = None

            try:

                exec_backend = await _resolve_exec_backend()

            except Exception:

                exec_backend = None

            await runtime.execution_store.append_run_event(

                run_id=execution_id,

                event_type="run_start",

                trace_id=trace_id,

                tenant_id=str(tenant_id) if tenant_id else None,

                payload={

                    "kind": "agent",

                    "agent_id": agent_id,

                    "user_id": user_id,

                    "session_id": req.session_id,

                    "exec_backend": exec_backend,

                    "request_payload": self._redact_request_payload(req.payload if isinstance(req.payload, dict) else {}),

                    "project_id": ((req.payload or {}).get("context") or {}).get("project_id") if isinstance(req.payload, dict) else None,

                },

            )

        except Exception as e:

            logging.debug(str(e), exc_info=True)



    try:

        payload = req.payload or {}

        # Normalize inputs: UI may send {input: {...}} without messages.

        messages = payload.get("messages", []) if isinstance(payload, dict) else []

        if not messages and isinstance(payload, dict):

            inp = payload.get("input")

            if isinstance(inp, str) and inp.strip():

                messages = [{"role": "user", "content": inp.strip()}]

            elif isinstance(inp, dict):

                # Best-effort common keys

                text = inp.get("message") or inp.get("prompt") or inp.get("task") or inp.get("query")

                if isinstance(text, str) and text.strip():

                    messages = [{"role": "user", "content": text.strip()}]



        # Persona injection (agency-agents / prompt_templates):

        # If payload.context.persona_template_id is provided, prepend as system message.

        try:

            ctx0 = payload.get("context") if isinstance(payload.get("context"), dict) else {}

            persona_tid = ctx0.get("persona_template_id") if isinstance(ctx0, dict) else None

            persona_tid = str(persona_tid).strip() if isinstance(persona_tid, str) and persona_tid.strip() else None

            if persona_tid and runtime and getattr(runtime, "execution_store", None):

                tpl = await runtime.execution_store.get_prompt_template(template_id=str(persona_tid))

                tpl_text = (tpl or {}).get("template") if isinstance(tpl, dict) else None

                tpl_text = str(tpl_text).strip() if isinstance(tpl_text, str) else ""

                if tpl_text:

                    # Avoid duplicating system messages if caller already injected.

                    if not (isinstance(messages, list) and messages and messages[0].get("role") == "system"):

                        messages = [{"role": "system", "content": tpl_text}] + (messages or [])

                    # observability (best-effort)

                    try:

                        await runtime.execution_store.append_run_event(

                            run_id=execution_id,

                            event_type="persona_applied",

                            trace_id=trace_id,

                            tenant_id=str(tenant_id) if tenant_id else None,

                            payload={"persona_template_id": str(persona_tid)},

                        )

                    except Exception as e:

                        logging.debug(str(e), exc_info=True)

        except Exception as e:

            logging.debug(str(e), exc_info=True)



        # Phase R1: workspace/repo context for prompt assembly (best-effort).

        # Phase R4: request identity context for session search injection.

        workspace_token = None

        request_token = None

        tenant_policy_token = None

        try:

            from core.harness.kernel.execution_context import (

                ActiveRequestContext,

                ActiveTenantPolicyContext,

                ActiveWorkspaceContext,

                set_active_request_context,

                set_active_tenant_policy_context,

                set_active_workspace_context,

            )



            # Phase R2: toolset selection (best-effort).

            requested_toolset = None

            try:

                if isinstance(payload, dict):

                    opts = payload.get("options") if isinstance(payload.get("options"), dict) else {}

                    ctx0 = payload.get("context") if isinstance(payload.get("context"), dict) else {}

                    requested_toolset = (

                        (opts.get("toolset") if isinstance(opts, dict) else None)

                        or payload.get("toolset")

                        or ctx0.get("toolset")

                        or ctx0.get("_toolset")

                    )

            except Exception:

                requested_toolset = None



            repo_root = None

            if isinstance(payload, dict):

                inp = payload.get("input")

                ctx = payload.get("context") if isinstance(payload.get("context"), dict) else {}

                if isinstance(inp, dict):

                    repo_root = inp.get("directory") or inp.get("repo_root") or inp.get("workspace_root")

                if not repo_root and isinstance(ctx, dict):

                    repo_root = ctx.get("directory") or ctx.get("repo_root") or ctx.get("workspace_root")

            # Best-effort auto repo_root (enables CLAUDE.md injection/enforcement even if client forgets).

            if not (isinstance(repo_root, str) and repo_root.strip()):

                try:

                    auto = os.getenv("AIPLAT_AUTO_REPO_ROOT", "true").strip().lower() in ("1", "true", "yes", "y", "on")

                    if auto:

                        repo_root = self._infer_default_repo_root()

                except Exception as e:

                    logging.debug(str(e), exc_info=True)

            if (isinstance(repo_root, str) and repo_root.strip()) or requested_toolset:

                workspace_token = set_active_workspace_context(

                    ActiveWorkspaceContext(

                        repo_root=repo_root.strip() if isinstance(repo_root, str) and repo_root.strip() else None,

                        toolset=str(requested_toolset) if requested_toolset else None,

                    )

                )

            # Always set request context so prompt assembly can access user/session identity.

            try:

                sess_id = None

                if isinstance(payload, dict):

                    ctx0 = payload.get("context") if isinstance(payload.get("context"), dict) else {}

                    sess_id = payload.get("session_id") or ctx0.get("session_id")

                request_token = set_active_request_context(

                    ActiveRequestContext(

                        user_id=str(user_id or "system"),

                        session_id=str(sess_id or req.session_id or "default"),

                        channel=str(getattr(req, "channel", None)) if hasattr(req, "channel") else None,

                        tenant_id=str(ctx0.get("tenant_id")) if isinstance(ctx0, dict) and ctx0.get("tenant_id") else None,

                        actor_id=str(ctx0.get("actor_id")) if isinstance(ctx0, dict) and ctx0.get("actor_id") else str(user_id or "system"),

                        actor_role=str(ctx0.get("actor_role")) if isinstance(ctx0, dict) and ctx0.get("actor_role") else None,

                        entrypoint=str(ctx0.get("entrypoint") or ctx0.get("source")) if isinstance(ctx0, dict) and (ctx0.get("entrypoint") or ctx0.get("source")) else None,

                        request_id=str(ctx0.get("request_id")) if isinstance(ctx0, dict) and ctx0.get("request_id") else getattr(req, "request_id", None),

                    )

                )

            except Exception:

                request_token = None



            # Tenant policy snapshot (best-effort): load once per execution for downstream syscalls.

            try:

                tenant_id0 = ctx0.get("tenant_id") if isinstance(ctx0, dict) else None

                store = getattr(runtime, "execution_store", None) if runtime else None

                if tenant_id0 and store:

                    rec = await store.get_tenant_policy(tenant_id=str(tenant_id0))

                    pol = rec.get("policy") if isinstance(rec, dict) and isinstance(rec.get("policy"), dict) else {}

                    ver = rec.get("version") if isinstance(rec, dict) else None

                    tenant_policy_token = set_active_tenant_policy_context(

                        ActiveTenantPolicyContext(

                            tenant_id=str(tenant_id0),

                            version=int(ver) if isinstance(ver, int) else None,

                            policy=pol,

                        )

                    )

            except Exception:

                tenant_policy_token = None

        except Exception:

            workspace_token = None

            request_token = None

            tenant_policy_token = None



        # If resuming, pass loop snapshot down via AgentContext.variables

        variables = payload.get("context", {}) if isinstance(payload, dict) else {}

        # Phase 10.1: extract run_context from API payload for contextual AI reasoning

        if isinstance(payload, dict) and payload.get("run_context"):

            variables = dict(variables or {})

            variables["_run_context"] = payload["run_context"]

        if isinstance(payload, dict) and "_resume_loop_state" in payload:

            try:

                variables = dict(variables or {})

                variables["_resume_loop_state"] = payload.get("_resume_loop_state")

            except Exception as e:

                logging.debug(str(e), exc_info=True)

        context = AgentContext(

            session_id=payload.get("session_id", req.session_id or "default"),

            user_id=user_id,

            messages=messages,

            variables=variables or {},

        )

        # Phase R2: toolset → context.tools injection (opt-in via env, or explicit toolset).

        try:

            if isinstance(payload, dict):

                explicit_tools = payload.get("tools")

            else:

                explicit_tools = None

            enable_toolsets = os.getenv("AIPLAT_ENABLE_TOOLSETS", "false").lower() in ("1", "true", "yes", "y")

            if isinstance(explicit_tools, list) and explicit_tools:

                context.tools = [str(t) for t in explicit_tools if t]

            elif enable_toolsets or requested_toolset:

                from core.harness.tools.toolsets import resolve_toolset



                policy = resolve_toolset(str(requested_toolset) if requested_toolset else None)

                context.tools = sorted(policy.allowed_tools)

                # Surface to downstream via variables/metadata for observability.

                context.variables.setdefault("_toolset", policy.name)

                context.metadata.setdefault("toolset", policy.name)

        except Exception as e:

            logging.debug(str(e), exc_info=True)

        # Propagate trace/run identifiers into agent variables so loops can pass them to syscalls.

        try:

            if isinstance(context.variables, dict):

                context.variables.setdefault("_trace_id", trace_id)

                context.variables.setdefault("_run_id", execution_id)

                # Phase 16: Tool whitelist — inject max_tools from complexity tier

                try:

                    msg_text = ""

                    if isinstance(payload, dict):

                        msgs = payload.get("messages", [])

                        if msgs:

                            msg_text = str(msgs[-1].get("content", "") or "")

                    if msg_text:

                        from core.harness.knowledge.complexity_router import ComplexityRouter

                        cr = ComplexityRouter.estimate([{"role": "user", "content": msg_text}])

                        from core.harness.routing.model_tier_router import get_tier_router

                        router = get_tier_router()

                        tier = router._complexity_to_tier(

                            router._normalize_complexity(cr.level, cr.confidence)

                        )

                        max_tools = router.get_max_tools(f"T{tier}")

                        if max_tools > 0:

                            context.variables["_max_tools"] = max_tools

                except Exception:

                    logging.getLogger(__name__).debug('code failed', exc_info=True)
        except Exception as e:

            logging.debug(str(e), exc_info=True)



        # Phase 5.2: optional Orchestrator planning (Phase 9: plan drives execution)

        orchestrator_plan = None

        execution_plan = None

        if os.getenv("AIPLAT_ENABLE_ORCHESTRATOR", "true").lower() in ("1", "true", "yes", "y"):

            try:

                # Extract user intent from messages

                user_input = ""

                messages_list = payload.get("messages", []) if isinstance(payload, dict) else []

                if messages_list:

                    last_msg = messages_list[-1]

                    user_input = last_msg.get("content", "") if isinstance(last_msg, dict) else str(last_msg)



                if user_input:

                    from core.orchestration.intent_analyzer import analyze_intent

                    from core.orchestration import Orchestrator



                    intent = analyze_intent(user_input)

                    orchestrator = Orchestrator()

                    execution_plan = await orchestrator.plan(intent)

            except Exception:

                orchestrator_plan = None

                execution_plan = None



        # Phase 9: inject plan into agent context for step-by-step execution

        if execution_plan is not None and hasattr(agent, "context") and isinstance(getattr(agent, "context", None), dict):

            try:

                agent.context.setdefault("_execution_plan", execution_plan.to_dict())

            except Exception as e:

                logging.debug(str(e), exc_info=True)



        # Phase 5.0: route via EngineRouter (plan-aware in Phase 9)

        engine_router = None

        try:

            from core.harness.execution.router import EngineRouter



            engine_router = EngineRouter()

            enriched_payload = dict(payload if isinstance(payload, dict) else {})

            # Inject agent_type for GraphEngine routing (P1-5 fix)

            try:

                agent_cfg = getattr(agent, 'config', None) or getattr(agent, '_config', None)

                if agent_cfg:

                    enriched_payload["agent_type"] = getattr(agent_cfg, 'agent_type', '') or ''

            except Exception as e:

                logging.debug(str(e), exc_info=True)

            engine, decision = engine_router.route_agent(

                agent_id=agent_id,

                payload=enriched_payload,

                plan=execution_plan,

            )

        except Exception:

            engine, decision = None, None

        active_release = None

        if os.getenv("AIPLAT_ENABLE_LEARNING_APPLIER", "false").lower() in ("1", "true", "yes", "y"):

            try:

                from core.learning.apply import LearningApplier



                applier = LearningApplier(self._runtime.execution_store if self._runtime else None)

                active_release = await applier.resolve_active_release(target_type="agent", target_id=agent_id)

            except Exception:

                active_release = None



        # Phase 6.8: set per-request active release context for syscalls (behavior change is gated elsewhere).

        token = None

        audit_token = None

        audit_data = None

        if active_release is not None:

            try:

                from core.harness.kernel.execution_context import (

                    ActiveReleaseContext,

                    PromptRevisionAudit,

                    set_active_release_context,

                    set_prompt_revision_audit,

                )



                token = set_active_release_context(

                    ActiveReleaseContext(

                        target_type="agent",

                        target_id=agent_id,

                        candidate_id=active_release.candidate_id,

                        version=active_release.version,

                        summary=active_release.summary,

                    )

                )

                # Phase 6.12: initialize prompt revision audit (will be populated by sys_llm_generate).

                audit_token = set_prompt_revision_audit(

                    PromptRevisionAudit(applied_ids=[], ignored_ids=[], conflicts=[], llm_calls=0, updated_at=0.0)

                )

            except Exception:

                token = None

                audit_token = None



        try:

            if engine is not None:

                from core.harness.infrastructure.gates import TraceGate



                exec_span = await TraceGate().start(

                    "agent.execute",

                    attributes={

                        "trace_id": trace_id,

                        "agent_id": agent_id,

                        "execution_id": execution_id,

                    },

                )

                try:

                    # Use fallback chain if EngineRouter provided one, otherwise

                    # call the primary engine directly.

                    if engine_router is not None and decision is not None:

                        result = await engine_router.execute_with_fallback(agent, context, decision)

                    else:

                        result = await engine.execute_agent(agent, context)  # type: ignore[attr-defined]

                finally:

                    try:

                        await TraceGate().end(exec_span, success=bool(getattr(result, "success", False)))  # type: ignore[name-defined]

                    except Exception:

                        # If result is not set due to exception, mark failed.

                        try:

                            await TraceGate().end(exec_span, success=False)

                        except Exception as e:

                            logging.debug(str(e), exc_info=True)

            else:

                from core.harness.infrastructure.gates import TraceGate



                exec_span = await TraceGate().start(

                    "agent.execute",

                    attributes={

                        "trace_id": trace_id,

                        "agent_id": agent_id,

                        "execution_id": execution_id,

                    },

                )

                try:

                    result = await agent.execute(context)  # type: ignore[attr-defined]

                finally:

                    try:

                        await TraceGate().end(exec_span, success=bool(getattr(result, "success", False)))  # type: ignore[name-defined]

                    except Exception:

                        try:

                            await TraceGate().end(exec_span, success=False)

                        except Exception as e:

                            logging.debug(str(e), exc_info=True)

        finally:

            # Capture then reset prompt revision audit

            if audit_token is not None:

                try:

                    from core.harness.kernel.execution_context import get_prompt_revision_audit, reset_prompt_revision_audit



                    audit = get_prompt_revision_audit()

                    audit_data = audit.to_dict() if audit is not None else None

                    reset_prompt_revision_audit(audit_token)

                except Exception as e:

                    logging.debug(str(e), exc_info=True)

            if token is not None:

                try:

                    from core.harness.kernel.execution_context import reset_active_release_context



                    reset_active_release_context(token)

                except Exception as e:

                    logging.debug(str(e), exc_info=True)

            if workspace_token is not None:

                try:

                    from core.harness.kernel.execution_context import reset_active_workspace_context



                    reset_active_workspace_context(workspace_token)

                except Exception as e:

                    logging.debug(str(e), exc_info=True)

            if request_token is not None:

                try:

                    from core.harness.kernel.execution_context import reset_active_request_context



                    reset_active_request_context(request_token)

                except Exception as e:

                    logging.debug(str(e), exc_info=True)

            if tenant_policy_token is not None:

                try:

                    from core.harness.kernel.execution_context import reset_active_tenant_policy_context



                    reset_active_tenant_policy_context(tenant_policy_token)

                except Exception as e:

                    logging.debug(str(e), exc_info=True)



        # Attach kernel-managed resume payload (Phase 3.5) so resume can work after server restart.

        # Keep it minimal: only what is required to re-run agent execute.

        kernel_resume = {

            "messages": payload.get("messages", []),

            "context": payload.get("context", {}),

            "session_id": payload.get("session_id", req.session_id or "default"),

            "user_id": user_id,

        }

        meta = dict(result.metadata or {})

        if decision is not None:

            # Keep as plain JSON for persistence

            meta.setdefault("engine", getattr(decision, "engine", None))

            meta.setdefault("engine_explain", getattr(decision, "explain", None))

            meta.setdefault("fallback_chain", getattr(decision, "fallback_chain", None))

            meta.setdefault("fallback_trace", getattr(decision, "fallback_trace", None))

        if orchestrator_plan is not None:

            try:

                meta.setdefault("orchestrator_plan", orchestrator_plan.to_dict())

            except Exception as e:

                logging.debug(str(e), exc_info=True)

        if active_release is not None:

            try:

                meta.setdefault("active_release", active_release.to_dict())

            except Exception as e:

                logging.debug(str(e), exc_info=True)

        # Phase 6.12: attach prompt revision audit into execution metadata

        if audit_data is not None:

            meta.setdefault("prompt_revision_audit", audit_data)

        meta.setdefault("kernel_resume", kernel_resume)

        # Phase 15: Completion checklist for all agent outputs

        try:

            from core.harness.infrastructure.gates.completion_gate import CompletionChecklistGate

            gate = CompletionChecklistGate(llm_threshold=99)

            q = ""

            if isinstance(payload, dict):

                msgs = payload.get("messages", [])

                if msgs:

                    q = str(msgs[-1].get("content", "") or "")[:300]

            if hasattr(result, "output"):

                out = getattr(result, "output", {})

                comp = gate.verify(

                    out if isinstance(out, dict) else {"answer": str(out)},

                    question=q,

                )

                meta.setdefault("completion_gate_status", comp.status)

                meta.setdefault("completion_gate_valid", comp.valid)

        except Exception:

            logging.getLogger(__name__).debug('code failed', exc_info=True)
        # Phase 11.2: Semantic compliance validation (all agents)

        try:

            from core.harness.infrastructure.gates.semantic_gate import SemanticGate

            gate = SemanticGate(mode=os.getenv("AIPLAT_SEMANTIC_GATE_MODE", "warn"))

            out = getattr(result, "output", {}) if hasattr(result, "output") else {}

            gate_result = gate.verify(out if isinstance(out, dict) else {}, domain_id="default")

            meta.setdefault("semantic_gate_status", gate_result.status)

            meta.setdefault("semantic_violations", len(gate_result.violations))

        except Exception:

            logging.getLogger(__name__).debug('code failed', exc_info=True)
        # Post-generation: quality assessment (all agents)

        try:

            from core.harness.evaluation.self_review import self_review

            out = getattr(result, "output", {}) if hasattr(result, "output") else {}

            answer = (out if isinstance(out, str) else

                      out.get("answer", "") if isinstance(out, dict) else "")

            citations = out.get("citations", []) if isinstance(out, dict) else []

            quality = self_review(str(answer), citations, [])

            meta.setdefault("quality", quality)

        except Exception:

            logging.getLogger(__name__).debug('code failed', exc_info=True)
        # Post-generation: Hallucination risk check (all agents)

        try:

            from core.harness.evaluation.hallucination_tracker import get_hallucination_tracker

            tracker = get_hallucination_tracker()

            out = getattr(result, "output", {}) if hasattr(result, "output") else {}

            answer = (out if isinstance(out, str) else

                      out.get("answer", "") if isinstance(out, dict) else "")

            citations = out.get("citations", []) if isinstance(out, dict) else []

            q = ""

            if isinstance(payload, dict):

                msgs = payload.get("messages", [])

                if msgs:

                    q = str(msgs[-1].get("content", "") or "")

            report = await tracker.evaluate(

                question=q, answer=str(answer),

                retrieved_context=[{"text": str(c.get("text", c))} for c in (citations or [])[:5]],

                run_id=execution_id, domain_id="default",

            )

            meta.setdefault("hallucination_risk", report.hallucination_risk)

            if report.hallucination_risk > 0.7:

                meta["quality"] = "low_evidence"  # downgrade quality on high risk

        except Exception:

            logging.getLogger(__name__).debug('code failed', exc_info=True)
        # Post-generation: Semantic cache write (all agents)

        try:

            from core.harness.knowledge.semantic_cache_hook import write_cache_result

            out = getattr(result, "output", {}) if hasattr(result, "output") else {}

            answer = (out if isinstance(out, str) else

                      out.get("answer", "") if isinstance(out, dict) else "")

            citations = out.get("citations", []) if isinstance(out, dict) else []

            q = ""

            if isinstance(payload, dict):

                msgs = payload.get("messages", [])

                if msgs:

                    q = str(msgs[-1].get("content", "") or "")

            if answer and q:

                await write_cache_result(q, "default", str(answer), list(citations or []))

        except Exception:

            logging.getLogger(__name__).debug('code failed', exc_info=True)
        # Post-generation: PatternCache store (all agents)

        try:

            from core.harness.execution.pattern_cache import get_pattern_cache

            pcache = get_pattern_cache()

            out = getattr(result, "output", {}) if hasattr(result, "output") else {}

            strategy = (out.get("strategy", "") if isinstance(out, dict) else "")

            await pcache.store("default", execution_id,

                                {"strategy": strategy, "quality": meta.get("quality", "")},

                                success=result.success)

        except Exception:

            logging.getLogger(__name__).debug('code failed', exc_info=True)
        # Post-generation: Memory save (all agents)

        try:

            from core.harness.memory.manager import MemoryManager

            mm = getattr(runtime, "memory_manager", None) if runtime else None

            if mm:

                q = ""

                if isinstance(payload, dict):

                    msgs = payload.get("messages", [])

                    if msgs:

                        q = str(msgs[-1].get("content", "") or "")

                out = getattr(result, "output", {}) if hasattr(result, "output") else {}

                answer = (out if isinstance(out, str) else

                          out.get("answer", "") if isinstance(out, dict) else "")

                if q and answer:

                    await mm.save_interaction(question=q, answer=str(answer), success=result.success)

        except Exception:

            logging.getLogger(__name__).debug('code failed', exc_info=True)
        # Phase 20: Audit trail — capture reasoning paths for compliance audit

        try:

            from core.harness.infrastructure.gates.audit_trail_gate import AuditTrailGate

            audit_gate = AuditTrailGate()

            audit_steps = audit_gate.capture(

                result, domain_id=agent_id, agent_id=agent_id,

                tenant_id=str(payload.get("tenant_id", "default")) if isinstance(payload, dict) else "default",

                session_id=str(payload.get("session_id", "default")) if isinstance(payload, dict) else "default",

            )

            if audit_steps:

                meta.setdefault("audit_steps", len(audit_steps))

                meta.setdefault("audit_rules_matched",

                                len([s for s in audit_steps if s.rule_ref]))

        except Exception:

            logging.getLogger(__name__).debug('code failed', exc_info=True)
        # Phase 23.3 G4: Retrieval precision feedback loop

        try:

            ctx = (payload.get("context") or {}) if isinstance(payload, dict) else {}

            feedback_action = payload.get("_feedback_action") if isinstance(payload, dict) else None

            if not feedback_action and isinstance(ctx, dict):

                feedback_action = ctx.get("_feedback_action")

            if feedback_action in ("regenerate", "ignore"):

                semantic_keys = (meta or {}).get("_semantic_keys_used", [])

                if semantic_keys:

                    try:

                        from core.harness.memory.manager import get_memory_manager

                        mm = get_memory_manager()

                        await mm.increment_semantic_access(semantic_keys)

                    except Exception:

                        logging.getLogger(__name__).debug('code failed', exc_info=True)
                    logger.debug("[FEEDBACK] %s → decay signal for %d keys",

                                 feedback_action, len(semantic_keys))

        except Exception:

            logging.getLogger(__name__).debug('code failed', exc_info=True)
        # Post-generation: Action bridge (fire webhooks for recommended_actions)

        try:

            out = getattr(result, "output", {}) if hasattr(result, "output") else {}

            decision = out.get("decision", out) if isinstance(out, dict) else {}

            if isinstance(decision, dict) and decision.get("recommended_actions"):

                from core.harness.actions.action_bridge import execute_decision_actions

                action_results = await execute_decision_actions(decision)

                meta.setdefault("actions_fired", len(action_results))

                meta.setdefault("action_results", action_results)

        except Exception:

            logging.getLogger(__name__).debug('code failed', exc_info=True)
        approval_req_id = None

        try:

            approval_req_id = (meta.get("approval") or {}).get("approval_request_id") if isinstance(meta.get("approval"), dict) else None

        except Exception:

            approval_req_id = None



        record = {

            "id": execution_id,

            "agent_id": agent_id,

            "status": "completed" if result.success else ("approval_required" if result.error == "approval_required" else "failed"),

            "input": payload.get("input", payload.get("messages", [])),

            "output": result.output,

            "error": result.error,

            "start_time": start_time,

            "end_time": time.time(),

            "duration_ms": int((time.time() - start_time) * 1000),

            "trace_id": trace_id,

            "metadata": meta,

            "approval_request_id": approval_req_id,

        }

        # Roadmap-0: persist structured error info into metadata for later UI/analytics.

        try:

            meta.setdefault(

                "error_detail",

                self._normalize_error(

                    error=result.error,

                    metadata=meta,

                    fallback_message=str(result.error or "执行失败"),

                ),

            )

        except Exception as e:

            logging.debug(str(e), exc_info=True)

        # Persist (best effort)

        if runtime.execution_store:

            try:

                # Propagate project_id into metadata for downstream policy selection / analytics

                try:

                    ctx0 = payload.get("context") if isinstance(payload, dict) else None

                    if isinstance(ctx0, dict) and ctx0.get("project_id") and isinstance(meta, dict):

                        meta.setdefault("project_id", str(ctx0.get("project_id")))

                except Exception as e:

                    logging.debug(str(e), exc_info=True)

                await runtime.execution_store.upsert_agent_execution(record)

            except Exception as e:

                logging.debug(str(e), exc_info=True)

            # Roadmap-4: persist session messages for cross-session search (best-effort).

            try:

                sess_id = str(payload.get("session_id", req.session_id or "default")) if isinstance(payload, dict) else str(req.session_id or "default")

                # pick last user message as the "current query"

                user_text = None

                for m in reversed(messages or []):

                    if isinstance(m, dict) and m.get("role") == "user":

                        user_text = m.get("content")

                        break

                if user_text:

                    await runtime.execution_store.add_memory_message(

                        session_id=sess_id,

                        user_id=str(user_id or "system"),

                        role="user",

                        content=str(user_text),

                        metadata={"trace_id": trace_id, "run_id": execution_id, "agent_id": agent_id},

                        trace_id=trace_id,

                        run_id=execution_id,

                    )

                if result.output is not None:

                    await runtime.execution_store.add_memory_message(

                        session_id=sess_id,

                        user_id=str(user_id or "system"),

                        role="assistant",

                        content=str(result.output),

                        metadata={"trace_id": trace_id, "run_id": execution_id, "agent_id": agent_id},

                        trace_id=trace_id,

                        run_id=execution_id,

                    )

            except Exception as e:

                logging.debug(str(e), exc_info=True)

        if runtime.trace_service and trace_id:

            try:

                from core.services.trace_service import SpanStatus



                await runtime.trace_service.end_trace(

                    trace_id, status=SpanStatus.SUCCESS if result.success else SpanStatus.FAILED

                )

            except Exception as e:

                logging.debug(str(e), exc_info=True)



        # Run events (best-effort): end

        if runtime.execution_store:

            try:

                await runtime.execution_store.append_run_event(

                    run_id=execution_id,

                    event_type="run_end",

                    trace_id=trace_id,

                    tenant_id=str(tenant_id) if tenant_id else None,

                    payload={

                        "kind": "agent",

                        "agent_id": agent_id,

                        "status": record["status"],

                        "error": result.error,

                    },

                )

            except Exception as e:

                logging.debug(str(e), exc_info=True)



        return ExecutionResult(

            ok=True,

            payload={

                "execution_id": execution_id,

                "status": record["status"],

                "output": result.output,

                # Roadmap-0 contract: error object is `error`, legacy string is `error_message`.

                "error": self._normalize_error(

                    error=result.error,

                    metadata=meta,

                    fallback_message=str(result.error or "执行失败"),

                ),

                "error_message": result.error,

                # Backward compatible alias

                "error_detail": self._normalize_error(

                    error=result.error,

                    metadata=meta,

                    fallback_message=str(result.error or "执行失败"),

                ),

                "trace_id": trace_id,

                "run_id": execution_id,

                "duration_ms": record["duration_ms"],

                "metadata": meta,

            },

            trace_id=trace_id,

            run_id=execution_id,

            error_detail=self._normalize_error(

                error=result.error,

                metadata=meta,

                fallback_message=str(result.error or "执行失败"),

            ),

        )

    except Exception as e:

        if runtime.execution_store:

            try:

                await runtime.execution_store.upsert_agent_execution(

                    {

                        "id": execution_id,

                        "agent_id": agent_id,

                        "status": "failed",

                        "error": str(e),

                        "start_time": start_time,

                        "end_time": time.time(),

                        "duration_ms": int((time.time() - start_time) * 1000),

                        "trace_id": trace_id,

                        "metadata": {"exception": str(e)},

                    }

                )

            except Exception as e:

                logging.debug(str(e), exc_info=True)

            try:

                await runtime.execution_store.append_run_event(

                    run_id=execution_id,

                    event_type="run_end",

                    trace_id=trace_id,

                    tenant_id=str(tenant_id) if tenant_id else None,

                    payload={"kind": "agent", "agent_id": agent_id, "status": "failed", "error": str(e)},

                )

            except Exception as e:

                logging.debug(str(e), exc_info=True)

        if runtime.trace_service and trace_id:

            try:

                from core.services.trace_service import SpanStatus



                await runtime.trace_service.end_trace(trace_id, status=SpanStatus.FAILED)

            except Exception as e:

                logging.debug(str(e), exc_info=True)

        return self._fail(code="EXCEPTION", message=str(e), http_status=500, trace_id=trace_id, run_id=execution_id)

