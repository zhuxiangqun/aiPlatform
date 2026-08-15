"""
Harness Integration Module

Provides a unified entry point for the Harness framework.

KNOWN ARCHITECTURE DEBT (Phase 9 in progress):
12 of 18 app-layer service-import sites converted to DI via _resolve_* helpers.
Remaining 6 SpanStatus imports are data-type imports (not service calls).
The DI container (_ensure_di) registers all factories at module init time.
Until fully migrated, NO NEW reverse imports should be added to this file.
"""

from __future__ import annotations
import logging

from typing import Any, Dict, List, Optional
from dataclasses import dataclass, field
import os
from pathlib import Path

from core.harness.memory.base import MemoryBase
from core.harness.memory.session import SessionManager
from core.harness.kernel.types import ExecutionRequest, ExecutionResult

# ── DI bridge (Phase 9) ─────────────────────────────────────────────
# Replaces 18 lazy imports with DI container lookups. Services are
# registered lazily on first use; individual import sites use
# _resolve_or_import() which tries DI first, falls back to direct import.

_di_container: Any = None


def _ensure_di():
    global _di_container
    if _di_container is not None:
        return _di_container
    try:
        from .infrastructure.di import DIContainer, Lifetime
        _di_container = DIContainer()

        # Register lazy factories (not imports — only loaded when resolved)
        def _agent_registry_factory():
            from core.apps.agents import AgentRegistry  # noqa
            return AgentRegistry()

        def _skill_registry_factory():
            from core.api.core_facade import get_skill_registry  # noqa
            return get_skill_registry()

        def _tool_registry_factory():
            from core.apps.tools.base import get_tool_registry  # noqa
            return get_tool_registry()

        def _trace_service_factory():
            from core.services.trace_service import TraceService  # noqa
            return TraceService()

        def _permission_factory():
            from core.apps.tools.permission import get_permission_manager  # noqa
            return get_permission_manager()

        def _exec_backend_factory():
            from core.apps.exec_drivers.registry import get_exec_backend  # noqa
            return get_exec_backend()

        def _subagent_coordinator_factory():
            from core.apps.agents.subagent.coordinator import get_subagent_coordinator  # noqa
            from core.api.core_facade import create_agent, get_tool_registry
            return get_subagent_coordinator(
                create_agent_fn=create_agent,
                get_tool_registry_fn=get_tool_registry,
            )

        def _skill_permission_resolver_factory(_di=None):
            from core.apps.tools.skill_tools import resolve_skill_permission, resolve_executable_skill_permission  # noqa
            return {"resolve": resolve_skill_permission, "resolve_exec": resolve_executable_skill_permission}

        def _skill_curator_factory(_di=None):
            from core.apps.skills.curator import get_skill_curator  # noqa
            return get_skill_curator()

        def _evolution_engine_factory():
            from core.apps.skills.evolution.engine import get_evolution_engine  # noqa
            return get_evolution_engine()

        def _mcp_runtime_factory():
            from core.apps.mcp.runtime import MCPRuntime  # noqa
            return MCPRuntime()

        def _latest_predictions_factory():
            from core.apps.skills.evolution.engine import get_latest_predictions  # noqa
            return get_latest_predictions

        def _bg_curator_factory():
            from core.apps.skills.registry import start_bg_curator as _curator  # noqa
            return _curator

        from .interfaces import IAgent, ISkill, ITool

        _di_container.register_singleton("AgentRegistry", _agent_registry_factory)
        _di_container.register_singleton("SkillRegistry", _skill_registry_factory)
        _di_container.register_singleton("ToolRegistry", _tool_registry_factory)
        _di_container.register_singleton("TraceService", _trace_service_factory)
        _di_container.register_singleton("PermissionManager", _permission_factory)
        _di_container.register_singleton("ExecBackend", _exec_backend_factory)
        _di_container.register_singleton("SubagentCoordinator", _subagent_coordinator_factory)
        _di_container.register_singleton("SkillPermissionResolver", _skill_permission_resolver_factory)
        _di_container.register_singleton("SkillCurator", _skill_curator_factory)
        _di_container.register_singleton("EvolutionEngine", _evolution_engine_factory)
        _di_container.register_singleton("MCPRuntime", _mcp_runtime_factory)
        _di_container.register_singleton("LatestPredictions", _latest_predictions_factory)
        _di_container.register_singleton("BgCurator", _bg_curator_factory)
        _di_container.register_singleton(IAgent, _agent_registry_factory)
        _di_container.register_singleton(ISkill, _skill_registry_factory)
        _di_container.register_singleton(ITool, _tool_registry_factory)
    except Exception:
        _di_container = None
    return _di_container


def _resolve_or_import(key: str, fallback_import: str) -> Any:
    """Resolve service from DI container, fall back to direct import."""
    di = _ensure_di()
    if di:
        try:
            result = di.resolve(key)
            if result is not None:
                return result
        except Exception as e:
            logging.debug(str(e), exc_info=True)
    # Fallback: direct import (legacy compat)
    import importlib
    mod_path, attr = fallback_import.rsplit(":", 1)
    mod = importlib.import_module(mod_path)
    return getattr(mod, attr)


def _resolve_tool_registry():
    """Get tool registry via DI (primary) or direct import (fallback)."""
    di = _ensure_di()
    if di:
        try:
            return di.resolve("ToolRegistry")
        except Exception as e:
            logging.debug(str(e), exc_info=True)
    from core.apps.tools.base import get_tool_registry  # noqa
    return get_tool_registry()


def _resolve_exec_backend():
    """Get exec backend via DI (primary) or direct import (fallback)."""
    di = _ensure_di()
    if di:
        try:
            return di.resolve("ExecBackend")
        except Exception as e:
            logging.debug(str(e), exc_info=True)
    from core.apps.exec_drivers.registry import get_exec_backend  # noqa
    return get_exec_backend()


# ── Public accessor functions for harness-internal use ──────────────
# These break the harness→apps reverse dependency by routing through
# DI container first, direct import as fallback. All harness modules
# should use these instead of importing from core.apps.* directly.


def get_tool_registry():
    """Resolve tool registry (DI first, direct import fallback)."""
    return _resolve_tool_registry()


def get_agent_registry():
    """Resolve agent registry."""
    return _resolve_or_import("AgentRegistry", "core.apps.agents.registry:AgentRegistry")()


def get_skill_registry():
    """Resolve skill registry."""
    return _resolve_or_import("SkillRegistry", "core.apps.skills.registry:get_skill_registry")()


def get_permission_manager():
    """Resolve permission manager."""
    return _resolve_or_import("PermissionManager", "core.apps.tools.permission:get_permission_manager")()


def get_exec_backend():
    """Resolve execution backend."""
    return _resolve_exec_backend()


def get_subagent_coordinator():
    """Resolve subagent coordinator."""
    return _resolve_or_import("SubagentCoordinator", "core.apps.agents.subagent.coordinator:get_subagent_coordinator")()


def get_skill_permission_resolver():
    """Resolve skill permission resolver function."""
    r = _resolve_or_import("SkillPermissionResolver", "core.apps.tools.skill_tools:resolve_skill_permission")
    if isinstance(r, dict):
        return r.get("resolve", r.get("resolve_exec", lambda n: "allow"))
    return r


def get_exec_skill_permission_resolver():
    """Resolve executable skill permission resolver function."""
    return _resolve_or_import("ExecSkillPermissionResolver", "core.apps.tools.skill_tools:resolve_executable_skill_permission")


def get_skill_curator():
    """Resolve skill curator."""
    return _resolve_or_import("SkillCurator", "core.apps.skills.curator:get_skill_curator")()


def get_evolution_engine():
    """Resolve evolution engine."""
    return _resolve_or_import("EvolutionEngine", "core.apps.skills.evolution.engine:get_evolution_engine")()


def get_parallel_executor():
    """Resolve parallel executor module (harness→apps boundary, via integration accessor).

    Returns the apps.agents.parallel_executor module; callers pick the symbols they
    need (parallel_analyze / create_dummy_agent / EmbeddingBridge / ParallelExecutor).
    Uses importlib (like _resolve_or_import) so harness modules never import apps directly.
    """
    import importlib
    return importlib.import_module("core.apps.agents.parallel_executor")


