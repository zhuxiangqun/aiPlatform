"""
Harness Integration Module

Provides a unified entry point for the Harness framework.
"""

from typing import Any, Dict, Optional
from dataclasses import dataclass, field
import os
import time
import uuid

from .interfaces import (
    IAgent,
    ITool,
    ISkill,
    ILoop,
    ICoordinator,
)
from .execution import (
    BaseLoop,
    ReActLoop,
    PlanExecuteLoop,
    create_loop,
)
from .coordination import (
    create_pattern,
    create_coordinator,
    create_detector,
)
from .observability import (
    MonitoringSystem,
    MetricsCollector,
    EventBus,
    AlertManager,
)
from .feedback_loops import (
    LocalFeedbackLoop,
    PushManager,
    ProductionFeedbackLoop,
    EvolutionEngine,
)
from .memory import (
    MemoryBase,
    MemoryScope,
    ShortTermMemory,
    LongTermMemory,
    SessionManager,
)
from .syscalls import sys_tool_call


@dataclass
class HarnessConfig:
    """Harness configuration"""
    enable_monitoring: bool = True
    enable_observability: bool = True
    enable_feedback_loops: bool = True
    enable_memory: bool = True
    enable_evolution: bool = True
    
    monitoring_config: Dict[str, Any] = field(default_factory=dict)
    memory_config: Dict[str, Any] = field(default_factory=dict)
    feedback_config: Dict[str, Any] = field(default_factory=dict)