def get_agent_discovery():
    """Resolve AgentDiscovery class (harness→apps boundary, via integration accessor)."""
    import importlib
    return importlib.import_module("core.apps.agents.discovery").AgentDiscovery


def _start_bg_curator():
    """Start background skill curator (DI-resolved for harness use)."""
    try:
        di = _ensure_di()
        curator_fn = None
        if di:
            curator_fn = di.resolve("BgCurator")
        if curator_fn is None:
            from core.apps.skills.registry import start_bg_curator as _curator
            curator_fn = _curator
        curator_fn()
    except Exception as e:
        logging.warning("Failed to start background skill curator: %s", e, exc_info=True)


def get_mcp_runtime():
    """Resolve MCP runtime."""
    di = _ensure_di()
    if di:
        try:
            return di.resolve("MCPRuntime")
        except Exception as e:
            logging.debug(str(e), exc_info=True)
    from core.apps.mcp.runtime import MCPRuntime  # noqa
    return MCPRuntime()


def get_latest_predictions():
    """Resolve evolution predictions."""
    di = _ensure_di()
    if di:
        try:
            return di.resolve("LatestPredictions")
        except Exception as e:
            logging.debug(str(e), exc_info=True)
    from core.apps.skills.evolution.engine import get_latest_predictions  # noqa
    return get_latest_predictions()

import asyncio
import time
import uuid

from core.utils.ids import new_prefixed_id
from core.harness.kernel.types import ExecutionResult

from .interfaces import (
    IAgent,
    ITool,
    ISkill,
    ILoop,
)
from .execution import (
    BaseLoop,
    ReActLoop,
    PlanExecuteLoop,
    create_loop,
)
from .coordination import (
    create_pattern,
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
from .syscalls import sys_tool_call
from core.harness.utils.llm_env import get_llm_api_key, get_llm_base_url


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

        # PR-04: prevent duplicate drain tasks per (tenant, session)
        self._session_drain_inflight: set[str] = set()
    
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
            from .memory import ShortTermMemory, SessionManager
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
        except Exception as e:
            logging.debug(str(e), exc_info=True)

    async def execute(self, request: ExecutionRequest) -> ExecutionResult:
        """
        Unified execution entry point (Phase 1).

        This method is intentionally minimal: it preserves existing API behavior while
        routing execution through a single kernel entry point.
        """
        # PR-04: per-session serialization + queueing (best-effort, can be disabled)
        runtime = getattr(self, "_runtime", None)
        store = getattr(runtime, "execution_store", None) if runtime else None
        enable_queue = os.getenv("AIPLAT_SESSION_QUEUE_ENABLED", "true").lower() in ("1", "true", "yes", "y")
        tenant_id = None
        queue_mode = None
        try:
            if isinstance(getattr(request, "payload", None), dict):
                ctx0 = request.payload.get("context") if isinstance(request.payload.get("context"), dict) else {}
                opts0 = request.payload.get("options") if isinstance(request.payload.get("options"), dict) else {}
                tenant_id = ctx0.get("tenant_id") if isinstance(ctx0, dict) else None
                queue_mode = (
                    (opts0.get("queue_mode") if isinstance(opts0, dict) else None)
                    or request.payload.get("queue_mode")
                    or (ctx0.get("queue_mode") if isinstance(ctx0, dict) else None)
                )
        except Exception:
            tenant_id = None
            queue_mode = None

        session_id = str(getattr(request, "session_id", None) or "")
        run_id = str(getattr(request, "run_id", None) or "") or new_prefixed_id("run")
        request.run_id = run_id
        # Cross-service tracing: if the caller passed a request_id, remember the mapping
        # so audit logs and the smoke test can trace executions across platform→core.
        req_id = getattr(request, "request_id", None)
        if req_id and store is not None:
            try:
                await store.remember_request_run_id(
                    request_id=str(req_id),
                    run_id=run_id,
                    tenant_id=str(tenant_id) if tenant_id is not None else None,
                )
            except Exception as e:
                logging.debug(str(e), exc_info=True)

        lock_acquired = False
        if enable_queue and store is not None and session_id and request.kind in ("agent", "skill", "tool", "graph"):
            try:
                lock_acquired = await store.try_acquire_session_lock(
                    tenant_id=str(tenant_id) if tenant_id is not None else None,
                    session_id=session_id,
                    run_id=run_id,
                    ttl_seconds=int(os.getenv("AIPLAT_SESSION_LOCK_TTL_SECONDS", "300") or "300"),
                )
            except Exception:
                lock_acquired = False

            if not lock_acquired:
                # Enqueue and return immediately (queue_mode default collect).
                try:
                    await store.enqueue_session_run(
                        tenant_id=str(tenant_id) if tenant_id is not None else None,
                        session_id=session_id,
                        run_id=run_id,
                        kind=str(request.kind),
                        target_id=str(request.target_id),
                        user_id=str(getattr(request, "user_id", None) or "system"),
                        payload=request.payload if isinstance(request.payload, dict) else {},
                        queue_mode=str(queue_mode) if queue_mode else None,
                    )
                except Exception as e:
                    logging.debug(str(e), exc_info=True)
                try:
                    await store.append_run_event(
                        run_id=run_id,
                        event_type="run_start",
                        trace_id=None,
                        tenant_id=str(tenant_id) if tenant_id is not None else None,
                        payload={
                            "kind": str(request.kind),
                            "target_id": str(request.target_id),
                            "user_id": str(getattr(request, "user_id", None) or "system"),
                            "session_id": session_id,
                            "status": "queued",
                            "queue_mode": str(queue_mode) if queue_mode else "collect",
                        },
                    )
                    await store.append_run_event(
                        run_id=run_id,
                        event_type="queued",
                        trace_id=None,
                        tenant_id=str(tenant_id) if tenant_id is not None else None,
                        payload={"reason": "session_locked", "session_id": session_id},
                    )
                except Exception as e:
                    logging.debug(str(e), exc_info=True)
                return ExecutionResult(
                    ok=True,
                    payload={
                        "execution_id": run_id,
                        "run_id": run_id,
                        "status": "queued",
                        "queued": True,
                        "queue_mode": str(queue_mode) if queue_mode else "collect",
                    },
                    run_id=run_id,
                )

        # ── Stream mode: return run_id immediately, execute in background ──
        stream_mode = False
        try:
            if isinstance(request.payload, dict):
                opts = request.payload.get("options", {}) if isinstance(request.payload.get("options"), dict) else {}
                stream_mode = str(opts.get("stream", "")).lower() in ("1", "true", "yes")
        except Exception as e:
            logging.debug(str(e), exc_info=True)
        if stream_mode:
            asyncio.create_task(self._execute_stream_background(request))
            return ExecutionResult(
                ok=True,
                run_id=run_id,
                payload={"run_id": run_id, "status": "running", "stream": True},
            )

        # Best-effort cancellation: if a cancel was requested before execution starts, abort early.
        try:
            if store is not None and await store.is_cancel_requested(run_id=run_id):  # type: ignore[arg-type]
                try:
                    await store.append_run_event(
                        run_id=run_id,
                        event_type="run_end",
                        trace_id=None,
                        tenant_id=str(tenant_id) if tenant_id is not None else None,
                        payload={"status": "cancelled", "reason": "cancel_requested"},
                    )
                except Exception as e:
                    logging.debug(str(e), exc_info=True)
                return ExecutionResult(
                    ok=False,
                    error="cancelled",
                    error_detail=self._error_detail("CANCELLED", "cancel_requested"),
                    http_status=409,
                    run_id=run_id,
                )
        except Exception as e:
            logging.debug(str(e), exc_info=True)

        try:
            if request.kind == "agent":
                return await self._execute_agent(request)
            if request.kind == "skill":
                return await self._execute_skill(request)
            if request.kind == "tool":
                return await self._execute_tool(request)
            if request.kind == "graph":
                return await self._execute_graph(request)
            if request.kind == "smoke_e2e":
                return await self._execute_smoke_e2e(request)
            if request.kind == "skill_lint_scan":
                return await self._execute_skill_lint_scan(request)
            if request.kind == "canary_web":
                return await self._execute_canary_web(request)
        finally:
            if lock_acquired and store is not None and session_id:
                try:
                    await store.release_session_lock(
                        tenant_id=str(tenant_id) if tenant_id is not None else None,
                        session_id=session_id,
                        run_id=run_id,
                    )
                except Exception as e:
                    logging.debug(str(e), exc_info=True)
                # Kick queue drain in background (best-effort)
                try:
                    self._kick_session_drain(tenant_id=str(tenant_id) if tenant_id is not None else None, session_id=session_id)
                except Exception as e:
                    logging.debug(str(e), exc_info=True)
        return ExecutionResult(
            ok=False,
            error=f"Unsupported kind: {request.kind}",
            error_detail=self._error_detail("UNSUPPORTED_KIND", f"Unsupported kind: {request.kind}"),
            http_status=400,
        )

    async def _execute_stream_background(self, request: ExecutionRequest) -> None:
        """Run execution in background for stream mode (returns run_id immediately)."""
        import time as _time
        run_id = request.run_id
        runtime = getattr(self, "_runtime", None)
        store = runtime.execution_store if runtime and hasattr(runtime, "execution_store") else None

        try:
            if store:
                await store.append_run_event(
                    run_id=run_id, event_type="run_start", trace_id=None, tenant_id=None,
                    payload={"kind": str(request.kind), "status": "running", "stream": True},
                )
        except Exception as e:
            logging.debug(str(e), exc_info=True)

        result = None
        try:
            if request.kind == "agent":
                result = await self._execute_agent(request)
            elif request.kind == "skill":
                result = await self._execute_skill(request)
            elif request.kind == "tool":
                result = await self._execute_tool(request)
            elif request.kind == "graph":
                result = await self._execute_graph(request)
            else:
                result = ExecutionResult(ok=False, error=f"Unsupported kind: {request.kind}", run_id=run_id)
        except Exception as e:
            result = ExecutionResult(ok=False, error=str(e), run_id=run_id)

        try:
            if store:
                await store.append_run_event(
                    run_id=run_id, event_type="run_end", trace_id=None, tenant_id=None,
                    payload={"status": "completed" if (result and result.ok) else "failed"},
                )
        except Exception as e:
            logging.debug(str(e), exc_info=True)

    async def _execute_skill_lint_scan(self, req: ExecutionRequest) -> ExecutionResult:
        """Scheduled lint scan over skills (workspace/engine), returns aggregated report."""
        from core.harness.kernel.types import ExecutionResult

        runtime = self._runtime
        if runtime is None or runtime.execution_store is None:
            return self._fail(code="NOT_INITIALIZED", message="ExecutionStore not initialized", http_status=503)

        payload = req.payload if isinstance(req.payload, dict) else {}
        run_id = str(getattr(req, "run_id", None) or "") or new_prefixed_id("run")

        trace_id = None
        if runtime.trace_service:
            try:
                trace = await runtime.trace_service.start_trace(
                    name="ops:skill_lint_scan",
                    attributes={
                        "run_id": run_id,
                        "kind": "skill_lint_scan",
                        "actor_id": payload.get("actor_id") or req.user_id,
                        "tenant_id": payload.get("tenant_id"),
                    },
                )
                trace_id = trace.trace_id
            except Exception:
                trace_id = None

        try:
            from core.harness.maintenance.skill_lint_scan import run_skill_lint_scan

            # Inject runtime IDs for alert/audit correlation (best-effort).
            try:
                payload = dict(payload) if isinstance(payload, dict) else {}
                payload.setdefault("trace_id", trace_id)
                payload.setdefault("run_id", run_id)
                ctx = payload.get("context") if isinstance(payload.get("context"), dict) else {}
                if isinstance(ctx, dict):
                    if ctx.get("job_id") and not payload.get("job_id"):
                        payload["job_id"] = ctx.get("job_id")
                    if ctx.get("job_run_id") and not payload.get("job_run_id"):
                        payload["job_run_id"] = ctx.get("job_run_id")
            except Exception:
                payload = req.payload if isinstance(req.payload, dict) else {}

            res = await run_skill_lint_scan(payload=payload, execution_store=runtime.execution_store)
            res = dict(res) if isinstance(res, dict) else {"ok": True, "status": "completed"}
            res.setdefault("trace_id", trace_id)
            res.setdefault("run_id", run_id)
            return ExecutionResult(ok=True, payload=res, trace_id=trace_id, run_id=run_id)
        except Exception as e:
            return self._fail(code="EXCEPTION", message=str(e), http_status=500, trace_id=trace_id, run_id=run_id)

    async def _execute_canary_web(self, req: ExecutionRequest) -> ExecutionResult:
        """
        P1-1 Canary (web): periodically run browser evidence + gates and persist artifacts.

        Intended to be triggered by Jobs/Cron with kind=canary_web.

        payload fields (subset):
          - project_id: str (recommended, enables baseline selection)
          - url: str (required)
          - steps: list[{tool,args,tag}] (optional)
          - expected_tags: list[str] (optional)
          - tag_expectations: dict (optional)
          - tag_template: str (optional)
          - enforce_gate: bool (default true)
          - base_evidence_pack_id: str (optional explicit baseline)
        """
        from core.harness.kernel.types import ExecutionResult

        runtime = self._runtime
        if runtime is None or runtime.execution_store is None:
            return self._fail(code="NOT_INITIALIZED", message="ExecutionStore not initialized", http_status=503)

        store = runtime.execution_store
        payload = req.payload if isinstance(req.payload, dict) else {}
        run_id = str(getattr(req, "run_id", None) or "") or new_prefixed_id("run")

        url = str(payload.get("url") or "").strip()
        if not url:
            return self._fail(code="INVALID_ARGUMENT", message="missing url", http_status=400, run_id=run_id)

        project_id = str(payload.get("project_id") or "").strip() or None
        candidate_id = str(payload.get("candidate_id") or "").strip() or None
        repo_change_id = str(payload.get("repo_change_id") or "").strip() or None
        steps = payload.get("steps") if isinstance(payload.get("steps"), list) else None
        expected_tags = payload.get("expected_tags") if isinstance(payload.get("expected_tags"), list) else None
        tag_expectations = payload.get("tag_expectations") if isinstance(payload.get("tag_expectations"), dict) else None
        tag_template = str(payload.get("tag_template") or "").strip() or None
        enforce_gate = bool(payload.get("enforce_gate", True))
        base_evidence_pack_id_req = str(payload.get("base_evidence_pack_id") or "").strip() or None

        trace_id = None
        if runtime.trace_service:
            try:
                trace = await runtime.trace_service.start_trace(
                    name=f"canary:web:{req.target_id}",
                    attributes={"run_id": run_id, "kind": "canary_web", "target_id": req.target_id, "project_id": project_id, "url": url},
                )
                trace_id = trace.trace_id
            except Exception:
                trace_id = None

        # run_start (so Runs/Links can see it; get_run_summary falls back to run_events)
        try:
            await store.append_run_event(
                run_id=run_id,
                event_type="run_start",
                trace_id=trace_id,
                tenant_id=None,
                payload={"kind": "canary_web", "status": "running", "request_payload": self._redact_request_payload(payload)},
            )
        except Exception as e:
            logging.debug(str(e), exc_info=True)

        # Load evaluation policy: system/default ⊕ project ⊕ request override (best-effort)
        evaluation_policy: Dict[str, Any] = {}
        try:
            from core.harness.evaluation.policy import DEFAULT_POLICY, merge_policy

            sys_obj = DEFAULT_POLICY
            try:
                sys_res = await store.list_learning_artifacts(target_type="system", target_id="default", kind="evaluation_policy", limit=5, offset=0)
                sys_items = (sys_res or {}).get("items") if isinstance(sys_res, dict) else None
                if isinstance(sys_items, list) and sys_items:
                    sys_items2 = sorted(sys_items, key=lambda x: float((x or {}).get("created_at") or 0), reverse=True)
                    p0 = (sys_items2[0] or {}).get("payload") if isinstance(sys_items2[0], dict) else None
                    if isinstance(p0, dict):
                        sys_obj = p0
            except Exception:
                sys_obj = DEFAULT_POLICY

            merged = dict(sys_obj)
            if project_id:
                try:
                    proj_res = await store.list_learning_artifacts(target_type="project", target_id=str(project_id), kind="evaluation_policy", limit=5, offset=0)
                    proj_items = (proj_res or {}).get("items") if isinstance(proj_res, dict) else None
                    if isinstance(proj_items, list) and proj_items:
                        proj_items2 = sorted(proj_items, key=lambda x: float((x or {}).get("created_at") or 0), reverse=True)
                        p1 = (proj_items2[0] or {}).get("payload") if isinstance(proj_items2[0], dict) else None
                        if isinstance(p1, dict):
                            merged = merge_policy(merged, p1)
                except Exception as e:
                    logging.debug(str(e), exc_info=True)
            # request override
            pol_override = payload.get("policy") if isinstance(payload.get("policy"), dict) else None
            if isinstance(pol_override, dict):
                merged = merge_policy(merged, pol_override)
            evaluation_policy = merged
        except Exception:
            evaluation_policy = {}

        # Apply tag template if provided or default (best-effort)
        try:
            pol = evaluation_policy if isinstance(evaluation_policy, dict) else {}
            templates = pol.get("tag_templates") if isinstance(pol.get("tag_templates"), dict) else {}
            tname = tag_template or str(pol.get("default_tag_template") or "").strip() or None
            if tname and isinstance(templates.get(tname), dict):
                tcfg = templates.get(tname) or {}
                if expected_tags is None and isinstance(tcfg.get("expected_tags"), list):
                    expected_tags = tcfg.get("expected_tags")
                if tag_expectations is None and isinstance(tcfg.get("tag_expectations"), dict):
                    tag_expectations = tcfg.get("tag_expectations")
                tag_template = tname
        except Exception as e:
            logging.debug(str(e), exc_info=True)

        # Build LLM adapter (same rules as auto-eval)
        provider = str(os.getenv("AIPLAT_AUTO_EVAL_LLM_PROVIDER") or os.getenv("LLM_PROVIDER") or "").strip().lower()  # noqa: env-legacy
        model = str(os.getenv("AIPLAT_AUTO_EVAL_LLM_MODEL") or os.getenv("LLM_MODEL") or "").strip()  # noqa: env-legacy
        api_key = get_llm_api_key(provider)
        base_url = get_llm_base_url(provider)
        try:
            from core.adapters.llm.base import create_adapter as _mk

            llm = _mk(provider=provider, api_key=api_key, model=model, base_url=base_url)
        except Exception as e:
            return self._fail(code="LLM_NOT_AVAILABLE", message=f"auto_eval_llm_not_available:{e}", http_status=503, trace_id=trace_id, run_id=run_id)

        from core.harness.evaluation.auto import build_auto_eval_prompt, parse_json_report, try_parse_json
        from core.harness.evaluation.workbench import EvaluatorThresholds, apply_threshold_gate

        # -------------------------
        # Browser evidence capture (best-effort)
        # -------------------------
        browser_evidence: Optional[Dict[str, Any]] = None
        evidence_capture_attempts = 0
        evidence_capture_error: Optional[str] = None

        cap = evaluation_policy.get("evidence_capture") if isinstance(evaluation_policy.get("evidence_capture"), dict) else {}
        try:
            max_retries = int(cap.get("max_retries", 1))
        except Exception:
            max_retries = 1
        max_retries = max(0, min(3, max_retries))
        attempts = 1 + max_retries

        try:
            reg = _resolve_tool_registry()

            def _get(name: str):
                t = reg.get(name) if hasattr(reg, "get") else None
                if t is None:
                    try:
                        t = reg.get_tool(name)
                    except Exception:
                        t = None
                return t

            async def _call(tool_full_name: str, args: Dict[str, Any]) -> Any:
                tool_obj = _get(tool_full_name)
                if tool_obj is None:
                    raise RuntimeError(f"missing_tool:{tool_full_name}")
                res0 = await sys_tool_call(
                    tool_obj,
                    args,
                    user_id=str(getattr(req, "user_id", None) or "system"),
                    session_id=str(getattr(req, "session_id", None) or "default"),
                    trace_context={"trace_id": trace_id, "run_id": run_id, "tenant_id": project_id},
                )
                if getattr(res0, "error", None) == "approval_required":
                    meta0 = getattr(res0, "metadata", {}) or {}
                    raise RuntimeError(f"approval_required:{meta0}")
                if getattr(res0, "error", None) in {"policy_denied", "toolset_denied"}:
                    meta0 = getattr(res0, "metadata", {}) or {}
                    raise RuntimeError(f"policy_denied:{meta0}")
                if not bool(getattr(res0, "success", True)):
                    raise RuntimeError(getattr(res0, "error", None) or "browser_tool_failed")
                return getattr(res0, "output", None)

            async def _collect_once() -> Dict[str, Any]:
                be: Dict[str, Any] = {
                    "url": url,
                    "steps": [],
                    "coverage": {"executed_tags": [], "expected_tags": expected_tags or []},
                    "by_tag": {},
                }
                _tag_started_at: Dict[str, float] = {}
                _active_tag: Optional[str] = None

                async def _capture_tag(tag: str) -> None:
                    by_tag = be.get("by_tag")
                    if not isinstance(by_tag, dict):
                        by_tag = {}
                        be["by_tag"] = by_tag
                    t0 = str(tag or "").strip()
                    if not t0:
                        return
                    started = _tag_started_at.get(t0)
                    dur_ms = (time.time() - started) * 1000.0 if started else None
                    try:
                        snap0 = await _call("mcp.integrated_browser.browser_snapshot", {})
                    except Exception:
                        snap0 = None
                    try:
                        con0 = await _call("mcp.integrated_browser.browser_console_messages", {})
                    except Exception:
                        con0 = None
                    try:
                        net0 = await _call("mcp.integrated_browser.browser_network_requests", {})
                    except Exception:
                        net0 = None
                    try:
                        shot0 = await _call("mcp.integrated_browser.browser_take_screenshot", {})
                    except Exception:
                        shot0 = None
                    by_tag[t0] = {
                        "snapshot": try_parse_json(snap0),
                        "console_messages": try_parse_json(con0),
                        "network_requests": try_parse_json(net0),
                        "screenshot": try_parse_json(shot0),
                        "duration_ms": dur_ms,
                    }

                await _call("mcp.integrated_browser.browser_navigate", {"url": url})
                be["steps"].append({"tool": "browser_navigate", "ok": True, "tag": "navigate"})
                be["coverage"]["executed_tags"].append("navigate")
                try:
                    out0 = await _call("mcp.integrated_browser.browser_wait_for", {"timeoutMs": 1500})
                    be["steps"].append({"tool": "browser_wait_for", "output": try_parse_json(out0), "tag": "wait_for"})
                    be["coverage"]["executed_tags"].append("wait_for")
                except Exception as e:
                    logging.debug(str(e), exc_info=True)
                try:
                    snap = await _call("mcp.integrated_browser.browser_snapshot", {})
                    be["snapshot"] = try_parse_json(snap)
                    be["coverage"]["executed_tags"].append("snapshot")
                except Exception as e:
                    logging.debug(str(e), exc_info=True)
                try:
                    shot = await _call("mcp.integrated_browser.browser_take_screenshot", {})
                    be["screenshot"] = try_parse_json(shot)
                    be["coverage"]["executed_tags"].append("screenshot")
                except Exception as e:
                    logging.debug(str(e), exc_info=True)
                try:
                    con = await _call("mcp.integrated_browser.browser_console_messages", {})
                    be["console_messages"] = try_parse_json(con)
                    be["coverage"]["executed_tags"].append("console")
                except Exception as e:
                    logging.debug(str(e), exc_info=True)
                try:
                    net = await _call("mcp.integrated_browser.browser_network_requests", {})
                    be["network_requests"] = try_parse_json(net)
                    be["coverage"]["executed_tags"].append("network")
                except Exception as e:
                    logging.debug(str(e), exc_info=True)

                # Optional steps with tags
                if steps:
                    for st in steps[:50]:
                        if not isinstance(st, dict):
                            continue
                        tname = str(st.get("tool") or "").strip()
                        args = st.get("args") if isinstance(st.get("args"), dict) else {}
                        tag = str(st.get("tag") or "").strip() or None
                        if tname not in {"browser_click", "browser_type", "browser_scroll", "browser_wait_for"}:
                            continue
                        if tag and tag != _active_tag:
                            if _active_tag:
                                try:
                                    await _capture_tag(_active_tag)
                                except Exception as e:
                                    logging.debug(str(e), exc_info=True)
                            _active_tag = tag
                            _tag_started_at.setdefault(tag, time.time())
                        out = await _call(f"mcp.integrated_browser.{tname}", args)
                        be["steps"].append({"tool": tname, "args": args, "output": try_parse_json(out), "tag": tag})
                        if tag:
                            be["coverage"]["executed_tags"].append(tag)
                    if _active_tag:
                        try:
                            await _capture_tag(_active_tag)
                        except Exception as e:
                            logging.debug(str(e), exc_info=True)
                return be

            for i in range(attempts):
                evidence_capture_attempts = i + 1
                try:
                    browser_evidence = await _collect_once()
                    evidence_capture_error = None
                    break
                except Exception as e:
                    evidence_capture_error = str(e)
                    browser_evidence = None
                    if i < attempts - 1:
                        continue
                    browser_evidence = {"url": url, "error": evidence_capture_error, "attempts": evidence_capture_attempts}
        except Exception as e:
            browser_evidence = {"url": url, "error": str(e), "attempts": evidence_capture_attempts or 1}

        # Normalize coverage for deterministic gates
        try:
            if isinstance(browser_evidence, dict):
                from core.harness.evaluation.coverage_gate import unique_preserve_order, evaluate_coverage

                cov = browser_evidence.get("coverage")
                if not isinstance(cov, dict):
                    cov = {}
                    browser_evidence["coverage"] = cov
                cov["executed_tags"] = unique_preserve_order([str(x) for x in (cov.get("executed_tags") or []) if str(x).strip()])
                cov["expected_tags"] = unique_preserve_order([str(x) for x in (cov.get("expected_tags") or []) if str(x).strip()])
                ok_cov, missing = evaluate_coverage(cov.get("expected_tags"), cov.get("executed_tags"))
                cov["missing_expected_tags"] = missing
                cov["ok"] = bool(ok_cov)
        except Exception as e:
            logging.debug(str(e), exc_info=True)

        # Persist evidence_pack artifact as run-scoped (so existing UI works)
        from core.learning.manager import LearningManager
        from core.learning.types import LearningArtifactKind

        mgr = LearningManager(execution_store=store)
        evidence_pack_id = None
        evidence_diff_id = None
        evidence_diff = None

        try:
            art = await mgr.create_artifact(
                kind=LearningArtifactKind.EVIDENCE_PACK,
                target_type="run",
                target_id=run_id,
                version=f"evidence_pack:{int(time.time())}",
                status="draft",
                payload=browser_evidence if isinstance(browser_evidence, dict) else {},
                metadata={
                    "source": "canary_web",
                    "canary_id": str(req.target_id),
                    "project_id": project_id,
                    "url": url,
                    "evidence_capture_attempts": evidence_capture_attempts,
                    "evidence_capture_error": evidence_capture_error,
                },
                trace_id=trace_id,
                run_id=run_id,
            )
            evidence_pack_id = getattr(art, "artifact_id", None)
            if isinstance(browser_evidence, dict) and evidence_pack_id:
                browser_evidence["evidence_pack_id"] = evidence_pack_id
        except Exception:
            evidence_pack_id = None

        # evidence diff baseline selection (same as auto-eval)
        try:
            if evidence_pack_id and isinstance(browser_evidence, dict):
                base_artifact_id = None
                base_payload = None

                # (1) explicit baseline
                if base_evidence_pack_id_req:
                    base_it = await store.get_learning_artifact(base_evidence_pack_id_req)
                    if isinstance(base_it, dict) and isinstance(base_it.get("payload"), dict):
                        base_artifact_id = str(base_it.get("artifact_id"))
                        base_payload = dict(base_it.get("payload") or {})

                # (2) latest PASS evaluation_report under same project_id -> evidence_pack_id
                if not base_payload and project_id:
                    marker = f"\"project_id\": \"{project_id}\""
                    rep_res = await store.list_learning_artifacts(kind="evaluation_report", metadata_contains=marker, limit=50, offset=0)
                    rep_items = (rep_res or {}).get("items") if isinstance(rep_res, dict) else None
                    if isinstance(rep_items, list):
                        rep2 = sorted(rep_items, key=lambda x: float((x or {}).get("created_at") or 0), reverse=True)
                        for it in rep2:
                            p = (it or {}).get("payload") if isinstance(it, dict) else None
                            if not isinstance(p, dict) or not bool(p.get("pass")):
                                continue
                            eid = p.get("evidence_pack_id")
                            if not eid or str(eid) == str(evidence_pack_id):
                                continue
                            base_it = await store.get_learning_artifact(str(eid))
                            if isinstance(base_it, dict) and isinstance(base_it.get("payload"), dict):
                                base_artifact_id = str(base_it.get("artifact_id"))
                                base_payload = dict(base_it.get("payload") or {})
                                break

                # (3) fallback: previous evidence_pack of this canary (by metadata canary_id)
                if not base_payload:
                    marker = f"\"canary_id\": \"{str(req.target_id)}\""
                    prev_res = await store.list_learning_artifacts(kind="evidence_pack", metadata_contains=marker, limit=10, offset=0)
                    prev_items = (prev_res or {}).get("items") if isinstance(prev_res, dict) else None
                    if isinstance(prev_items, list) and len(prev_items) >= 2:
                        prev2 = sorted(prev_items, key=lambda x: float((x or {}).get("created_at") or 0), reverse=True)
                        bp = (prev2[1] or {}).get("payload") if isinstance(prev2[1], dict) else None
                        if isinstance(bp, dict):
                            base_artifact_id = str((prev2[1] or {}).get("artifact_id"))
                            base_payload = dict(bp)

                if isinstance(base_payload, dict) and base_artifact_id:
                    base_payload.setdefault("evidence_pack_id", base_artifact_id)
                    browser_evidence.setdefault("evidence_pack_id", evidence_pack_id)
                    from core.harness.evaluation.evidence_diff import compute_evidence_diff

                    evidence_diff = compute_evidence_diff(base_payload, browser_evidence)
                    art2 = await mgr.create_artifact(
                        kind=LearningArtifactKind.EVIDENCE_DIFF,
                        target_type="run",
                        target_id=run_id,
                        version=f"evidence_diff:{int(time.time())}",
                        status="draft",
                        payload=evidence_diff,
                        metadata={"source": "canary_web", "project_id": project_id, "base_evidence_pack_id": str(base_artifact_id), "new_evidence_pack_id": str(evidence_pack_id)},
                        trace_id=trace_id,
                        run_id=run_id,
                    )
                    evidence_diff_id = getattr(art2, "artifact_id", None)
        except Exception:
            evidence_diff_id = None
            evidence_diff = None

        # Build prompt and evaluate using same gates
        extra = {
            "source": "canary_web",
            "canary_id": str(req.target_id),
            "project_id": project_id,
            "url": url,
            "tag_template": tag_template,
            "evaluation_policy": evaluation_policy,
            "evidence_pack_id": evidence_pack_id,
            "evidence_diff_id": evidence_diff_id,
            "evidence_diff_summary": (evidence_diff or {}).get("summary") if isinstance(evidence_diff, dict) else None,
        }
        fake_run = {"id": run_id, "run_id": run_id, "trace_id": trace_id, "status": "completed", "task": f"canary_web:{req.target_id}"}
        msgs = build_auto_eval_prompt(run=fake_run, events=[], extra=extra, browser_evidence=browser_evidence if isinstance(browser_evidence, dict) else None)
        try:
            from core.harness.syscalls.llm import sys_llm_generate
            resp = await sys_llm_generate(llm, msgs, temperature=0.0, trace_context={"trace_id": trace_id, "run_id": run_id})
            text = getattr(resp, "content", "") or ""
        except Exception as e:
            return self._fail(code="AUTO_EVAL_FAILED", message=f"auto_eval_failed:{e}", http_status=500, trace_id=trace_id, run_id=run_id)

        report, why = parse_json_report(text)
        if report is None:
            from core.harness.evaluation.dimensions import build_default_score_schema
            report = {
                "pass": False,
                "score": build_default_score_schema(),
                "issues": [{"severity": "P0", "title": "自动评估输出无法解析为 JSON", "expected": "LLM 输出符合约定 JSON 报告格式", "actual": f"{why}: {text[:800]}", "repro_steps": []}],
                "positive_notes": [],
                "next_actions_for_generator": [],
            }

        # attach evidence references
        try:
            if isinstance(report, dict) and evidence_pack_id:
                report.setdefault("evidence_pack_id", evidence_pack_id)
            if isinstance(report, dict) and evidence_diff_id:
                report.setdefault("evidence_diff_id", evidence_diff_id)
                if isinstance(evidence_diff, dict):
                    report.setdefault("evidence_diff_summary", evidence_diff.get("summary"))
        except Exception as e:
            logging.debug(str(e), exc_info=True)

        thresholds0 = evaluation_policy.get("thresholds") if isinstance(evaluation_policy.get("thresholds"), dict) else {}
        thresholds = EvaluatorThresholds.from_dict(thresholds0)
        gated_report = apply_threshold_gate(report, thresholds)
        # stamp identity
        try:
            gated_report.setdefault("project_id", project_id)
            gated_report.setdefault("url", url)
            gated_report.setdefault("canary_id", str(req.target_id))
            if base_evidence_pack_id_req:
                gated_report.setdefault("base_evidence_pack_id", base_evidence_pack_id_req)
        except Exception as e:
            logging.debug(str(e), exc_info=True)

        # Coverage gate + tag assertions + regression gate (reuse server helpers)
        try:
            if isinstance(browser_evidence, dict):
                from core.harness.evaluation.coverage_gate import evaluate_coverage

                exp = (browser_evidence.get("coverage") or {}).get("expected_tags") if isinstance(browser_evidence.get("coverage"), dict) else None
                if not exp:
                    gate0 = evaluation_policy.get("regression_gate") if isinstance(evaluation_policy.get("regression_gate"), dict) else {}
                    exp = gate0.get("required_tags") if isinstance(gate0.get("required_tags"), list) else None
                executed = (browser_evidence.get("coverage") or {}).get("executed_tags") if isinstance(browser_evidence.get("coverage"), dict) else None
                ok_cov, missing = evaluate_coverage(exp, executed)
                gated_report.setdefault("coverage", {})
                gated_report["coverage"]["expected_tags"] = exp or []
                gated_report["coverage"]["executed_tags"] = executed or []
                gated_report["coverage"]["missing_expected_tags"] = missing
                if (exp or []) and (not ok_cov):
                    gated_report["pass"] = False
                    gated_report.setdefault("issues", [])
                    if isinstance(gated_report.get("issues"), list):
                        gated_report["issues"].insert(
                            0,
                            {
                                "severity": "P0",
                                "title": "关键路径覆盖不足（Coverage Gate）",
                                "expected": {"expected_tags": exp},
                                "actual": {"missing_expected_tags": missing},
                                "repro_steps": [],
                                "evidence": {"evidence_pack_id": evidence_pack_id},
                                "suggested_fix": "补齐 steps[] 的 tag 或调整 expected/required tags。",
                            },
                        )
        except Exception as e:
            logging.debug(str(e), exc_info=True)

        try:
            if isinstance(browser_evidence, dict) and isinstance(tag_expectations, dict) and tag_expectations:
                from core.harness.evaluation.tag_assertions import evaluate_tag_assertions_with_stats

                ok, failures, stats = evaluate_tag_assertions_with_stats(browser_evidence, tag_expectations)
                gated_report.setdefault("assertions", {})
                gated_report["assertions"]["tag_expectations"] = tag_expectations
                gated_report["assertions"]["tag_failures"] = failures
                gated_report["assertions"]["tag_stats"] = stats
                if not ok:
                    gated_report["pass"] = False
        except Exception as e:
            logging.debug(str(e), exc_info=True)

        try:
            gate = evaluation_policy.get("regression_gate") if isinstance(evaluation_policy.get("regression_gate"), dict) else None
            if gate and isinstance(evidence_diff, dict):
                from core.harness.evaluation.evidence_diff import evaluate_regression

                executed_tags = None
                cov = browser_evidence.get("coverage") if isinstance(browser_evidence, dict) else None
                if isinstance(cov, dict) and isinstance(cov.get("executed_tags"), list):
                    executed_tags = cov.get("executed_tags")
                is_reg, reasons = evaluate_regression(evidence_diff, gate, executed_tags=executed_tags)
                gated_report["regression"] = {"is_regression": is_reg, "reasons": reasons, "gate": gate, "evidence_diff_id": evidence_diff_id}
                if is_reg:
                    gated_report["pass"] = False
        except Exception as e:
            logging.debug(str(e), exc_info=True)

        # persist evaluation_report + canary_report
        eval_artifact_id = None
        try:
            art3 = await mgr.create_artifact(
                kind=LearningArtifactKind.EVALUATION_REPORT,
                target_type="run",
                target_id=run_id,
                version=f"eval:{int(time.time())}",
                status="draft",
                payload=gated_report if isinstance(gated_report, dict) else {},
                metadata={"source": "canary_web", "canary_id": str(req.target_id), "project_id": project_id, "url": url, "pass": bool((gated_report or {}).get("pass"))},
                trace_id=trace_id,
                run_id=run_id,
            )
            eval_artifact_id = getattr(art3, "artifact_id", None)
        except Exception:
            eval_artifact_id = None

        canary_report_id = None
        try:
            art_canary = await mgr.create_artifact(
                kind=LearningArtifactKind.CANARY_REPORT,
                target_type="canary",
                target_id=str(req.target_id),
                version=f"canary:{int(time.time())}",
                status="draft",
                payload={
                    "schema_version": "0.1",
                    "canary_id": str(req.target_id),
                    "run_id": run_id,
                    "trace_id": trace_id,
                    "project_id": project_id,
                    "url": url,
                    "pass": bool((gated_report or {}).get("pass")),
                    "status": "completed" if bool((gated_report or {}).get("pass")) else "failed",
                    "evaluation_report_id": eval_artifact_id,
                    "evidence_pack_id": evidence_pack_id,
                    "evidence_diff_id": evidence_diff_id,
                },
                metadata={"source": "canary_web"},
                trace_id=trace_id,
                run_id=run_id,
            )
            canary_report_id = getattr(art_canary, "artifact_id", None)
        except Exception as e:
            logging.debug(str(e), exc_info=True)

        status = "completed" if bool((gated_report or {}).get("pass")) else "failed"

        # Escalate canary failures into Change Control (syscall_events kind=changeset)
        try:
            if status != "completed":
                canary_cfg = evaluation_policy.get("canary") if isinstance(evaluation_policy.get("canary"), dict) else {}
                esc = canary_cfg.get("escalate") if isinstance(canary_cfg.get("escalate"), dict) else {}
                enabled = bool(esc.get("enabled", True))
                p0_only = bool(esc.get("p0_only", True))
                try:
                    consecutive_failures_threshold = int(esc.get("consecutive_failures", 2))
                except Exception:
                    consecutive_failures_threshold = 2
                consecutive_failures_threshold = max(1, min(10, consecutive_failures_threshold))

                # Load recent canary reports (newest-first) to compute consecutive failures.
                recent_payloads: List[Dict[str, Any]] = []
                try:
                    rr = await store.list_learning_artifacts(
                        target_type="canary",
                        target_id=str(req.target_id),
                        kind="canary_report",
                        limit=consecutive_failures_threshold + 5,
                        offset=0,
                    )
                    items = (rr or {}).get("items") if isinstance(rr, dict) else None
                    if isinstance(items, list):
                        items2 = sorted(items, key=lambda x: float((x or {}).get("created_at") or 0), reverse=True)
                        for it in items2[:50]:
                            p = (it or {}).get("payload") if isinstance(it, dict) else None
                            if isinstance(p, dict):
                                recent_payloads.append(p)
                except Exception:
                    recent_payloads = []

                from core.harness.canary.escalation import (
                    change_id_for_canary,
                    consecutive_failures_from_reports,
                    should_escalate,
                )

                streak = consecutive_failures_from_reports(recent_payloads)
                # gated_report is the "new report" for P0 detection
                if should_escalate(
                    enabled=enabled,
                    p0_only=p0_only,
                    consecutive_failures_threshold=consecutive_failures_threshold,
                    new_report=gated_report if isinstance(gated_report, dict) else {},
                    new_consecutive_failures=streak,
                ):
                    change_id = change_id_for_canary(str(req.target_id))
                    from core.harness.canary.recommendation import recommend_action

                    action, action_reason = recommend_action(gated_report if isinstance(gated_report, dict) else {})
                    approval_rc_id = None
                    approval_repo_id = None

                    # When action=block, create approval requests to connect canary to:
                    # - release_candidate (candidate_id)
                    # - repo_changeset (repo_change_id)
                    if action == "block":
                        now_ts = time.time()

                        async def _create_approval(operation: str, details: str, meta: Dict[str, Any]) -> str:
                            rid0 = new_prefixed_id("apr")
                            await store.upsert_approval_request(
                                {
                                    "request_id": rid0,
                                    "user_id": str(getattr(req, "user_id", None) or "system"),
                                    "operation": operation,
                                    "details": details,
                                    "rule_id": "canary_block",
                                    "rule_type": "sensitive_operation",
                                    "status": "pending",
                                    "created_at": now_ts,
                                    "updated_at": now_ts,
                                    "metadata": meta,
                                    "tenant_id": str(project_id) if project_id else None,
                                    "actor_id": str(getattr(req, "user_id", None) or "system"),
                                    "actor_role": "system",
                                    "session_id": str(getattr(req, "session_id", None) or "default"),
                                    "run_id": run_id,
                                }
                            )
                            return rid0

                        base_meta = {
                            "kind": "canary_block",
                            "source": "canary_web",
                            "canary_id": str(req.target_id),
                            "project_id": project_id,
                            "url": url,
                            "run_id": run_id,
                            "trace_id": trace_id,
                            "canary_report_id": canary_report_id,
                            "evaluation_report_id": eval_artifact_id,
                            "evidence_pack_id": evidence_pack_id,
                            "evidence_diff_id": evidence_diff_id,
                            "recommendation": {"action": action, "reason": action_reason},
                            "change_id": change_id,
                        }
                        if candidate_id:
                            approval_rc_id = await _create_approval(
                                "canary:block_release_candidate",
                                f"canary block: {action_reason}",
                                {**base_meta, "candidate_id": candidate_id},
                            )
                        if repo_change_id:
                            approval_repo_id = await _create_approval(
                                "canary:block_repo_changeset",
                                f"canary block: {action_reason}",
                                {**base_meta, "repo_change_id": repo_change_id},
                            )
                    await store.add_syscall_event(
                        {
                            "trace_id": trace_id,
                            "run_id": run_id,
                            "kind": "changeset",
                            "name": "canary_escalate",
                            "status": "failed",
                            "args": {
                                "source": "canary_web",
                                "canary_id": str(req.target_id),
                                "project_id": project_id,
                                "url": url,
                                "consecutive_failures": streak,
                                "threshold": consecutive_failures_threshold,
                                "p0_only": p0_only,
                            },
                            "result": {
                                "canary_report_id": canary_report_id,
                                "evaluation_report_id": eval_artifact_id,
                                "evidence_pack_id": evidence_pack_id,
                                "evidence_diff_id": evidence_diff_id,
                                "pass": bool((gated_report or {}).get("pass")),
                                "summary": (evidence_diff or {}).get("summary") if isinstance(evidence_diff, dict) else None,
                                "recommendation": {"action": action, "reason": action_reason},
                                "approval_request_ids": {"release_candidate": approval_rc_id, "repo_changeset": approval_repo_id},
                            },
                            "target_type": "change",
                            "target_id": change_id,
                            "approval_request_id": approval_rc_id or approval_repo_id,
                            "user_id": str(getattr(req, "user_id", None) or "system"),
                            "session_id": str(getattr(req, "session_id", None) or "default"),
                            "tenant_id": str(project_id) if project_id else None,
                        }
                    )

                    # Link into repo change-control stream (if provided)
                    if approval_repo_id and repo_change_id:
                        try:
                            await store.add_syscall_event(
                                {
                                    "trace_id": trace_id,
                                    "run_id": run_id,
                                    "kind": "changeset",
                                    "name": "canary_block_repo_changeset",
                                    "status": "approval_required",
                                    "args": {"source": "canary_web", "canary_id": str(req.target_id), "repo_change_id": repo_change_id},
                                    "result": {"approval_request_id": approval_repo_id, "canary_change_id": change_id, "canary_report_id": canary_report_id},
                                    "target_type": "change",
                                    "target_id": str(repo_change_id),
                                    "approval_request_id": approval_repo_id,
                                    "user_id": str(getattr(req, "user_id", None) or "system"),
                                    "session_id": str(getattr(req, "session_id", None) or "default"),
                                    "tenant_id": str(project_id) if project_id else None,
                                }
                            )
                        except Exception as e:
                            logging.debug(str(e), exc_info=True)

                    # Link into release-candidate change-control stream (if provided)
                    if approval_rc_id and candidate_id:
                        try:
                            from core.harness.canary.escalation import change_id_for_release_candidate

                            rc_change_id = change_id_for_release_candidate(candidate_id)
                            await store.add_syscall_event(
                                {
                                    "trace_id": trace_id,
                                    "run_id": run_id,
                                    "kind": "changeset",
                                    "name": "canary_block_release_candidate",
                                    "status": "approval_required",
                                    "args": {"source": "canary_web", "canary_id": str(req.target_id), "candidate_id": candidate_id},
                                    "result": {"approval_request_id": approval_rc_id, "canary_change_id": change_id, "canary_report_id": canary_report_id},
                                    "target_type": "change",
                                    "target_id": rc_change_id,
                                    "approval_request_id": approval_rc_id,
                                    "user_id": str(getattr(req, "user_id", None) or "system"),
                                    "session_id": str(getattr(req, "session_id", None) or "default"),
                                    "tenant_id": str(project_id) if project_id else None,
                                }
                            )
                        except Exception as e:
                            logging.debug(str(e), exc_info=True)
        except Exception as e:
            logging.debug(str(e), exc_info=True)
        try:
            await store.append_run_event(run_id=run_id, event_type="run_end", trace_id=trace_id, tenant_id=None, payload={"kind": "canary_web", "status": status, "evaluation_report_id": eval_artifact_id})
        except Exception:
            logging.warning("run_end event append failed for canary_web", exc_info=True)

        # Finish trace
        if runtime.trace_service and trace_id:
            try:
                from core.services.trace_service import SpanStatus

                await runtime.trace_service.end_trace(trace_id, status=SpanStatus.SUCCESS if status == "completed" else SpanStatus.ERROR)
            except Exception as e:
                logging.debug(str(e), exc_info=True)

        if enforce_gate and status != "completed":
            return ExecutionResult(ok=False, error="canary_failed", payload={"run_id": run_id, "status": status, "artifact_id": eval_artifact_id, "report": gated_report}, trace_id=trace_id, run_id=run_id)
        return ExecutionResult(ok=True, payload={"run_id": run_id, "status": status, "artifact_id": eval_artifact_id, "report": gated_report}, trace_id=trace_id, run_id=run_id)

    def _redact_request_payload(self, payload: Any) -> Any:
        """
        Best-effort redaction for storing request payload in run_events (for retry/debug).
        """
        sensitive_keys = {"api_key", "token", "access_token", "refresh_token", "secret", "password"}

        def _walk(x: Any, depth: int = 0) -> Any:
            if depth > 4:
                return "..."
            if isinstance(x, dict):
                out: Dict[str, Any] = {}
                for k, v in x.items():
                    ks = str(k).lower()
                    if ks in sensitive_keys or "secret" in ks or "token" in ks or "password" in ks or "api_key" in ks:
                        out[k] = "***"
                    else:
                        out[k] = _walk(v, depth + 1)
                return out
            if isinstance(x, list):
                return [_walk(v, depth + 1) for v in x[:50]]
            if isinstance(x, str):
                s = x
                if len(s) > 2000:
                    return s[:2000] + "…"
                return s
            return x

        try:
            return _walk(payload, 0)
        except Exception:
            return {}

    def _kick_session_drain(self, *, tenant_id: Optional[str], session_id: str) -> None:
        key = f"{tenant_id or ''}::{session_id}"
        if key in self._session_drain_inflight:
            return
        self._session_drain_inflight.add(key)

        async def _runner():
            try:
                await self._drain_session_queue(tenant_id=tenant_id, session_id=session_id)
            finally:
                try:
                    self._session_drain_inflight.discard(key)
                except Exception as e:
                    logging.debug(str(e), exc_info=True)

        asyncio.create_task(_runner())

    async def _drain_session_queue(self, *, tenant_id: Optional[str], session_id: str) -> None:
        runtime = getattr(self, "_runtime", None)
        store = getattr(runtime, "execution_store", None) if runtime else None
        if store is None:
            return
        while True:
            item = None
            try:
                item = await store.dequeue_session_run(tenant_id=tenant_id, session_id=session_id)
            except Exception:
                item = None
            if not item:
                return
            run_id = str(item.get("run_id") or "") or new_prefixed_id("run")
            try:
                await store.append_run_event(
                    run_id=run_id,
                    event_type="dequeued",
                    trace_id=None,
                    tenant_id=str(tenant_id) if tenant_id is not None else None,
                    payload={"session_id": session_id, "kind": item.get("kind"), "target_id": item.get("target_id")},
                )
            except Exception as e:
                logging.debug(str(e), exc_info=True)
            try:
                from core.harness.kernel.types import ExecutionRequest

                req = ExecutionRequest(
                    kind=str(item.get("kind") or "agent"),  # type: ignore[arg-type]
                    target_id=str(item.get("target_id") or ""),
                    payload=item.get("payload") if isinstance(item.get("payload"), dict) else {},
                    user_id=str(item.get("user_id") or "system"),
                    session_id=str(item.get("session_id") or session_id),
                    run_id=run_id,
                )
                if req.target_id:
                    await self.execute(req)
            except Exception as e:
                # best-effort: swallow to continue draining other sessions
                logging.debug(str(e), exc_info=True)

    # -----------------------------
    # Roadmap-0: error normalization
    # -----------------------------
    def _error_detail(self, code: str, message: str, *, extra: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        d: Dict[str, Any] = {"code": code, "message": message}
        if isinstance(extra, dict) and extra:
            d["extra"] = extra
        return d

    def _fail(
        self,
        *,
        code: str,
        message: str,
        http_status: int,
        trace_id: Optional[str] = None,
        run_id: Optional[str] = None,
    ) -> ExecutionResult:
        """Create a standardized failure ExecutionResult (Roadmap-0)."""
        return ExecutionResult(
            ok=False,
            error=message,
            error_detail=self._error_detail(code, message),
            http_status=http_status,
            trace_id=trace_id,
            run_id=run_id,
        )

    def _normalize_error(
        self,
        *,
        error: Optional[str],
        metadata: Optional[Dict[str, Any]] = None,
        fallback_message: str = "Execution failed",
    ) -> Optional[Dict[str, Any]]:
        """
        Normalize internal error strings into a stable {code,message} object.

        Backward compatible:
        - Callers still receive the legacy `error: str | null`
        - New field is exposed as `error_detail`
        """
        if not error:
            return None
        meta = metadata or {}
        err = str(error)

        # Prefer human-readable reason when available (toolset/policy denials).
        reason = None
        try:
            if isinstance(meta.get("reason"), str):
                reason = meta.get("reason")
            if isinstance(meta.get("policy"), dict) and isinstance(meta["policy"].get("reason"), str):
                reason = meta["policy"].get("reason")
        except Exception:
            reason = None

        if err == "toolset_denied":
            return self._error_detail("TOOLSET_DENIED", reason or fallback_message, extra={"error": err})
        if err == "policy_denied":
            approval_request_id = None
            try:
                if isinstance(meta.get("approval_request_id"), str):
                    approval_request_id = meta.get("approval_request_id")
                if isinstance(meta.get("policy"), dict) and isinstance(meta["policy"].get("approval_request_id"), str):
                    approval_request_id = meta["policy"].get("approval_request_id")
            except Exception:
                approval_request_id = None
            extra = {"error": err}
            if approval_request_id:
                extra["approval_request_id"] = str(approval_request_id)
            return self._error_detail("POLICY_DENIED", reason or fallback_message, extra=extra)
        if err == "approval_required":
            approval_request_id = None
            try:
                if isinstance(meta.get("approval_request_id"), str):
                    approval_request_id = meta.get("approval_request_id")
                if isinstance(meta.get("policy"), dict) and isinstance(meta["policy"].get("approval_request_id"), str):
                    approval_request_id = meta["policy"].get("approval_request_id")
            except Exception:
                approval_request_id = None
            extra = {"error": err}
            if approval_request_id:
                extra["approval_request_id"] = str(approval_request_id)
            return self._error_detail("APPROVAL_REQUIRED", reason or "需要审批", extra=extra)
        if err == "quota_exceeded":
            return self._error_detail("QUOTA_EXCEEDED", reason or "超出配额", extra={"error": err})

        if "timeout" in err.lower():
            return self._error_detail("TIMEOUT", err, extra={"error": err})
        if "no model" in err.lower() or ("model" in err.lower() and "available" in err.lower()):
            return self._error_detail("NO_MODEL", err, extra={"error": err})

        return self._error_detail("EXCEPTION", err or fallback_message, extra={"error": err})

    async def _execute_agent(self, req: ExecutionRequest) -> ExecutionResult:
        from core.harness.integration.agent import _execute_agent_impl
        return await _execute_agent_impl(self, req)

    async def _execute_skill(self, req: ExecutionRequest) -> ExecutionResult:
        from core.harness.integration.skill import _execute_skill_impl
        return await _execute_skill_impl(self, req)

    async def _execute_tool(self, req: ExecutionRequest) -> ExecutionResult:
        from core.harness.integration.tool import _execute_tool_impl
        return await _execute_tool_impl(self, req)

    async def _execute_graph(self, req: ExecutionRequest) -> ExecutionResult:
        from core.harness.integration.graph import _execute_graph_impl
        return await _execute_graph_impl(self, req)

    async def _execute_smoke_e2e(self, req: ExecutionRequest) -> ExecutionResult:
        from core.harness.integration.graph import _execute_smoke_e2e_impl
        return await _execute_smoke_e2e_impl(self, req)

    @staticmethod
    def _infer_default_repo_root() -> Optional[str]:
        """
        Best-effort repo_root inference when caller did not provide one.

        Motivation:
        - Allow server-side injection/enforcement of project-level CLAUDE.md rules
          even when the client does not pass repo_root.

        Resolution order:
        1) env AIPLAT_DEFAULT_REPO_ROOT
        2) workspace root (parent of aiPlat-core repo) if it contains CLAUDE.md
        3) aiPlat-core repo root if it contains CLAUDE.md
        """
        try:
            env_root = (os.getenv("AIPLAT_DEFAULT_REPO_ROOT", "") or "").strip()
            if env_root:
                return env_root
        except Exception as e:
            logging.debug(str(e), exc_info=True)

        try:
            here = Path(__file__).resolve()  # .../aiPlat-core/core/harness/integration.py
            core_repo_root = here.parents[3]  # .../aiPlat-core
            workspace_root = core_repo_root.parent
            if (workspace_root / "CLAUDE.md").is_file():
                return str(workspace_root)
            if (core_repo_root / "CLAUDE.md").is_file():
                return str(core_repo_root)
        except Exception:
            return None
        return None


@dataclass
class KernelRuntime:
    """Runtime dependencies provided by the application layer (core/server.py lifespan)."""

    agent_manager: Any = None
    skill_manager: Any = None
    workspace_agent_manager: Any = None
    workspace_skill_manager: Any = None
    workspace_mcp_manager: Any = None
    mcp_manager: Any = None
    # Optional: allow API routers to use the same harness instance (helps testing & consistency)
    harness: Any = None
    execution_store: Any = None
    trace_service: Any = None
    approval_manager: Any = None
    job_scheduler: Any = None
    plugin_manager: Any = None
    package_manager: Any = None
    workspace_package_manager: Any = None
    memory_manager: Any = None
    knowledge_manager: Any = None
    adapter_manager: Any = None
    harness_manager: Any = None
    
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
            from .memory import MemoryScope
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