class HarnessIntegration:
    """
    Harness Integration - Unified Entry Point
    
    Provides centralized access to all Harness components.
    """
    
    _instance: Optional["HarnessIntegration"] = None
    
    def __init__(self, config: Optional[HarnessConfig] = None):
        self._config = config or HarnessConfig()
        self._initialized = False
        
        self._monitoring: Optional[MonitoringSystem] = None
        self._metrics: Optional[MetricsCollector] = None
        self._event_bus: Optional[EventBus] = None
        self._alert_manager: Optional[AlertManager] = None
        self._feedback: Optional[LocalFeedbackLoop] = None
        self._push_manager: Optional[PushManager] = None
        self._prod_feedback: Optional[ProductionFeedbackLoop] = None
        self._evolution: Optional[EvolutionEngine] = None
        self._memory: Optional[MemoryBase] = None
        self._session_manager: Optional[SessionManager] = None

        # Phase-1 Kernel runtime dependencies (wired by core/server.py lifespan)
        self._runtime: Optional["KernelRuntime"] = None
    
    @classmethod
    def get_instance(cls) -> "HarnessIntegration":
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance
    
    @classmethod
    def initialize(cls, config: Optional[HarnessConfig] = None) -> "HarnessIntegration":
        instance = cls.get_instance()
        instance._config = config or HarnessConfig()
        instance._setup()
        return instance
    
    def _setup(self):
        if self._initialized:
            return
        
        if self._config.enable_observability:
            self._monitoring = MonitoringSystem.get_instance()
            self._metrics = MetricsCollector.get_instance()
            self._event_bus = EventBus.get_instance()
            self._alert_manager = AlertManager.get_instance()
        
        if self._config.enable_feedback_loops:
            self._feedback = LocalFeedbackLoop()
            self._push_manager = PushManager()
            self._prod_feedback = ProductionFeedbackLoop()
            if self._config.enable_evolution:
                self._evolution = EvolutionEngine()
        
        if self._config.enable_memory:
            self._memory = ShortTermMemory(self._config.memory_config)
            self._session_manager = SessionManager()
        
        self._initialized = True

    # ------------------------------
    # Phase-1: single entry execute()
    # ------------------------------

    def attach_runtime(self, runtime: "KernelRuntime") -> None:
        """Attach runtime dependencies (managers/stores/tracing) from application layer."""
        self._runtime = runtime
        try:
            from core.harness.kernel.runtime import set_kernel_runtime

            set_kernel_runtime(runtime)
        except Exception:
            pass

    async def execute(self, request: "ExecutionRequest") -> "ExecutionResult":
        """
        Unified execution entry point (Phase 1).

        This method is intentionally minimal: it preserves existing API behavior while
        routing execution through a single kernel entry point.
        """
        if request.kind == "agent":
            return await self._execute_agent(request)
        if request.kind == "skill":
            return await self._execute_skill(request)
        if request.kind == "tool":
            return await self._execute_tool(request)
        if request.kind == "graph":
            return await self._execute_graph(request)
        return ExecutionResult(ok=False, error=f"Unsupported kind: {request.kind}", http_status=400)

    async def _execute_agent(self, req: "ExecutionRequest") -> "ExecutionResult":
        from core.apps.agents import get_agent_registry
        from core.apps.skills import get_skill_registry
        from core.apps.tools import get_tool_registry
        from core.apps.tools.permission import get_permission_manager, Permission
        from core.harness.interfaces import AgentContext
        from core.harness.kernel.types import ExecutionResult

        runtime = self._runtime
        if runtime is None or runtime.agent_manager is None:
            return ExecutionResult(ok=False, error="Kernel runtime not initialized", http_status=503)

        agent_id = req.target_id
        registry = get_agent_registry()
        agent = registry.get(agent_id)
        if not agent:
            return ExecutionResult(ok=False, error=f"Agent {agent_id} not found", http_status=404)

        user_id = req.user_id or (req.payload.get("user_id") if isinstance(req.payload, dict) else None) or "system"
        perm_mgr = get_permission_manager()
        if not perm_mgr.check_permission(user_id, agent_id, Permission.EXECUTE):
            return ExecutionResult(
                ok=False,
                error=f"User '{user_id}' lacks EXECUTE permission for agent '{agent_id}'",
                http_status=403,
            )

        # Resolve model name from AgentManager metadata (best effort)
        agent_info = await runtime.agent_manager.get_agent(agent_id)
        model_name = agent_info.config.get("model", "gpt-4") if agent_info else "gpt-4"

        # Inject model if needed (best effort, mirrors server.py behavior)
        if hasattr(agent, "_model") and getattr(agent, "_model") is None:
            try:
                from core.adapters.llm import create_adapter

                agent.set_model(create_adapter(provider="openai", api_key="", model=model_name))  # type: ignore[attr-defined]
            except Exception:
                pass

        # Wire approval manager into loop (best effort)
        if runtime.approval_manager and hasattr(agent, "_loop") and hasattr(agent._loop, "set_approval_manager"):
            try:
                agent._loop.set_approval_manager(runtime.approval_manager)  # type: ignore[attr-defined]
            except Exception:
                pass

        # Bind tools (best effort)
        if agent_info and getattr(agent_info, "tools", None) and hasattr(agent, "add_tool"):
            tool_registry = get_tool_registry()
            for tool_name in agent_info.tools:
                if not perm_mgr.check_permission(user_id, tool_name, Permission.EXECUTE):
                    return ExecutionResult(
                        ok=False,
                        error=f"User '{user_id}' lacks EXECUTE permission for tool '{tool_name}'",
                        http_status=403,
                    )
                tool = tool_registry.get(tool_name)
                if tool:
                    try:
                        agent.add_tool(tool)  # type: ignore[attr-defined]
                    except Exception:
                        pass

        # Bind skills (best effort)
        if agent_info and getattr(agent_info, "skills", None) and hasattr(agent, "add_skill"):
            skill_registry = get_skill_registry()
            for skill_name in agent_info.skills:
                skill = skill_registry.get(skill_name)
                if skill:
                    # inject model if needed
                    if hasattr(skill, "_model") and getattr(skill, "_model") is None:
                        try:
                            from core.adapters.llm import create_adapter

                            skill.set_model(create_adapter(provider="openai", api_key="", model=model_name))  # type: ignore[attr-defined]
                        except Exception:
                            pass
                    try:
                        agent.add_skill(skill)  # type: ignore[attr-defined]
                    except Exception:
                        pass

        execution_id = f"exec-{agent_id}-{uuid.uuid4().hex[:8]}"
        start_time = time.time()

        trace_id = None
        if runtime.trace_service:
            try:
                trace = await runtime.trace_service.start_trace(
                    name=f"agent:{agent_id}",
                    attributes={"execution_id": execution_id, "agent_id": agent_id, "user_id": user_id},
                )
                trace_id = trace.trace_id
            except Exception:
                trace_id = None

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

            # Phase R1: workspace/repo context for prompt assembly (best-effort).
            workspace_token = None
            try:
                from core.harness.kernel.execution_context import (
                    ActiveWorkspaceContext,
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
                if (isinstance(repo_root, str) and repo_root.strip()) or requested_toolset:
                    workspace_token = set_active_workspace_context(
                        ActiveWorkspaceContext(
                            repo_root=repo_root.strip() if isinstance(repo_root, str) and repo_root.strip() else None,
                            toolset=str(requested_toolset) if requested_toolset else None,
                        )
                    )
            except Exception:
                workspace_token = None

            # If resuming, pass loop snapshot down via AgentContext.variables
            variables = payload.get("context", {}) if isinstance(payload, dict) else {}
            if isinstance(payload, dict) and "_resume_loop_state" in payload:
                try:
                    variables = dict(variables or {})
                    variables["_resume_loop_state"] = payload.get("_resume_loop_state")
                except Exception:
                    pass
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
            except Exception:
                pass
            # Propagate trace/run identifiers into agent variables so loops can pass them to syscalls.
            try:
                if isinstance(context.variables, dict):
                    context.variables.setdefault("_trace_id", trace_id)
                    context.variables.setdefault("_run_id", execution_id)
            except Exception:
                pass

            # Phase 5.0: route via EngineRouter (behavior-preserving)
            try:
                from core.harness.execution.router import EngineRouter

                engine, decision = EngineRouter().route_agent(agent_id=agent_id, payload=payload if isinstance(payload, dict) else {})
            except Exception:
                engine, decision = None, None

            # Phase 6.7: optional LearningApplier (behavior-preserving; metadata-only)
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

            # Phase 5.2: optional Orchestrator planning (plan-only; does NOT affect execution)
            orchestrator_plan = None
            if os.getenv("AIPLAT_ENABLE_ORCHESTRATOR", "false").lower() in ("1", "true", "yes", "y"):
                try:
                    from core.orchestration import Orchestrator

                    orchestrator = Orchestrator()
                    orchestrator_plan = await orchestrator.plan(
                        agent_id=agent_id,
                        model=getattr(agent, "_model", None),
                        messages=payload.get("messages", []) if isinstance(payload, dict) else [],
                        context=payload.get("context") if isinstance(payload, dict) else {},
                        trace_context={"trace_id": trace_id, "run_id": execution_id},
                    )
                except Exception:
                    orchestrator_plan = None

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
                        result = await engine.execute_agent(agent, context)  # type: ignore[attr-defined]
                    finally:
                        try:
                            await TraceGate().end(exec_span, success=bool(getattr(result, "success", False)))  # type: ignore[name-defined]
                        except Exception:
                            # If result is not set due to exception, mark failed.
                            try:
                                await TraceGate().end(exec_span, success=False)
                            except Exception:
                                pass
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
                            except Exception:
                                pass
            finally:
                # Capture then reset prompt revision audit
                if audit_token is not None:
                    try:
                        from core.harness.kernel.execution_context import get_prompt_revision_audit, reset_prompt_revision_audit

                        audit = get_prompt_revision_audit()
                        audit_data = audit.to_dict() if audit is not None else None
                        reset_prompt_revision_audit(audit_token)
                    except Exception:
                        pass
                if token is not None:
                    try:
                        from core.harness.kernel.execution_context import reset_active_release_context

                        reset_active_release_context(token)
                    except Exception:
                        pass
                if workspace_token is not None:
                    try:
                        from core.harness.kernel.execution_context import reset_active_workspace_context

                        reset_active_workspace_context(workspace_token)
                    except Exception:
                        pass

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
                except Exception:
                    pass
            if active_release is not None:
                try:
                    meta.setdefault("active_release", active_release.to_dict())
                except Exception:
                    pass
            # Phase 6.12: attach prompt revision audit into execution metadata
            if audit_data is not None:
                meta.setdefault("prompt_revision_audit", audit_data)
            meta.setdefault("kernel_resume", kernel_resume)
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
            # Persist (best effort)
            if runtime.execution_store:
                try:
                    await runtime.execution_store.upsert_agent_execution(record)
                except Exception:
                    pass
            if runtime.trace_service and trace_id:
                try:
                    from core.services.trace_service import SpanStatus

                    await runtime.trace_service.end_trace(
                        trace_id, status=SpanStatus.SUCCESS if result.success else SpanStatus.FAILED
                    )
                except Exception:
                    pass

            return ExecutionResult(
                ok=True,
                payload={
                    "execution_id": execution_id,
                    "status": record["status"],
                    "output": result.output,
                    "error": result.error,
                    "duration_ms": record["duration_ms"],
                    "metadata": meta,
                },
                trace_id=trace_id,
                run_id=execution_id,
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
                except Exception:
                    pass
            if runtime.trace_service and trace_id:
                try:
                    from core.services.trace_service import SpanStatus

                    await runtime.trace_service.end_trace(trace_id, status=SpanStatus.FAILED)
                except Exception:
                    pass
            return ExecutionResult(ok=False, error=str(e), http_status=500, trace_id=trace_id, run_id=execution_id)

    async def _execute_skill(self, req: "ExecutionRequest") -> "ExecutionResult":
        from core.apps.tools.permission import get_permission_manager, Permission
        from core.harness.kernel.types import ExecutionResult

        runtime = self._runtime
        if runtime is None or runtime.skill_manager is None:
            return ExecutionResult(ok=False, error="Kernel runtime not initialized", http_status=503)

        skill_id = req.target_id
        user_id = req.user_id or (req.payload.get("context", {}) or {}).get("user_id", "system")

        perm_mgr = get_permission_manager()
        if not perm_mgr.check_permission(user_id, skill_id, Permission.EXECUTE):
            return ExecutionResult(
                ok=False,
                error=f"User '{user_id}' lacks EXECUTE permission for skill '{skill_id}'",
                http_status=403,
            )

        trace_id = None
        if runtime.trace_service:
            try:
                trace = await runtime.trace_service.start_trace(
                    name=f"skill:{skill_id}",
                    attributes={"skill_id": skill_id, "user_id": user_id},
                )
                trace_id = trace.trace_id
            except Exception:
                trace_id = None

        payload = req.payload or {}
        try:
            execution = await runtime.skill_manager.execute_skill(
                skill_id,
                payload.get("input"),
                context=payload.get("context") or {},
                mode=payload.get("mode", "inline"),
            )
        except Exception as e:
            return ExecutionResult(ok=False, error=str(e), http_status=500, trace_id=trace_id)

        # Persist execution (best effort)
        if runtime.execution_store:
            try:
                await runtime.execution_store.upsert_skill_execution(
                    {
                        "id": execution.id,
                        "skill_id": execution.skill_id,
                        "status": execution.status,
                        "input": execution.input_data,
                        "output": execution.output_data,
                        "error": execution.error,
                        "start_time": execution.start_time.timestamp() if execution.start_time else 0.0,
                        "end_time": execution.end_time.timestamp() if execution.end_time else 0.0,
                        "duration_ms": execution.duration_ms or 0,
                        "user_id": user_id,
                        "trace_id": trace_id,
                        "metadata": {
                            "mode": payload.get("mode", "inline"),
                            "session_id": (payload.get("context") or {}).get("session_id", req.session_id),
                        },
                    }
                )
            except Exception:
                pass

        if runtime.trace_service and trace_id:
            try:
                from core.services.trace_service import SpanStatus

                await runtime.trace_service.end_trace(
                    trace_id, status=SpanStatus.SUCCESS if execution.status == "completed" else SpanStatus.FAILED
                )
            except Exception:
                pass

        return ExecutionResult(
            ok=True,
            payload={
                "execution_id": execution.id,
                "skill_id": execution.skill_id,
                "status": execution.status,
                "input": execution.input_data,
                "output": execution.output_data,
                "error": execution.error,
                "trace_id": trace_id,
                "start_time": execution.start_time.isoformat() if execution.start_time else None,
                "end_time": execution.end_time.isoformat() if execution.end_time else None,
                "duration_ms": execution.duration_ms,
            },
            trace_id=trace_id,
            run_id=execution.id,
        )

    async def _execute_tool(self, req: "ExecutionRequest") -> "ExecutionResult":
        from core.apps.tools import get_tool_registry
        from core.harness.kernel.types import ExecutionResult

        registry = get_tool_registry()
        tool = registry.get(req.target_id)
        if not tool:
            return ExecutionResult(ok=False, error=f"Tool {req.target_id} not found", http_status=404)

        input_data = (req.payload or {}).get("input", {})
        try:
            result = await sys_tool_call(
                tool,
                input_data if isinstance(input_data, dict) else {},
                user_id=req.user_id,
                session_id=req.session_id,
                timeout_seconds=60,
            )
            return ExecutionResult(
                ok=True,
                payload={
                    "success": getattr(result, "success", True),
                    "output": getattr(result, "output", str(result)),
                    "error": getattr(result, "error", None) or None,
                    "latency": getattr(result, "latency", 0),
                    "metadata": getattr(result, "metadata", {}) or {},
                },
            )
        except asyncio.TimeoutError:
            return ExecutionResult(ok=False, error="Tool execution timed out (60s)", http_status=504)
        except Exception as e:
            return ExecutionResult(ok=False, error=str(e), http_status=500)

    async def _execute_graph(self, req: "ExecutionRequest") -> "ExecutionResult":
        # Phase-1: only support compiled_react execution via internal compiled graph.
        from core.harness.kernel.types import ExecutionResult

        runtime = self._runtime
        if runtime is None or runtime.execution_store is None:
            return ExecutionResult(ok=False, error="ExecutionStore not initialized", http_status=503)

        payload = req.payload or {}
        messages = payload.get("messages") or []
        context = payload.get("context") or {}
        max_steps = int(payload.get("max_steps", 10) or 10)
        checkpoint_interval = int(payload.get("checkpoint_interval", 1) or 1)

        class _DefaultModel:
            async def generate(self, prompt):
                return type("R", (), {"content": "DONE"})

        from core.harness.execution.langgraph.compiled_graphs import create_compiled_react_graph
        from core.harness.execution.langgraph.core import GraphConfig

        graph_run_id = str(uuid.uuid4())

        trace_id = None
        if runtime.trace_service:
            try:
                t = await runtime.trace_service.start_trace(
                    name=f"graph:{req.target_id}",
                    attributes={"graph_name": req.target_id, "graph_run_id": graph_run_id, "source": "graph"},
                )
                trace_id = t.trace_id
            except Exception:
                trace_id = None

        graph = create_compiled_react_graph(model=_DefaultModel(), tools=[], max_steps=max_steps)
        initial_state = {
            "messages": messages,
            "context": context,
            "step_count": 0,
            "max_steps": max_steps,
            "metadata": {"graph_run_id": graph_run_id, "trace_id": trace_id},
        }
        try:
            final_state = await graph.execute(
                initial_state,
                config=GraphConfig(
                    max_steps=max_steps,
                    enable_checkpoints=True,
                    checkpoint_interval=checkpoint_interval,
                    enable_callbacks=True,
                ),
            )
        finally:
            if runtime.trace_service and trace_id:
                try:
                    from core.services.trace_service import SpanStatus

                    await runtime.trace_service.end_trace(trace_id, status=SpanStatus.SUCCESS)
                except Exception:
                    pass
        run_id = (final_state.get("metadata") or {}).get("graph_run_id")
        return ExecutionResult(ok=True, payload={"run_id": run_id, "final_state": final_state}, trace_id=trace_id, run_id=run_id)


@dataclass
class KernelRuntime:
    """Runtime dependencies provided by the application layer (core/server.py lifespan)."""

    agent_manager: Any = None
    skill_manager: Any = None
    execution_store: Any = None
    trace_service: Any = None
    approval_manager: Any = None
    
    @property
    def config(self) -> HarnessConfig:
        return self._config
    
    @property
    def monitoring(self) -> Optional[MonitoringSystem]:
        return self._monitoring
    
    @property
    def metrics(self) -> Optional[MetricsCollector]:
        return self._metrics
    
    @property
    def event_bus(self) -> Optional[EventBus]:
        return self._event_bus
    
    @property
    def alert_manager(self) -> Optional[AlertManager]:
        return self._alert_manager
    
    @property
    def feedback(self) -> Optional[LocalFeedbackLoop]:
        return self._feedback
    
    @property
    def push_manager(self) -> Optional[PushManager]:
        return self._push_manager
    
    @property
    def prod_feedback(self) -> Optional[ProductionFeedbackLoop]:
        return self._prod_feedback
    
    @property
    def evolution(self) -> Optional[EvolutionEngine]:
        return self._evolution
    
    @property
    def memory(self) -> Optional[MemoryBase]:
        return self._memory
    
    @property
    def session_manager(self) -> Optional[SessionManager]:
        return self._session_manager
    
    def create_agent_loop(
        self,
        agent: IAgent,
        loop_type: str = "react",
        **kwargs,
    ) -> ILoop:
        return create_loop(loop_type, agent=agent, **kwargs)
    
    def create_coordinator_pattern(
        self,
        pattern_type: str = "pipeline",
        **kwargs,
    ):
        return create_pattern(pattern_type, **kwargs)
    
    def create_convergence_detector(
        self,
        detector_type: str = "exact",
        **kwargs,
    ):
        return create_detector(detector_type, **kwargs)
    
    async def start(self):
        if self._config.enable_observability and self._monitoring:
            await self._monitoring.start_monitoring()
        if self._config.enable_feedback_loops and self._push_manager:
            await self._push_manager.start()
    
    async def stop(self):
        if self._config.enable_observability and self._monitoring:
            self._monitoring.stop_monitoring()
        if self._config.enable_feedback_loops and self._push_manager:
            await self._push_manager.stop()
    
    async def reset(self):
        if self._metrics:
            self._metrics.reset()
        if self._feedback:
            self._feedback.clear()
        if self._memory:
            await self._memory.clear(MemoryScope.SESSION)


def create_harness(config: Optional[HarnessConfig] = None) -> HarnessIntegration:
    return HarnessIntegration.initialize(config)


def get_harness() -> HarnessIntegration:
    return HarnessIntegration.get_instance()


__all__ = [
    "HarnessConfig",
    "HarnessIntegration",
    "create_harness",
    "get_harness",
]
