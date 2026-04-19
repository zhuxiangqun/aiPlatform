"""
aiPlat-core REST API Server

Provides REST API endpoints for agent, skill, tool, memory, knowledge, and harness management.
Runs on port 8002.
"""

from fastapi import FastAPI, HTTPException, APIRouter, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from typing import Optional, List, Dict, Any
from contextlib import asynccontextmanager
from datetime import datetime
import asyncio
import time
import json
import os
import shutil
import tarfile
import tempfile
import hashlib
from pathlib import Path
import yaml
import uvicorn
import aiohttp

from core.utils.ids import new_prefixed_id
from core.security.rbac import check_permission as rbac_check_permission, should_enforce as rbac_should_enforce

from core.schemas import (
    AgentCreateRequest,
    AgentUpdateRequest,
    SkillCreateRequest,
    SkillExecuteRequest,
    JobCreateRequest,
    JobUpdateRequest,
    GatewayExecuteRequest,
    SkillPackCreateRequest,
    SkillPackUpdateRequest,
    SkillPackPublishRequest,
    SkillPackInstallRequest,
    PackagePublishRequest,
    PackageInstallRequest,
    PackageUninstallRequest,
    OnboardingDefaultLLMRequest,
    OnboardingInitTenantRequest,
    OnboardingAutosmokeConfigRequest,
    OnboardingSecretsMigrateRequest,
    OnboardingStrongGateRequest,
    OnboardingExecBackendRequest,
    OnboardingTrustedSkillKeysRequest,
    DiagnosticsPromptAssembleRequest,
    PromptTemplateUpsertRequest,
    PromptTemplateRollbackRequest,
    RepoChangesetPreviewRequest,
    RepoTestsRunRequest,
    RepoStagedPreviewRequest,
    LongTermMemoryAddRequest,
    LongTermMemorySearchRequest,
    MessageCreateRequest,
    SessionCreateRequest,
    SearchRequest,
    CollectionCreateRequest,
    DocumentCreateRequest,
    AdapterCreateRequest,
    AdapterUpdateRequest,
    ModelUpdateRequest,
    HookCreateRequest,
    HookUpdateRequest,
    CoordinatorCreateRequest,
    FeedbackConfigUpdateRequest,
    RunStatus,
)
from core.management import (
    AgentManager,
    SkillManager,
    MemoryManager,
    KnowledgeManager,
    AdapterManager,
    HarnessManager,
)
from core.management.job_scheduler import JobScheduler, SchedulerConfig, next_run_from_cron
from core.apps.mcp.runtime import MCPRuntime
from core.apps.tools.base import ToolRegistry, get_tool_registry, create_tool
from core.apps.tools.permission import PermissionManager, Permission, get_permission_manager
from core.apps.agents import get_agent_registry
from core.apps.skills import get_skill_registry, get_skill_executor
from core.services import get_execution_store
from core.services.trace_service import TraceService, TraceServiceTracer, SpanStatus
from core.harness.integration import get_harness, KernelRuntime
from core.harness.kernel.types import ExecutionRequest
import uuid


def _seed_default_permissions(
    perm_mgr: PermissionManager,
    tool_names: List[str],
    skill_names: List[str],
    agent_names: List[str],
    users: Optional[List[str]] = None,
) -> None:
    """Seed default permissions for built-in resources.

    Policy (default):
    - system/admin get EXECUTE on all currently registered tools/skills/agents
    - others remain deny-by-default
    """
    users = users or ["system", "admin"]
    for user_id in users:
        for name in tool_names:
            perm_mgr.grant_permission(user_id, name, Permission.EXECUTE, granted_by="bootstrap")
        for name in skill_names:
            perm_mgr.grant_permission(user_id, name, Permission.EXECUTE, granted_by="bootstrap")
        for name in agent_names:
            perm_mgr.grant_permission(user_id, name, Permission.EXECUTE, granted_by="bootstrap")


def _create_llm_adapter(model_name: str = "gpt-4"):
    """Create an LLM adapter instance from a model name.
    
    Uses AdapterManager if available, otherwise falls back to create_adapter().
    """
    try:
        from core.harness.utils.model_injection import create_selected_adapter

        return create_selected_adapter(model_name=model_name)
    except Exception:
        return None


def _inject_model_into_agent(agent: object, model_name: str = "gpt-4"):
    """Inject LLM adapter into an agent if it doesn't have one."""
    if hasattr(agent, '_model') and agent._model is None:
        adapter = _create_llm_adapter(model_name)
        if adapter and hasattr(agent, 'set_model'):
            agent.set_model(adapter)
        elif adapter:
            agent._model = adapter


def _inject_model_into_skill(skill: object, model_name: str = "gpt-4"):
    """Inject LLM adapter into a skill if it doesn't have one."""
    if hasattr(skill, '_model') and skill._model is None:
        adapter = _create_llm_adapter(model_name)
        if adapter and hasattr(skill, 'set_model'):
            skill.set_model(adapter)
        elif adapter:
            skill._model = adapter


_agent_discovery = None
_skill_discovery = None
_mcp_manager = None
_workspace_agent_manager = None
_workspace_skill_manager = None
_workspace_mcp_manager = None
_package_manager = None
_workspace_package_manager = None

_agent_executions: Dict[str, Dict[str, Any]] = {}
_skill_executions: Dict[str, Dict[str, Any]] = {}
_agent_history: Dict[str, List[Dict[str, Any]]] = {}
# Phase 3+: paused agent executions (approval_required / policy_denied) used for minimal resume.
_paused_agent_executions: Dict[str, Dict[str, Any]] = {}
_execution_store = None
_trace_service: Optional[TraceService] = None





_agent_manager: Optional[AgentManager] = None
_skill_manager: Optional[SkillManager] = None
_memory_manager: Optional[MemoryManager] = None
_knowledge_manager: Optional[KnowledgeManager] = None
_adapter_manager: Optional[AdapterManager] = None
_harness_manager: Optional[HarnessManager] = None
_approval_manager: Optional[Any] = None
_job_scheduler: Optional[JobScheduler] = None
_mcp_runtime: Optional[MCPRuntime] = None


async def _get_trusted_skill_pubkeys_map() -> Dict[str, str]:
    """
    Global trusted public keys for skill signature verification.
    Stored in global_setting: trusted_skill_pubkeys = {"keys":[{"key_id","public_key"}]}
    """
    out: Dict[str, str] = {}
    try:
        if _execution_store is None:
            return out
        gs = await _execution_store.get_global_setting(key="trusted_skill_pubkeys")
        v = gs.get("value") if isinstance(gs, dict) else None
        keys = (v or {}).get("keys") if isinstance(v, dict) else None
        if isinstance(keys, list):
            for it in keys:
                if not isinstance(it, dict):
                    continue
                kid = str(it.get("key_id") or "").strip()
                pk = str(it.get("public_key") or "").strip()
                if kid and pk:
                    out[kid] = pk
    except Exception:
        return {}
    return out


async def _maybe_verify_and_audit_skill_signature(*, skill: Any, scope: str) -> None:
    """
    Best-effort: compute verification status and record a changeset event.
    """
    try:
        meta = getattr(skill, "metadata", None)
        if not isinstance(meta, dict):
            return
        prov = meta.get("provenance") if isinstance(meta.get("provenance"), dict) else {}
        integ = meta.get("integrity") if isinstance(meta.get("integrity"), dict) else {}
        if not prov.get("signature") or not integ.get("bundle_sha256"):
            return

        trusted = await _get_trusted_skill_pubkeys_map()
        mgr = _workspace_skill_manager if scope == "workspace" else _skill_manager
        if not mgr:
            return
        prov2 = mgr.compute_skill_signature_verification(skill, trusted)
        if prov2:
            meta["provenance"] = prov2

        status = "success" if bool(prov2.get("signature_verified")) else "failed"
        if not trusted:
            status = "failed"
        await _record_changeset(
            name="skill_signature_verify",
            target_type="skill",
            target_id=str(getattr(skill, "id", "") or ""),
            status=status,
            args={"scope": scope, "trusted_keys_count": len(trusted)},
            result={
                "bundle_sha256": integ.get("bundle_sha256"),
                "signature_verified": prov2.get("signature_verified"),
                "signature_verified_key_id": prov2.get("signature_verified_key_id"),
                "signature_verified_reason": prov2.get("signature_verified_reason"),
            },
        )
    except Exception:
        return


async def _require_skill_signature_gate_approval(*, user_id: str, skill_id: str, action: str, details: str, metadata: Dict[str, Any]) -> str:
    """
    Create approval request for unverified skill signature actions.
    """
    from core.harness.infrastructure.approval.types import ApprovalContext, ApprovalRule, RuleType

    if not _approval_manager:
        raise HTTPException(status_code=503, detail="Approval manager not available")
    op = f"skills:signature_gate:{action}"
    rule = ApprovalRule(
        rule_id=f"skills_signature_gate_{action}",
        rule_type=RuleType.SENSITIVE_OPERATION,
        name=f"Skills signature gate（{action}）审批",
        description=f"workspace skill 签名未验证，{action} 需要审批",
        priority=1,
        metadata={"sensitive_operations": ["skills:signature_gate"]},
    )
    _approval_manager.register_rule(rule)
    ctx = ApprovalContext(
        user_id=user_id or "admin",
        operation=op,
        operation_context={"details": details},
        metadata=metadata or {},
    )
    req = _approval_manager.create_request(ctx, rule=rule)
    try:
        await _approval_manager._persist(req)  # type: ignore[attr-defined]
    except Exception:
        pass
    return req.request_id


def _signature_gate_eval(*, metadata: Optional[Dict[str, Any]], trusted_keys_count: int) -> Dict[str, Any]:
    """
    Determine whether signature gate should trigger.
    Rule: require approval unless signature_verified == True.
    """
    prov = (metadata or {}).get("provenance") if isinstance((metadata or {}).get("provenance"), dict) else {}
    integ = (metadata or {}).get("integrity") if isinstance((metadata or {}).get("integrity"), dict) else {}
    sig = prov.get("signature")
    bundle = integ.get("bundle_sha256")
    verified = prov.get("signature_verified") is True
    reason = prov.get("signature_verified_reason")
    if verified:
        return {"required": False, "verified": True, "reason": None}
    if not bundle:
        return {"required": True, "verified": False, "reason": "missing_bundle_sha256"}
    if not sig:
        return {"required": True, "verified": False, "reason": "missing_signature"}
    if trusted_keys_count <= 0:
        return {"required": True, "verified": False, "reason": "no_trusted_keys"}
    return {"required": True, "verified": False, "reason": str(reason or "not_verified")}


async def _sync_mcp_runtime() -> None:
    """Best-effort: sync MCP servers into ToolRegistry runtime."""
    global _mcp_runtime
    if _mcp_runtime is None:
        _mcp_runtime = MCPRuntime()
    try:
        servers: Dict[str, Any] = {}
        if _mcp_manager:
            for s in _mcp_manager.list_servers():
                servers[s.name] = s
        if _workspace_mcp_manager:
            for s in _workspace_mcp_manager.list_servers():
                servers[s.name] = s
        await _mcp_runtime.sync_from_servers(servers=list(servers.values()), tool_registry=get_tool_registry())
    except Exception:
        pass


def _reload_workspace_managers() -> None:
    """
    Best-effort reload workspace managers from filesystem.
    Needed for operations that modify ~/.aiplat directly (e.g., package install).
    """
    global _workspace_agent_manager, _workspace_skill_manager, _workspace_mcp_manager
    try:
        if _agent_manager:
            _workspace_agent_manager = AgentManager(seed=False, scope="workspace", reserved_ids=set(_agent_manager.get_agent_ids()))
        if _skill_manager:
            _workspace_skill_manager = SkillManager(seed=False, scope="workspace", reserved_ids=set(_skill_manager.get_skill_ids()))
        if _mcp_manager is not None:
            from core.management.mcp_manager import MCPManager

            _workspace_mcp_manager = MCPManager(scope="workspace", reserved_names=set(_mcp_manager.get_server_names()) if _mcp_manager else set())
    except Exception:
        return


@asynccontextmanager
async def lifespan(app: FastAPI):
    global _agent_discovery, _skill_discovery
    global _agent_manager, _skill_manager, _memory_manager
    global _knowledge_manager, _adapter_manager, _harness_manager
    global _approval_manager
    global _execution_store
    global _trace_service
    
    from core.apps.agents import create_agent_discovery
    from core.apps.skills import create_discovery
    from core.harness.infrastructure.approval import ApprovalManager, ApprovalRule, RuleType
    
    _approval_manager = ApprovalManager(execution_store=_execution_store)
    _approval_manager.register_rule(ApprovalRule(
        rule_id="sensitive-ops",
        rule_type=RuleType.SENSITIVE_OPERATION,
        name="Sensitive Operations",
        description="Require approval for sensitive operations",
        # NOTE: ApprovalRule.matches currently checks metadata.sensitive_operations.
        # Keep condition for future expression evaluation, but set metadata now for correctness.
        condition="tool in ['code','file_operations','database']",
        auto_approve=False,
        enabled=True,
        priority=10,
        metadata={"sensitive_operations": ["tool:code", "tool:file_operations", "tool:database"]},
    ))

    # ExecutionStore (SQLite) - persistent execution/history
    _execution_store = get_execution_store()
    await _execution_store.init()

    # TraceService (optional persistence) + tool tracer wiring
    try:
        _trace_service = TraceService(execution_store=_execution_store)
        # inject tracer into tool registry (so BaseTool wrapper can create spans)
        try:
            registry = get_tool_registry()
            if hasattr(registry, "set_tracer"):
                registry.set_tracer(TraceServiceTracer(_trace_service))
        except Exception:
            pass
    except Exception:
        _trace_service = None

    # Persist LangGraph checkpoints/traces (best-effort) via callback manager
    try:
        from core.harness.execution.langgraph.callbacks import CallbackManager, CallbackEvent

        cb = CallbackManager.get_instance()

        async def _persist_graph_events(ctx):  # type: ignore[no-redef]
            try:
                store = _execution_store
                if not store:
                    return
                state = ctx.state if isinstance(getattr(ctx, "state", None), dict) else {}
                meta = state.get("metadata") if isinstance(state.get("metadata"), dict) else {}
                run_id = meta.get("graph_run_id")
                if not run_id:
                    return

                if ctx.event == CallbackEvent.GRAPH_START:
                    await store.start_graph_run(
                        graph_name=ctx.graph_name,
                        run_id=run_id,
                        initial_state=state,
                        parent_run_id=meta.get("parent_run_id"),
                        resumed_from_checkpoint_id=meta.get("resumed_from_checkpoint_id"),
                    )
                elif ctx.event == CallbackEvent.CHECKPOINT:
                    ckpt_id = (ctx.metadata or {}).get("checkpoint_id")
                    step = int(state.get("step_count", 0) or 0)
                    await store.add_graph_checkpoint(run_id=run_id, step=step, state=state, checkpoint_id=ckpt_id)
                elif ctx.event == CallbackEvent.GRAPH_END:
                    await store.finish_graph_run(run_id=run_id, status="completed", final_state=state, summary=state.get("metadata", {}).get("trace", {}))
                elif ctx.event == CallbackEvent.GRAPH_ERROR:
                    await store.finish_graph_run(run_id=run_id, status="failed", final_state=state, summary={"error": str(getattr(ctx, "error", "") or "")})
            except Exception:
                return

        cb.register_global(_persist_graph_events)
    except Exception:
        pass
    _approval_manager.register_rule(ApprovalRule(
        rule_id="first-time-ops",
        rule_type=RuleType.FIRST_TIME,
        name="First Time Operations",
        description="Auto-approve known safe operations",
        condition="",
        auto_approve=True,
        enabled=True,
        priority=5,
    ))
    
    # Engine agents (AGENT.md): core/engine/agents
    try:
        from pathlib import Path
        import os
        engine_agents = str(Path(__file__).resolve().parent / "engine" / "agents")
        agents_path = os.environ.get("AIPLAT_ENGINE_AGENTS_PATH") or engine_agents
    except Exception:
        agents_path = "agents"

    _agent_discovery = create_agent_discovery(agents_path)
    await _agent_discovery.discover()
    
    # Engine skills (SKILL.md): core/engine/skills
    try:
        from pathlib import Path
        import os
        engine_skills = str(Path(__file__).resolve().parent / "engine" / "skills")
        skills_path = os.environ.get("AIPLAT_ENGINE_SKILLS_PATH") or engine_skills
    except Exception:
        skills_path = "skills"

    _skill_discovery = create_discovery(skills_path)
    await _skill_discovery.discover()
    
    # Engine managers (core-only)
    _agent_manager = AgentManager(seed=False, scope="engine")
    _skill_manager = SkillManager(seed=False, scope="engine")
    # Engine packages (filesystem)
    try:
        from core.management.package_manager import PackageManager

        global _package_manager
        _package_manager = PackageManager(scope="engine")
    except Exception:
        _package_manager = None
    try:
        from core.management.mcp_manager import MCPManager
        global _mcp_manager
        _mcp_manager = MCPManager(scope="engine")
    except Exception:
        _mcp_manager = None

    # Workspace seeds (user-facing). Best-effort materialization into ~/.aiplat (do NOT overwrite).
    # This ensures "workspace skills" can exist out-of-the-box while keeping engine minimal and stable.
    try:
        from pathlib import Path

        seeds_dir = Path(__file__).resolve().parent / "workspace_seeds" / "skills"
        workspace_dir = Path.home() / ".aiplat" / "skills"
        if seeds_dir.exists():
            workspace_dir.mkdir(parents=True, exist_ok=True)
            for item in seeds_dir.iterdir():
                if not item.is_dir():
                    continue
                dst = workspace_dir / item.name
                if dst.exists():
                    continue
                try:
                    shutil.copytree(item, dst)
                except Exception:
                    pass
    except Exception:
        pass

    # Workspace agent seeds (user-facing). Best-effort materialization into ~/.aiplat/agents (do NOT overwrite).
    try:
        from pathlib import Path

        seeds_dir = Path(__file__).resolve().parent / "workspace_seeds" / "agents"
        workspace_dir = Path.home() / ".aiplat" / "agents"
        if seeds_dir.exists():
            workspace_dir.mkdir(parents=True, exist_ok=True)
            for item in seeds_dir.iterdir():
                if not item.is_dir():
                    continue
                dst = workspace_dir / item.name
                if dst.exists():
                    continue
                try:
                    shutil.copytree(item, dst)
                except Exception:
                    pass
    except Exception:
        pass

    # Workspace MCP seeds (user-facing). Best-effort materialization into ~/.aiplat/mcps (do NOT overwrite).
    try:
        from pathlib import Path

        seeds_dir = Path(__file__).resolve().parent / "workspace_seeds" / "mcps"
        workspace_dir = Path.home() / ".aiplat" / "mcps"
        if seeds_dir.exists():
            workspace_dir.mkdir(parents=True, exist_ok=True)
            for item in seeds_dir.iterdir():
                if not item.is_dir():
                    continue
                dst = workspace_dir / item.name
                if dst.exists():
                    continue
                try:
                    shutil.copytree(item, dst)
                except Exception:
                    pass
    except Exception:
        pass

    # Workspace managers (user-facing). Strictly separated: no override of engine ids.
    try:
        global _workspace_agent_manager, _workspace_skill_manager, _workspace_mcp_manager
        _workspace_agent_manager = AgentManager(seed=False, scope="workspace", reserved_ids=set(_agent_manager.get_agent_ids()))
        _workspace_skill_manager = SkillManager(seed=False, scope="workspace", reserved_ids=set(_skill_manager.get_skill_ids()))
        _workspace_mcp_manager = MCPManager(scope="workspace", reserved_names=set(_mcp_manager.get_server_names()) if _mcp_manager else set())
    except Exception:
        _workspace_agent_manager = None
        _workspace_skill_manager = None
        _workspace_mcp_manager = None
    # Workspace packages
    try:
        from core.management.package_manager import PackageManager

        global _workspace_package_manager
        _workspace_package_manager = PackageManager(
            scope="workspace",
            reserved_names=set([p.name for p in (_package_manager.list_packages() if _package_manager else [])]),
        )
    except Exception:
        _workspace_package_manager = None
    _memory_manager = MemoryManager(seed=True)
    _knowledge_manager = KnowledgeManager()
    _adapter_manager = AdapterManager(execution_store=_execution_store)
    try:
        await _adapter_manager.init_from_store()
    except Exception:
        pass
    _harness_manager = HarnessManager()
    
    # Seed execution-layer registries with real instances
    skill_registry = get_skill_registry()
    skill_registry.seed_data()
    
    # Register discovered skills into registry
    if _skill_discovery:
        from core.apps.skills.registry import _GenericSkill
        from core.harness.interfaces import SkillConfig
        for skill_name, discovered in _skill_discovery._discovered.items():
            try:
                if skill_registry.get(skill_name) is not None:
                    continue
                config = SkillConfig(
                    name=skill_name,
                    description=getattr(discovered, 'description', ''),
                    metadata={"category": getattr(discovered, 'category', 'general'), "version": getattr(discovered, 'version', '1.0.0')}
                )
                skill_instance = _GenericSkill(config)
                skill_registry.register(skill_instance)
            except Exception:
                pass
    
    # Register discovered agents into registry
    if _agent_discovery:
        from core.apps.agents import create_agent
        from core.harness.interfaces import AgentConfig
        agent_registry = get_agent_registry()
        for agent_name, discovered in _agent_discovery._discovered.items():
            try:
                if agent_registry.get(agent_name) is not None:
                    continue
                agent_type = getattr(discovered, 'agent_type', 'base')
                agent_config = AgentConfig(
                    name=getattr(discovered, 'display_name', agent_name),
                    model="gpt-4",
                    metadata=getattr(discovered, 'config_schema', {}) or {}
                )
                agent_instance = create_agent(agent_type=agent_type, config=agent_config)
                agent_registry.register(
                    agent_name,
                    agent_instance,
                    config=agent_config.metadata if isinstance(agent_config.metadata, dict) else {},
                    metadata=discovered
                )
            except Exception:
                pass
    
    # Register all available tools
    registry = get_tool_registry()
    # Inject permission manager to tools (so BaseTool wrapper can enforce when user_id is provided)
    try:
        perm_mgr = get_permission_manager()
        if hasattr(registry, "set_permission_manager"):
            registry.set_permission_manager(perm_mgr)
    except Exception:
        perm_mgr = None
    
    # Built-in tools via create_tool factory
    for tool_type in ["calculator", "search", "file_operations"]:
        try:
            tool = create_tool(tool_type)
            registry.register(tool)
        except ValueError:
            pass
    
    # Tools from dedicated modules (real implementations and stubs)
    _tool_modules = [
        ("core.apps.tools.webfetch", "WebFetchTool", {"timeout": 30000, "max_content_size": 1048576}),
        ("core.apps.tools.http", "HTTPClientTool", {"timeout": 30000, "max_response_size": 10485760}),
        ("core.apps.tools.code", "CodeExecutionTool", {"timeout": 30000}),
        ("core.apps.tools.database", "DatabaseTool", {"timeout": 60000}),
        ("core.apps.tools.browser", "BrowserTool", {"navigation_timeout": 30000}),
    ]
    for module_path, cls_name, kwargs in _tool_modules:
        try:
            import importlib
            module = importlib.import_module(module_path)
            cls = getattr(module, cls_name)
            tool = cls(**kwargs)
            registry.register(tool)
        except Exception:
            pass

    # Seed default permissions so the system is usable out-of-the-box.
    # Can be disabled by setting AIPLAT_SEED_DEFAULT_PERMISSIONS=false
    seed_enabled = os.getenv("AIPLAT_SEED_DEFAULT_PERMISSIONS", "true").lower() in ("1", "true", "yes", "y")
    if seed_enabled:
        try:
            perm_mgr = perm_mgr or get_permission_manager()
            tool_names = registry.list_tools()
            skill_names = skill_registry.list_skills()
            agent_registry = get_agent_registry()
            agent_names = agent_registry.list_all()
            _seed_default_permissions(
                perm_mgr=perm_mgr,
                tool_names=tool_names,
                skill_names=skill_names,
                agent_names=agent_names,
                users=os.getenv("AIPLAT_DEFAULT_PERMISSION_USERS", "system,admin").split(","),
            )
        except Exception:
            pass

    # Roadmap-2: wire MCP servers into ToolRegistry (best-effort).
    # Safe-by-default: prod forbids stdio unless explicitly allowed in policy.
    try:
        await _sync_mcp_runtime()
    except Exception:
        pass

    # Phase-1: wire application runtime into HarnessIntegration (single entry execute)
    try:
        get_harness().attach_runtime(
            KernelRuntime(
                agent_manager=_agent_manager,
                skill_manager=_skill_manager,
                execution_store=_execution_store,
                trace_service=_trace_service,
                approval_manager=_approval_manager,
            )
        )
    except Exception:
        pass

    # Roadmap-3: Jobs/Cron scheduler (default enabled)
    global _job_scheduler
    try:
        enable_jobs = os.getenv("AIPLAT_ENABLE_JOBS", "true").lower() in ("1", "true", "yes", "y")
        if enable_jobs and _execution_store is not None:
            _job_scheduler = JobScheduler(
                execution_store=_execution_store,
                harness=get_harness(),
                config=SchedulerConfig(
                    poll_interval_seconds=float(os.getenv("AIPLAT_JOBS_POLL_SECONDS", "2") or "2"),
                    batch_size=int(os.getenv("AIPLAT_JOBS_BATCH_SIZE", "20") or "20"),
                ),
            )
            await _job_scheduler.start()
    except Exception:
        _job_scheduler = None
    
    yield

    # Shutdown background services
    try:
        if _job_scheduler is not None:
            await _job_scheduler.stop()
    except Exception:
        pass


app = FastAPI(
    title="aiPlat-core API",
    description="Core layer API for Agent, Skill, Tool, Memory, Knowledge, and Harness management",
    version="0.1.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

api_router = APIRouter(prefix="/api/core")


def _runtime_env() -> str:
    """Runtime environment string for policy gates (dev/staging/prod)."""
    env = (os.environ.get("AIPLAT_ENV") or os.environ.get("APP_ENV") or os.environ.get("ENV") or "dev").strip().lower()
    if env in {"production"}:
        env = "prod"
    return env


def _autosmoke_enforce() -> bool:
    # Env override has highest priority.
    v = (os.getenv("AIPLAT_AUTOSMOKE_ENFORCE", "") or "").strip().lower()
    if v:
        return v in {"1", "true", "yes", "y", "on"}
    # Otherwise, best-effort load from global_settings(key="autosmoke")
    try:
        if _execution_store is None:
            return False
        db_path = getattr(getattr(_execution_store, "_config", None), "db_path", None)
        if not db_path:
            return False
        import sqlite3, json

        conn = sqlite3.connect(str(db_path))
        try:
            row = conn.execute("SELECT value_json FROM global_settings WHERE key='autosmoke' LIMIT 1;").fetchone()
        finally:
            conn.close()
        if not row or not row[0]:
            return False
        cfg = json.loads(row[0]) if isinstance(row[0], str) else {}
        return bool(cfg.get("enforce")) is True
    except Exception:
        return False


def _is_verified(meta: Dict[str, Any] | None) -> bool:
    if not isinstance(meta, dict):
        return False
    v = meta.get("verification")
    if isinstance(v, dict):
        return str(v.get("status") or "") == "verified"
    return False


def _governance_publish_gate(meta: Dict[str, Any] | None) -> Dict[str, Any]:
    """
    If a workspace skill has a governance candidate, it must be published before enable/execute.
    """
    if not isinstance(meta, dict):
        return {"required": False}
    gov = meta.get("governance")
    if not isinstance(gov, dict):
        return {"required": False}
    candidate_id = gov.get("candidate_id")
    if not isinstance(candidate_id, str) or not candidate_id.strip():
        return {"required": False}
    candidate_id = candidate_id.strip()
    published_candidate_id = gov.get("published_candidate_id")
    if isinstance(published_candidate_id, str) and published_candidate_id.strip() == candidate_id:
        return {"required": False, "candidate_id": candidate_id, "published_candidate_id": published_candidate_id}
    if str(gov.get("status") or "").lower() == "published":
        return {"required": False, "candidate_id": candidate_id, "published_candidate_id": published_candidate_id}
    return {"required": True, "candidate_id": candidate_id, "published_candidate_id": published_candidate_id, "status": gov.get("status")}


def _management_public_url() -> str:
    """
    Public base URL for management UI (for clickable links in API errors).

    Example: https://console.example.com
    """
    return (os.getenv("AIPLAT_MANAGEMENT_PUBLIC_URL") or "").rstrip("/")


def _ui_url(path: str) -> str:
    base = _management_public_url()
    if not base:
        return path
    if not path.startswith("/"):
        path = "/" + path
    return base + path


def _api_url(path: str) -> str:
    """
    API URL under management domain (assumes /api is served from same host).
    """
    return _ui_url(path)


def _inject_http_request_context(payload: Any, http_request: Request, *, entrypoint: str) -> Any:
    """
    Best-effort: inject tenant/actor/request identity from headers into payload.context.
    Used for PR-01 tenant/actor propagation into harness/syscalls.
    """
    if not isinstance(payload, dict):
        return payload
    try:
        ctx = payload.get("context") if isinstance(payload.get("context"), dict) else {}
        ctx = dict(ctx) if isinstance(ctx, dict) else {}
        ctx.setdefault("entrypoint", str(entrypoint or "api"))

        tenant_id = http_request.headers.get("X-AIPLAT-TENANT-ID") or http_request.headers.get("x-aiplat-tenant-id")
        actor_id = http_request.headers.get("X-AIPLAT-ACTOR-ID") or http_request.headers.get("x-aiplat-actor-id")
        actor_role = http_request.headers.get("X-AIPLAT-ACTOR-ROLE") or http_request.headers.get("x-aiplat-actor-role")
        req_id = http_request.headers.get("X-AIPLAT-REQUEST-ID") or http_request.headers.get("x-aiplat-request-id")
        if tenant_id:
            ctx.setdefault("tenant_id", str(tenant_id))
        if actor_id:
            ctx.setdefault("actor_id", str(actor_id))
        if actor_role:
            ctx.setdefault("actor_role", str(actor_role))
        if req_id:
            ctx.setdefault("request_id", str(req_id))
        payload["context"] = ctx
    except Exception:
        return payload
    return payload


def _rbac_actor_from_http(http_request: Request, payload: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    ctx0 = None
    try:
        if isinstance(payload, dict):
            ctx0 = payload.get("context") if isinstance(payload.get("context"), dict) else {}
    except Exception:
        ctx0 = {}
    ctx0 = ctx0 if isinstance(ctx0, dict) else {}

    actor_id = (
        (ctx0.get("actor_id") if isinstance(ctx0, dict) else None)
        or http_request.headers.get("X-AIPLAT-ACTOR-ID")
        or http_request.headers.get("x-aiplat-actor-id")
        or (payload.get("user_id") if isinstance(payload, dict) else None)
    )
    actor_role = (
        (ctx0.get("actor_role") if isinstance(ctx0, dict) else None)
        or http_request.headers.get("X-AIPLAT-ACTOR-ROLE")
        or http_request.headers.get("x-aiplat-actor-role")
    )
    tenant_id = (
        (ctx0.get("tenant_id") if isinstance(ctx0, dict) else None)
        or http_request.headers.get("X-AIPLAT-TENANT-ID")
        or http_request.headers.get("x-aiplat-tenant-id")
    )
    return {"actor_id": actor_id, "actor_role": actor_role, "tenant_id": tenant_id}


async def _rbac_guard(
    *,
    http_request: Request,
    payload: Optional[Dict[str, Any]],
    action: str,
    resource_type: str,
    resource_id: Optional[str] = None,
    run_id: Optional[str] = None,
) -> Optional[JSONResponse]:
    """
    返回 JSONResponse 表示拒绝；返回 None 表示允许继续。
    enforced 模式：直接 403
    warn 模式：写审计但不阻断
    """
    actor = _rbac_actor_from_http(http_request, payload)
    decision = rbac_check_permission(actor_role=actor.get("actor_role"), action=action, resource_type=resource_type)
    if decision.allowed:
        return None

    # audit best-effort
    if _execution_store:
        try:
            await _execution_store.add_audit_log(
                action=f"rbac_{action}",
                status="denied" if rbac_should_enforce() else "warn",
                tenant_id=str(actor.get("tenant_id") or "") or None,
                actor_id=str(actor.get("actor_id") or "") or None,
                actor_role=str(actor.get("actor_role") or "") or None,
                resource_type=str(resource_type),
                resource_id=str(resource_id) if resource_id else None,
                run_id=str(run_id) if run_id else None,
                request_id=http_request.headers.get("X-AIPLAT-REQUEST-ID") or http_request.headers.get("x-aiplat-request-id"),
                detail={"reason": decision.reason},
            )
        except Exception:
            pass

    if not rbac_should_enforce():
        return None

    # enforced: block
    body = {
        "ok": False,
        "run_id": str(run_id or new_prefixed_id("run")),
        "trace_id": None,
        "status": RunStatus.failed.value,
        "legacy_status": "forbidden",
        "output": None,
        "error": {"code": "FORBIDDEN", "message": "forbidden", "detail": {"reason": decision.reason}},
        "error_code": "FORBIDDEN",
        "error_message": "forbidden",
    }
    return JSONResponse(status_code=403, content=body)


async def _audit_execute(
    *,
    http_request: Request,
    payload: Optional[Dict[str, Any]],
    resource_type: str,
    resource_id: str,
    resp: Dict[str, Any],
    action: Optional[str] = None,
) -> None:
    """PR-06: enterprise audit for execute entrypoints (best-effort)."""
    if not _execution_store:
        return
    try:
        actor = _rbac_actor_from_http(http_request, payload)
        await _execution_store.add_audit_log(
            action=action or f"execute_{resource_type}",
            status=str(resp.get("legacy_status") or resp.get("status") or ("ok" if resp.get("ok") else "failed")),
            tenant_id=str(actor.get("tenant_id") or "") or None,
            actor_id=str(actor.get("actor_id") or "") or None,
            actor_role=str(actor.get("actor_role") or "") or None,
            resource_type=str(resource_type),
            resource_id=str(resource_id),
            request_id=str(resp.get("request_id") or "") or (http_request.headers.get("X-AIPLAT-REQUEST-ID") or http_request.headers.get("x-aiplat-request-id")),
            run_id=str(resp.get("run_id") or resp.get("execution_id") or "") or None,
            trace_id=str(resp.get("trace_id") or "") or None,
            detail={
                "status": resp.get("status"),
                "legacy_status": resp.get("legacy_status"),
                "error": resp.get("error"),
            },
        )
    except Exception:
        return


def _normalize_run_status_v2(*, ok: bool, legacy_status: Optional[str], error_code: Optional[str]) -> str:
    s = str(legacy_status or "").lower().strip()
    c = str(error_code or "").upper().strip()
    if s in {"accepted", "queued"}:
        return RunStatus.accepted.value
    if s in {"running"}:
        return RunStatus.running.value
    if s in {"approval_required", "waiting_approval"} or c == "APPROVAL_REQUIRED":
        return RunStatus.waiting_approval.value
    if s in {"timeout"} or c == "TIMEOUT":
        return RunStatus.timeout.value
    if ok:
        return RunStatus.completed.value
    if s in {"publish_required", "blocked"} or c == "PUBLISH_REQUIRED":
        return RunStatus.aborted.value
    if s in {"aborted"}:
        return RunStatus.aborted.value
    return RunStatus.failed.value


def _normalize_run_error(*, code: Optional[str], message: Optional[str], detail: Optional[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    if not code and not message and not detail:
        return None
    return {"code": str(code or "EXECUTION_FAILED"), "message": str(message or "Execution failed"), "detail": detail or None}


def _wrap_execution_result_as_run_summary(result: Any) -> Dict[str, Any]:
    """
    PR-02: Run Contract v2
    Return: {ok, run_id, trace_id, status, output, error{code,message,detail}, ...legacy fields...}
    """
    payload = dict(getattr(result, "payload", None) or {}) if isinstance(getattr(result, "payload", None), dict) else {}
    # Determine ok semantics: allow payload override
    ok0 = bool(getattr(result, "ok", False))
    if payload.get("ok") is False:
        ok0 = False
    legacy_status = payload.get("status")
    # Run id: prefer ExecutionResult.run_id then payload
    run_id = (
        getattr(result, "run_id", None)
        or payload.get("run_id")
        or payload.get("execution_id")
        or payload.get("executionId")
        or new_prefixed_id("run")
    )
    trace_id = getattr(result, "trace_id", None) or payload.get("trace_id")

    # Error normalization
    err_detail = getattr(result, "error_detail", None) if isinstance(getattr(result, "error_detail", None), dict) else None
    # payload may already have structured error
    err_obj = payload.get("error") if isinstance(payload.get("error"), dict) else None
    err_code = None
    err_msg = None
    if isinstance(err_obj, dict):
        err_code = err_obj.get("code")
        err_msg = err_obj.get("message")
        err_detail = err_obj.get("detail") if isinstance(err_obj.get("detail"), dict) else (err_detail or None)
    else:
        err_code = payload.get("error_code") or (err_detail or {}).get("code") if isinstance(err_detail, dict) else None
        err_msg = payload.get("error_message") or (err_detail or {}).get("message") if isinstance(err_detail, dict) else None
        if not err_msg:
            err_msg = getattr(result, "error", None)
    run_status = _normalize_run_status_v2(ok=ok0, legacy_status=legacy_status, error_code=err_code)

    out = dict(payload)
    out.setdefault("legacy_status", legacy_status)
    out["ok"] = ok0
    out["run_id"] = str(run_id)
    out["trace_id"] = trace_id
    out["status"] = run_status
    out["output"] = payload.get("output")
    if ok0:
        out["error"] = None
    else:
        out["error"] = _normalize_run_error(code=err_code, message=err_msg, detail=err_detail)
    # Keep old aliases for compatibility
    if not ok0:
        out.setdefault("error_detail", out.get("error"))
        out.setdefault("error_message", (out.get("error") or {}).get("message") if isinstance(out.get("error"), dict) else None)
        out.setdefault("error_code", (out.get("error") or {}).get("code") if isinstance(out.get("error"), dict) else None)
    return out


async def _require_targets_verified(targets: list[tuple[str, str]]) -> None:
    """
    Gate publish/enable actions by autosmoke verification status.

    targets: list of (target_type, target_id), e.g. ("agent","xxx")
    """
    if not _autosmoke_enforce():
        return
    missing: list[dict] = []
    for ttype, tid in targets:
        ttype = str(ttype or "").strip().lower()
        tid = str(tid or "").strip()
        if not ttype or not tid:
            continue
        if ttype == "agent":
            if not _workspace_agent_manager:
                missing.append({"type": ttype, "id": tid, "reason": "agent_manager_unavailable"})
                continue
            a = await _workspace_agent_manager.get_agent(tid)
            meta = getattr(a, "metadata", None) if a else None
            ver = meta.get("verification") if isinstance(meta, dict) else None
            if not a or not _is_verified(meta):
                item = {"type": ttype, "id": tid, "reason": "unverified", "verification": ver or {}}
                jr = (ver or {}).get("job_run_id") if isinstance(ver, dict) else None
                jid = (ver or {}).get("job_id") if isinstance(ver, dict) else None
                if isinstance(jr, str) and jr:
                    item["diagnostics_url"] = _ui_url(f"/diagnostics/runs?run_id={jr}")
                    if _execution_store:
                        try:
                            item["job_run"] = await _execution_store.get_job_run(jr)
                        except Exception:
                            pass
                if isinstance(jid, str) and jid:
                    item["retry"] = {"method": "POST", "api_url": _api_url(f"/api/core/jobs/{jid}/run"), "job_id": jid}
                missing.append(item)
        elif ttype == "skill":
            if not _workspace_skill_manager:
                missing.append({"type": ttype, "id": tid, "reason": "skill_manager_unavailable"})
                continue
            s = await _workspace_skill_manager.get_skill(tid)
            meta = getattr(s, "metadata", None) if s else None
            ver = meta.get("verification") if isinstance(meta, dict) else None
            if not s or not _is_verified(meta):
                item = {"type": ttype, "id": tid, "reason": "unverified", "verification": ver or {}}
                jr = (ver or {}).get("job_run_id") if isinstance(ver, dict) else None
                jid = (ver or {}).get("job_id") if isinstance(ver, dict) else None
                if isinstance(jr, str) and jr:
                    item["diagnostics_url"] = _ui_url(f"/diagnostics/runs?run_id={jr}")
                    if _execution_store:
                        try:
                            item["job_run"] = await _execution_store.get_job_run(jr)
                        except Exception:
                            pass
                if isinstance(jid, str) and jid:
                    item["retry"] = {"method": "POST", "api_url": _api_url(f"/api/core/jobs/{jid}/run"), "job_id": jid}
                missing.append(item)
        elif ttype == "mcp":
            if not _workspace_mcp_manager:
                missing.append({"type": ttype, "id": tid, "reason": "mcp_manager_unavailable"})
                continue
            m = _workspace_mcp_manager.get_server(tid)
            meta = getattr(m, "metadata", None) if m else None
            ver = meta.get("verification") if isinstance(meta, dict) else None
            if not m or not _is_verified(meta):
                item = {"type": ttype, "id": tid, "reason": "unverified", "verification": ver or {}}
                jr = (ver or {}).get("job_run_id") if isinstance(ver, dict) else None
                jid = (ver or {}).get("job_id") if isinstance(ver, dict) else None
                if isinstance(jr, str) and jr:
                    item["diagnostics_url"] = _ui_url(f"/diagnostics/runs?run_id={jr}")
                    if _execution_store:
                        try:
                            item["job_run"] = await _execution_store.get_job_run(jr)
                        except Exception:
                            pass
                if isinstance(jid, str) and jid:
                    item["retry"] = {"method": "POST", "api_url": _api_url(f"/api/core/jobs/{jid}/run"), "job_id": jid}
                missing.append(item)
        else:
            # ignore other target types
            continue
    if missing:
        raise HTTPException(
            status_code=403,
            detail={
                "code": "unverified",
                "message": "autosmoke must pass before publish/enable",
                "hint": "查看 targets[*].diagnostics_url 获取失败原因；或等待 autosmoke 完成后再重试",
                "targets": missing,
            },
        )

async def _audit_event(kind: str, name: str, status: str, *, args: Dict[str, Any] | None = None, result: Dict[str, Any] | None = None, error: str | None = None) -> None:
    """Best-effort append to ExecutionStore syscall_events for auditability."""
    try:
        if not _execution_store:
            return
        await _execution_store.add_syscall_event(
            {
                "kind": kind,
                "name": name,
                "status": status,
                "args": args or {},
                "result": result or {},
                "error": error,
            }
        )
    except Exception:
        return


async def _record_changeset(
    *,
    name: str,
    target_type: str,
    target_id: str,
    status: str = "success",
    args: Dict[str, Any] | None = None,
    result: Dict[str, Any] | None = None,
    error: str | None = None,
    user_id: str = "admin",
    session_id: str | None = None,
    approval_request_id: str | None = None,
) -> None:
    """
    Record a governance "changeset" event (best-effort).
    IMPORTANT: Do not store secrets; pass hashes/lengths instead.
    """
    try:
        if not _execution_store:
            return
        await _execution_store.add_syscall_event(
            {
                "kind": "changeset",
                "name": str(name),
                "status": str(status or "success"),
                "args": args or {},
                "result": result or {},
                "error": str(error) if error else None,
                "target_type": str(target_type),
                "target_id": str(target_id),
                "user_id": str(user_id or "admin"),
                "session_id": str(session_id) if session_id else None,
                "approval_request_id": str(approval_request_id) if approval_request_id else None,
            }
        )
    except Exception:
        return


def _prod_stdio_policy_check(
    server_name: str,
    transport: str,
    command: str | None,
    args: List[str] | None,
    metadata: Dict[str, Any] | None,
) -> tuple[bool, str]:
    """
    Policy: allow stdio MCP in prod only when explicitly allowlisted.

    Requirements (all must pass) when AIPLAT_ENV=prod and transport=stdio:
    1) server metadata contains prod_allowed=true
    2) server_name is in AIPLAT_PROD_STDIO_MCP_ALLOWLIST (comma-separated)
    3) command path is absolute and starts with one of AIPLAT_STDIO_ALLOWED_COMMAND_PREFIXES
       - prefixes separated by os.pathsep (:) or comma
    4) basic hardening:
       - deny risky interpreter basenames in prod (configurable)
       - command exists and is executable (best-effort)
       - args count/length sanity (avoid abuse)
    5) optional hardening (recommended):
       - force launcher in prod (AIPLAT_STDIO_FORCE_LAUNCHER_IN_PROD=true)
    """
    if _runtime_env() != "prod":
        return True, ""
    if (transport or "").strip().lower() != "stdio":
        return True, ""

    meta = metadata or {}
    if not bool(meta.get("prod_allowed", False)):
        return False, "metadata.prod_allowed is not true"

    allowlist_raw = os.environ.get("AIPLAT_PROD_STDIO_MCP_ALLOWLIST", "")
    allowlist = {x.strip() for x in allowlist_raw.split(",") if x.strip()}
    if not allowlist or server_name not in allowlist:
        return False, f"server_name '{server_name}' not in AIPLAT_PROD_STDIO_MCP_ALLOWLIST"

    if not command or not str(command).strip():
        return False, "missing stdio command"
    cmd = str(command).strip()
    if not cmd.startswith("/"):
        return False, "stdio command must be an absolute path"

    # optional: force a single controlled launcher in prod
    force_launcher = (os.environ.get("AIPLAT_STDIO_FORCE_LAUNCHER_IN_PROD", "") or "").strip().lower() in {"1", "true", "yes", "on"}
    if force_launcher:
        launcher = (os.environ.get("AIPLAT_STDIO_PROD_LAUNCHER") or "").strip()
        if not launcher:
            return False, "AIPLAT_STDIO_FORCE_LAUNCHER_IN_PROD is true but AIPLAT_STDIO_PROD_LAUNCHER is empty"
        if not launcher.startswith("/"):
            return False, "AIPLAT_STDIO_PROD_LAUNCHER must be an absolute path"
        if cmd != launcher:
            return False, "command must equal AIPLAT_STDIO_PROD_LAUNCHER when launcher enforcement is enabled"

    # deny risky basenames (configurable; defaults to common shells)
    deny_raw = os.environ.get("AIPLAT_STDIO_DENY_COMMAND_BASENAMES", "bash,sh,zsh")
    deny = {x.strip().lower() for x in deny_raw.split(",") if x.strip()}
    base = os.path.basename(cmd).lower()
    if base in deny:
        return False, f"command basename '{base}' is denied by policy"

    # command prefix allowlist
    prefixes_raw = os.environ.get("AIPLAT_STDIO_ALLOWED_COMMAND_PREFIXES", "")
    parts: List[str] = []
    for chunk in prefixes_raw.split(os.pathsep):
        parts.extend([x.strip() for x in chunk.split(",") if x.strip()])
    prefixes = [p if p.endswith("/") else (p + "/") for p in parts]
    if not prefixes:
        return False, "AIPLAT_STDIO_ALLOWED_COMMAND_PREFIXES is empty"
    if not any(cmd.startswith(p) or cmd == p.rstrip("/") for p in prefixes):
        return False, "command path not in allowed prefixes"

    # best-effort executable check
    if not (os.path.exists(cmd) and os.access(cmd, os.X_OK)):
        return False, "command is not an executable file on this host"

    # args sanity
    a = list(args or [])
    max_args = int(os.environ.get("AIPLAT_STDIO_MAX_ARGS", "32") or 32)
    max_arg_len = int(os.environ.get("AIPLAT_STDIO_MAX_ARG_LENGTH", "512") or 512)
    if len(a) > max_args:
        return False, f"too many args (>{max_args})"
    for one in a:
        s = str(one)
        if "\n" in s or "\r" in s or "\x00" in s:
            return False, "args contain illegal control characters"
        if len(s) > max_arg_len:
            return False, f"arg too long (>{max_arg_len})"

    return True, ""


def _prod_stdio_policy_ok(server_name: str, transport: str, command: str | None, args: List[str] | None, metadata: Dict[str, Any] | None) -> bool:
    ok, _ = _prod_stdio_policy_check(server_name, transport, command, args, metadata)
    return ok


# ==================== Permission Management ====================

@api_router.get("/permissions/stats")
async def get_permission_stats():
    """Get permission statistics"""
    perm_mgr = get_permission_manager()
    return perm_mgr.get_stats()


@api_router.get("/permissions/users/{user_id}")
async def get_user_permissions(user_id: str):
    """Get all permissions for a user (resource_id -> permissions)."""
    perm_mgr = get_permission_manager()
    tools = perm_mgr.get_user_tools(user_id)
    return {
        "user_id": user_id,
        "permissions": {k: [p.value for p in v] for k, v in tools.items()},
    }


@api_router.get("/permissions/resources/{resource_id}")
async def get_resource_permissions(resource_id: str):
    """Get all users who have permissions on a resource."""
    perm_mgr = get_permission_manager()
    users = perm_mgr.get_tool_users(resource_id)
    return {
        "resource_id": resource_id,
        "users": {k: [p.value for p in v] for k, v in users.items()},
    }


@api_router.post("/permissions/grant")
async def grant_permission(request: Dict[str, Any]):
    """Grant permission to a user for a resource (tool/skill/agent)."""
    user_id = request.get("user_id")
    resource_id = request.get("resource_id") or request.get("tool_name")
    permission = request.get("permission", "execute")
    granted_by = request.get("granted_by")
    if not user_id or not resource_id:
        raise HTTPException(status_code=400, detail="user_id and resource_id are required")
    try:
        perm_enum = Permission(permission)
    except Exception:
        raise HTTPException(status_code=400, detail=f"Invalid permission: {permission}")
    perm_mgr = get_permission_manager()
    perm_mgr.grant_permission(user_id, resource_id, perm_enum, granted_by=granted_by)
    return {"status": "granted", "user_id": user_id, "resource_id": resource_id, "permission": perm_enum.value}


@api_router.post("/permissions/revoke")
async def revoke_permission(request: Dict[str, Any]):
    """Revoke permission from a user for a resource (tool/skill/agent)."""
    user_id = request.get("user_id")
    resource_id = request.get("resource_id") or request.get("tool_name")
    permission = request.get("permission")
    if not user_id or not resource_id:
        raise HTTPException(status_code=400, detail="user_id and resource_id are required")
    perm_enum = None
    if permission is not None:
        try:
            perm_enum = Permission(permission)
        except Exception:
            raise HTTPException(status_code=400, detail=f"Invalid permission: {permission}")
    perm_mgr = get_permission_manager()
    perm_mgr.revoke_permission(user_id, resource_id, perm_enum)
    return {"status": "revoked", "user_id": user_id, "resource_id": resource_id, "permission": perm_enum.value if perm_enum else None}


# ==================== Agent Management ====================

@api_router.get("/agents")
async def list_agents(
    agent_type: Optional[str] = None,
    status: Optional[str] = None,
    limit: int = 100,
    offset: int = 0
):
    """List all agents"""
    agents = await _agent_manager.list_agents(agent_type, status, limit, offset)
    
    return {
        "agents": [
            {
                "id": a.id,
                "name": a.name,
                "agent_type": a.type,
                "status": a.status,
                "skills": a.skills,
                "tools": a.tools,
                "metadata": a.metadata
            }
            for a in agents
        ],
        "total": _agent_manager.get_agent_count().get("total", 0),
        "limit": limit,
        "offset": offset
    }


@api_router.post("/agents")
async def create_agent(request: AgentCreateRequest):
    """Create a new agent"""
    agent = await _agent_manager.create_agent(
        name=request.name,
        agent_type=request.agent_type,
        config=request.config,
        skills=request.skills,
        tools=request.tools,
        memory_config=request.memory_config,
        metadata=request.metadata,
    )
    return {
        "id": agent.id,
        "status": "created",
        "name": agent.name
    }


@api_router.get("/agents/{agent_id}")
async def get_agent(agent_id: str):
    """Get agent details"""
    agent = await _agent_manager.get_agent(agent_id)
    if not agent:
        raise HTTPException(status_code=404, detail=f"Agent {agent_id} not found")
    
    return {
        "id": agent.id,
        "name": agent.name,
        "agent_type": agent.type,
        "status": agent.status,
        "config": agent.config,
        "skills": agent.skills,
        "tools": agent.tools,
        "metadata": agent.metadata
    }


@api_router.put("/agents/{agent_id}")
async def update_agent(agent_id: str, request: AgentUpdateRequest):
    """Update agent"""
    try:
        agent = await _agent_manager.update_agent(
            agent_id,
            name=request.name,
            config=request.config,
            skills=request.skills,
            tools=request.tools,
            memory_config=request.memory_config,
            metadata=request.metadata
        )
    except PermissionError as e:
        raise HTTPException(status_code=403, detail=str(e))
    if not agent:
        raise HTTPException(status_code=404, detail=f"Agent {agent_id} not found")
    return {"status": "updated", "id": agent_id}


@api_router.delete("/agents/{agent_id}")
async def delete_agent(agent_id: str):
    """Delete agent"""
    try:
        success = await _agent_manager.delete_agent(agent_id)
    except PermissionError as e:
        raise HTTPException(status_code=403, detail=str(e))
    if not success:
        raise HTTPException(status_code=404, detail=f"Agent {agent_id} not found")
    return {"status": "deleted", "id": agent_id}


@api_router.post("/agents/{agent_id}/start")
async def start_agent(agent_id: str):
    """Start agent"""
    success = await _agent_manager.start_agent(agent_id)
    if not success:
        raise HTTPException(status_code=404, detail=f"Agent {agent_id} not found")
    return {"status": "started", "id": agent_id}


@api_router.post("/agents/{agent_id}/stop")
async def stop_agent(agent_id: str):
    """Stop agent"""
    success = await _agent_manager.stop_agent(agent_id)
    if not success:
        raise HTTPException(status_code=404, detail=f"Agent {agent_id} not found")
    return {"status": "stopped", "id": agent_id}


# ==================== Workspace Agent Management ====================


@api_router.get("/workspace/agents")
async def list_workspace_agents(
    agent_type: Optional[str] = None,
    status: Optional[str] = None,
    limit: int = 100,
    offset: int = 0,
):
    if not _workspace_agent_manager:
        return {"agents": [], "total": 0, "limit": limit, "offset": offset}
    agents = await _workspace_agent_manager.list_agents(agent_type, status, limit, offset)
    return {
        "agents": [
            {
                "id": a.id,
                "name": a.name,
                "agent_type": a.type,
                "status": a.status,
                "skills": a.skills,
                "tools": a.tools,
                "metadata": a.metadata,
            }
            for a in agents
        ],
        "total": _workspace_agent_manager.get_agent_count().get("total", 0),
        "limit": limit,
        "offset": offset,
    }


@api_router.post("/workspace/agents")
async def create_workspace_agent(request: AgentCreateRequest, http_request: Request):
    if not _workspace_agent_manager:
        raise HTTPException(status_code=503, detail="Workspace agent manager not available")
    try:
        agent = await _workspace_agent_manager.create_agent(
            name=request.name,
            agent_type=request.agent_type,
            config=request.config,
            skills=request.skills,
            tools=request.tools,
            memory_config=request.memory_config,
            metadata=request.metadata,
        )
        # Mark as pending verification (best-effort)
        try:
            await _workspace_agent_manager.update_agent(
                str(agent.id),
                metadata={
                    "verification": {
                        "status": "pending",
                        "updated_at": time.time(),
                        "source": "autosmoke",
                    }
                },
            )
        except Exception:
            pass
        # Auto-smoke (async, dedup): trigger on create/update to validate the full chain.
        try:
            if _execution_store is not None and _job_scheduler is not None:
                from core.harness.smoke import enqueue_autosmoke

                tenant_id = http_request.headers.get("X-AIPLAT-TENANT-ID", "ops_smoke")
                actor_id = http_request.headers.get("X-AIPLAT-ACTOR-ID", "admin")
                agent_id = str(agent.id)

                async def _on_complete(job_run: Dict[str, Any]):
                    st = str(job_run.get("status") or "")
                    ver = {
                        "status": "verified" if st == "completed" else "failed",
                        "updated_at": time.time(),
                        "source": "autosmoke",
                        "job_id": f"autosmoke-agent:{agent_id}",
                        "job_run_id": str(job_run.get("id") or ""),
                        "reason": str(job_run.get("error") or ""),
                    }
                    try:
                        await _workspace_agent_manager.update_agent(agent_id, metadata={"verification": ver})
                    except Exception:
                        pass

                await enqueue_autosmoke(
                    execution_store=_execution_store,
                    job_scheduler=_job_scheduler,
                    resource_type="agent",
                    resource_id=agent_id,
                    tenant_id=tenant_id or "ops_smoke",
                    actor_id=actor_id or "admin",
                    detail={"op": "create", "name": agent.name},
                    on_complete=_on_complete,
                )
        except Exception:
            pass
        return {"id": agent.id, "status": "created", "name": agent.name}
    except ValueError as e:
        raise HTTPException(status_code=409, detail=str(e))


@api_router.get("/workspace/agents/{agent_id}")
async def get_workspace_agent(agent_id: str):
    if not _workspace_agent_manager:
        raise HTTPException(status_code=503, detail="Workspace agent manager not available")
    agent = await _workspace_agent_manager.get_agent(agent_id)
    if not agent:
        raise HTTPException(status_code=404, detail=f"Agent {agent_id} not found")
    return {
        "id": agent.id,
        "name": agent.name,
        "agent_type": agent.type,
        "status": agent.status,
        "config": agent.config,
        "skills": agent.skills,
        "tools": agent.tools,
        "memory_config": agent.memory_config,
        "metadata": agent.metadata,
    }


@api_router.get("/workspace/agents/{agent_id}/sop")
async def get_workspace_agent_sop(agent_id: str):
    """Get agent SOP (markdown) from AGENT.md '## SOP' section."""
    if not _workspace_agent_manager:
        raise HTTPException(status_code=503, detail="Workspace agent manager not available")
    agent = await _workspace_agent_manager.get_agent(agent_id)
    if not agent:
        raise HTTPException(status_code=404, detail=f"Agent {agent_id} not found")
    data = await _workspace_agent_manager.get_agent_sop(agent_id)  # type: ignore[attr-defined]
    if not data:
        raise HTTPException(status_code=404, detail="SOP not found")
    return data


@api_router.put("/workspace/agents/{agent_id}/sop")
async def update_workspace_agent_sop(agent_id: str, request: dict):
    """Update agent SOP section in AGENT.md."""
    if not _workspace_agent_manager:
        raise HTTPException(status_code=503, detail="Workspace agent manager not available")
    agent = await _workspace_agent_manager.get_agent(agent_id)
    if not agent:
        raise HTTPException(status_code=404, detail=f"Agent {agent_id} not found")
    sop = (request or {}).get("sop")
    if sop is None:
        raise HTTPException(status_code=400, detail="Missing field: sop")
    try:
        ok = await _workspace_agent_manager.update_agent_sop(agent_id, str(sop))  # type: ignore[attr-defined]
    except PermissionError as e:
        raise HTTPException(status_code=403, detail=str(e))
    if not ok:
        raise HTTPException(status_code=500, detail="Failed to update SOP")
    return {"status": "updated", "id": agent_id}


@api_router.get("/workspace/agents/{agent_id}/execution-help")
async def get_workspace_agent_execution_help(agent_id: str):
    """Get execution input help/examples for agent."""
    if not _workspace_agent_manager:
        raise HTTPException(status_code=503, detail="Workspace agent manager not available")
    agent = await _workspace_agent_manager.get_agent(agent_id)
    if not agent:
        raise HTTPException(status_code=404, detail=f"Agent {agent_id} not found")
    data = await _workspace_agent_manager.get_agent_execution_help(agent_id)  # type: ignore[attr-defined]
    if not data:
        raise HTTPException(status_code=404, detail="Execution help not found")
    return data


@api_router.delete("/workspace/agents/{agent_id}")
async def delete_workspace_agent(agent_id: str):
    if not _workspace_agent_manager:
        raise HTTPException(status_code=503, detail="Workspace agent manager not available")
    ok = await _workspace_agent_manager.delete_agent(agent_id)
    if not ok:
        raise HTTPException(status_code=404, detail=f"Agent {agent_id} not found")
    return {"status": "deleted", "id": agent_id}


@api_router.post("/workspace/agents/{agent_id}/start")
async def start_workspace_agent(agent_id: str):
    if not _workspace_agent_manager:
        raise HTTPException(status_code=503, detail="Workspace agent manager not available")
    if _autosmoke_enforce():
        a = await _workspace_agent_manager.get_agent(agent_id)
        if not a:
            raise HTTPException(status_code=404, detail=f"Agent {agent_id} not found")
        if not _is_verified(getattr(a, "metadata", None)):
            raise HTTPException(status_code=403, detail="agent_unverified: smoke must pass before start")
    ok = await _workspace_agent_manager.start_agent(agent_id)
    if not ok:
        raise HTTPException(status_code=404, detail=f"Agent {agent_id} not found")
    return {"status": "started", "id": agent_id}


@api_router.post("/workspace/agents/{agent_id}/stop")
async def stop_workspace_agent(agent_id: str):
    if not _workspace_agent_manager:
        raise HTTPException(status_code=503, detail="Workspace agent manager not available")
    ok = await _workspace_agent_manager.stop_agent(agent_id)
    if not ok:
        raise HTTPException(status_code=404, detail=f"Agent {agent_id} not found")
    return {"status": "stopped", "id": agent_id}


@api_router.put("/workspace/agents/{agent_id}")
async def update_workspace_agent(agent_id: str, request: AgentUpdateRequest, http_request: Request):
    """Update workspace agent."""
    if not _workspace_agent_manager:
        raise HTTPException(status_code=503, detail="Workspace agent manager not available")
    agent = await _workspace_agent_manager.update_agent(
        agent_id,
        name=request.name,
        config=request.config,
        skills=request.skills,
        tools=request.tools,
        memory_config=request.memory_config,
        metadata=request.metadata,
    )
    if not agent:
        raise HTTPException(status_code=404, detail=f"Agent {agent_id} not found")
    # Mark as pending verification (best-effort)
    try:
        await _workspace_agent_manager.update_agent(
            str(agent_id),
            metadata={
                "verification": {
                    "status": "pending",
                    "updated_at": time.time(),
                    "source": "autosmoke",
                }
            },
        )
    except Exception:
        pass
    try:
        if _execution_store is not None and _job_scheduler is not None:
            from core.harness.smoke import enqueue_autosmoke

            tenant_id = http_request.headers.get("X-AIPLAT-TENANT-ID", "ops_smoke")
            actor_id = http_request.headers.get("X-AIPLAT-ACTOR-ID", "admin")
            aid = str(agent_id)

            async def _on_complete(job_run: Dict[str, Any]):
                st = str(job_run.get("status") or "")
                ver = {
                    "status": "verified" if st == "completed" else "failed",
                    "updated_at": time.time(),
                    "source": "autosmoke",
                    "job_id": f"autosmoke-agent:{aid}",
                    "job_run_id": str(job_run.get("id") or ""),
                    "reason": str(job_run.get("error") or ""),
                }
                try:
                    await _workspace_agent_manager.update_agent(aid, metadata={"verification": ver})
                except Exception:
                    pass

            await enqueue_autosmoke(
                execution_store=_execution_store,
                job_scheduler=_job_scheduler,
                resource_type="agent",
                resource_id=aid,
                tenant_id=tenant_id or "ops_smoke",
                actor_id=actor_id or "admin",
                detail={"op": "update"},
                on_complete=_on_complete,
            )
    except Exception:
        pass
    return {"status": "updated", "id": agent_id}


@api_router.get("/workspace/agents/{agent_id}/skills")
async def get_workspace_agent_skills(agent_id: str):
    """Get skills bound to workspace agent."""
    if not _workspace_agent_manager:
        raise HTTPException(status_code=503, detail="Workspace agent manager not available")
    agent = await _workspace_agent_manager.get_agent(agent_id)
    if not agent:
        raise HTTPException(status_code=404, detail=f"Agent {agent_id} not found")
    bindings = await _workspace_agent_manager.get_skill_bindings(agent_id)
    return {
        "skills": [
            {
                "skill_id": b.skill_id,
                "skill_name": b.skill_name,
                "skill_type": b.skill_type,
                "call_count": b.call_count,
                "success_rate": b.success_rate,
            }
            for b in bindings
        ],
        "skill_ids": agent.skills,
        "total": len(agent.skills),
    }


@api_router.post("/workspace/agents/{agent_id}/skills")
async def bind_workspace_agent_skills(agent_id: str, request: dict):
    """Bind skills to workspace agent."""
    if not _workspace_agent_manager:
        raise HTTPException(status_code=503, detail="Workspace agent manager not available")
    agent = await _workspace_agent_manager.get_agent(agent_id)
    if not agent:
        raise HTTPException(status_code=404, detail=f"Agent {agent_id} not found")
    skill_ids = request.get("skill_ids", [])
    if skill_ids:
        await _workspace_agent_manager.bind_skills(agent_id, skill_ids)
    return {"status": "bound", "skill_ids": skill_ids}


@api_router.delete("/workspace/agents/{agent_id}/skills/{skill_id}")
async def unbind_workspace_agent_skill(agent_id: str, skill_id: str):
    """Unbind skill from workspace agent."""
    if not _workspace_agent_manager:
        raise HTTPException(status_code=503, detail="Workspace agent manager not available")
    agent = await _workspace_agent_manager.get_agent(agent_id)
    if not agent:
        raise HTTPException(status_code=404, detail=f"Agent {agent_id} not found")
    await _workspace_agent_manager.unbind_skill(agent_id, skill_id)
    return {"status": "unbound"}


@api_router.get("/workspace/agents/{agent_id}/tools")
async def get_workspace_agent_tools(agent_id: str):
    """Get tools bound to workspace agent."""
    if not _workspace_agent_manager:
        raise HTTPException(status_code=503, detail="Workspace agent manager not available")
    agent = await _workspace_agent_manager.get_agent(agent_id)
    if not agent:
        raise HTTPException(status_code=404, detail=f"Agent {agent_id} not found")
    bindings = await _workspace_agent_manager.get_tool_bindings(agent_id)
    return {
        "tools": [
            {
                "tool_id": b.tool_id,
                "tool_name": b.tool_name,
                "tool_type": b.tool_type,
                "call_count": b.call_count,
                "success_rate": b.success_rate,
            }
            for b in bindings
        ],
        "tool_ids": agent.tools,
        "total": len(agent.tools),
    }


@api_router.post("/workspace/agents/{agent_id}/tools")
async def bind_workspace_agent_tools(agent_id: str, request: dict):
    """Bind tools to workspace agent."""
    if not _workspace_agent_manager:
        raise HTTPException(status_code=503, detail="Workspace agent manager not available")
    agent = await _workspace_agent_manager.get_agent(agent_id)
    if not agent:
        raise HTTPException(status_code=404, detail=f"Agent {agent_id} not found")
    tool_ids = request.get("tool_ids", [])
    if tool_ids:
        await _workspace_agent_manager.bind_tools(agent_id, tool_ids)
    return {"status": "bound", "tool_ids": tool_ids}


@api_router.delete("/workspace/agents/{agent_id}/tools/{tool_id}")
async def unbind_workspace_agent_tool(agent_id: str, tool_id: str):
    """Unbind tool from workspace agent."""
    if not _workspace_agent_manager:
        raise HTTPException(status_code=503, detail="Workspace agent manager not available")
    agent = await _workspace_agent_manager.get_agent(agent_id)
    if not agent:
        raise HTTPException(status_code=404, detail=f"Agent {agent_id} not found")
    await _workspace_agent_manager.unbind_tool(agent_id, tool_id)
    return {"status": "unbound"}


@api_router.post("/workspace/agents/{agent_id}/execute")
async def execute_workspace_agent(agent_id: str, request: dict, http_request: Request):
    """Execute workspace agent."""
    if not _workspace_agent_manager:
        raise HTTPException(status_code=503, detail="Workspace agent manager not available")
    agent = await _workspace_agent_manager.get_agent(agent_id)
    if not agent:
        raise HTTPException(status_code=404, detail=f"Agent {agent_id} not found")
    harness = get_harness()
    payload = _inject_http_request_context(dict(request or {}), http_request, entrypoint="api")
    deny = await _rbac_guard(http_request=http_request, payload=payload, action="execute", resource_type="agent", resource_id=str(agent_id))
    if deny:
        return deny
    ctx0 = payload.get("context") if isinstance(payload.get("context"), dict) else {}
    user_id = payload.get("user_id") or (ctx0.get("actor_id") if isinstance(ctx0, dict) else None) or "system"
    session_id = payload.get("session_id") or (ctx0.get("session_id") if isinstance(ctx0, dict) else None) or "default"
    exec_req = ExecutionRequest(
        kind="agent",
        target_id=agent_id,
        payload=payload,
        user_id=str(user_id),
        session_id=str(session_id),
    )
    result = await harness.execute(exec_req)
    resp = _wrap_execution_result_as_run_summary(result)
    try:
        await _audit_execute(http_request=http_request, payload=payload, resource_type="agent", resource_id=str(agent_id), resp=resp)
    except Exception:
        pass
    return JSONResponse(status_code=200 if resp.get("ok") else int(getattr(result, "http_status", 500) or 500), content=resp)


@api_router.get("/workspace/agents/{agent_id}/history")
async def get_workspace_agent_history(agent_id: str, limit: int = 100, offset: int = 0):
    """Get workspace agent execution history."""
    if _execution_store:
        history, total = await _execution_store.list_agent_history(agent_id, limit=limit, offset=offset)
        return {"history": history, "total": total}
    history = _agent_history.get(agent_id, [])
    history = history[offset:offset + limit]
    return {"history": history, "total": len(_agent_history.get(agent_id, []))}


@api_router.get("/workspace/agents/{agent_id}/versions")
async def get_workspace_agent_versions(agent_id: str):
    """Get workspace agent versions."""
    if not _workspace_agent_manager:
        raise HTTPException(status_code=503, detail="Workspace agent manager not available")
    agent = await _workspace_agent_manager.get_agent(agent_id)
    if not agent:
        raise HTTPException(status_code=404, detail=f"Agent {agent_id} not found")
    versions = await _workspace_agent_manager.get_versions(agent_id)
    return {
        "agent_id": agent_id,
        "versions": [
            {"version": v.version, "status": v.status, "created_at": v.created_at.isoformat(), "changes": v.changes}
            for v in versions
        ],
    }


@api_router.post("/workspace/agents/{agent_id}/versions")
async def create_workspace_agent_version(agent_id: str, request: dict):
    """Create new workspace agent version."""
    if not _workspace_agent_manager:
        raise HTTPException(status_code=503, detail="Workspace agent manager not available")
    changes = (request or {}).get("changes", "")
    version = await _workspace_agent_manager.create_version(agent_id, changes)
    if not version:
        raise HTTPException(status_code=404, detail=f"Agent {agent_id} not found")
    return {"version": version.version, "status": version.status, "created_at": version.created_at.isoformat(), "changes": version.changes}


@api_router.post("/workspace/agents/{agent_id}/versions/{version}/rollback")
async def rollback_workspace_agent_version(agent_id: str, version: str):
    """Rollback workspace agent to specific version."""
    if not _workspace_agent_manager:
        raise HTTPException(status_code=503, detail="Workspace agent manager not available")
    ok = await _workspace_agent_manager.rollback_version(agent_id, version)
    if not ok:
        raise HTTPException(status_code=404, detail=f"Agent or version {version} not found")
    return {"status": "rolled_back", "version": version}


@api_router.get("/agents/{agent_id}/skills")
async def get_agent_skills(agent_id: str):
    """Get skills bound to agent"""
    agent = await _agent_manager.get_agent(agent_id)
    if not agent:
        raise HTTPException(status_code=404, detail=f"Agent {agent_id} not found")
    bindings = await _agent_manager.get_skill_bindings(agent_id)
    return {
        "skills": [
            {
                "skill_id": b.skill_id,
                "skill_name": b.skill_name,
                "skill_type": b.skill_type,
                "call_count": b.call_count,
                "success_rate": b.success_rate,
            }
            for b in bindings
        ],
        "skill_ids": agent.skills,
        "total": len(agent.skills)
    }


@api_router.post("/agents/{agent_id}/skills")
async def bind_agent_skills(agent_id: str, request: dict):
    """Bind skills to agent"""
    agent = await _agent_manager.get_agent(agent_id)
    if not agent:
        raise HTTPException(status_code=404, detail=f"Agent {agent_id} not found")
    skill_ids = request.get("skill_ids", [])
    if skill_ids:
        await _agent_manager.bind_skills(agent_id, skill_ids)
    return {"status": "bound", "skill_ids": skill_ids}


@api_router.delete("/agents/{agent_id}/skills/{skill_id}")
async def unbind_agent_skill(agent_id: str, skill_id: str):
    """Unbind skill from agent"""
    agent = await _agent_manager.get_agent(agent_id)
    if not agent:
        raise HTTPException(status_code=404, detail=f"Agent {agent_id} not found")
    await _agent_manager.unbind_skill(agent_id, skill_id)
    return {"status": "unbound"}


@api_router.get("/agents/{agent_id}/tools")
async def get_agent_tools(agent_id: str):
    """Get tools bound to agent"""
    agent = await _agent_manager.get_agent(agent_id)
    if not agent:
        raise HTTPException(status_code=404, detail=f"Agent {agent_id} not found")
    bindings = await _agent_manager.get_tool_bindings(agent_id)
    return {
        "tools": [
            {
                "tool_id": b.tool_id,
                "tool_name": b.tool_name,
                "tool_type": b.tool_type,
                "call_count": b.call_count,
                "success_rate": b.success_rate,
            }
            for b in bindings
        ],
        "tool_ids": agent.tools,
        "total": len(agent.tools)
    }


@api_router.post("/agents/{agent_id}/tools")
async def bind_agent_tools(agent_id: str, request: dict):
    """Bind tools to agent"""
    agent = await _agent_manager.get_agent(agent_id)
    if not agent:
        raise HTTPException(status_code=404, detail=f"Agent {agent_id} not found")
    tool_ids = request.get("tool_ids", [])
    if tool_ids:
        await _agent_manager.bind_tools(agent_id, tool_ids)
    return {"status": "bound", "tool_ids": tool_ids}


@api_router.delete("/agents/{agent_id}/tools/{tool_id}")
async def unbind_agent_tool(agent_id: str, tool_id: str):
    """Unbind tool from agent"""
    agent = await _agent_manager.get_agent(agent_id)
    if not agent:
        raise HTTPException(status_code=404, detail=f"Agent {agent_id} not found")
    await _agent_manager.unbind_tool(agent_id, tool_id)
    return {"status": "unbound"}


@api_router.post("/agents/{agent_id}/execute")
async def execute_agent(agent_id: str, request: dict, http_request: Request):
    """Execute agent"""
    harness = get_harness()
    payload = _inject_http_request_context(dict(request or {}), http_request, entrypoint="api")
    deny = await _rbac_guard(http_request=http_request, payload=payload, action="execute", resource_type="agent", resource_id=str(agent_id))
    if deny:
        return deny
    ctx0 = payload.get("context") if isinstance(payload.get("context"), dict) else {}
    user_id = payload.get("user_id") or (ctx0.get("actor_id") if isinstance(ctx0, dict) else None) or "system"
    session_id = payload.get("session_id") or (ctx0.get("session_id") if isinstance(ctx0, dict) else None) or "default"
    exec_req = ExecutionRequest(
        kind="agent",
        target_id=agent_id,
        payload=payload,
        user_id=str(user_id),
        session_id=str(session_id),
    )
    result = await harness.execute(exec_req)
    if not result.ok:
        resp = _wrap_execution_result_as_run_summary(result)
        try:
            await _audit_execute(http_request=http_request, payload=payload, resource_type="agent", resource_id=str(agent_id), resp=resp)
        except Exception:
            pass
        return JSONResponse(status_code=int(getattr(result, "http_status", 500) or 500), content=resp)
    # Minimal resume semantics: cache paused requests in memory
    try:
        payload = result.payload or {}
        if payload.get("status") in ("approval_required", "policy_denied"):
            exec_id = payload.get("execution_id")
            approval_id = (
                ((payload.get("metadata") or {}).get("approval") or {}).get("approval_request_id")
                if isinstance(payload.get("metadata"), dict)
                else None
            )
            loop_snapshot = (
                (payload.get("metadata") or {}).get("loop_state_snapshot")
                if isinstance(payload.get("metadata"), dict)
                else None
            )
            if exec_id:
                _paused_agent_executions[exec_id] = {
                    "agent_id": agent_id,
                    "request": request or {},
                    "user_id": (request or {}).get("user_id", "system"),
                    "session_id": (request or {}).get("session_id", "default"),
                    "approval_request_id": approval_id,
                    "loop_state_snapshot": loop_snapshot,
                    "created_at": datetime.utcnow().isoformat(),
                }
                # also expose via legacy in-memory execution lookup
                _agent_executions[exec_id] = payload
    except Exception:
        pass
    resp = _wrap_execution_result_as_run_summary(result)
    try:
        await _audit_execute(http_request=http_request, payload=payload, resource_type="agent", resource_id=str(agent_id), resp=resp)
    except Exception:
        pass
    return JSONResponse(status_code=200 if resp.get("ok") else int(getattr(result, "http_status", 500) or 500), content=resp)


@api_router.post("/agents/executions/{execution_id}/resume")
async def resume_agent_execution(execution_id: str, request: dict):
    """
    Minimal resume: re-run the original execution request after approval is granted.

    Notes:
    - Phase 3 does not checkpoint loop state; resume is implemented as "replay from start".
    - Requires the paused execution to be present in _paused_agent_executions (in-memory).
    """
    paused = _paused_agent_executions.get(execution_id)
    agent_id = None
    original_request = None
    approval_id = None

    if paused:
        agent_id = paused.get("agent_id")
        original_request = paused.get("request") or {}
        approval_id = paused.get("approval_request_id")
    else:
        # Fallback: recover from ExecutionStore after server restart
        if not _execution_store:
            raise HTTPException(status_code=404, detail="Paused execution not found (no in-memory state and no store)")
        rec = await _execution_store.get_agent_execution(execution_id)
        if not rec:
            raise HTTPException(status_code=404, detail="Paused execution not found (execution not in store)")
        meta = rec.get("metadata") if isinstance(rec.get("metadata"), dict) else {}
        kr = (meta or {}).get("kernel_resume") if isinstance(meta, dict) else None
        if not isinstance(kr, dict):
            raise HTTPException(status_code=409, detail="Execution found but has no resumable payload")
        agent_id = rec.get("agent_id")
        original_request = {
            "messages": kr.get("messages", []),
            "context": kr.get("context", {}),
            "session_id": kr.get("session_id", "default"),
            "user_id": kr.get("user_id", "system"),
        }
        approval_id = ((meta or {}).get("approval") or {}).get("approval_request_id") if isinstance((meta or {}).get("approval"), dict) else None

    if not agent_id or not isinstance(original_request, dict):
        raise HTTPException(status_code=500, detail="Invalid paused execution record")

    # If there is an approval request, ensure it is resolved/approved
    if approval_id:
        if not _approval_manager:
            raise HTTPException(status_code=503, detail="ApprovalManager not initialized")
        ar = _approval_manager.get_request(approval_id)
        if not ar:
            raise HTTPException(status_code=404, detail=f"Approval request not found: {approval_id}")
        from core.harness.infrastructure.approval.types import RequestStatus
        if ar.status not in (RequestStatus.APPROVED, RequestStatus.AUTO_APPROVED):
            raise HTTPException(status_code=409, detail=f"Approval not granted: status={ar.status.value}")

    # Prefer checkpointed resume when available (Phase 3.5):
    # If we have a loop snapshot, pass it down and let HarnessIntegration run from that state.
    loop_snapshot = None
    try:
        # try from cached paused entry first
        loop_snapshot = paused.get("loop_state_snapshot") if paused else None
        # fallback: read from persisted agent execution record
        if loop_snapshot is None and _execution_store:
            rec = await _execution_store.get_agent_execution(execution_id)
            meta = (rec or {}).get("metadata") if isinstance((rec or {}).get("metadata"), dict) else None
            loop_snapshot = (meta or {}).get("loop_state_snapshot") if isinstance(meta, dict) else None
    except Exception:
        loop_snapshot = None

    harness = get_harness()
    payload = dict(original_request or {})
    if loop_snapshot is not None:
        payload["_resume_loop_state"] = loop_snapshot

    exec_req = ExecutionRequest(
        kind="agent",
        target_id=agent_id,
        payload=payload,
        user_id=original_request.get("user_id", "system"),
        session_id=original_request.get("session_id", "default"),
    )
    result = await harness.execute(exec_req)
    if not result.ok:
        raise HTTPException(status_code=result.http_status, detail=result.error or "Execution failed")

    # On successful resume, optionally drop the paused entry
    try:
        if (result.payload or {}).get("status") == "completed":
            _paused_agent_executions.pop(execution_id, None)
    except Exception:
        pass

    payload = result.payload or {}
    payload["resumed_from_execution_id"] = execution_id
    payload["approval_request_id"] = approval_id
    return payload


# ==================== Approval Management (Phase 3) ====================

@api_router.get("/approvals")
async def list_approvals(
    status: Optional[str] = None,
    tenant_id: Optional[str] = None,
    actor_id: Optional[str] = None,
    run_id: Optional[str] = None,
    operation: Optional[str] = None,
    user_id: Optional[str] = None,
    include_related_counts: bool = False,
    order_by: str = "created_at",
    order_dir: str = "desc",
    limit: int = 100,
    offset: int = 0,
):
    """List approvals (store-backed)."""
    if not _execution_store:
        raise HTTPException(status_code=503, detail="ExecutionStore not initialized")
    return await _execution_store.list_approval_requests(
        status=status,
        user_id=user_id,
        tenant_id=tenant_id,
        actor_id=actor_id,
        run_id=run_id,
        operation=operation,
        include_related_counts=include_related_counts,
        order_by=order_by,
        order_dir=order_dir,
        limit=limit,
        offset=offset,
    )


@api_router.get("/approvals/pending")
async def list_pending_approvals(
    user_id: Optional[str] = None,
    order_by: str = "priority_score",
    order_dir: str = "desc",
    limit: int = 200,
    offset: int = 0,
):
    """List pending approval requests (in-memory)."""
    if not _approval_manager:
        raise HTTPException(status_code=503, detail="ApprovalManager not initialized")
    # Prefer store-backed listing (survives restarts) and enrich with related counts.
    if _execution_store:
        try:
            res = await _execution_store.list_approval_requests(
                status="pending",
                user_id=user_id,
                include_related_counts=True,
                order_by=order_by,
                order_dir=order_dir,
                limit=limit,
                offset=offset,
            )
            return res
        except Exception:
            pass

    items = _approval_manager.get_pending_requests(user_id=user_id)
    out = []
    for r in items:
        out.append(
            {
                "request_id": r.request_id,
                "user_id": r.user_id,
                "operation": r.operation,
                "status": r.status.value,
                "rule_id": r.rule_id,
                "rule_type": r.rule_type.value if r.rule_type else None,
                "is_first_time": r.is_first_time,
                "created_at": r.created_at.isoformat(),
                "expires_at": r.expires_at.isoformat() if r.expires_at else None,
                "metadata": r.metadata,
                "related_counts": {"syscall_events": 0, "agent_executions": 0},
            }
        )
    return {"items": out, "total": len(out)}


@api_router.get("/approvals/{request_id}")
async def get_approval_request(request_id: str):
    if not _approval_manager:
        raise HTTPException(status_code=503, detail="ApprovalManager not initialized")
    r = _approval_manager.get_request(request_id)
    if not r:
        raise HTTPException(status_code=404, detail="Approval request not found")
    resp = {
        "request_id": r.request_id,
        "user_id": r.user_id,
        "operation": r.operation,
        "status": r.status.value,
        "details": r.details,
        "rule_id": r.rule_id,
        "rule_type": r.rule_type.value if r.rule_type else None,
        "is_first_time": r.is_first_time,
        "created_at": r.created_at.isoformat(),
        "updated_at": r.updated_at.isoformat(),
        "expires_at": r.expires_at.isoformat() if r.expires_at else None,
        "metadata": r.metadata,
        "result": {
            "decision": r.result.decision.value,
            "comments": r.result.comments,
            "approved_by": r.result.approved_by,
            "timestamp": r.result.timestamp.isoformat(),
        } if r.result else None,
    }

    # Attach audit linkages (best effort)
    if _execution_store:
        try:
            calls = await _execution_store.list_syscall_events(
                approval_request_id=request_id,
                limit=200,
                offset=0,
            )
        except Exception:
            calls = {"items": [], "total": 0}
        try:
            execs = await _execution_store.list_agent_executions_by_approval_request_id(
                request_id, limit=50, offset=0
            )
        except Exception:
            execs = {"items": [], "total": 0}

        resp["related"] = {
            "agent_executions": execs,
            "syscall_events": calls,
        }
    return resp


@api_router.post("/approvals/{request_id}/replay")
async def replay_approval(request_id: str, request: dict, http_request: Request):
    """
    PR-08: Approval Hub replay

    - tool:* : replay blocked tool call with _approval_request_id injected
    - learning:* : re-run publish/rollback actions (status transitions only)
    """
    if not _approval_manager:
        raise HTTPException(status_code=503, detail="ApprovalManager not initialized")
    r = _approval_manager.get_request(request_id)
    if not r:
        raise HTTPException(status_code=404, detail="Approval request not found")
    from core.harness.infrastructure.approval.types import RequestStatus

    if r.status not in (RequestStatus.APPROVED, RequestStatus.AUTO_APPROVED):
        raise HTTPException(status_code=409, detail=f"not_approved:{r.status.value}")

    op = str(r.operation or "")
    meta = r.metadata if isinstance(r.metadata, dict) else {}
    opctx = meta.get("operation_context") if isinstance(meta.get("operation_context"), dict) else {}

    # Replay tool call (best-effort).
    if op.startswith("tool:"):
        tool_name = op.split(":", 1)[1]
        tool_args = opctx.get("args") if isinstance(opctx, dict) else None
        tool_args = dict(tool_args) if isinstance(tool_args, dict) else {}
        tool_args["_approval_request_id"] = str(request_id)

        ctx = {
            "tenant_id": meta.get("tenant_id"),
            "actor_id": meta.get("actor_id") or r.user_id,
            "actor_role": meta.get("actor_role"),
            "session_id": meta.get("session_id"),
            "entrypoint": "approval_hub",
            "source": "approval_hub",
        }
        payload = {"input": tool_args, "context": ctx}

        harness = get_harness()
        exec_req = ExecutionRequest(
            kind="tool",
            target_id=str(tool_name),
            payload=payload,
            user_id=str(ctx.get("actor_id") or "system"),
            session_id=str(ctx.get("session_id") or "default"),
            run_id=str(meta.get("run_id") or new_prefixed_id("run")),
        )
        result = await harness.execute(exec_req)
        resp = _wrap_execution_result_as_run_summary(result)
        return JSONResponse(status_code=200, content=resp)

    # Replay learning release transitions.
    if op in ("learning:publish_release", "learning:rollback_release"):
        candidate_id = meta.get("candidate_id")
        if not isinstance(candidate_id, str) or not candidate_id:
            raise HTTPException(status_code=400, detail="missing_candidate_id")
        if op == "learning:publish_release":
            return await publish_release_candidate(
                candidate_id=str(candidate_id),
                request={"require_approval": True, "approval_request_id": str(request_id), "user_id": r.user_id},
            )
        return await rollback_release_candidate(
            candidate_id=str(candidate_id),
            request={"require_approval": True, "approval_request_id": str(request_id), "user_id": r.user_id},
        )

    raise HTTPException(status_code=400, detail=f"unsupported_operation:{op}")


@api_router.get("/approvals/{request_id}/audit")
async def get_approval_audit(request_id: str):
    """Return approval + related syscall events + related agent executions."""
    approval = await get_approval_request(request_id)
    return approval


# ==================== Syscall Events (Diagnostics) ====================


@api_router.get("/syscalls/events")
async def list_syscall_events(
    limit: int = 100,
    offset: int = 0,
    trace_id: Optional[str] = None,
    run_id: Optional[str] = None,
    kind: Optional[str] = None,
    name: Optional[str] = None,
    status: Optional[str] = None,
    error_contains: Optional[str] = None,
    error_code: Optional[str] = None,
    target_type: Optional[str] = None,
    target_id: Optional[str] = None,
    approval_request_id: Optional[str] = None,
    span_id: Optional[str] = None,
):
    if not _execution_store:
        raise HTTPException(status_code=503, detail="ExecutionStore not initialized")
    return await _execution_store.list_syscall_events(
        limit=limit,
        offset=offset,
        trace_id=trace_id,
        run_id=run_id,
        kind=kind,
        name=name,
        status=status,
        error_contains=error_contains,
        error_code=error_code,
        target_type=target_type,
        target_id=target_id,
        approval_request_id=approval_request_id,
        span_id=span_id,
    )


@api_router.get("/syscalls/stats")
async def get_syscall_stats(
    window_hours: int = 24,
    top_n: int = 10,
    kind: Optional[str] = None,
):
    if not _execution_store:
        raise HTTPException(status_code=503, detail="ExecutionStore not initialized")
    return await _execution_store.get_syscall_event_stats(window_hours=window_hours, top_n=top_n, kind=kind)


# ==================== Runs (Platform Execution Contract) ====================


@api_router.get("/runs/{run_id}")
async def get_run(run_id: str):
    if not _execution_store:
        raise HTTPException(status_code=503, detail="ExecutionStore not initialized")
    run = await _execution_store.get_run_summary(run_id=str(run_id))
    if not run:
        raise HTTPException(status_code=404, detail="run_not_found")
    # PR-03 + PR-02: return unified RunSummary v2 (but keep extra fields like target_type/target_id).
    legacy_status = run.get("status")
    err_code = run.get("error_code")
    try:
        if isinstance(run.get("error"), dict) and (run.get("error") or {}).get("code"):
            err_code = (run.get("error") or {}).get("code")
    except Exception:
        pass
    status2 = _normalize_run_status_v2(ok=str(legacy_status) == "completed", legacy_status=legacy_status, error_code=err_code)
    # ok: treat queued/accepted/running as ok (no error), but waiting_approval carries error
    ok2 = status2 not in {RunStatus.failed.value, RunStatus.aborted.value, RunStatus.timeout.value, RunStatus.waiting_approval.value}
    err_obj = None
    if not ok2:
        err_obj = _normalize_run_error(
            code=err_code or (run.get("error") or {}).get("code") if isinstance(run.get("error"), dict) else None,
            message=run.get("error_message") or (run.get("error") or {}).get("message") if isinstance(run.get("error"), dict) else None,
            detail=(run.get("error") or {}).get("detail") if isinstance(run.get("error"), dict) else None,
        )
    resp = dict(run)
    resp["ok"] = ok2
    resp["legacy_status"] = legacy_status
    resp["status"] = status2
    resp["error"] = None if ok2 else err_obj
    resp["output"] = run.get("output")
    return resp


@api_router.get("/runs/{run_id}/events")
async def list_run_events(run_id: str, after_seq: int = 0, limit: int = 200):
    if not _execution_store:
        raise HTTPException(status_code=503, detail="ExecutionStore not initialized")
    return await _execution_store.list_run_events(run_id=str(run_id), after_seq=int(after_seq or 0), limit=int(limit or 200))


# ==================== Audit Logs (enterprise governance) ====================


@api_router.get("/audit/logs")
async def list_audit_logs(
    tenant_id: Optional[str] = None,
    actor_id: Optional[str] = None,
    action: Optional[str] = None,
    resource_type: Optional[str] = None,
    resource_id: Optional[str] = None,
    request_id: Optional[str] = None,
    run_id: Optional[str] = None,
    trace_id: Optional[str] = None,
    status: Optional[str] = None,
    created_after: Optional[float] = None,
    created_before: Optional[float] = None,
    limit: int = 100,
    offset: int = 0,
):
    if not _execution_store:
        raise HTTPException(status_code=503, detail="ExecutionStore not initialized")
    return await _execution_store.list_audit_logs(
        tenant_id=tenant_id,
        actor_id=actor_id,
        action=action,
        resource_type=resource_type,
        resource_id=resource_id,
        request_id=request_id,
        run_id=run_id,
        trace_id=trace_id,
        status=status,
        created_after=created_after,
        created_before=created_before,
        limit=limit,
        offset=offset,
    )


# ==================== Tenant Policies (policy-as-code) ====================


@api_router.get("/policies/tenants")
async def list_tenant_policies(limit: int = 100, offset: int = 0):
    if not _execution_store:
        raise HTTPException(status_code=503, detail="ExecutionStore not initialized")
    return await _execution_store.list_tenant_policies(limit=limit, offset=offset)


# PR-07: policy engine API aliases (tenant snapshot)
@api_router.get("/policy/snapshot")
async def get_policy_snapshot(tenant_id: str):
    if not _execution_store:
        raise HTTPException(status_code=503, detail="ExecutionStore not initialized")
    item = await _execution_store.get_tenant_policy(tenant_id=str(tenant_id))
    if not item:
        raise HTTPException(status_code=404, detail="tenant_policy_not_found")
    return item


@api_router.put("/policy/snapshot")
async def put_policy_snapshot(request: dict, http_request: Request):
    if not _execution_store:
        raise HTTPException(status_code=503, detail="ExecutionStore not initialized")
    tenant_id = (request or {}).get("tenant_id")
    policy = (request or {}).get("policy")
    version = (request or {}).get("version")
    if not tenant_id:
        raise HTTPException(status_code=400, detail="tenant_id is required")
    if not isinstance(policy, dict):
        raise HTTPException(status_code=400, detail="policy must be an object")
    deny = await _rbac_guard(http_request=http_request, payload=request if isinstance(request, dict) else None, action="policy_upsert", resource_type="tenant_policy", resource_id=str(tenant_id))
    if deny:
        return deny
    if version is not None:
        try:
            version = int(version)
        except Exception:
            raise HTTPException(status_code=400, detail="invalid version")
    return await _execution_store.upsert_tenant_policy(tenant_id=str(tenant_id), policy=policy, version=version)


@api_router.get("/policy/versions")
async def list_policy_versions(tenant_id: Optional[str] = None):
    """
    MVP：tenant_policies 仅保存最新 version，因此 versions 返回 [current]。
    后续可扩展为历史版本表 policy_snapshots。
    """
    if not _execution_store:
        raise HTTPException(status_code=503, detail="ExecutionStore not initialized")
    if tenant_id:
        item = await _execution_store.get_tenant_policy(tenant_id=str(tenant_id))
        if not item:
            return {"tenant_id": str(tenant_id), "versions": []}
        return {"tenant_id": str(tenant_id), "versions": [item.get("version")]}
    items = await _execution_store.list_tenant_policies(limit=200, offset=0)
    out = []
    for it in (items.get("items") or []):
        if isinstance(it, dict) and it.get("tenant_id"):
            out.append({"tenant_id": it.get("tenant_id"), "version": it.get("version")})
    return {"items": out}


@api_router.get("/policies/tenants/{tenant_id}")
async def get_tenant_policy(tenant_id: str):
    if not _execution_store:
        raise HTTPException(status_code=503, detail="ExecutionStore not initialized")
    item = await _execution_store.get_tenant_policy(tenant_id=str(tenant_id))
    if not item:
        raise HTTPException(status_code=404, detail="tenant_policy_not_found")
    return item


@api_router.put("/policies/tenants/{tenant_id}")
async def upsert_tenant_policy(tenant_id: str, request: dict, http_request: Request):
    if not _execution_store:
        raise HTTPException(status_code=503, detail="ExecutionStore not initialized")
    deny = await _rbac_guard(http_request=http_request, payload=request if isinstance(request, dict) else None, action="policy_upsert", resource_type="tenant_policy", resource_id=str(tenant_id))
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
        saved = await _execution_store.upsert_tenant_policy(tenant_id=str(tenant_id), policy=policy, version=version)
    except ValueError as e:
        if str(e) == "version_conflict":
            raise HTTPException(status_code=409, detail="version_conflict")
        raise
    # Audit (best-effort)
    try:
        actor0 = _rbac_actor_from_http(http_request, request if isinstance(request, dict) else None)
        await _execution_store.add_audit_log(
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

        await _record_changeset(
            name="tenant_policy_upsert",
            target_type="tenant_policy",
            target_id=str(tenant_id),
            args={"tenant_id": str(tenant_id), "prev_version": int(version) if isinstance(version, int) else None},
            result={
                "version": saved.get("version") if isinstance(saved, dict) else None,
                "policy_sha256": hashlib.sha256(json.dumps(policy, sort_keys=True).encode("utf-8")).hexdigest(),
            },
            user_id=str((request or {}).get("actor_id") or "admin"),
        )
    except Exception:
        pass
    return saved


@api_router.get("/policies/tenants/{tenant_id}/evaluate-tool")
async def evaluate_tenant_tool_policy(tenant_id: str, tool_name: str):
    """
    Evaluate a single tool against tenant policy (best-effort).
    Returns: allow | deny | approval_required with policy_version and matched rule.
    """
    if not _execution_store:
        raise HTTPException(status_code=503, detail="ExecutionStore not initialized")
    item = await _execution_store.get_tenant_policy(tenant_id=str(tenant_id))
    if not item:
        raise HTTPException(status_code=404, detail="tenant_policy_not_found")
    policy = item.get("policy") if isinstance(item, dict) else {}
    tool_policy = policy.get("tool_policy") if isinstance(policy, dict) else None
    deny_tools = tool_policy.get("deny_tools") if isinstance(tool_policy, dict) and isinstance(tool_policy.get("deny_tools"), list) else []
    approval_tools = (
        tool_policy.get("approval_required_tools")
        if isinstance(tool_policy, dict) and isinstance(tool_policy.get("approval_required_tools"), list)
        else []
    )
    decision = "allow"
    matched = None
    if str(tool_name) in deny_tools:
        decision = "deny"
        matched = "tool_policy.deny_tools"
    elif str(tool_name) in approval_tools:
        decision = "approval_required"
        matched = "tool_policy.approval_required_tools"
    return {
        "tenant_id": str(tenant_id),
        "tool_name": str(tool_name),
        "decision": decision,
        "policy_version": item.get("version"),
        "matched_rule": matched,
    }


@api_router.post("/runs/{run_id}/wait")
async def wait_run(run_id: str, request: dict):
    """
    Long-poll run events until terminal state or timeout.
    Body:
      { "timeout_ms": 30000, "after_seq": 0 }
    """
    if not _execution_store:
        raise HTTPException(status_code=503, detail="ExecutionStore not initialized")
    timeout_ms = int((request or {}).get("timeout_ms") or 30000)
    after_seq = int((request or {}).get("after_seq") or 0)
    deadline = time.time() + max(1, timeout_ms) / 1000.0

    # quick check
    run = await _execution_store.get_run_summary(run_id=str(run_id))
    if not run:
        raise HTTPException(status_code=404, detail="run_not_found")

    last_seq = after_seq
    events: list = []
    done = False

    while time.time() < deadline:
        batch = await _execution_store.list_run_events(run_id=str(run_id), after_seq=last_seq, limit=200)
        new_events = batch.get("items") or []
        if new_events:
            events.extend(new_events)
            last_seq = int(batch.get("last_seq") or last_seq)
            if any(e.get("type") in {"run_end", "approval_requested"} for e in new_events):
                done = True
                break
        # refresh run status (best-effort)
        run = await _execution_store.get_run_summary(run_id=str(run_id)) or run
        # done when reaching terminal or waiting_approval (paused)
        legacy = str(run.get("status") or "")
        err_code = run.get("error_code")
        try:
            if isinstance(run.get("error"), dict) and (run.get("error") or {}).get("code"):
                err_code = (run.get("error") or {}).get("code")
        except Exception:
            pass
        st2 = _normalize_run_status_v2(ok=legacy == "completed", legacy_status=legacy, error_code=err_code)
        if st2 in {RunStatus.completed.value, RunStatus.failed.value, RunStatus.aborted.value, RunStatus.timeout.value, RunStatus.waiting_approval.value}:
            done = True
            break
        await asyncio.sleep(0.5)

    # normalize run to v2 contract
    legacy_status = run.get("status")
    err_code = run.get("error_code")
    try:
        if isinstance(run.get("error"), dict) and (run.get("error") or {}).get("code"):
            err_code = (run.get("error") or {}).get("code")
    except Exception:
        pass
    status2 = _normalize_run_status_v2(ok=str(legacy_status) == "completed", legacy_status=legacy_status, error_code=err_code)
    ok2 = status2 not in {RunStatus.failed.value, RunStatus.aborted.value, RunStatus.timeout.value, RunStatus.waiting_approval.value}
    err_obj = None
    if not ok2:
        err_obj = _normalize_run_error(
            code=err_code or (run.get("error") or {}).get("code") if isinstance(run.get("error"), dict) else None,
            message=run.get("error_message") or (run.get("error") or {}).get("message") if isinstance(run.get("error"), dict) else None,
            detail=(run.get("error") or {}).get("detail") if isinstance(run.get("error"), dict) else None,
        )
    run2 = dict(run)
    run2["ok"] = ok2
    run2["legacy_status"] = legacy_status
    run2["status"] = status2
    run2["error"] = None if ok2 else err_obj
    run2["output"] = run.get("output")

    return {"run": run2, "events": events, "after_seq": after_seq, "last_seq": last_seq, "done": done}


@api_router.post("/approvals/{request_id}/approve")
async def approve_request(request_id: str, request: dict, http_request: Request):
    if not _approval_manager:
        raise HTTPException(status_code=503, detail="ApprovalManager not initialized")
    deny = await _rbac_guard(http_request=http_request, payload=request if isinstance(request, dict) else None, action="approve", resource_type="approval_request", resource_id=str(request_id))
    if deny:
        return deny
    approved_by = (request or {}).get("approved_by", "admin")
    comments = (request or {}).get("comments", "")
    updated = await _approval_manager.approve(request_id=request_id, approved_by=approved_by, comments=comments)
    if not updated:
        raise HTTPException(status_code=404, detail="Approval request not found")
    # PR-08: run_events linkage (best-effort)
    try:
        meta = updated.metadata if isinstance(getattr(updated, "metadata", None), dict) else {}
        if _execution_store and meta.get("run_id"):
            await _execution_store.append_run_event(
                run_id=str(meta.get("run_id")),
                event_type="approval_approved",
                trace_id=None,
                tenant_id=str(meta.get("tenant_id")) if meta.get("tenant_id") else None,
                payload={"approval_request_id": str(request_id), "approved_by": str(approved_by), "comments": str(comments or "")},
            )
    except Exception:
        pass
    if _execution_store:
        try:
            actor0 = _rbac_actor_from_http(http_request, request if isinstance(request, dict) else None)
            await _execution_store.add_audit_log(
                action="approval_approve",
                status="ok",
                tenant_id=str(actor0.get("tenant_id") or "") or None,
                actor_id=str(approved_by),
                actor_role=str(actor0.get("actor_role") or "") or None,
                resource_type="approval_request",
                resource_id=str(request_id),
                detail={"comments": comments},
            )
        except Exception:
            pass
    return {"status": updated.status.value, "request_id": updated.request_id}


@api_router.post("/approvals/{request_id}/reject")
async def reject_request(request_id: str, request: dict, http_request: Request):
    if not _approval_manager:
        raise HTTPException(status_code=503, detail="ApprovalManager not initialized")
    deny = await _rbac_guard(http_request=http_request, payload=request if isinstance(request, dict) else None, action="reject", resource_type="approval_request", resource_id=str(request_id))
    if deny:
        return deny
    rejected_by = (request or {}).get("rejected_by", "admin")
    comments = (request or {}).get("comments", "")
    updated = await _approval_manager.reject(request_id=request_id, rejected_by=rejected_by, comments=comments)
    if not updated:
        raise HTTPException(status_code=404, detail="Approval request not found")
    # PR-08: run_events linkage (best-effort)
    try:
        meta = updated.metadata if isinstance(getattr(updated, "metadata", None), dict) else {}
        if _execution_store and meta.get("run_id"):
            await _execution_store.append_run_event(
                run_id=str(meta.get("run_id")),
                event_type="approval_rejected",
                trace_id=None,
                tenant_id=str(meta.get("tenant_id")) if meta.get("tenant_id") else None,
                payload={"approval_request_id": str(request_id), "rejected_by": str(rejected_by), "comments": str(comments or "")},
            )
    except Exception:
        pass
    if _execution_store:
        try:
            actor0 = _rbac_actor_from_http(http_request, request if isinstance(request, dict) else None)
            await _execution_store.add_audit_log(
                action="approval_reject",
                status="ok",
                tenant_id=str(actor0.get("tenant_id") or "") or None,
                actor_id=str(rejected_by),
                actor_role=str(actor0.get("actor_role") or "") or None,
                resource_type="approval_request",
                resource_id=str(request_id),
                detail={"comments": comments},
            )
        except Exception:
            pass
    return {"status": updated.status.value, "request_id": updated.request_id}


# ==================== Learning / Release Management (Phase 6) ====================


@api_router.get("/learning/artifacts")
async def list_learning_artifacts(
    target_type: Optional[str] = None,
    target_id: Optional[str] = None,
    kind: Optional[str] = None,
    status: Optional[str] = None,
    trace_id: Optional[str] = None,
    run_id: Optional[str] = None,
    limit: int = 50,
    offset: int = 0,
):
    """List learning_artifacts stored in ExecutionStore."""
    if not _execution_store:
        raise HTTPException(status_code=503, detail="ExecutionStore not initialized")
    res = await _execution_store.list_learning_artifacts(
        target_type=target_type,
        target_id=target_id,
        kind=kind,
        status=status,
        trace_id=trace_id,
        run_id=run_id,
        limit=limit,
        offset=offset,
    )
    return res


@api_router.get("/learning/artifacts/{artifact_id}")
async def get_learning_artifact(artifact_id: str):
    if not _execution_store:
        raise HTTPException(status_code=503, detail="ExecutionStore not initialized")
    art = await _execution_store.get_learning_artifact(artifact_id)
    if not art:
        raise HTTPException(status_code=404, detail="artifact_not_found")
    return art


@api_router.post("/learning/artifacts/{artifact_id}/status")
async def set_learning_artifact_status(artifact_id: str, request: dict):
    """Update artifact status + merge metadata (status transitions only)."""
    if not _execution_store:
        raise HTTPException(status_code=503, detail="ExecutionStore not initialized")
    from core.learning.manager import LearningManager

    status = (request or {}).get("status")
    if not isinstance(status, str) or not status:
        raise HTTPException(status_code=400, detail="missing_status")
    metadata_update = (request or {}).get("metadata_update") if isinstance((request or {}).get("metadata_update"), dict) else {}
    mgr = LearningManager(execution_store=_execution_store)
    await mgr.set_artifact_status(artifact_id=artifact_id, status=status, metadata_update=metadata_update)
    return {"status": "ok", "artifact_id": artifact_id, "new_status": status}


@api_router.post("/learning/autocapture")
async def autocapture_learning_suggestion(request: dict):
    """
    Roadmap-4 (minimal): create a reviewable learning artifact from one execution.

    Input:
      {
        "target_type": "agent|skill",
        "target_id": "...",
        "run_id": "...",          # optional
        "trace_id": "...",        # optional
        "reason": "optional human note"
      }
    Output: created LearningArtifact record.
    """
    if not _execution_store:
        raise HTTPException(status_code=503, detail="ExecutionStore not initialized")
    import time
    import uuid
    from core.learning.pipeline import summarize_syscall_events
    from core.learning.types import LearningArtifact, LearningArtifactKind, LearningArtifactStatus

    target_type = str((request or {}).get("target_type") or "").strip()
    target_id = str((request or {}).get("target_id") or "").strip()
    trace_id = (request or {}).get("trace_id")
    run_id = (request or {}).get("run_id")
    reason = (request or {}).get("reason") or ""
    if not target_type or not target_id:
        raise HTTPException(status_code=400, detail="target_type and target_id are required")
    if not trace_id and not run_id:
        raise HTTPException(status_code=400, detail="trace_id or run_id is required")

    # Collect syscall events
    events_res = await _execution_store.list_syscall_events(
        limit=500,
        offset=0,
        trace_id=str(trace_id) if trace_id else None,
        run_id=str(run_id) if run_id else None,
    )
    events = (events_res or {}).get("items") or []
    summary = summarize_syscall_events(events)

    # Collect execution record (best-effort)
    exec_rec: Optional[Dict[str, Any]] = None
    try:
        if target_type == "agent" and run_id:
            exec_rec = await _execution_store.get_agent_execution(str(run_id))
        if target_type == "skill" and run_id:
            exec_rec = await _execution_store.get_skill_execution(str(run_id))
    except Exception:
        exec_rec = None

    # Basic recommendations (best-effort, deterministic)
    failed = [e for e in events if str(e.get("status") or "").lower() in ("failed", "error")]
    top_failed = {}
    for e in failed:
        k = f"{e.get('kind')}:{e.get('name')}"
        top_failed[k] = top_failed.get(k, 0) + 1
    top_failed_list = sorted(top_failed.items(), key=lambda kv: kv[1], reverse=True)[:10]

    feedback = {
        "reason": str(reason),
        "execution": exec_rec or {},
        "syscalls_summary": summary,
        "top_failed_syscalls": [{"key": k, "count": v} for k, v in top_failed_list],
        "notes": [
            "该 artifact 仅用于审核/分析，不会自动改变线上行为。",
            "如需自动修复/沉淀为技能包，请基于该 artifact 人工生成 prompt_revision/skill_evolution 后再发布。",
        ],
    }

    artifact = LearningArtifact(
        artifact_id=f"auto-{uuid.uuid4().hex[:12]}",
        kind=LearningArtifactKind.FEEDBACK_SUMMARY,
        target_type=target_type,
        target_id=target_id,
        version=f"auto:{int(time.time())}",
        status=LearningArtifactStatus.DRAFT,
        trace_id=str(trace_id) if trace_id else None,
        run_id=str(run_id) if run_id else None,
        payload={"feedback": feedback},
        metadata={"source": "autocapture", "event_count": len(events)},
    )
    await _execution_store.upsert_learning_artifact(artifact.to_record())
    return await _execution_store.get_learning_artifact(artifact.artifact_id)


@api_router.post("/learning/autocapture/to_prompt_revision")
async def autocapture_to_prompt_revision(request: dict):
    """
    Roadmap-4 (minimal): convert a feedback_summary artifact into a draft prompt_revision,
    optionally wrapping it into a draft release_candidate.

    Input:
      {
        "artifact_id": "auto-xxx",
        "patch": {"prepend": "...", "append": "..."},   # optional; if absent auto-generated
        "priority": 0,                                   # optional (metadata)
        "exclusive_group": "auto",                       # optional (metadata)
        "create_release_candidate": false,               # optional
        "summary": "..."                                 # optional (for release_candidate)
      }
    """
    if not _execution_store:
        raise HTTPException(status_code=503, detail="ExecutionStore not initialized")
    import time
    import uuid
    from core.learning.types import LearningArtifact, LearningArtifactKind, LearningArtifactStatus

    artifact_id = str((request or {}).get("artifact_id") or "").strip()
    if not artifact_id:
        raise HTTPException(status_code=400, detail="artifact_id is required")
    src = await _execution_store.get_learning_artifact(artifact_id)
    if not src:
        raise HTTPException(status_code=404, detail="artifact_not_found")
    if src.get("kind") != "feedback_summary":
        raise HTTPException(status_code=400, detail="artifact_kind_must_be_feedback_summary")

    target_type = str(src.get("target_type") or "")
    target_id = str(src.get("target_id") or "")
    trace_id = src.get("trace_id")
    run_id = src.get("run_id")
    fb = (src.get("payload") or {}).get("feedback") if isinstance(src.get("payload"), dict) else None
    fb = fb if isinstance(fb, dict) else {}

    patch = (request or {}).get("patch") if isinstance((request or {}).get("patch"), dict) else None
    if patch is None:
        # Auto-generate a minimal prepend patch from feedback (deterministic, reviewable).
        top_failed = fb.get("top_failed_syscalls") if isinstance(fb.get("top_failed_syscalls"), list) else []
        lines = []
        reason = fb.get("reason")
        if isinstance(reason, str) and reason.strip():
            lines.append(f"【背景】{reason.strip()}")
        if top_failed:
            lines.append("【近期失败 syscall Top】")
            for x in top_failed[:10]:
                if not isinstance(x, dict):
                    continue
                k = x.get("key")
                c = x.get("count")
                if k:
                    lines.append(f"- {k}: {c}")
        lines.append("【要求】当执行失败时：优先给出可操作的下一步（包括需要的参数、检查点、以及可复现步骤）。")
        patch = {"prepend": "\n".join(lines)}

    pr_id = f"pr-auto-{uuid.uuid4().hex[:12]}"
    meta: Dict[str, Any] = {"source": "autocapture", "source_artifact_id": artifact_id}
    if (request or {}).get("priority") is not None:
        meta["priority"] = (request or {}).get("priority")
    if isinstance((request or {}).get("exclusive_group"), str) and (request or {}).get("exclusive_group"):
        meta["exclusive_group"] = (request or {}).get("exclusive_group")

    pr = LearningArtifact(
        artifact_id=pr_id,
        kind=LearningArtifactKind.PROMPT_REVISION,
        target_type=target_type,
        target_id=target_id,
        version=f"auto:{int(time.time())}",
        status=LearningArtifactStatus.DRAFT,
        trace_id=str(trace_id) if trace_id else None,
        run_id=str(run_id) if run_id else None,
        payload={"patch": patch},
        metadata=meta,
    )
    await _execution_store.upsert_learning_artifact(pr.to_record())

    out: Dict[str, Any] = {"prompt_revision": await _execution_store.get_learning_artifact(pr_id)}

    if bool((request or {}).get("create_release_candidate", False)):
        rc_id = f"rc-auto-{uuid.uuid4().hex[:12]}"
        summary = (request or {}).get("summary")
        if not isinstance(summary, str) or not summary.strip():
            summary = f"auto from {artifact_id}"
        rc = LearningArtifact(
            artifact_id=rc_id,
            kind=LearningArtifactKind.RELEASE_CANDIDATE,
            target_type=target_type,
            target_id=target_id,
            version=f"auto:{int(time.time())}",
            status=LearningArtifactStatus.DRAFT,
            trace_id=str(trace_id) if trace_id else None,
            run_id=str(run_id) if run_id else None,
            payload={"artifact_ids": [pr_id], "summary": str(summary)},
            metadata={"source": "autocapture", "source_artifact_id": artifact_id},
        )
        await _execution_store.upsert_learning_artifact(rc.to_record())
        out["release_candidate"] = await _execution_store.get_learning_artifact(rc_id)

    return out


@api_router.post("/learning/autocapture/to_skill_evolution")
async def autocapture_to_skill_evolution(request: dict):
    """
    Roadmap-4 (minimal): convert a feedback_summary into a draft skill_evolution suggestion artifact.

    Input:
      {
        "artifact_id": "auto-xxx",
        "suggestion": "...",                     # optional; if absent auto-generated
        "create_release_candidate": false,       # optional
        "summary": "..."                         # optional (release_candidate summary)
      }
    """
    if not _execution_store:
        raise HTTPException(status_code=503, detail="ExecutionStore not initialized")
    import time
    import uuid
    from core.learning.types import LearningArtifact, LearningArtifactKind, LearningArtifactStatus

    artifact_id = str((request or {}).get("artifact_id") or "").strip()
    if not artifact_id:
        raise HTTPException(status_code=400, detail="artifact_id is required")
    src = await _execution_store.get_learning_artifact(artifact_id)
    if not src:
        raise HTTPException(status_code=404, detail="artifact_not_found")
    if src.get("kind") != "feedback_summary":
        raise HTTPException(status_code=400, detail="artifact_kind_must_be_feedback_summary")

    target_type = str(src.get("target_type") or "")
    target_id = str(src.get("target_id") or "")
    trace_id = src.get("trace_id")
    run_id = src.get("run_id")
    fb = (src.get("payload") or {}).get("feedback") if isinstance(src.get("payload"), dict) else None
    fb = fb if isinstance(fb, dict) else {}

    suggestion = (request or {}).get("suggestion")
    if not isinstance(suggestion, str) or not suggestion.strip():
        top_failed = fb.get("top_failed_syscalls") if isinstance(fb.get("top_failed_syscalls"), list) else []
        lines = []
        if fb.get("reason"):
            lines.append(f"【来源】{fb.get('reason')}")
        lines.append("【建议】基于失败 syscall 归因，补充技能 SOP 的前置条件/参数校验/失败分支处理。")
        if top_failed:
            lines.append("【失败 syscall Top】")
            for x in top_failed[:10]:
                if isinstance(x, dict) and x.get("key"):
                    lines.append(f"- {x.get('key')}: {x.get('count')}")
        suggestion = "\n".join(lines)

    se_id = f"se-auto-{uuid.uuid4().hex[:12]}"
    se = LearningArtifact(
        artifact_id=se_id,
        kind=LearningArtifactKind.SKILL_EVOLUTION,
        target_type=target_type,
        target_id=target_id,
        version=f"auto:{int(time.time())}",
        status=LearningArtifactStatus.DRAFT,
        trace_id=str(trace_id) if trace_id else None,
        run_id=str(run_id) if run_id else None,
        payload={"suggestion": suggestion},
        metadata={"source": "autocapture", "source_artifact_id": artifact_id},
    )
    await _execution_store.upsert_learning_artifact(se.to_record())
    out: Dict[str, Any] = {"skill_evolution": await _execution_store.get_learning_artifact(se_id)}

    if bool((request or {}).get("create_release_candidate", False)):
        rc_id = f"rc-auto-{uuid.uuid4().hex[:12]}"
        summary = (request or {}).get("summary")
        if not isinstance(summary, str) or not summary.strip():
            summary = f"auto from {artifact_id}"
        rc = LearningArtifact(
            artifact_id=rc_id,
            kind=LearningArtifactKind.RELEASE_CANDIDATE,
            target_type=target_type,
            target_id=target_id,
            version=f"auto:{int(time.time())}",
            status=LearningArtifactStatus.DRAFT,
            trace_id=str(trace_id) if trace_id else None,
            run_id=str(run_id) if run_id else None,
            payload={"artifact_ids": [se_id], "summary": str(summary)},
            metadata={"source": "autocapture", "source_artifact_id": artifact_id},
        )
        await _execution_store.upsert_learning_artifact(rc.to_record())
        out["release_candidate"] = await _execution_store.get_learning_artifact(rc_id)

    return out


@api_router.post("/learning/releases/{candidate_id}/publish")
async def publish_release_candidate(candidate_id: str, request: dict):
    """
    Publish a release_candidate (status transitions only).

    Supports optional approval gate using existing ApprovalManager.
    """
    if not _execution_store:
        raise HTTPException(status_code=503, detail="ExecutionStore not initialized")
    from core.learning.manager import LearningManager
    from core.learning.release import require_publish_approval, is_approved
    from core.harness.infrastructure.approval.manager import ApprovalManager

    mgr = LearningManager(execution_store=_execution_store)
    approval_mgr = _approval_manager or ApprovalManager(execution_store=_execution_store)

    cand = await _execution_store.get_learning_artifact(candidate_id)
    if not cand:
        raise HTTPException(status_code=404, detail="candidate_not_found")
    if cand.get("kind") != "release_candidate":
        raise HTTPException(status_code=400, detail="not_a_release_candidate")

    # Gate: ensure involved targets are verified before publish (when enforcement enabled).
    try:
        targets: list[tuple[str, str]] = []
        if cand.get("target_type") and cand.get("target_id"):
            targets.append((str(cand.get("target_type")), str(cand.get("target_id"))))
        ids = (cand.get("payload") or {}).get("artifact_ids") if isinstance(cand.get("payload"), dict) else []
        if isinstance(ids, list):
            for aid in ids:
                if not isinstance(aid, str) or not aid:
                    continue
                a = await _execution_store.get_learning_artifact(aid)
                if isinstance(a, dict) and a.get("target_type") and a.get("target_id"):
                    targets.append((str(a.get("target_type")), str(a.get("target_id"))))
        # unique
        uniq = list({(t[0].lower(), t[1]) for t in targets})
        await _require_targets_verified(uniq)
    except HTTPException:
        raise
    except Exception:
        # fail-open if any unexpected parsing issues happen
        pass

    user_id = (request or {}).get("user_id") or "system"
    require_approval = bool((request or {}).get("require_approval", False))
    approval_request_id = (request or {}).get("approval_request_id")
    details = (request or {}).get("details") or ""

    if require_approval:
        if not approval_request_id:
            req_id = await require_publish_approval(
                approval_manager=approval_mgr,
                user_id=user_id,
                candidate_id=candidate_id,
                details=details,
            )
            return {"status": "approval_required", "approval_request_id": req_id}
        if not is_approved(approval_mgr, approval_request_id):
            raise HTTPException(status_code=409, detail="not_approved")

    now = __import__("time").time()
    meta_update = {"published_via": "core_api", "approval_request_id": approval_request_id, "published_at": now}
    expires_at = (request or {}).get("expires_at")
    ttl_seconds = (request or {}).get("ttl_seconds")
    if expires_at is not None:
        try:
            meta_update["expires_at"] = float(expires_at)
        except Exception:
            pass
    if ttl_seconds is not None:
        try:
            ttl = float(ttl_seconds)
            meta_update["ttl_seconds"] = ttl
            if "expires_at" not in meta_update:
                meta_update["expires_at"] = now + ttl
        except Exception:
            pass

    await mgr.set_artifact_status(artifact_id=candidate_id, status="published", metadata_update=meta_update)
    ids = (cand.get("payload") or {}).get("artifact_ids") if isinstance(cand.get("payload"), dict) else []
    if isinstance(ids, list):
        for aid in ids:
            if isinstance(aid, str) and aid:
                await mgr.set_artifact_status(artifact_id=aid, status="published", metadata_update={"published_by_candidate": candidate_id})
    # Best-effort: reflect publish into target skill metadata for runtime gating.
    try:
        if str(cand.get("target_type") or "").lower() == "skill" and cand.get("target_id"):
            sid = str(cand.get("target_id"))
            # Prefer workspace skills (this phase).
            target_skill = None
            if _workspace_skill_manager:
                target_skill = await _workspace_skill_manager.get_skill(sid)
            mgr2 = _workspace_skill_manager
            if not target_skill and _skill_manager:
                target_skill = await _skill_manager.get_skill(sid)
                mgr2 = _skill_manager
            if target_skill and mgr2:
                meta = getattr(target_skill, "metadata", None) if target_skill else None
                gov = meta.get("governance") if isinstance(meta, dict) and isinstance(meta.get("governance"), dict) else {}
                gov2 = dict(gov)
                gov2.update(
                    {
                        "status": "published",
                        "published_candidate_id": candidate_id,
                        "published_at": now,
                        "updated_at": now,
                    }
                )
                await mgr2.update_skill(sid, metadata={"governance": gov2})
    except Exception:
        pass
    return {"status": "published", "candidate_id": candidate_id, "approval_request_id": approval_request_id}


@api_router.post("/learning/releases/{candidate_id}/rollback")
async def rollback_release_candidate(candidate_id: str, request: dict):
    """
    Rollback a release_candidate (status transitions only).

    Supports optional approval gate (learning:rollback_release).
    """
    if not _execution_store:
        raise HTTPException(status_code=503, detail="ExecutionStore not initialized")
    from core.learning.manager import LearningManager
    from core.learning.release import require_rollback_approval, is_approved
    from core.harness.infrastructure.approval.manager import ApprovalManager

    mgr = LearningManager(execution_store=_execution_store)
    approval_mgr = _approval_manager or ApprovalManager(execution_store=_execution_store)

    cand = await _execution_store.get_learning_artifact(candidate_id)
    if not cand:
        raise HTTPException(status_code=404, detail="candidate_not_found")
    if cand.get("kind") != "release_candidate":
        raise HTTPException(status_code=400, detail="not_a_release_candidate")

    user_id = (request or {}).get("user_id") or "system"
    require_approval = bool((request or {}).get("require_approval", False))
    approval_request_id = (request or {}).get("approval_request_id")
    reason = (request or {}).get("reason") or ""

    if require_approval:
        if not approval_request_id:
            req_id = await require_rollback_approval(
                approval_manager=approval_mgr,
                user_id=user_id,
                candidate_id=candidate_id,
                regression_report_id=None,
                details=reason or "manual_rollback",
            )
            return {"status": "approval_required", "approval_request_id": req_id}
        if not is_approved(approval_mgr, approval_request_id):
            raise HTTPException(status_code=409, detail="not_approved")

    await mgr.set_artifact_status(
        artifact_id=candidate_id,
        status="rolled_back",
        metadata_update={"rolled_back_via": "core_api", "reason": reason, "approval_request_id": approval_request_id},
    )
    ids = (cand.get("payload") or {}).get("artifact_ids") if isinstance(cand.get("payload"), dict) else []
    if isinstance(ids, list):
        for aid in ids:
            if isinstance(aid, str) and aid:
                await mgr.set_artifact_status(artifact_id=aid, status="rolled_back", metadata_update={"rolled_back_by_candidate": candidate_id})

    # Best-effort: reflect rollback into target skill metadata for runtime gating.
    try:
        if str(cand.get("target_type") or "").lower() == "skill" and cand.get("target_id"):
            sid = str(cand.get("target_id"))
            target_skill = None
            mgr2 = None
            if _workspace_skill_manager:
                target_skill = await _workspace_skill_manager.get_skill(sid)
                mgr2 = _workspace_skill_manager
            if not target_skill and _skill_manager:
                target_skill = await _skill_manager.get_skill(sid)
                mgr2 = _skill_manager
            if target_skill and mgr2:
                meta = getattr(target_skill, "metadata", None) if target_skill else None
                gov = meta.get("governance") if isinstance(meta, dict) and isinstance(meta.get("governance"), dict) else {}
                gov2 = dict(gov)
                if gov2.get("published_candidate_id") == candidate_id:
                    gov2.pop("published_candidate_id", None)
                    gov2.pop("published_at", None)
                gov2.update({"status": "rolled_back", "rolled_back_candidate_id": candidate_id})
                await mgr2.update_skill(sid, metadata={"governance": gov2})
    except Exception:
        pass
    return {"status": "rolled_back", "candidate_id": candidate_id, "approval_request_id": approval_request_id}


@api_router.post("/learning/releases/expire")
async def expire_releases(request: dict):
    """Expire published release candidates based on metadata.expires_at (offline status transitions only)."""
    if not _execution_store:
        raise HTTPException(status_code=503, detail="ExecutionStore not initialized")
    from core.learning.manager import LearningManager

    mgr = LearningManager(execution_store=_execution_store)
    now = float((request or {}).get("now") or __import__("time").time())
    dry_run = bool((request or {}).get("dry_run", False))
    target_type = (request or {}).get("target_type")
    target_id = (request or {}).get("target_id")

    res = await _execution_store.list_learning_artifacts(target_type=target_type, target_id=target_id, kind="release_candidate", status="published", limit=2000, offset=0)
    items = res.get("items") or []
    rolled_back = []
    kept = []
    for cand in items:
        meta = cand.get("metadata") if isinstance(cand.get("metadata"), dict) else {}
        exp = meta.get("expires_at")
        try:
            exp_ts = float(exp) if exp is not None else None
        except Exception:
            exp_ts = None
        if exp_ts is None or exp_ts > now:
            kept.append(cand.get("artifact_id"))
            continue
        cid = cand.get("artifact_id")
        if not isinstance(cid, str) or not cid:
            continue
        if dry_run:
            rolled_back.append(cid)
            continue
        await mgr.set_artifact_status(artifact_id=cid, status="rolled_back", metadata_update={"rolled_back_via": "expire_releases", "rolled_back_at": now})
        rolled_back.append(cid)

    return {"now": now, "dry_run": dry_run, "rolled_back": rolled_back, "kept": kept}


@api_router.post("/learning/auto-rollback/regression")
async def api_auto_rollback_regression(request: dict):
    """HTTP wrapper for auto-rollback-regression (offline) used by management plane."""
    if not _execution_store:
        raise HTTPException(status_code=503, detail="ExecutionStore not initialized")
    if not _approval_manager:
        raise HTTPException(status_code=503, detail="ApprovalManager not initialized")
    from core.learning.autorollback import auto_rollback_regression

    agent_id = (request or {}).get("agent_id")
    if not isinstance(agent_id, str) or not agent_id:
        raise HTTPException(status_code=400, detail="missing_agent_id")

    return await auto_rollback_regression(
        store=_execution_store,
        approval_manager=_approval_manager,
        agent_id=agent_id,
        candidate_id=(request or {}).get("candidate_id"),
        baseline_candidate_id=(request or {}).get("baseline_candidate_id"),
        current_window=int((request or {}).get("current_window", 50) or 50),
        baseline_window=int((request or {}).get("baseline_window", 50) or 50),
        min_samples=int((request or {}).get("min_samples", 10) or 10),
        error_rate_delta_threshold=float((request or {}).get("error_rate_delta_threshold", 0.1) or 0.1),
        avg_duration_delta_threshold=(float((request or {}).get("avg_duration_delta_threshold")) if (request or {}).get("avg_duration_delta_threshold") is not None else None),
        link_baseline=bool((request or {}).get("link_baseline", False)),
        max_linked_evidence=int((request or {}).get("max_linked_evidence", 200) or 200),
        require_approval=bool((request or {}).get("require_approval", False)),
        approval_request_id=(request or {}).get("approval_request_id"),
        user_id=(request or {}).get("user_id") or "system",
        dry_run=bool((request or {}).get("dry_run", False)),
        now=(float((request or {}).get("now")) if (request or {}).get("now") is not None else None),
    )


@api_router.post("/learning/approvals/cleanup-rollback-approvals")
async def api_cleanup_rollback_approvals(request: dict):
    """HTTP wrapper for cleanup-rollback-approvals."""
    if not _execution_store:
        raise HTTPException(status_code=503, detail="ExecutionStore not initialized")
    if not _approval_manager:
        raise HTTPException(status_code=503, detail="ApprovalManager not initialized")
    from core.learning.autorollback import cleanup_rollback_approvals

    return await cleanup_rollback_approvals(
        store=_execution_store,
        approval_manager=_approval_manager,
        now=(float((request or {}).get("now")) if (request or {}).get("now") is not None else None),
        dry_run=bool((request or {}).get("dry_run", False)),
        user_id=(request or {}).get("user_id"),
        candidate_id=(request or {}).get("candidate_id"),
        page_size=int((request or {}).get("page_size", 500) or 500),
    )


@api_router.get("/agents/executions/{execution_id}")
async def get_agent_execution(execution_id: str):
    """Get agent execution"""
    execution = await _execution_store.get_agent_execution(execution_id) if _execution_store else None
    if not execution:
        execution = _agent_executions.get(execution_id)
    if not execution:
        raise HTTPException(status_code=404, detail=f"Execution {execution_id} not found")
    return execution


@api_router.get("/agents/{agent_id}/history")
async def get_agent_history(agent_id: str, limit: int = 100, offset: int = 0):
    """Get agent execution history"""
    if _execution_store:
        history, total = await _execution_store.list_agent_history(agent_id, limit=limit, offset=offset)
        return {"history": history, "total": total}

    history = _agent_history.get(agent_id, [])
    history = history[offset:offset + limit]
    return {"history": history, "total": len(_agent_history.get(agent_id, []))}


@api_router.get("/agents/{agent_id}/versions")
async def get_agent_versions(agent_id: str):
    """Get agent versions"""
    agent = await _agent_manager.get_agent(agent_id)
    if not agent:
        raise HTTPException(status_code=404, detail=f"Agent {agent_id} not found")
    versions = await _agent_manager.get_versions(agent_id)
    return {
        "agent_id": agent_id,
        "versions": [{"version": v.version, "status": v.status, "created_at": v.created_at.isoformat(), "changes": v.changes} for v in versions]
    }


@api_router.post("/agents/{agent_id}/versions")
async def create_agent_version(agent_id: str, request: dict):
    """Create new agent version"""
    changes = request.get("changes", "")
    version = await _agent_manager.create_version(agent_id, changes)
    if not version:
        raise HTTPException(status_code=404, detail=f"Agent {agent_id} not found")
    return {"version": version.version, "status": version.status, "created_at": version.created_at.isoformat(), "changes": version.changes}


@api_router.post("/agents/{agent_id}/versions/{version}/rollback")
async def rollback_agent_version(agent_id: str, version: str):
    """Rollback agent to specific version"""
    success = await _agent_manager.rollback_version(agent_id, version)
    if not success:
        raise HTTPException(status_code=404, detail=f"Agent or version {version} not found")
    return {"status": "rolled_back", "version": version}


# ==================== Skill Management ====================

@api_router.get("/skills")
async def list_skills(
    category: Optional[str] = None,
    enabled_only: bool = False,
    status: Optional[str] = None,
    limit: int = 100,
    offset: int = 0
):
    """List all skills"""
    # SkillManager.list_skills signature: (skill_type, status, limit, offset)
    skills = await _skill_manager.list_skills(category, status, limit, offset)

    trusted_keys = await _get_trusted_skill_pubkeys_map()
    
    result = []
    for s in skills:
        if enabled_only and s.status != "enabled":
            continue
        # Enrich verification status in response (no persistence here)
        try:
            if trusted_keys and isinstance(getattr(s, "metadata", None), dict):
                prov2 = _skill_manager.compute_skill_signature_verification(s, trusted_keys)
                if prov2:
                    s.metadata["provenance"] = prov2
        except Exception:
            pass
        result.append({
            "id": s.id,
            "name": s.name,
            "category": s.type,
            "description": s.description,
            "status": s.status,
            "enabled": s.status == "enabled",
            "config": s.config or {},
            "input_schema": s.input_schema or {},
            "output_schema": s.output_schema or {},
            "metadata": s.metadata or {},
        })
    
    return {
        "skills": result,
        "total": _skill_manager.get_skill_count().get("total", 0),
        "limit": limit,
        "offset": offset
    }


@api_router.post("/skills")
async def create_skill(request: SkillCreateRequest):
    """Create a new skill"""
    skill = await _skill_manager.create_skill(
        name=request.name,
        skill_type=request.category,
        description=request.description,
        config=request.config or {},
        input_schema=request.input_schema or {},
        output_schema=request.output_schema or {},
    )
    try:
        await _record_changeset(
            name="skill_upsert",
            target_type="skill",
            target_id=str(skill.id),
            args={"scope": "engine", "category": request.category, "name": request.name},
            result={
                "status": "created",
                "integrity": (getattr(skill, "metadata", None) or {}).get("integrity") if isinstance(getattr(skill, "metadata", None), dict) else None,
                "provenance": (getattr(skill, "metadata", None) or {}).get("provenance") if isinstance(getattr(skill, "metadata", None), dict) else None,
            },
        )
    except Exception:
        pass
    try:
        await _maybe_verify_and_audit_skill_signature(skill=skill, scope="engine")
    except Exception:
        pass
    return {
        "id": skill.id,
        "status": "created",
        "name": skill.name
    }


@api_router.get("/skills/{skill_id}")
async def get_skill(skill_id: str):
    """Get skill details"""
    skill = await _skill_manager.get_skill(skill_id)
    if not skill:
        raise HTTPException(status_code=404, detail=f"Skill {skill_id} not found")
    
    return {
        "id": skill.id,
        "name": skill.name,
        "type": skill.type,
        "category": skill.type,
        "description": skill.description,
        "status": skill.status,
        "enabled": skill.status == "enabled",
        "config": skill.config or {},
        "input_schema": skill.input_schema or {},
        "output_schema": skill.output_schema or {},
        "metadata": skill.metadata or {},
    }


@api_router.put("/skills/{skill_id}")
async def update_skill(skill_id: str, request: dict):
    """Update skill"""
    from core.schemas import SkillUpdateRequest
    try:
        skill = await _skill_manager.update_skill(
            skill_id,
            name=request.get("name"),
            description=request.get("description"),
            config=request.get("config"),
            metadata=request.get("metadata")
        )
    except PermissionError as e:
        raise HTTPException(status_code=403, detail=str(e))
    if not skill:
        raise HTTPException(status_code=404, detail=f"Skill {skill_id} not found")
    try:
        await _record_changeset(
            name="skill_upsert",
            target_type="skill",
            target_id=str(skill_id),
            args={"scope": "engine", "fields": list((request or {}).keys())[:50]},
            result={
                "status": "updated",
                "integrity": (getattr(skill, "metadata", None) or {}).get("integrity") if isinstance(getattr(skill, "metadata", None), dict) else None,
                "provenance": (getattr(skill, "metadata", None) or {}).get("provenance") if isinstance(getattr(skill, "metadata", None), dict) else None,
            },
        )
    except Exception:
        pass
    try:
        await _maybe_verify_and_audit_skill_signature(skill=skill, scope="engine")
    except Exception:
        pass
    return {"status": "updated"}


@api_router.delete("/skills/{skill_id}")
async def delete_skill(skill_id: str, delete_files: bool = False):
    """Delete skill (default: soft delete; delete_files=true for hard delete)."""
    try:
        success = await _skill_manager.delete_skill(skill_id, delete_files=delete_files)
    except PermissionError as e:
        raise HTTPException(status_code=403, detail=str(e))
    if not success:
        raise HTTPException(status_code=404, detail=f"Skill {skill_id} not found")
    return {"status": "deleted" if delete_files else "deprecated"}


@api_router.post("/skills/{skill_id}/enable")
async def enable_skill(skill_id: str):
    """Enable skill"""
    success = await _skill_manager.enable_skill(skill_id)
    if not success:
        raise HTTPException(status_code=400, detail=f"Skill {skill_id} cannot be enabled (maybe deprecated; use restore)")
    return {"status": "enabled"}


@api_router.post("/skills/{skill_id}/disable")
async def disable_skill(skill_id: str):
    """Disable skill"""
    success = await _skill_manager.disable_skill(skill_id)
    if not success:
        raise HTTPException(status_code=404, detail=f"Skill {skill_id} not found")
    return {"status": "disabled"}


@api_router.post("/skills/{skill_id}/restore")
async def restore_skill(skill_id: str):
    """Restore a deprecated skill (status -> enabled)."""
    success = await _skill_manager.restore_skill(skill_id)
    if not success:
        raise HTTPException(status_code=404, detail=f"Skill {skill_id} not found")
    return {"status": "enabled"}


# ==================== Workspace Skill Management ====================


@api_router.get("/workspace/skills")
async def list_workspace_skills(
    category: Optional[str] = None,
    enabled_only: bool = False,
    status: Optional[str] = None,
    limit: int = 100,
    offset: int = 0,
):
    """List workspace skills (~/.aiplat/skills)."""
    if not _workspace_skill_manager:
        return {"skills": [], "total": 0, "limit": limit, "offset": offset}
    skills = await _workspace_skill_manager.list_skills(category, status, limit, offset)

    trusted_keys = await _get_trusted_skill_pubkeys_map()
    result = []
    for s in skills:
        if enabled_only and s.status != "enabled":
            continue
        try:
            if trusted_keys and isinstance(getattr(s, "metadata", None), dict):
                prov2 = _workspace_skill_manager.compute_skill_signature_verification(s, trusted_keys)
                if prov2:
                    s.metadata["provenance"] = prov2
        except Exception:
            pass
        result.append(
            {
                "id": s.id,
                "name": s.name,
                "category": s.type,
                "description": s.description,
                "status": s.status,
                "enabled": s.status == "enabled",
                "config": s.config or {},
                "input_schema": s.input_schema or {},
                "output_schema": s.output_schema or {},
                "metadata": s.metadata or {},
            }
        )
    return {
        "skills": result,
        "total": _workspace_skill_manager.get_skill_count().get("total", 0),
        "limit": limit,
        "offset": offset,
    }


@api_router.post("/workspace/skills")
async def create_workspace_skill(request: SkillCreateRequest, http_request: Request):
    """Create a new workspace skill."""
    if not _workspace_skill_manager:
        raise HTTPException(status_code=503, detail="Workspace skill manager not available")
    try:
        skill = await _workspace_skill_manager.create_skill(
            name=request.name,
            skill_type=request.category,
            description=request.description,
            config=request.config or {},
            input_schema=request.input_schema or {},
            output_schema=request.output_schema or {},
            metadata={"template": request.template, "sop": request.sop},
        )
        # Mark as pending verification (best-effort)
        eval_artifact_id: Optional[str] = None
        candidate_id: Optional[str] = None
        job_id = None
        try:
            await _workspace_skill_manager.update_skill(
                str(skill.id),
                metadata={
                    "verification": {
                        "status": "pending",
                        "updated_at": time.time(),
                        "source": "autosmoke",
                    }
                },
            )
        except Exception:
            pass
        # Create governance artifacts (best-effort): evaluation_report + release_candidate
        try:
            if _execution_store is not None:
                from core.learning.manager import LearningManager
                from core.learning.types import LearningArtifactKind

                mgr = LearningManager(execution_store=_execution_store)
                sid = str(skill.id)
                job_id = f"autosmoke-skill:{sid}"
                eval_art = await mgr.create_artifact(
                    kind=LearningArtifactKind.EVALUATION_REPORT,
                    target_type="skill",
                    target_id=sid,
                    version=f"autosmoke:{int(time.time())}",
                    status="pending",
                    payload={"source": "autosmoke", "job_id": job_id, "op": "create"},
                    metadata={"governance": True},
                )
                eval_artifact_id = eval_art.artifact_id
                cand = await mgr.create_artifact(
                    kind=LearningArtifactKind.RELEASE_CANDIDATE,
                    target_type="skill",
                    target_id=sid,
                    version=str(getattr(skill, "version", "") or "v1.0.0"),
                    status="draft",
                    payload={"evaluation_artifact_id": eval_artifact_id},
                    metadata={"governance": True, "ready": False},
                )
                candidate_id = cand.artifact_id
                await _workspace_skill_manager.update_skill(
                    sid,
                    metadata={
                        "governance": {
                            "status": "pending",
                            "evaluation_artifact_id": eval_artifact_id,
                            "candidate_id": candidate_id,
                            "job_id": job_id,
                            "last_op": "create",
                            "updated_at": time.time(),
                        }
                    },
                )
        except Exception:
            pass
        try:
            if _execution_store is not None and _job_scheduler is not None:
                from core.harness.smoke import enqueue_autosmoke

                tenant_id = http_request.headers.get("X-AIPLAT-TENANT-ID", "ops_smoke")
                actor_id = http_request.headers.get("X-AIPLAT-ACTOR-ID", "admin")
                sid = str(skill.id)

                async def _on_complete(job_run: Dict[str, Any]):
                    st = str(job_run.get("status") or "")
                    ver = {
                        "status": "verified" if st == "completed" else "failed",
                        "updated_at": time.time(),
                        "source": "autosmoke",
                        "job_id": job_id or f"autosmoke-skill:{sid}",
                        "job_run_id": str(job_run.get("id") or ""),
                        "reason": str(job_run.get("error") or ""),
                    }
                    try:
                        await _workspace_skill_manager.update_skill(sid, metadata={"verification": ver})
                    except Exception:
                        pass
                    # Update governance artifacts (best-effort)
                    try:
                        if _execution_store is not None:
                            from core.learning.manager import LearningManager

                            mgr = LearningManager(execution_store=_execution_store)
                            gid = eval_artifact_id
                            cid = candidate_id
                            if not gid or not cid:
                                # Try read from persisted frontmatter
                                s2 = await _workspace_skill_manager.get_skill(sid)
                                g = (getattr(s2, "metadata", None) or {}).get("governance") if isinstance(getattr(s2, "metadata", None), dict) else {}
                                gid = g.get("evaluation_artifact_id")
                                cid = g.get("candidate_id")
                            if gid:
                                await mgr.set_artifact_status(
                                    artifact_id=str(gid),
                                    status="verified" if st == "completed" else "failed",
                                    metadata_update={"job_run_id": str(job_run.get("id") or ""), "reason": str(job_run.get("error") or "")},
                                )
                            if cid:
                                await mgr.set_artifact_status(
                                    artifact_id=str(cid),
                                    status="draft",
                                    metadata_update={
                                        "ready": bool(st == "completed"),
                                        "verification": ver,
                                        "job_run_id": str(job_run.get("id") or ""),
                                    },
                                )
                            await _workspace_skill_manager.update_skill(
                                sid,
                                metadata={
                                    "governance": {
                                        "status": "verified" if st == "completed" else "failed",
                                        "job_run_id": str(job_run.get("id") or ""),
                                        "updated_at": time.time(),
                                    }
                                },
                            )
                    except Exception:
                        pass

                await enqueue_autosmoke(
                    execution_store=_execution_store,
                    job_scheduler=_job_scheduler,
                    resource_type="skill",
                    resource_id=sid,
                    tenant_id=tenant_id or "ops_smoke",
                    actor_id=actor_id or "admin",
                    detail={"op": "create", "name": skill.name},
                    on_complete=_on_complete,
                )
        except Exception:
            pass
        try:
            await _record_changeset(
                name="skill_upsert",
                target_type="skill",
                target_id=str(skill.id),
                args={"scope": "workspace", "category": request.category, "name": request.name},
                result={
                    "status": "created",
                    "integrity": (getattr(skill, "metadata", None) or {}).get("integrity") if isinstance(getattr(skill, "metadata", None), dict) else None,
                    "provenance": (getattr(skill, "metadata", None) or {}).get("provenance") if isinstance(getattr(skill, "metadata", None), dict) else None,
                },
            )
        except Exception:
            pass
        try:
            await _maybe_verify_and_audit_skill_signature(skill=skill, scope="workspace")
        except Exception:
            pass
        return {"id": skill.id, "status": "created", "name": skill.name}
    except ValueError as e:
        raise HTTPException(status_code=409, detail=str(e))


@api_router.get("/workspace/skills/{skill_id}")
async def get_workspace_skill(skill_id: str):
    if not _workspace_skill_manager:
        raise HTTPException(status_code=503, detail="Workspace skill manager not available")
    skill = await _workspace_skill_manager.get_skill(skill_id)
    if not skill:
        raise HTTPException(status_code=404, detail=f"Skill {skill_id} not found")
    return {
        "id": skill.id,
        "name": skill.name,
        "type": skill.type,
        "category": skill.type,
        "description": skill.description,
        "status": skill.status,
        "enabled": skill.status == "enabled",
        "config": skill.config or {},
        "input_schema": skill.input_schema or {},
        "output_schema": skill.output_schema or {},
        "metadata": skill.metadata or {},
    }


@api_router.put("/workspace/skills/{skill_id}")
async def update_workspace_skill(skill_id: str, request: dict, http_request: Request):
    if not _workspace_skill_manager:
        raise HTTPException(status_code=503, detail="Workspace skill manager not available")
    from core.schemas import SkillUpdateRequest

    r = SkillUpdateRequest(**(request or {}))
    # NOTE: SkillManager.update_skill expects keyword fields; do not pass the dict as positional arg.
    skill = await _workspace_skill_manager.update_skill(skill_id, **r.model_dump(exclude_unset=True))
    if not skill:
        raise HTTPException(status_code=404, detail=f"Skill {skill_id} not found")
    # Mark as pending verification (best-effort)
    eval_artifact_id: Optional[str] = None
    candidate_id: Optional[str] = None
    job_id = None
    try:
        await _workspace_skill_manager.update_skill(
            str(skill_id),
            metadata={
                "verification": {
                    "status": "pending",
                    "updated_at": time.time(),
                    "source": "autosmoke",
                }
            },
        )
    except Exception:
        pass
    # Create governance artifacts (best-effort)
    try:
        if _execution_store is not None:
            from core.learning.manager import LearningManager
            from core.learning.types import LearningArtifactKind

            mgr = LearningManager(execution_store=_execution_store)
            sid = str(skill_id)
            job_id = f"autosmoke-skill:{sid}"
            eval_art = await mgr.create_artifact(
                kind=LearningArtifactKind.EVALUATION_REPORT,
                target_type="skill",
                target_id=sid,
                version=f"autosmoke:{int(time.time())}",
                status="pending",
                payload={"source": "autosmoke", "job_id": job_id, "op": "update"},
                metadata={"governance": True},
            )
            eval_artifact_id = eval_art.artifact_id
            cand = await mgr.create_artifact(
                kind=LearningArtifactKind.RELEASE_CANDIDATE,
                target_type="skill",
                target_id=sid,
                version=str(getattr(skill, "version", "") or "v1.0.0"),
                status="draft",
                payload={"evaluation_artifact_id": eval_artifact_id},
                metadata={"governance": True, "ready": False},
            )
            candidate_id = cand.artifact_id
            await _workspace_skill_manager.update_skill(
                sid,
                metadata={
                    "governance": {
                        "status": "pending",
                        "evaluation_artifact_id": eval_artifact_id,
                        "candidate_id": candidate_id,
                        "job_id": job_id,
                        "last_op": "update",
                        "updated_at": time.time(),
                    }
                },
            )
    except Exception:
        pass
    try:
        if _execution_store is not None and _job_scheduler is not None:
            from core.harness.smoke import enqueue_autosmoke

            tenant_id = http_request.headers.get("X-AIPLAT-TENANT-ID", "ops_smoke")
            actor_id = http_request.headers.get("X-AIPLAT-ACTOR-ID", "admin")
            sid = str(skill_id)

            async def _on_complete(job_run: Dict[str, Any]):
                st = str(job_run.get("status") or "")
                ver = {
                    "status": "verified" if st == "completed" else "failed",
                    "updated_at": time.time(),
                    "source": "autosmoke",
                    "job_id": job_id or f"autosmoke-skill:{sid}",
                    "job_run_id": str(job_run.get("id") or ""),
                    "reason": str(job_run.get("error") or ""),
                }
                try:
                    await _workspace_skill_manager.update_skill(sid, metadata={"verification": ver})
                except Exception:
                    pass
                try:
                    if _execution_store is not None:
                        from core.learning.manager import LearningManager

                        mgr = LearningManager(execution_store=_execution_store)
                        gid = eval_artifact_id
                        cid = candidate_id
                        if not gid or not cid:
                            s2 = await _workspace_skill_manager.get_skill(sid)
                            g = (getattr(s2, "metadata", None) or {}).get("governance") if isinstance(getattr(s2, "metadata", None), dict) else {}
                            gid = g.get("evaluation_artifact_id")
                            cid = g.get("candidate_id")
                        if gid:
                            await mgr.set_artifact_status(
                                artifact_id=str(gid),
                                status="verified" if st == "completed" else "failed",
                                metadata_update={"job_run_id": str(job_run.get("id") or ""), "reason": str(job_run.get("error") or "")},
                            )
                        if cid:
                            await mgr.set_artifact_status(
                                artifact_id=str(cid),
                                status="draft",
                                metadata_update={
                                    "ready": bool(st == "completed"),
                                    "verification": ver,
                                    "job_run_id": str(job_run.get("id") or ""),
                                },
                            )
                        await _workspace_skill_manager.update_skill(
                            sid,
                            metadata={
                                "governance": {
                                    "status": "verified" if st == "completed" else "failed",
                                    "job_run_id": str(job_run.get("id") or ""),
                                    "updated_at": time.time(),
                                }
                            },
                        )
                except Exception:
                    pass

            await enqueue_autosmoke(
                execution_store=_execution_store,
                job_scheduler=_job_scheduler,
                resource_type="skill",
                resource_id=sid,
                tenant_id=tenant_id or "ops_smoke",
                actor_id=actor_id or "admin",
                detail={"op": "update"},
                on_complete=_on_complete,
            )
    except Exception:
        pass
    try:
        await _record_changeset(
            name="skill_upsert",
            target_type="skill",
            target_id=str(skill_id),
            args={"scope": "workspace", "fields": list(r.model_dump(exclude_unset=True).keys())[:50]},
            result={
                "status": "updated",
                "integrity": (getattr(skill, "metadata", None) or {}).get("integrity") if isinstance(getattr(skill, "metadata", None), dict) else None,
                "provenance": (getattr(skill, "metadata", None) or {}).get("provenance") if isinstance(getattr(skill, "metadata", None), dict) else None,
            },
        )
    except Exception:
        pass
    try:
        await _maybe_verify_and_audit_skill_signature(skill=skill, scope="workspace")
    except Exception:
        pass
    return {"status": "updated", "id": skill_id}


@api_router.delete("/workspace/skills/{skill_id}")
async def delete_workspace_skill(skill_id: str, delete_files: bool = False):
    if not _workspace_skill_manager:
        raise HTTPException(status_code=503, detail="Workspace skill manager not available")
    ok = await _workspace_skill_manager.delete_skill(skill_id, delete_files=delete_files)
    if not ok:
        raise HTTPException(status_code=404, detail=f"Skill {skill_id} not found")
    return {"status": "deleted", "id": skill_id, "delete_files": delete_files}


@api_router.post("/workspace/skills/{skill_id}/enable")
async def enable_workspace_skill(skill_id: str, request: Optional[Dict[str, Any]] = None):
    if not _workspace_skill_manager:
        raise HTTPException(status_code=503, detail="Workspace skill manager not available")
    req = request or {}
    approval_request_id = str(req.get("approval_request_id") or "").strip() or None
    details = str(req.get("details") or "").strip()
    if _autosmoke_enforce():
        s = await _workspace_skill_manager.get_skill(skill_id)
        if not s:
            raise HTTPException(status_code=404, detail=f"Skill {skill_id} not found")
        if not _is_verified(getattr(s, "metadata", None)):
            raise HTTPException(status_code=403, detail="skill_unverified: smoke must pass before enable")

    # Signature gate: unverified workspace skills require approval to enable.
    s = await _workspace_skill_manager.get_skill(skill_id)
    if not s:
        raise HTTPException(status_code=404, detail=f"Skill {skill_id} not found")

    # Publish gate: if governance candidate exists, require it to be published before enabling.
    pg = _governance_publish_gate(getattr(s, "metadata", None))
    if pg.get("required") is True:
        try:
            await _record_changeset(
                name="skill_publish_gate",
                target_type="skill",
                target_id=str(skill_id),
                status="blocked",
                args={"scope": "workspace", "action": "enable", "candidate_id": pg.get("candidate_id")},
                result={"reason": "publish_required"},
            )
        except Exception:
            pass
        return {
            "status": "publish_required",
            "candidate_id": pg.get("candidate_id"),
            "releases_url": _ui_url("/core/learning/releases"),
        }
    trusted = await _get_trusted_skill_pubkeys_map()
    try:
        prov2 = _workspace_skill_manager.compute_skill_signature_verification(s, trusted)
        if isinstance(getattr(s, "metadata", None), dict) and prov2:
            s.metadata["provenance"] = prov2
    except Exception:
        prov2 = (getattr(s, "metadata", None) or {}).get("provenance") if isinstance(getattr(s, "metadata", None), dict) else {}
    gate = _signature_gate_eval(metadata=getattr(s, "metadata", None), trusted_keys_count=len(trusted))
    if gate.get("required") is True:
        if not approval_request_id:
            rid = await _require_skill_signature_gate_approval(
                user_id="admin",
                skill_id=str(skill_id),
                action="enable",
                details=details or f"enable workspace skill {skill_id}",
                metadata={
                    "skill_id": str(skill_id),
                    "action": "enable",
                    "reason": gate.get("reason"),
                    "provenance": (getattr(s, "metadata", None) or {}).get("provenance") if isinstance(getattr(s, "metadata", None), dict) else {},
                    "integrity": (getattr(s, "metadata", None) or {}).get("integrity") if isinstance(getattr(s, "metadata", None), dict) else {},
                },
            )
            try:
                await _record_changeset(
                    name="skill_signature_gate",
                    target_type="skill",
                    target_id=str(skill_id),
                    status="approval_required",
                    args={"scope": "workspace", "action": "enable", "reason": gate.get("reason")},
                    approval_request_id=rid,
                )
            except Exception:
                pass
            return {"status": "approval_required", "approval_request_id": rid}
        if not _is_approval_resolved_approved(approval_request_id):
            try:
                await _record_changeset(
                    name="skill_signature_gate",
                    target_type="skill",
                    target_id=str(skill_id),
                    status="failed",
                    args={"scope": "workspace", "action": "enable", "reason": gate.get("reason")},
                    error="not_approved",
                    approval_request_id=approval_request_id,
                )
            except Exception:
                pass
            raise HTTPException(status_code=409, detail="not_approved")
        try:
            await _record_changeset(
                name="skill_signature_gate",
                target_type="skill",
                target_id=str(skill_id),
                status="success",
                args={"scope": "workspace", "action": "enable"},
                approval_request_id=approval_request_id,
            )
        except Exception:
            pass
    ok = await _workspace_skill_manager.enable_skill(skill_id)
    if not ok:
        raise HTTPException(status_code=400, detail=f"Skill {skill_id} cannot be enabled (maybe deprecated; use restore)")
    return {"status": "enabled", "approval_request_id": approval_request_id}


@api_router.post("/workspace/skills/{skill_id}/disable")
async def disable_workspace_skill(skill_id: str):
    if not _workspace_skill_manager:
        raise HTTPException(status_code=503, detail="Workspace skill manager not available")
    ok = await _workspace_skill_manager.disable_skill(skill_id)
    if not ok:
        raise HTTPException(status_code=404, detail=f"Skill {skill_id} not found")
    return {"status": "disabled"}


@api_router.post("/workspace/skills/{skill_id}/restore")
async def restore_workspace_skill(skill_id: str):
    if not _workspace_skill_manager:
        raise HTTPException(status_code=503, detail="Workspace skill manager not available")
    ok = await _workspace_skill_manager.restore_skill(skill_id)
    if not ok:
        raise HTTPException(status_code=404, detail=f"Skill {skill_id} not found")
    return {"status": "enabled"}


@api_router.get("/workspace/skills/{skill_id}/revisions")
async def list_workspace_skill_revisions(skill_id: str, limit: int = 50, offset: int = 0):
    """List revision snapshots for a workspace skill (best-effort)."""
    if not _workspace_skill_manager:
        raise HTTPException(status_code=503, detail="Workspace skill manager not available")
    skill = await _workspace_skill_manager.get_skill(skill_id)
    if not skill:
        raise HTTPException(status_code=404, detail=f"Skill {skill_id} not found")
    from pathlib import Path

    skill_dir = None
    try:
        fs = skill.metadata.get("filesystem") if isinstance(skill.metadata, dict) else None
        if isinstance(fs, dict) and fs.get("skill_dir"):
            skill_dir = Path(str(fs.get("skill_dir")))
    except Exception:
        skill_dir = None
    if skill_dir is None:
        # best effort fallback
        base = _workspace_skill_manager._resolve_skills_base_path()  # type: ignore[attr-defined]
        skill_dir = Path(base) / skill_id

    rev_root = skill_dir / ".revisions"
    if not rev_root.exists():
        return {"items": [], "total": 0, "limit": limit, "offset": offset}
    revs = sorted([p.name for p in rev_root.iterdir() if p.is_dir()], reverse=True)
    total = len(revs)
    page = revs[offset : offset + limit]
    return {"items": page, "total": total, "limit": limit, "offset": offset}


@api_router.get("/workspace/skills/{skill_id}/files")
async def list_workspace_skill_files(skill_id: str, dir: str = "references"):
    """List files under workspace skill directory (references/scripts/assets)."""
    if not _workspace_skill_manager:
        raise HTTPException(status_code=503, detail="Workspace skill manager not available")
    skill = await _workspace_skill_manager.get_skill(skill_id)
    if not skill:
        raise HTTPException(status_code=404, detail=f"Skill {skill_id} not found")
    from pathlib import Path

    base = _workspace_skill_manager._resolve_skills_base_path()  # type: ignore[attr-defined]
    skill_dir = Path(base) / skill_id
    allow = {"references", "scripts", "assets"}
    if dir not in allow:
        raise HTTPException(status_code=400, detail=f"dir must be one of {sorted(list(allow))}")
    root = (skill_dir / dir).resolve()
    if not root.exists():
        return {"items": [], "total": 0}

    items = []
    for p in root.rglob("*"):
        if not p.is_file():
            continue
        try:
            rel = str(p.relative_to(skill_dir))
        except Exception:
            continue
        st = p.stat()
        items.append({"path": rel, "size": int(st.st_size), "mtime": float(st.st_mtime)})
    items.sort(key=lambda x: x["path"])
    return {"items": items, "total": len(items)}


@api_router.get("/workspace/skills/{skill_id}/files/{rel_path:path}")
async def get_workspace_skill_file(skill_id: str, rel_path: str):
    """Fetch a workspace skill file content (text only, best-effort)."""
    if not _workspace_skill_manager:
        raise HTTPException(status_code=503, detail="Workspace skill manager not available")
    from pathlib import Path

    base = _workspace_skill_manager._resolve_skills_base_path()  # type: ignore[attr-defined]
    skill_dir = (Path(base) / skill_id).resolve()
    p = (skill_dir / rel_path).resolve()
    # enforce allowed subpaths
    allowed_roots = [(skill_dir / "references").resolve(), (skill_dir / "scripts").resolve(), (skill_dir / "assets").resolve(), (skill_dir / ".revisions").resolve()]
    if not any(str(p).startswith(str(r)) for r in allowed_roots):
        raise HTTPException(status_code=403, detail="path not allowed")
    if not p.exists() or not p.is_file():
        raise HTTPException(status_code=404, detail="file not found")
    # small text only
    data = p.read_bytes()
    if len(data) > 200_000:
        raise HTTPException(status_code=413, detail="file too large")
    try:
        text = data.decode("utf-8")
    except Exception:
        raise HTTPException(status_code=415, detail="binary file not supported")
    return {"path": rel_path, "content": text}


@api_router.post("/workspace/skills/{skill_id}/execute")
async def execute_workspace_skill(skill_id: str, request: SkillExecuteRequest, http_request: Request):
    """Execute workspace skill."""
    if not _workspace_skill_manager:
        raise HTTPException(status_code=503, detail="Workspace skill manager not available")
    skill = await _workspace_skill_manager.get_skill(skill_id)
    if not skill:
        raise HTTPException(status_code=404, detail=f"Skill {skill_id} not found")

    # Publish gate: if governance candidate exists, require it to be published before executing.
    pg = _governance_publish_gate(getattr(skill, "metadata", None))
    if pg.get("required") is True:
        try:
            await _record_changeset(
                name="skill_publish_gate",
                target_type="skill",
                target_id=str(skill_id),
                status="blocked",
                args={"scope": "workspace", "action": "execute", "candidate_id": pg.get("candidate_id")},
                result={"reason": "publish_required"},
            )
        except Exception:
            pass
        # PR-02: Run Contract v2 (blocked)
        resp = {
            "ok": False,
            "run_id": new_prefixed_id("run"),
            "trace_id": None,
            "status": RunStatus.aborted.value,
            "legacy_status": "publish_required",
            "output": None,
            "error": {"code": "PUBLISH_REQUIRED", "message": "publish_required", "detail": {"candidate_id": pg.get("candidate_id")}},
            "candidate_id": pg.get("candidate_id"),
            "releases_url": _ui_url("/core/learning/releases"),
        }
        try:
            await _audit_execute(http_request=http_request, payload={"context": {}}, resource_type="skill", resource_id=str(skill_id), resp=resp, action="execute_skill")
        except Exception:
            pass
        return resp

    # Merge platform identity headers into context (best-effort)
    ctx_for_user: Dict[str, Any] = dict(request.context or {}) if isinstance(request.context, dict) else {}
    try:
        tmp = _inject_http_request_context({"context": dict(ctx_for_user)}, http_request, entrypoint="api")
        ctx_for_user = tmp.get("context") if isinstance(tmp, dict) and isinstance(tmp.get("context"), dict) else ctx_for_user
    except Exception:
        pass

    deny = await _rbac_guard(http_request=http_request, payload={"context": ctx_for_user}, action="execute", resource_type="skill", resource_id=str(skill_id))
    if deny:
        return deny
    # Signature gate: unverified workspace skills require approval to execute.
    try:
        opts = request.options if isinstance(getattr(request, "options", None), dict) else {}
    except Exception:
        opts = {}
    approval_request_id = None
    details = ""
    try:
        approval_request_id = str(opts.get("approval_request_id") or "").strip() or None
        details = str(opts.get("details") or "").strip()
    except Exception:
        approval_request_id = None
        details = ""

    trusted = await _get_trusted_skill_pubkeys_map()
    try:
        prov2 = _workspace_skill_manager.compute_skill_signature_verification(skill, trusted)
        if isinstance(getattr(skill, "metadata", None), dict) and prov2:
            skill.metadata["provenance"] = prov2
    except Exception:
        pass
    gate = _signature_gate_eval(metadata=getattr(skill, "metadata", None), trusted_keys_count=len(trusted))
    if gate.get("required") is True:
        if not approval_request_id:
            rid = await _require_skill_signature_gate_approval(
                user_id=str(ctx_for_user.get("actor_id") or ctx_for_user.get("user_id") or "admin"),
                skill_id=str(skill_id),
                action="execute",
                details=details or f"execute workspace skill {skill_id}",
                metadata={
                    "skill_id": str(skill_id),
                    "action": "execute",
                    "reason": gate.get("reason"),
                    "provenance": (getattr(skill, "metadata", None) or {}).get("provenance") if isinstance(getattr(skill, "metadata", None), dict) else {},
                    "integrity": (getattr(skill, "metadata", None) or {}).get("integrity") if isinstance(getattr(skill, "metadata", None), dict) else {},
                },
            )
            try:
                await _record_changeset(
                    name="skill_signature_gate",
                    target_type="skill",
                    target_id=str(skill_id),
                    status="approval_required",
                    args={"scope": "workspace", "action": "execute", "reason": gate.get("reason")},
                    approval_request_id=rid,
                )
            except Exception:
                pass
            resp = {
                "ok": False,
                "run_id": new_prefixed_id("run"),
                "trace_id": None,
                "status": RunStatus.waiting_approval.value,
                "legacy_status": "approval_required",
                "output": None,
                "error": {
                    "code": "APPROVAL_REQUIRED",
                    "message": "approval_required",
                    "detail": {"approval_request_id": rid, "reason": gate.get("reason")},
                },
                "approval_request_id": rid,
                "reason": gate.get("reason"),
            }
            try:
                await _audit_execute(http_request=http_request, payload={"context": ctx_for_user}, resource_type="skill", resource_id=str(skill_id), resp=resp, action="execute_skill")
            except Exception:
                pass
            return resp
        if not _is_approval_resolved_approved(approval_request_id):
            try:
                await _record_changeset(
                    name="skill_signature_gate",
                    target_type="skill",
                    target_id=str(skill_id),
                    status="failed",
                    args={"scope": "workspace", "action": "execute", "reason": gate.get("reason")},
                    error="not_approved",
                    approval_request_id=approval_request_id,
                )
            except Exception:
                pass
            raise HTTPException(status_code=409, detail="not_approved")
        try:
            await _record_changeset(
                name="skill_signature_gate",
                target_type="skill",
                target_id=str(skill_id),
                status="success",
                args={"scope": "workspace", "action": "execute"},
                approval_request_id=approval_request_id,
            )
        except Exception:
            pass
    user_id = str(ctx_for_user.get("actor_id") or ctx_for_user.get("user_id") or "system")
    harness = get_harness()
    exec_req = ExecutionRequest(
        kind="skill",
        target_id=skill_id,
        payload={
            "input": request.input,
            "context": ctx_for_user,
            "mode": getattr(request, "mode", "inline"),
            "options": getattr(request, "options", None) or None,
        },
        user_id=user_id,
        session_id=str(ctx_for_user.get("session_id") or "default"),
    )
    result = await harness.execute(exec_req)
    resp = _wrap_execution_result_as_run_summary(result)
    try:
        await _audit_execute(http_request=http_request, payload={"context": ctx_for_user}, resource_type="skill", resource_id=str(skill_id), resp=resp, action="execute_skill")
    except Exception:
        pass
    return JSONResponse(status_code=200 if resp.get("ok") else int(getattr(result, "http_status", 500) or 500), content=resp)


@api_router.get("/workspace/skills/{skill_id}/agents")
async def get_workspace_skill_agents(skill_id: str):
    """Get agents bound to workspace skill."""
    if not _workspace_skill_manager:
        raise HTTPException(status_code=503, detail="Workspace skill manager not available")
    agent_ids = await _workspace_skill_manager.get_bound_agents(skill_id)
    return {"agents": [{"id": a} for a in agent_ids], "total": len(agent_ids)}


@api_router.get("/workspace/skills/{skill_id}/executions")
async def list_workspace_skill_executions(skill_id: str, limit: int = 100, offset: int = 0):
    """List workspace skill executions."""
    if not _workspace_skill_manager:
        raise HTTPException(status_code=503, detail="Workspace skill manager not available")
    skill = await _workspace_skill_manager.get_skill(skill_id)
    if not skill:
        raise HTTPException(status_code=404, detail=f"Skill {skill_id} not found")
    # Reuse global execution store; workspace and engine ids are collision-free.
    return await list_skill_executions(skill_id, limit=limit, offset=offset)


@api_router.get("/workspace/skills/{skill_id}/versions")
async def get_workspace_skill_versions(skill_id: str):
    """Get versions for a workspace skill."""
    if not _workspace_skill_manager:
        raise HTTPException(status_code=503, detail="Workspace skill manager not available")
    skill = await _workspace_skill_manager.get_skill(skill_id)
    if not skill:
        raise HTTPException(status_code=404, detail=f"Skill {skill_id} not found")
    registry = get_skill_registry()
    versions = registry.get_versions(skill_id)
    return {"versions": [{"version": v.version, "is_active": v.is_active} for v in versions]}


@api_router.get("/workspace/skills/{skill_id}/versions/{version}")
async def get_workspace_skill_version(skill_id: str, version: str):
    """Get specific version config for workspace skill."""
    if not _workspace_skill_manager:
        raise HTTPException(status_code=503, detail="Workspace skill manager not available")
    skill = await _workspace_skill_manager.get_skill(skill_id)
    if not skill:
        raise HTTPException(status_code=404, detail=f"Skill {skill_id} not found")
    registry = get_skill_registry()
    config = registry.get_version(skill_id, version)
    if not config:
        raise HTTPException(status_code=404, detail=f"Version {version} not found")
    try:
        from dataclasses import asdict, is_dataclass
        cfg_dict = asdict(config) if is_dataclass(config) else dict(config)  # type: ignore[arg-type]
    except Exception:
        cfg_dict = {
            "name": getattr(config, "name", ""),
            "description": getattr(config, "description", ""),
            "input_schema": getattr(config, "input_schema", {}) or {},
            "output_schema": getattr(config, "output_schema", {}) or {},
            "timeout": getattr(config, "timeout", None),
            "metadata": getattr(config, "metadata", {}) or {},
        }
    return {"version": version, "config": cfg_dict}


@api_router.post("/workspace/skills/{skill_id}/versions/{version}/rollback")
async def rollback_workspace_skill_version(skill_id: str, version: str):
    """Rollback workspace skill to a specific version."""
    if not _workspace_skill_manager:
        raise HTTPException(status_code=503, detail="Workspace skill manager not available")
    skill = await _workspace_skill_manager.get_skill(skill_id)
    if not skill:
        raise HTTPException(status_code=404, detail=f"Skill {skill_id} not found")
    registry = get_skill_registry()
    ok = registry.rollback_version(skill_id, version)
    if not ok:
        raise HTTPException(status_code=404, detail=f"Version {version} not found")
    active_version = registry.get_active_version(skill_id) if hasattr(registry, "get_active_version") else version
    return {"status": "rolled_back", "active_version": active_version}


@api_router.get("/workspace/skills/{skill_id}/active-version")
async def get_workspace_skill_active_version(skill_id: str):
    """Get currently active version for a workspace skill."""
    if not _workspace_skill_manager:
        raise HTTPException(status_code=503, detail="Workspace skill manager not available")
    skill = await _workspace_skill_manager.get_skill(skill_id)
    if not skill:
        raise HTTPException(status_code=404, detail=f"Skill {skill_id} not found")
    registry = get_skill_registry()
    active_version = registry.get_active_version(skill_id) if hasattr(registry, "get_active_version") else None
    return {"skill_id": skill_id, "active_version": active_version}


@api_router.get("/workspace/skills/{skill_id}/execution-help")
async def get_workspace_skill_execution_help(skill_id: str):
    """Get execution input help/examples for a skill."""
    if not _workspace_skill_manager:
        raise HTTPException(status_code=503, detail="Workspace skill manager not available")
    skill = await _workspace_skill_manager.get_skill(skill_id)
    if not skill:
        raise HTTPException(status_code=404, detail=f"Skill {skill_id} not found")
    data = await _workspace_skill_manager.get_skill_execution_help(skill_id)  # type: ignore[attr-defined]
    if not data:
        raise HTTPException(status_code=404, detail="Execution help not found")
    return data


@api_router.get("/workspace/skills/{skill_id}/skill-md")
async def get_workspace_skill_markdown(skill_id: str):
    """Fetch raw SKILL.md content for a workspace skill (for UI preview)."""
    if not _workspace_skill_manager:
        raise HTTPException(status_code=503, detail="Workspace skill manager not available")
    skill = await _workspace_skill_manager.get_skill(skill_id)
    if not skill:
        raise HTTPException(status_code=404, detail=f"Skill {skill_id} not found")
    try:
        from pathlib import Path

        md_path = _workspace_skill_manager._find_skill_md(skill_id)  # type: ignore[attr-defined]
        if not md_path:
            raise HTTPException(status_code=404, detail="SKILL.md not found")
        p = Path(str(md_path)).expanduser().resolve()
        if not p.exists():
            raise HTTPException(status_code=404, detail="SKILL.md not found")

        # Security: only allow reading files under workspace skills paths.
        allowed_roots = []
        try:
            for root in _workspace_skill_manager._resolve_skills_paths():  # type: ignore[attr-defined]
                allowed_roots.append(Path(str(root)).expanduser().resolve())
        except Exception:
            allowed_roots = []
        if allowed_roots and not any(str(p).startswith(str(r) + "/") or str(p) == str(r) for r in allowed_roots):
            raise HTTPException(status_code=403, detail="SKILL.md path is outside workspace scope")

        text = p.read_text(encoding="utf-8", errors="replace")
        if len(text) > 200_000:
            text = text[:200_000] + "\n\n[TRUNCATED]"
        return {"skill_id": skill_id, "path": str(p), "content": text}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to read SKILL.md: {e}")


@api_router.get("/skills/{skill_id}/agents")
async def get_skill_agents(skill_id: str):
    """Get agents bound to skill"""
    agent_ids = await _skill_manager.get_bound_agents(skill_id)
    return {"agents": [{"id": a} for a in agent_ids], "total": len(agent_ids)}


# ---------------------------
# MCP (directory-based config)
# ---------------------------

@api_router.get("/mcp/servers")
async def list_mcp_servers():
    """List MCP servers configured via filesystem (mcps/<server>/server.yaml)."""
    if not _mcp_manager:
        return {"servers": []}
    return {
        "servers": [
            {
                "name": s.name,
                "enabled": s.enabled,
                "transport": s.transport,
                "url": s.url,
                "command": s.command,
                "args": s.args,
                "auth": s.auth,
                "allowed_tools": s.allowed_tools,
                "metadata": s.metadata,
            }
            for s in _mcp_manager.list_servers()
        ]
    }


@api_router.post("/mcp/servers/{server_name}/enable")
async def enable_mcp_server(server_name: str):
    """Enable an MCP server in filesystem config."""
    if not _mcp_manager:
        raise HTTPException(status_code=503, detail="MCP manager not available")
    ok = _mcp_manager.set_enabled(server_name, True)
    if not ok:
        raise HTTPException(status_code=404, detail=f"MCP server {server_name} not found")
    return {"status": "enabled"}


@api_router.post("/mcp/servers/{server_name}/disable")
async def disable_mcp_server(server_name: str):
    """Disable an MCP server in filesystem config."""
    if not _mcp_manager:
        raise HTTPException(status_code=503, detail="MCP manager not available")
    ok = _mcp_manager.set_enabled(server_name, False)
    if not ok:
        raise HTTPException(status_code=404, detail=f"MCP server {server_name} not found")
    return {"status": "disabled"}


# ==================== Workspace (user-facing) Resources ====================


@api_router.get("/workspace/mcp/servers")
async def list_workspace_mcp_servers():
    """List workspace MCP servers (~/.aiplat/mcps)."""
    if not _workspace_mcp_manager:
        return {"servers": []}
    return {
        "servers": [
            {
                "name": s.name,
                "enabled": s.enabled,
                "transport": s.transport,
                "url": s.url,
                "command": s.command,
                "args": s.args,
                "auth": s.auth,
                "allowed_tools": s.allowed_tools,
                "metadata": s.metadata,
            }
            for s in _workspace_mcp_manager.list_servers()
        ]
    }

@api_router.get("/workspace/mcp/servers/{server_name}")
async def get_workspace_mcp_server(server_name: str):
    """Get workspace MCP server details."""
    if not _workspace_mcp_manager:
        raise HTTPException(status_code=503, detail="Workspace MCP manager not available")
    s = _workspace_mcp_manager.get_server(server_name)
    if not s:
        raise HTTPException(status_code=404, detail=f"MCP server {server_name} not found")
    return {
        "name": s.name,
        "enabled": s.enabled,
        "transport": s.transport,
        "url": s.url,
        "command": s.command,
        "args": s.args,
        "auth": s.auth,
        "allowed_tools": s.allowed_tools,
        "metadata": s.metadata,
    }


@api_router.get("/workspace/mcp/servers/{server_name}/tools")
async def discover_workspace_mcp_tools(server_name: str, timeout_seconds: int = 10):
    """
    Best-effort tool discovery via MCP protocol (tools/list).
    - For sse/http: POST JSON-RPC to url
    - For stdio: spawn process, send JSON-RPC via stdin/stdout (dev/staging recommended)
    """
    if not _workspace_mcp_manager:
        raise HTTPException(status_code=503, detail="Workspace MCP manager not available")
    s = _workspace_mcp_manager.get_server(server_name)
    if not s:
        raise HTTPException(status_code=404, detail=f"MCP server {server_name} not found")

    transport = str(s.transport or "").strip().lower()
    ok, reason = _prod_stdio_policy_check(server_name, transport, s.command, s.args, s.metadata)
    if not ok:
        await _audit_event(
            "mcp_admin",
            "workspace.mcp.discover_tools",
            "failed",
            args={"server_name": server_name, "transport": transport, "command": s.command, "args": s.args},
            error=reason,
        )
        raise HTTPException(
            status_code=403,
            detail=f"stdio MCP tool discovery is blocked by prod policy: {reason}",
        )

    async def _jsonrpc_post(url: str, payload: dict) -> dict:
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=max(1, int(timeout_seconds)))) as session:
            async with session.post(url, data=json.dumps(payload), headers={"Content-Type": "application/json"}) as resp:
                if resp.status != 200:
                    raise HTTPException(status_code=502, detail=f"MCP server returned HTTP {resp.status}")
                return await resp.json()

    try:
        if transport in {"sse", "http"}:
            if not s.url:
                raise HTTPException(status_code=400, detail="Missing MCP server url")
            # best-effort initialize
            try:
                await _jsonrpc_post(
                    s.url,
                    {
                        "jsonrpc": "2.0",
                        "id": 0,
                        "method": "initialize",
                        "params": {
                            "protocolVersion": "2024-11-05",
                            "capabilities": {"tools": {}},
                            "clientInfo": {"name": "aiplat-core", "version": "1.0.0"},
                        },
                    },
                )
            except Exception:
                pass

            res = await _jsonrpc_post(s.url, {"jsonrpc": "2.0", "id": 1, "method": "tools/list", "params": {}})
            if "error" in res and res["error"]:
                raise HTTPException(status_code=502, detail=str(res["error"]))
            tools = (res.get("result") or {}).get("tools") or []
            norm = [
                {
                    "name": t.get("name"),
                    "description": t.get("description", ""),
                    "input_schema": t.get("inputSchema", {}) or {},
                }
                for t in tools
                if isinstance(t, dict) and t.get("name")
            ]
            await _audit_event(
                "mcp_admin",
                "workspace.mcp.discover_tools",
                "success",
                args={"server_name": server_name, "transport": transport},
                result={"total": len(norm)},
            )
            return {"tools": norm, "total": len(norm)}

        if transport == "stdio":
            if not s.command:
                raise HTTPException(status_code=400, detail="Missing MCP stdio command")
            proc = await asyncio.create_subprocess_exec(
                s.command,
                *(s.args or []),
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            try:
                # initialize
                init = {
                    "jsonrpc": "2.0",
                    "id": 0,
                    "method": "initialize",
                    "params": {
                        "protocolVersion": "2024-11-05",
                        "capabilities": {"tools": {}},
                        "clientInfo": {"name": "aiplat-core", "version": "1.0.0"},
                    },
                }
                proc.stdin.write((json.dumps(init) + "\n").encode("utf-8"))  # type: ignore[union-attr]
                await proc.stdin.drain()  # type: ignore[union-attr]
                await asyncio.wait_for(proc.stdout.readline(), timeout=max(1, int(timeout_seconds)))  # type: ignore[union-attr]

                # tools/list
                req = {"jsonrpc": "2.0", "id": 1, "method": "tools/list", "params": {}}
                proc.stdin.write((json.dumps(req) + "\n").encode("utf-8"))  # type: ignore[union-attr]
                await proc.stdin.drain()  # type: ignore[union-attr]
                line = await asyncio.wait_for(proc.stdout.readline(), timeout=max(1, int(timeout_seconds)))  # type: ignore[union-attr]
                if not line:
                    raise HTTPException(status_code=502, detail="MCP stdio server returned empty response")
                res = json.loads(line.decode("utf-8"))
                if res.get("error"):
                    raise HTTPException(status_code=502, detail=str(res["error"]))
                tools = (res.get("result") or {}).get("tools") or []
                norm = [
                    {
                        "name": t.get("name"),
                        "description": t.get("description", ""),
                        "input_schema": t.get("inputSchema", {}) or {},
                    }
                    for t in tools
                    if isinstance(t, dict) and t.get("name")
                ]
                await _audit_event(
                    "mcp_admin",
                    "workspace.mcp.discover_tools",
                    "success",
                    args={"server_name": server_name, "transport": transport},
                    result={"total": len(norm)},
                )
                return {"tools": norm, "total": len(norm)}
            finally:
                try:
                    proc.terminate()
                    await asyncio.wait_for(proc.wait(), timeout=2)
                except Exception:
                    pass

        raise HTTPException(status_code=400, detail=f"Unsupported MCP transport: {transport}")
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=502, detail=str(e))


@api_router.get("/workspace/mcp/servers/{server_name}/policy-check")
async def check_workspace_mcp_server_policy(server_name: str):
    """Check whether a workspace MCP server can be enabled/discovered under current policy."""
    if not _workspace_mcp_manager:
        raise HTTPException(status_code=503, detail="Workspace MCP manager not available")
    s = _workspace_mcp_manager.get_server(server_name)
    if not s:
        raise HTTPException(status_code=404, detail=f"MCP server {server_name} not found")

    env = _runtime_env()
    transport = str(s.transport or "").strip().lower()

    ok, reason = _prod_stdio_policy_check(server_name, transport, s.command, s.args, s.metadata)

    # Provide best-effort detail for admins (do not fail if any parsing errors happen).
    details: Dict[str, Any] = {"checks": {}, "policy": {}}
    try:
        details["checks"]["metadata_prod_allowed"] = bool((s.metadata or {}).get("prod_allowed", False))
        allowlist_raw = os.environ.get("AIPLAT_PROD_STDIO_MCP_ALLOWLIST", "")
        allowlist = [x.strip() for x in allowlist_raw.split(",") if x.strip()]
        details["checks"]["server_in_allowlist"] = server_name in set(allowlist)
        details["policy"]["AIPLAT_PROD_STDIO_MCP_ALLOWLIST"] = allowlist

        cmd = (s.command or "").strip()
        details["checks"]["command_present"] = bool(cmd)
        details["checks"]["command_absolute"] = bool(cmd.startswith("/"))

        prefixes_raw = os.environ.get("AIPLAT_STDIO_ALLOWED_COMMAND_PREFIXES", "")
        parts: List[str] = []
        for chunk in prefixes_raw.split(os.pathsep):
            parts.extend([x.strip() for x in chunk.split(",") if x.strip()])
        details["policy"]["AIPLAT_STDIO_ALLOWED_COMMAND_PREFIXES"] = parts
        details["checks"]["command_prefix_ok"] = bool(cmd and any(cmd.startswith((p if p.endswith("/") else p + "/")) or cmd == p for p in parts))

        deny_raw = os.environ.get("AIPLAT_STDIO_DENY_COMMAND_BASENAMES", "bash,sh,zsh")
        deny = [x.strip() for x in deny_raw.split(",") if x.strip()]
        details["policy"]["AIPLAT_STDIO_DENY_COMMAND_BASENAMES"] = deny
        details["checks"]["deny_basename_ok"] = (os.path.basename(cmd).lower() not in {x.lower() for x in deny}) if cmd else True

        details["checks"]["executable_ok"] = bool(cmd and os.path.exists(cmd) and os.access(cmd, os.X_OK))

        a = list(s.args or [])
        max_args = int(os.environ.get("AIPLAT_STDIO_MAX_ARGS", "32") or 32)
        max_len = int(os.environ.get("AIPLAT_STDIO_MAX_ARG_LENGTH", "512") or 512)
        details["policy"]["AIPLAT_STDIO_MAX_ARGS"] = max_args
        details["policy"]["AIPLAT_STDIO_MAX_ARG_LENGTH"] = max_len
        details["checks"]["args_count_ok"] = len(a) <= max_args
        details["checks"]["args_length_ok"] = all(len(str(x)) <= max_len for x in a)

        force_launcher = (os.environ.get("AIPLAT_STDIO_FORCE_LAUNCHER_IN_PROD", "") or "").strip().lower() in {"1", "true", "yes", "on"}
        launcher = (os.environ.get("AIPLAT_STDIO_PROD_LAUNCHER") or "").strip()
        details["policy"]["AIPLAT_STDIO_FORCE_LAUNCHER_IN_PROD"] = force_launcher
        details["policy"]["AIPLAT_STDIO_PROD_LAUNCHER"] = launcher
        details["checks"]["launcher_required"] = force_launcher
        details["checks"]["launcher_ok"] = (not force_launcher) or (bool(launcher) and cmd == launcher)
    except Exception:
        pass

    return {
        "env": env,
        "server_name": server_name,
        "transport": transport,
        "ok": bool(ok),
        "reason": reason,
        "details": details,
    }


@api_router.post("/workspace/mcp/servers")
async def upsert_workspace_mcp_server(request: dict, http_request: Request):
    """Create or update a workspace MCP server (writes to ~/.aiplat/mcps/<name>/server.yaml + policy.yaml)."""
    if not _workspace_mcp_manager:
        raise HTTPException(status_code=503, detail="Workspace MCP manager not available")
    try:
        from core.management.mcp_manager import MCPServerInfo

        name = str((request or {}).get("name") or "").strip()
        if not name:
            raise HTTPException(status_code=400, detail="Missing required field: name")
        info = MCPServerInfo(
            name=name,
            enabled=bool((request or {}).get("enabled", True)),
            transport=str((request or {}).get("transport") or "sse"),
            url=(request or {}).get("url"),
            command=(request or {}).get("command"),
            args=list((request or {}).get("args") or []),
            auth=(request or {}).get("auth") if isinstance((request or {}).get("auth"), dict) else None,
            allowed_tools=[str(x) for x in ((request or {}).get("allowed_tools") or [])],
            metadata=(request or {}).get("metadata") if isinstance((request or {}).get("metadata"), dict) else {},
        )
        saved = _workspace_mcp_manager.upsert_server(info)
        await _audit_event(
            "mcp_admin",
            "workspace.mcp.upsert",
            "success",
            args={"server_name": saved.name, "transport": saved.transport, "command": saved.command, "url": saved.url},
        )
        # Sync runtime tools (best-effort)
        try:
            await _sync_mcp_runtime()
        except Exception:
            pass
        # Mark as pending verification (best-effort)
        try:
            cur = _workspace_mcp_manager.get_server(saved.name)
            if cur:
                meta = dict(cur.metadata or {})
                meta["verification"] = {"status": "pending", "updated_at": time.time(), "source": "autosmoke"}
                cur.metadata = meta
                _workspace_mcp_manager.upsert_server(cur)
        except Exception:
            pass
        # Auto-smoke on MCP upsert (async, dedup)
        try:
            if _execution_store is not None and _job_scheduler is not None:
                from core.harness.smoke import enqueue_autosmoke

                tenant_id = http_request.headers.get("X-AIPLAT-TENANT-ID", "ops_smoke")
                actor_id = http_request.headers.get("X-AIPLAT-ACTOR-ID", "admin")
                sid = str(saved.name)

                async def _on_complete(job_run: Dict[str, Any]):
                    st = str(job_run.get("status") or "")
                    ver = {
                        "status": "verified" if st == "completed" else "failed",
                        "updated_at": time.time(),
                        "source": "autosmoke",
                        "job_id": f"autosmoke-mcp:{sid}",
                        "job_run_id": str(job_run.get("id") or ""),
                        "reason": str(job_run.get("error") or ""),
                    }
                    try:
                        cur2 = _workspace_mcp_manager.get_server(sid)
                        if cur2:
                            m2 = dict(cur2.metadata or {})
                            m2["verification"] = ver
                            cur2.metadata = m2
                            _workspace_mcp_manager.upsert_server(cur2)
                    except Exception:
                        pass

                await enqueue_autosmoke(
                    execution_store=_execution_store,
                    job_scheduler=_job_scheduler,
                    resource_type="mcp",
                    resource_id=sid,
                    tenant_id=tenant_id or "ops_smoke",
                    actor_id=actor_id or "admin",
                    detail={"op": "upsert", "transport": saved.transport},
                    on_complete=_on_complete,
                )
        except Exception:
            pass
        return {"status": "upserted", "server": {"name": saved.name, "enabled": saved.enabled}}
    except ValueError as e:
        raise HTTPException(status_code=409, detail=str(e))


@api_router.put("/workspace/mcp/servers/{server_name}")
async def update_workspace_mcp_server(server_name: str, request: dict, http_request: Request):
    """Update workspace MCP server (upsert semantics)."""
    payload = dict(request or {})
    payload["name"] = server_name
    return await upsert_workspace_mcp_server(payload, http_request)



@api_router.post("/workspace/mcp/servers/{server_name}/enable")
async def enable_workspace_mcp_server(server_name: str):
    if not _workspace_mcp_manager:
        raise HTTPException(status_code=503, detail="Workspace MCP manager not available")
    # Policy gate: stdio MCP is high risk. Default deny in prod.
    s = _workspace_mcp_manager.get_server(server_name)
    if not s:
        raise HTTPException(status_code=404, detail=f"MCP server {server_name} not found")
    if _autosmoke_enforce():
        if not _is_verified(getattr(s, "metadata", None)):
            raise HTTPException(status_code=403, detail="mcp_unverified: smoke must pass before enable")
    ok, reason = _prod_stdio_policy_check(server_name, str(s.transport or ""), s.command, s.args, s.metadata)
    if not ok:
        await _audit_event(
            "mcp_admin",
            "workspace.mcp.enable",
            "failed",
            args={"server_name": server_name, "transport": str(s.transport or ""), "command": s.command, "args": s.args},
            error=reason,
        )
        raise HTTPException(
            status_code=403,
            detail=f"stdio MCP server is blocked by prod policy: {reason}",
        )
    ok = _workspace_mcp_manager.set_enabled(server_name, True)
    if not ok:
        raise HTTPException(status_code=404, detail=f"MCP server {server_name} not found")
    await _audit_event(
        "mcp_admin",
        "workspace.mcp.enable",
        "success",
        args={"server_name": server_name, "transport": str(s.transport or ""), "command": s.command, "args": s.args},
    )
    try:
        await _sync_mcp_runtime()
    except Exception:
        pass
    return {"status": "enabled"}


@api_router.post("/workspace/mcp/servers/{server_name}/disable")
async def disable_workspace_mcp_server(server_name: str):
    if not _workspace_mcp_manager:
        raise HTTPException(status_code=503, detail="Workspace MCP manager not available")
    ok = _workspace_mcp_manager.set_enabled(server_name, False)
    if not ok:
        raise HTTPException(status_code=404, detail=f"MCP server {server_name} not found")
    await _audit_event("mcp_admin", "workspace.mcp.disable", "success", args={"server_name": server_name})
    try:
        await _sync_mcp_runtime()
    except Exception:
        pass
    return {"status": "disabled"}


# ==================== Workspace Packages (P0 MVP) ====================


@api_router.get("/workspace/packages")
async def list_workspace_packages(include_engine: bool = True) -> Dict[str, Any]:
    items: List[Dict[str, Any]] = []
    if _workspace_package_manager:
        for p in _workspace_package_manager.list_packages():
            items.append({"name": p.name, "scope": p.scope, "version": p.version, "description": p.description, "resources": p.resources})
    if include_engine and _package_manager:
        for p in _package_manager.list_packages():
            items.append({"name": p.name, "scope": p.scope, "version": p.version, "description": p.description, "resources": p.resources})
    return {"items": items, "total": len(items)}


@api_router.get("/workspace/packages/{pkg_name}")
async def get_workspace_package(pkg_name: str) -> Dict[str, Any]:
    p = _workspace_package_manager.get_package(pkg_name) if _workspace_package_manager else None
    if not p and _package_manager:
        p = _package_manager.get_package(pkg_name)
    if not p:
        raise HTTPException(status_code=404, detail="package_not_found")
    return {
        "name": p.name,
        "scope": p.scope,
        "version": p.version,
        "description": p.description,
        "manifest_path": p.manifest_path,
        "package_dir": p.package_dir,
        "resources": p.resources,
    }


@api_router.post("/workspace/packages")
async def create_workspace_package(request: Dict[str, Any]) -> Dict[str, Any]:
    if not _workspace_package_manager:
        raise HTTPException(status_code=503, detail="Workspace package manager not available")
    name = str((request or {}).get("name") or "").strip()
    if not name:
        raise HTTPException(status_code=400, detail="missing_name")
    bundle = bool((request or {}).get("bundle", True))
    resources = (request or {}).get("resources") or []
    if not isinstance(resources, list):
        raise HTTPException(status_code=400, detail="resources_must_be_list")

    manifest = {
        "name": name,
        "version": str((request or {}).get("version") or "0.1.0"),
        "description": str((request or {}).get("description") or ""),
        "resources": resources,
    }
    info = _workspace_package_manager.upsert_package(manifest=manifest)

    # Optional: bundle resources into package/bundle/*
    if bundle:
        try:
            import shutil
            from pathlib import Path

            pkg_dir = Path(info.package_dir)
            bdir = pkg_dir / "bundle"
            if bdir.exists():
                shutil.rmtree(bdir, ignore_errors=True)
            (bdir / "agents").mkdir(parents=True, exist_ok=True)
            (bdir / "skills").mkdir(parents=True, exist_ok=True)
            (bdir / "mcps").mkdir(parents=True, exist_ok=True)
            (bdir / "hooks").mkdir(parents=True, exist_ok=True)

            repo_root = Path(__file__).resolve().parent  # aiPlat-core/core
            engine_agents = (repo_root / "engine" / "agents").resolve()
            engine_skills = (repo_root / "engine" / "skills").resolve()
            engine_mcps = (repo_root / "engine" / "mcps").resolve()
            wk_agents = (Path.home() / ".aiplat" / "agents").resolve()
            wk_skills = (Path.home() / ".aiplat" / "skills").resolve()
            wk_mcps = (Path.home() / ".aiplat" / "mcps").resolve()
            wk_hooks = (Path.home() / ".aiplat" / "hooks").resolve()

            for r in resources:
                if not isinstance(r, dict):
                    continue
                kind = str(r.get("kind") or "")
                rid = str(r.get("id") or "")
                scope = str(r.get("scope") or "engine").lower()
                if not kind or not rid:
                    continue
                if kind == "agent":
                    src = (engine_agents / rid) if scope == "engine" else (wk_agents / rid)
                    dst = bdir / "agents" / rid
                    if src.exists() and src.is_dir():
                        shutil.copytree(src, dst, dirs_exist_ok=True)
                        r["bundled"] = True
                elif kind == "skill":
                    src = (engine_skills / rid) if scope == "engine" else (wk_skills / rid)
                    dst = bdir / "skills" / rid
                    if src.exists() and src.is_dir():
                        shutil.copytree(src, dst, dirs_exist_ok=True)
                        r["bundled"] = True
                elif kind == "mcp":
                    src = (engine_mcps / rid) if scope == "engine" else (wk_mcps / rid)
                    dst = bdir / "mcps" / rid
                    if src.exists() and src.is_dir():
                        shutil.copytree(src, dst, dirs_exist_ok=True)
                        r["bundled"] = True
                elif kind == "hook":
                    src = wk_hooks / f"{rid}.py"
                    dst = bdir / "hooks" / f"{rid}.py"
                    if src.exists() and src.is_file():
                        dst.parent.mkdir(parents=True, exist_ok=True)
                        shutil.copy2(src, dst)
                        r["bundled"] = True

            (pkg_dir / "package.yaml").write_text(yaml.safe_dump(manifest, sort_keys=False, allow_unicode=True), encoding="utf-8")
            _workspace_package_manager.reload()
        except Exception:
            pass

    return {"status": "upserted", "package": await get_workspace_package(name)}


@api_router.delete("/workspace/packages/{pkg_name}")
async def delete_workspace_package(pkg_name: str) -> Dict[str, Any]:
    if not _workspace_package_manager:
        raise HTTPException(status_code=503, detail="Workspace package manager not available")
    ok = _workspace_package_manager.delete_package(pkg_name)
    if not ok:
        raise HTTPException(status_code=404, detail="package_not_found")
    return {"status": "deleted", "name": pkg_name}


@api_router.post("/workspace/packages/{pkg_name}/install")
async def install_workspace_package(pkg_name: str, http_request: Request, request: Dict[str, Any]) -> Dict[str, Any]:
    allow_overwrite = bool((request or {}).get("allow_overwrite", False))
    mgr = _workspace_package_manager if (_workspace_package_manager and _workspace_package_manager.get_package(pkg_name)) else _package_manager
    if not mgr:
        raise HTTPException(status_code=404, detail="package_not_found")
    try:
        record = mgr.install(pkg_name=pkg_name, allow_overwrite=allow_overwrite)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))

    _reload_workspace_managers()
    await _sync_mcp_runtime()

    try:
        if _execution_store is not None and _job_scheduler is not None:
            from core.harness.smoke import enqueue_autosmoke

            tenant_id = http_request.headers.get("X-AIPLAT-TENANT-ID", "ops_smoke")
            actor_id = http_request.headers.get("X-AIPLAT-ACTOR-ID", "admin")
            for it in (record.get("applied") or []):
                k = str(it.get("kind") or "")
                rid = str(it.get("id") or "")
                if k not in {"agent", "skill", "mcp"} or not rid:
                    continue
                await enqueue_autosmoke(
                    execution_store=_execution_store,
                    job_scheduler=_job_scheduler,
                    resource_type=k,
                    resource_id=rid,
                    tenant_id=tenant_id or "ops_smoke",
                    actor_id=actor_id or "admin",
                    detail={"op": "package_install", "package": pkg_name},
                )
    except Exception:
        pass

    return {"status": "installed", "record": record}


@api_router.post("/workspace/packages/{pkg_name}/uninstall")
async def uninstall_workspace_package(pkg_name: str, request: Dict[str, Any]) -> Dict[str, Any]:
    if not _workspace_package_manager:
        raise HTTPException(status_code=503, detail="Workspace package manager not available")
    keep_modified = bool((request or {}).get("keep_modified", True))
    try:
        res = _workspace_package_manager.uninstall(pkg_name=pkg_name, keep_modified=keep_modified)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))

    _reload_workspace_managers()
    await _sync_mcp_runtime()
    return {"status": "uninstalled", "result": res}


@api_router.get("/skills/{skill_id}/binding-stats")
async def get_skill_binding_stats(skill_id: str):
    """Get skill binding statistics"""
    registry = get_skill_registry()
    stats = registry.get_binding_stats(skill_id)
    if not stats:
        return {"total_agents": 0, "total_calls": 0}
    return {
        "total_agents": len(stats.bound_agents),
        "total_calls": stats.total_executions,
        "avg_success_rate": stats.success_count / stats.total_executions if stats.total_executions > 0 else 0
    }


@api_router.get("/skills/{skill_id}/versions")
async def get_skill_versions(skill_id: str):
    """Get skill versions"""
    registry = get_skill_registry()
    versions = registry.get_versions(skill_id)
    return {
        "versions": [{"version": v.version, "is_active": v.is_active} for v in versions]
    }


@api_router.get("/skills/{skill_id}/versions/{version}")
async def get_skill_version(skill_id: str, version: str):
    """Get specific skill version"""
    registry = get_skill_registry()
    config = registry.get_version(skill_id, version)
    if not config:
        raise HTTPException(status_code=404, detail=f"Version {version} not found")
    # Return real config for auditability & rollback verification
    try:
        from dataclasses import asdict, is_dataclass
        cfg_dict = asdict(config) if is_dataclass(config) else dict(config)  # type: ignore[arg-type]
    except Exception:
        cfg_dict = {
            "name": getattr(config, "name", ""),
            "description": getattr(config, "description", ""),
            "input_schema": getattr(config, "input_schema", {}) or {},
            "output_schema": getattr(config, "output_schema", {}) or {},
            "timeout": getattr(config, "timeout", None),
            "metadata": getattr(config, "metadata", {}) or {},
        }
    return {"version": version, "config": cfg_dict}


@api_router.post("/skills/{skill_id}/versions/{version}/rollback")
async def rollback_skill_version(skill_id: str, version: str):
    """Rollback skill version"""
    registry = get_skill_registry()
    ok = registry.rollback_version(skill_id, version)
    if not ok:
        raise HTTPException(status_code=404, detail=f"Version {version} not found")
    active_version = registry.get_active_version(skill_id) if hasattr(registry, "get_active_version") else version
    active_config = registry.get_version(skill_id, active_version) if active_version else None
    cfg = None
    if active_config is not None:
        try:
            from dataclasses import asdict, is_dataclass
            cfg = asdict(active_config) if is_dataclass(active_config) else dict(active_config)  # type: ignore[arg-type]
        except Exception:
            cfg = {"name": getattr(active_config, "name", ""), "metadata": getattr(active_config, "metadata", {}) or {}}
    return {"status": "rolled_back", "active_version": active_version, "active_config": cfg}


@api_router.get("/skills/{skill_id}/active-version")
async def get_skill_active_version(skill_id: str):
    """Get currently active version for a skill."""
    registry = get_skill_registry()
    if not registry.get(skill_id):
        raise HTTPException(status_code=404, detail=f"Skill {skill_id} not found")
    active_version = registry.get_active_version(skill_id) if hasattr(registry, "get_active_version") else None
    return {"skill_id": skill_id, "active_version": active_version}


@api_router.post("/skills/{skill_id}/execute")
async def execute_skill(skill_id: str, request: SkillExecuteRequest, http_request: Request):
    """Execute skill"""
    ctx_for_user: Dict[str, Any] = dict(request.context or {}) if isinstance(request.context, dict) else {}
    try:
        tmp = _inject_http_request_context({"context": dict(ctx_for_user)}, http_request, entrypoint="api")
        ctx_for_user = tmp.get("context") if isinstance(tmp, dict) and isinstance(tmp.get("context"), dict) else ctx_for_user
    except Exception:
        pass
    deny = await _rbac_guard(http_request=http_request, payload={"context": ctx_for_user}, action="execute", resource_type="skill", resource_id=str(skill_id))
    if deny:
        return deny
    user_id = str(ctx_for_user.get("actor_id") or ctx_for_user.get("user_id") or "system")
    harness = get_harness()
    exec_req = ExecutionRequest(
        kind="skill",
        target_id=skill_id,
        payload={
            "input": request.input,
            "context": ctx_for_user,
            "mode": getattr(request, "mode", "inline"),
            "options": getattr(request, "options", None) or None,
        },
        user_id=user_id,
        session_id=str(ctx_for_user.get("session_id") or "default"),
    )
    result = await harness.execute(exec_req)
    resp = _wrap_execution_result_as_run_summary(result)
    try:
        await _audit_execute(http_request=http_request, payload={"context": ctx_for_user}, resource_type="skill", resource_id=str(skill_id), resp=resp, action="execute_skill")
    except Exception:
        pass
    return JSONResponse(status_code=200 if resp.get("ok") else int(getattr(result, "http_status", 500) or 500), content=resp)


@api_router.get("/skills/executions/{execution_id}")
async def get_skill_execution(execution_id: str):
    """Get skill execution"""
    record = await _execution_store.get_skill_execution(execution_id) if _execution_store else None
    if not record:
        record = _skill_executions.get(execution_id)
    if not record:
        # fallback to in-memory SkillManager store if present
        try:
            exec_ = await _skill_manager.get_execution(execution_id)  # type: ignore[union-attr]
            if exec_:
                return {
                    "execution_id": exec_.id,
                    "skill_id": exec_.skill_id,
                    "status": exec_.status,
                    "input": exec_.input_data,
                    "output": exec_.output_data,
                    "error": exec_.error,
                    "start_time": exec_.start_time.isoformat() if exec_.start_time else None,
                    "end_time": exec_.end_time.isoformat() if exec_.end_time else None,
                    "duration_ms": exec_.duration_ms,
                }
        except Exception:
            pass
        raise HTTPException(status_code=404, detail=f"Execution {execution_id} not found")

    # normalize payload shape for API stability
    return {
        "execution_id": record["id"],
        "skill_id": record["skill_id"],
        "status": record["status"],
        "input": record.get("input"),
        "output": record.get("output"),
        "error": record.get("error"),
        "trace_id": record.get("trace_id"),
        "start_time": datetime.utcfromtimestamp(record["start_time"]).isoformat() if record.get("start_time") else None,
        "end_time": datetime.utcfromtimestamp(record["end_time"]).isoformat() if record.get("end_time") else None,
        "duration_ms": record.get("duration_ms"),
    }


@api_router.get("/skills/{skill_id}/executions")
async def list_skill_executions(skill_id: str, limit: int = 100, offset: int = 0):
    """List skill executions"""
    if _execution_store:
        items, total = await _execution_store.list_skill_executions(skill_id, limit=limit, offset=offset)
        executions = [
            {
                "execution_id": r["id"],
                "skill_id": r["skill_id"],
                "status": r["status"],
                "input": r.get("input"),
                "output": r.get("output"),
                "error": r.get("error"),
                "trace_id": r.get("trace_id"),
                "start_time": datetime.utcfromtimestamp(r["start_time"]).isoformat() if r.get("start_time") else None,
                "end_time": datetime.utcfromtimestamp(r["end_time"]).isoformat() if r.get("end_time") else None,
                "duration_ms": r.get("duration_ms"),
            }
            for r in items
        ]
        return {"executions": executions, "total": total}

    skill_executions = [e for e in _skill_executions.values() if e.get("skill_id") == skill_id]
    skill_executions = skill_executions[offset : offset + limit]
    return {"executions": skill_executions, "total": len([e for e in _skill_executions.values() if e.get("skill_id") == skill_id])}


@api_router.get("/skills/{skill_id}/trigger-conditions")
async def get_skill_trigger_conditions(skill_id: str):
    """Get skill trigger conditions (routing rules)"""
    skill = await _skill_manager.get_skill(skill_id)
    if not skill:
        raise HTTPException(status_code=404, detail=f"Skill {skill_id} not found")
    
    return {
        "skill_id": skill_id,
        "trigger_conditions": skill.metadata.get("trigger_conditions", []) if skill.metadata else []
    }


@api_router.put("/skills/{skill_id}/trigger-conditions")
async def update_skill_trigger_conditions(skill_id: str, request: dict):
    """Update skill trigger conditions"""
    skill = await _skill_manager.get_skill(skill_id)
    if not skill:
        raise HTTPException(status_code=404, detail=f"Skill {skill_id} not found")
    
    trigger_conditions = request.get("trigger_conditions", [])
    await _skill_manager.update_skill(skill_id, metadata={"trigger_conditions": trigger_conditions})
    
    return {"status": "updated", "trigger_conditions": trigger_conditions}


@api_router.post("/skills/{skill_id}/test-trigger")
async def test_skill_trigger(skill_id: str, request: dict):
    """Test if skill would be triggered by given input"""
    skill = await _skill_manager.get_skill(skill_id)
    if not skill:
        raise HTTPException(status_code=404, detail=f"Skill {skill_id} not found")
    
    test_input = request.get("input", "")
    conditions = skill.metadata.get("trigger_conditions", []) if skill.metadata else []
    
    matched = False
    for condition in conditions:
        if condition.get("keyword") in test_input.lower():
            matched = True
            break
    
    return {
        "skill_id": skill_id,
        "would_trigger": matched,
        "matched_condition": condition if matched else None
    }


# ==================== Trace / Graph Persistence ====================

@api_router.get("/traces")
async def list_traces(limit: int = 100, offset: int = 0, status: Optional[str] = None):
    """List persisted traces (requires ExecutionStore)."""
    if not _execution_store:
        raise HTTPException(status_code=503, detail="ExecutionStore not initialized")
    items, total = await _execution_store.list_traces(limit=limit, offset=offset, status=status)
    traces = [
        {
            **t,
            "start_time": datetime.utcfromtimestamp(t["start_time"]).isoformat() if t.get("start_time") else None,
            "end_time": datetime.utcfromtimestamp(t["end_time"]).isoformat() if t.get("end_time") else None,
        }
        for t in items
    ]
    return {"traces": traces, "total": total, "limit": limit, "offset": offset}


@api_router.get("/traces/{trace_id}")
async def get_trace(trace_id: str):
    """Get a persisted trace with spans."""
    if not _execution_store:
        raise HTTPException(status_code=503, detail="ExecutionStore not initialized")
    trace = await _execution_store.get_trace(trace_id, include_spans=True)
    if not trace:
        raise HTTPException(status_code=404, detail=f"Trace {trace_id} not found")
    trace["start_time"] = datetime.utcfromtimestamp(trace["start_time"]).isoformat() if trace.get("start_time") else None
    trace["end_time"] = datetime.utcfromtimestamp(trace["end_time"]).isoformat() if trace.get("end_time") else None
    for s in trace.get("spans", []) or []:
        s["start_time"] = datetime.utcfromtimestamp(s["start_time"]).isoformat() if s.get("start_time") else None
        s["end_time"] = datetime.utcfromtimestamp(s["end_time"]).isoformat() if s.get("end_time") else None
    return trace


@api_router.get("/executions/{execution_id}/trace")
async def get_trace_by_execution(execution_id: str):
    """Get trace (with spans) by execution_id (agent/skill)."""
    if not _execution_store:
        raise HTTPException(status_code=503, detail="ExecutionStore not initialized")
    trace_id = await _execution_store.get_trace_id_by_execution_id(execution_id)
    if not trace_id:
        raise HTTPException(status_code=404, detail=f"Trace not found for execution {execution_id}")
    trace = await _execution_store.get_trace(trace_id, include_spans=True)
    if not trace:
        raise HTTPException(status_code=404, detail=f"Trace {trace_id} not found")
    trace["start_time"] = datetime.utcfromtimestamp(trace["start_time"]).isoformat() if trace.get("start_time") else None
    trace["end_time"] = datetime.utcfromtimestamp(trace["end_time"]).isoformat() if trace.get("end_time") else None
    return trace


@api_router.get("/traces/{trace_id}/executions")
async def list_executions_by_trace(trace_id: str, limit: int = 100, offset: int = 0):
    """List agent/skill executions linked to a trace_id."""
    if not _execution_store:
        raise HTTPException(status_code=503, detail="ExecutionStore not initialized")
    items = await _execution_store.list_executions_by_trace_id(trace_id, limit=limit, offset=offset)
    return {"trace_id": trace_id, "items": items, "limit": limit, "offset": offset}


@api_router.get("/graphs/runs/{run_id}")
async def get_graph_run(run_id: str):
    """Get a persisted LangGraph run (requires ExecutionStore)."""
    if not _execution_store:
        raise HTTPException(status_code=503, detail="ExecutionStore not initialized")
    run = await _execution_store.get_graph_run(run_id)
    if not run:
        raise HTTPException(status_code=404, detail=f"Graph run {run_id} not found")
    run["start_time"] = datetime.utcfromtimestamp(run["start_time"]).isoformat() if run.get("start_time") else None
    run["end_time"] = datetime.utcfromtimestamp(run["end_time"]).isoformat() if run.get("end_time") else None
    return run


@api_router.get("/graphs/runs")
async def list_graph_runs(
    limit: int = 100,
    offset: int = 0,
    graph_name: Optional[str] = None,
    status: Optional[str] = None,
    trace_id: Optional[str] = None,
):
    """List persisted graph runs (requires ExecutionStore)."""
    if not _execution_store:
        raise HTTPException(status_code=503, detail="ExecutionStore not initialized")
    result = await _execution_store.list_graph_runs(limit=limit, offset=offset, graph_name=graph_name, status=status, trace_id=trace_id)
    items = result.get("items", [])
    for r in items:
        r["start_time"] = datetime.utcfromtimestamp(r["start_time"]).isoformat() if r.get("start_time") else None
        r["end_time"] = datetime.utcfromtimestamp(r["end_time"]).isoformat() if r.get("end_time") else None
    return {"runs": items, "total": result.get("total", 0), "limit": limit, "offset": offset}


@api_router.get("/graphs/runs/{run_id}/checkpoints")
async def list_graph_checkpoints(run_id: str, limit: int = 100, offset: int = 0):
    """List persisted checkpoints for a run."""
    if not _execution_store:
        raise HTTPException(status_code=503, detail="ExecutionStore not initialized")
    checkpoints = await _execution_store.list_graph_checkpoints(run_id, limit=limit, offset=offset)
    for c in checkpoints:
        c["created_at"] = datetime.utcfromtimestamp(c["created_at"]).isoformat() if c.get("created_at") else None
    return {"run_id": run_id, "checkpoints": checkpoints, "limit": limit, "offset": offset}


@api_router.get("/graphs/runs/{run_id}/checkpoints/{checkpoint_id}")
async def get_graph_checkpoint(run_id: str, checkpoint_id: str):
    """Get a persisted checkpoint by id."""
    if not _execution_store:
        raise HTTPException(status_code=503, detail="ExecutionStore not initialized")
    ckpt = await _execution_store.get_graph_checkpoint(checkpoint_id)
    if not ckpt or ckpt.get("run_id") != run_id:
        raise HTTPException(status_code=404, detail=f"Checkpoint {checkpoint_id} not found")
    ckpt["created_at"] = datetime.utcfromtimestamp(ckpt["created_at"]).isoformat() if ckpt.get("created_at") else None
    return ckpt


@api_router.post("/graphs/runs/{run_id}/resume")
async def resume_graph_run(run_id: str, request: dict):
    """
    Create a new run from a checkpoint state (restore/resume semantics).
    request:
      - checkpoint_id (optional)
      - step (optional)
    """
    if not _execution_store:
        raise HTTPException(status_code=503, detail="ExecutionStore not initialized")

    user_id = request.get("user_id", "system")
    if user_id != "system":
        perm_mgr = get_permission_manager()
        parent = await _execution_store.get_graph_run(run_id)
        graph_name = parent.get("graph_name") if parent else None
        resource_id = f"graph:{graph_name}" if graph_name else f"graph_run:{run_id}"
        if not perm_mgr.check_permission(user_id, resource_id, Permission.EXECUTE):
            raise HTTPException(status_code=403, detail=f"User '{user_id}' lacks EXECUTE permission for '{resource_id}'")

    checkpoint_id = request.get("checkpoint_id")
    step = request.get("step")

    ckpt = None
    if checkpoint_id:
        ckpt = await _execution_store.get_graph_checkpoint(checkpoint_id)
    elif step is not None:
        ckpt = await _execution_store.get_graph_checkpoint_by_step(run_id, int(step))
    else:
        ckpt = await _execution_store.get_latest_graph_checkpoint(run_id)

    if not ckpt:
        raise HTTPException(status_code=404, detail="Checkpoint not found")
    if ckpt.get("run_id") != run_id:
        raise HTTPException(status_code=400, detail="Checkpoint does not belong to run_id")

    resumed = await _execution_store.resume_graph_run(parent_run_id=run_id, checkpoint_id=ckpt["checkpoint_id"])
    if not resumed:
        raise HTTPException(status_code=500, detail="Failed to resume graph run")
    return resumed


@api_router.post("/graphs/compiled/react/execute")
async def execute_compiled_react_graph(request: dict, http_request: Request):
    """
    Execute internal CompiledGraph-based ReAct workflow (checkpoint/callback enabled).

    request:
      - messages: [{role, content}]
      - context: dict
      - max_steps: int
      - checkpoint_interval: int
    """
    harness = get_harness()
    payload = _inject_http_request_context(dict(request or {}), http_request, entrypoint="api")
    ctx0 = payload.get("context") if isinstance(payload.get("context"), dict) else {}
    user_id = payload.get("user_id") or (ctx0.get("actor_id") if isinstance(ctx0, dict) else None) or "system"
    session_id = payload.get("session_id") or (ctx0.get("session_id") if isinstance(ctx0, dict) else None) or "default"
    exec_req = ExecutionRequest(
        kind="graph",
        target_id="compiled_react",
        payload=payload,
        user_id=str(user_id),
        session_id=str(session_id),
    )
    result = await harness.execute(exec_req)
    resp = _wrap_execution_result_as_run_summary(result)
    return JSONResponse(status_code=200 if resp.get("ok") else int(getattr(result, "http_status", 500) or 500), content=resp)


@api_router.post("/graphs/runs/{run_id}/resume/execute")
async def resume_and_execute_compiled_graph(run_id: str, request: dict):
    """
    Resume from a checkpoint and continue executing using CompiledGraph-based ReAct workflow.
    This endpoint closes the loop: resume -> execute -> persist.

    request:
      - checkpoint_id (optional)
      - step (optional)
      - max_steps (optional)
      - checkpoint_interval (optional)
    """
    if not _execution_store:
        raise HTTPException(status_code=503, detail="ExecutionStore not initialized")

    user_id = request.get("user_id", "system")
    if user_id != "system":
        perm_mgr = get_permission_manager()
        parent = await _execution_store.get_graph_run(run_id)
        graph_name = parent.get("graph_name") if parent else None
        resource_id = f"graph:{graph_name}" if graph_name else f"graph_run:{run_id}"
        if not perm_mgr.check_permission(user_id, resource_id, Permission.EXECUTE):
            raise HTTPException(status_code=403, detail=f"User '{user_id}' lacks EXECUTE permission for '{resource_id}'")

    checkpoint_id = request.get("checkpoint_id")
    step = request.get("step")
    max_steps = int(request.get("max_steps", 10) or 10)
    checkpoint_interval = int(request.get("checkpoint_interval", 1) or 1)

    ckpt = None
    if checkpoint_id:
        ckpt = await _execution_store.get_graph_checkpoint(checkpoint_id)
    elif step is not None:
        ckpt = await _execution_store.get_graph_checkpoint_by_step(run_id, int(step))
    else:
        ckpt = await _execution_store.get_latest_graph_checkpoint(run_id)

    if not ckpt:
        raise HTTPException(status_code=404, detail="Checkpoint not found")
    if ckpt.get("run_id") != run_id:
        raise HTTPException(status_code=400, detail="Checkpoint does not belong to run_id")

    resumed = await _execution_store.resume_graph_run(parent_run_id=run_id, checkpoint_id=ckpt["checkpoint_id"])
    if not resumed:
        raise HTTPException(status_code=500, detail="Failed to resume graph run")

    restored_state = resumed.get("state") if isinstance(resumed.get("state"), dict) else {}
    # ensure max_steps override
    restored_state["max_steps"] = max_steps

    class _DefaultModel:
        async def generate(self, prompt):
            return type("R", (), {"content": "DONE"})

    from core.harness.execution.langgraph.compiled_graphs import create_compiled_react_graph
    from core.harness.execution.langgraph.core import GraphConfig

    import uuid  # noqa: F401  (kept for symmetry; graph_run_id may be generated in other flows)

    # attach trace_id for correlation: run_id -> trace_id, and tool spans -> trace_id
    trace_id = None
    if _trace_service:
        try:
            t = await _trace_service.start_trace(
                name=f"graph:{resumed.get('graph_name') or 'compiled_react'}",
                attributes={"graph_name": resumed.get("graph_name") or "compiled_react", "graph_run_id": resumed.get("run_id"), "parent_run_id": run_id, "source": "graph"},
            )
            trace_id = t.trace_id
        except Exception:
            trace_id = None
    try:
        meta = restored_state.get("metadata") if isinstance(restored_state.get("metadata"), dict) else {}
        meta["trace_id"] = trace_id
        restored_state["metadata"] = meta
    except Exception:
        pass

    graph = create_compiled_react_graph(model=_DefaultModel(), tools=[], max_steps=max_steps, graph_name=resumed.get("graph_name") or "compiled_react")
    try:
        final_state = await graph.execute(
            restored_state,
            config=GraphConfig(max_steps=max_steps, enable_checkpoints=True, checkpoint_interval=checkpoint_interval, enable_callbacks=True),
        )
    finally:
        if _trace_service and trace_id:
            try:
                await _trace_service.end_trace(trace_id, status=SpanStatus.SUCCESS)
            except Exception:
                pass
            try:
                _trace_service._context = None
            except Exception:
                pass
    return {"parent_run_id": run_id, "run_id": resumed.get("run_id"), "checkpoint_id": resumed.get("checkpoint_id"), "final_state": final_state}


@api_router.get("/skills/{skill_id}/evolution")
async def get_skill_evolution_status(skill_id: str):
    """Get skill evolution status (CAPTURED/FIX/DERIVED)"""
    skill = await _skill_manager.get_skill(skill_id)
    if not skill:
        raise HTTPException(status_code=404, detail=f"Skill {skill_id} not found")
    
    evolution = skill.metadata.get("evolution", {}) if skill.metadata else {}
    
    return {
        "skill_id": skill_id,
        "status": evolution.get("status", "stable"),
        "last_evolution": evolution.get("last_evolution", None),
        "evolution_count": evolution.get("evolution_count", 0),
        "parent_skill_id": evolution.get("parent_skill_id", None),
        "child_skill_ids": evolution.get("child_skill_ids", [])
    }


@api_router.post("/skills/{skill_id}/evolution")
async def trigger_skill_evolution(skill_id: str, request: dict):
    """Manually trigger skill evolution"""
    skill = await _skill_manager.get_skill(skill_id)
    if not skill:
        raise HTTPException(status_code=404, detail=f"Skill {skill_id} not found")
    
    trigger_type = request.get("trigger_type", "manual")
    
    evolution = skill.metadata.get("evolution", {}) if skill.metadata else {}
    evolution["status"] = "capturing" if trigger_type == "capture" else "fixing"
    evolution["last_evolution"] = datetime.utcnow().isoformat()
    evolution["evolution_count"] = evolution.get("evolution_count", 0) + 1
    
    await _skill_manager.update_skill(skill_id, metadata={"evolution": evolution})
    
    return {
        "status": "triggered",
        "evolution_type": trigger_type,
        "evolution_count": evolution["evolution_count"]
    }


@api_router.get("/skills/{skill_id}/lineage")
async def get_skill_lineage(skill_id: str):
    """Get skill lineage (evolution history)"""
    skill = await _skill_manager.get_skill(skill_id)
    if not skill:
        raise HTTPException(status_code=404, detail=f"Skill {skill_id} not found")
    
    lineage = skill.metadata.get("lineage", []) if skill.metadata else []
    
    return {
        "skill_id": skill_id,
        "lineage": lineage,
        "total": len(lineage)
    }


@api_router.get("/skills/{skill_id}/captures")
async def get_skill_captures(skill_id: str, limit: int = 100, offset: int = 0):
    """Get captured interactions for skill"""
    return {
        "captures": [],
        "total": 0,
        "note": "Captures are stored in skill evolution module"
    }


@api_router.get("/skills/{skill_id}/fixes")
async def get_skill_fixes(skill_id: str, limit: int = 100, offset: int = 0):
    """Get applied fixes for skill"""
    skill = await _skill_manager.get_skill(skill_id)
    if not skill:
        raise HTTPException(status_code=404, detail=f"Skill {skill_id} not found")
    
    evolution = skill.metadata.get("evolution", {}) if skill.metadata else {}
    fixes = evolution.get("fixes", [])
    
    return {
        "fixes": fixes[offset:offset+limit],
        "total": len(fixes)
    }


@api_router.get("/skills/{skill_id}/derived")
async def get_skill_derived(skill_id: str):
    """Get derived skills (children) from this skill"""
    skill = await _skill_manager.get_skill(skill_id)
    if not skill:
        raise HTTPException(status_code=404, detail=f"Skill {skill_id} not found")
    
    evolution = skill.metadata.get("evolution", {}) if skill.metadata else {}
    child_ids = evolution.get("child_skill_ids", [])
    
    return {
        "derived_skills": [{"id": c} for c in child_ids],
        "total": len(child_ids)
    }


# ==================== Memory Management ====================

@api_router.get("/memory/sessions")
async def list_sessions(http_request: Request, limit: int = 100, offset: int = 0):
    """List memory sessions"""
    if _execution_store:
        tenant_id = None
        try:
            if http_request is not None:
                tenant_id = _rbac_actor_from_http(http_request, None).get("tenant_id")
        except Exception:
            tenant_id = None
        res = await _execution_store.list_memory_sessions(tenant_id=str(tenant_id) if tenant_id else None, limit=limit, offset=offset)
        out = []
        for s in res.get("items") or []:
            out.append(
                {
                    "session_id": s.get("id"),
                    "tenant_id": s.get("tenant_id"),
                    "metadata": s.get("metadata") or {},
                    "created_at": s.get("created_at"),
                    "updated_at": s.get("updated_at"),
                    "message_count": s.get("message_count") or 0,
                }
            )
        return {"sessions": out, "total": int(res.get("total") or 0)}

    # Fallback to legacy in-memory manager
    sessions = await _memory_manager.list_sessions(limit=limit, offset=offset)
    result = []
    for s in sessions:
        result.append(
            {
                "session_id": s.id,
                "metadata": s.metadata,
                "created_at": s.created_at.isoformat() if s.created_at else None,
                "updated_at": s.last_activity.isoformat() if s.last_activity else None,
                "message_count": s.message_count,
            }
        )
    counts = _memory_manager.get_session_count()
    return {"sessions": result, "total": counts["total"]}


@api_router.post("/memory/sessions")
async def create_session(request: SessionCreateRequest, http_request: Request):
    """Create memory session"""
    meta = request.metadata or {}
    if _execution_store:
        actor0 = _rbac_actor_from_http(http_request, {"context": meta} if isinstance(meta, dict) else None)
        tid = actor0.get("tenant_id")
        # keep old behavior: allow user_id from metadata, else fall back to actor_id
        uid = meta.get("user_id") if isinstance(meta, dict) else None
        if not uid:
            uid = actor0.get("actor_id") or "system"
        if isinstance(meta, dict):
            meta.setdefault("tenant_id", tid)
            meta.setdefault("actor_id", actor0.get("actor_id"))
            meta.setdefault("actor_role", actor0.get("actor_role"))
        session = await _execution_store.create_memory_session(
            tenant_id=str(tid) if tid else None,
            user_id=str(uid),
            agent_type=str(meta.get("agent_type", "default")),
            session_type=str(meta.get("session_type", "session")),
            metadata=meta,
            session_id=request.session_id,
        )
        return {"session_id": session.get("id"), "status": "created"}

    session = await _memory_manager.create_session(
        agent_type=meta.get("agent_type", "default"),
        user_id=meta.get("user_id", "system"),
        session_type=meta.get("session_type", "short_term"),
        metadata=meta,
    )
    return {"session_id": session.id, "status": "created"}


@api_router.get("/memory/sessions/{session_id}")
async def get_session(session_id: str, http_request: Request):
    """Get session details"""
    if _execution_store:
        actor0 = _rbac_actor_from_http(http_request, None)
        tid = actor0.get("tenant_id")
        session = await _execution_store.get_memory_session(session_id=session_id)
        if not session or (tid and str(session.get("tenant_id") or "") != str(tid)):
            raise HTTPException(status_code=404, detail=f"Session {session_id} not found")
        msgs = await _execution_store.list_memory_messages(session_id=session_id, tenant_id=str(tid) if tid else None, limit=200, offset=0)
        return {
            "session_id": session_id,
            "messages": [
                {
                    "role": m.get("role"),
                    "content": m.get("content"),
                    "timestamp": m.get("created_at"),
                    "source_run_id": m.get("source_run_id"),
                    "run_id": m.get("run_id"),
                    "sensitivity": m.get("sensitivity"),
                }
                for m in (msgs.get("items") or [])
            ],
            "metadata": session.get("metadata") or {},
            "message_count": int(msgs.get("total") or 0),
            "tenant_id": session.get("tenant_id"),
        }

    session = await _memory_manager.get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail=f"Session {session_id} not found")
    messages = await _memory_manager.get_messages(session_id)
    return {
        "session_id": session_id,
        "messages": [
            {"role": m.role, "content": m.content, "timestamp": m.created_at.isoformat() if m.created_at else None}
            for m in messages
        ],
        "metadata": session.metadata,
        "message_count": len(messages),
    }


@api_router.delete("/memory/sessions/{session_id}")
async def delete_session(session_id: str, http_request: Request):
    """Delete session"""
    if _execution_store:
        actor0 = _rbac_actor_from_http(http_request, None)
        tid = actor0.get("tenant_id")
        session = await _execution_store.get_memory_session(session_id=session_id)
        if not session or (tid and str(session.get("tenant_id") or "") != str(tid)):
            raise HTTPException(status_code=404, detail=f"Session {session_id} not found")
        success = await _execution_store.delete_memory_session(session_id=session_id)
    else:
        success = await _memory_manager.delete_session(session_id)
    if not success:
        raise HTTPException(status_code=404, detail=f"Session {session_id} not found")
    return {"status": "deleted", "session_id": session_id}


@api_router.get("/memory/sessions/{session_id}/context")
async def get_session_context(session_id: str, http_request: Request):
    """Get session context"""
    if _execution_store:
        actor0 = _rbac_actor_from_http(http_request, None)
        tid = actor0.get("tenant_id")
        session = await _execution_store.get_memory_session(session_id=session_id)
        if not session or (tid and str(session.get("tenant_id") or "") != str(tid)):
            raise HTTPException(status_code=404, detail=f"Session {session_id} not found")
        msgs = await _execution_store.list_memory_messages(session_id=session_id, tenant_id=str(tid) if tid else None, limit=200, offset=0)
        return {
            "session_id": session_id,
            "context": {"messages": msgs.get("items") or [], "message_count": int(msgs.get("total") or 0)},
        }

    context = await _memory_manager.get_context(session_id)
    if not context:
        raise HTTPException(status_code=404, detail=f"Session {session_id} not found")
    return {"session_id": session_id, "context": {"messages": context.get("messages", []), "message_count": len(context.get("messages", []))}}


@api_router.post("/memory/sessions/{session_id}/messages")
async def add_message(session_id: str, request: MessageCreateRequest, http_request: Request):
    """Add message to session"""
    if _execution_store:
        actor0 = _rbac_actor_from_http(http_request, None)
        tid = actor0.get("tenant_id")
        session = await _execution_store.get_memory_session(session_id=session_id)
        if not session or (tid and str(session.get("tenant_id") or "") != str(tid)):
            raise HTTPException(status_code=404, detail=f"Session {session_id} not found")
        msg = await _execution_store.add_memory_message(
            tenant_id=str(tid) if tid else None,
            session_id=session_id,
            user_id=str(actor0.get("actor_id") or session.get("user_id") or "system"),
            role=request.role,
            content=request.content,
            metadata=None,
        )
        return {"status": "added", "message": {"role": msg.get("role"), "content": msg.get("content"), "timestamp": msg.get("created_at")}}

    session = await _memory_manager.get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail=f"Session {session_id} not found")
    message = await _memory_manager.add_message(session_id=session_id, role=request.role, content=request.content, metadata=request.metadata)
    return {
        "status": "added",
        "message": {
            "role": message.role,
            "content": message.content,
            "timestamp": message.created_at.isoformat() if message.created_at else None,
        },
    }


@api_router.post("/memory/search")
async def search_memory(request: SearchRequest, http_request: Request):
    """Search memory"""
    if _execution_store:
        actor0 = _rbac_actor_from_http(http_request, None)
        tid = actor0.get("tenant_id")
        res = await _execution_store.search_memory_messages(
            query=request.query,
            user_id=None,
            tenant_id=str(tid) if tid else None,
            limit=int(request.limit or 10),
            offset=0,
        )
        return {"results": res.get("items") or [], "total": int(res.get("total") or 0)}

    results = await _memory_manager.search_memory(request.query, request.limit)
    return {"results": results, "total": len(results)}


@api_router.get("/memory/pins")
async def list_memory_pins(http_request: Request, session_id: Optional[str] = None, limit: int = 100, offset: int = 0):
    if not _execution_store:
        raise HTTPException(status_code=503, detail="ExecutionStore not initialized")
    tenant_id = None
    try:
        if http_request is not None:
            tenant_id = _rbac_actor_from_http(http_request, None).get("tenant_id")
    except Exception:
        tenant_id = None
    return await _execution_store.list_memory_pins(tenant_id=str(tenant_id) if tenant_id else None, session_id=session_id, limit=limit, offset=offset)


@api_router.post("/memory/pins")
async def pin_memory(request: dict, http_request: Request):
    if not _execution_store:
        raise HTTPException(status_code=503, detail="ExecutionStore not initialized")
    actor0 = _rbac_actor_from_http(http_request, request if isinstance(request, dict) else None)
    tenant_id = actor0.get("tenant_id")
    session_id = (request or {}).get("session_id")
    message_id = (request or {}).get("message_id")
    if not session_id or not message_id:
        raise HTTPException(status_code=400, detail="session_id and message_id are required")
    note = (request or {}).get("note")
    rec = await _execution_store.pin_memory_message(
        tenant_id=str(tenant_id) if tenant_id else None,
        session_id=str(session_id),
        message_id=str(message_id),
        created_by=str(actor0.get("actor_id") or "system"),
        note=str(note) if note else None,
    )
    return {"status": "pinned", "pin": rec}


@api_router.delete("/memory/pins/{message_id}")
async def unpin_memory(message_id: str, http_request: Request):
    if not _execution_store:
        raise HTTPException(status_code=503, detail="ExecutionStore not initialized")
    actor0 = _rbac_actor_from_http(http_request, None)
    tenant_id = actor0.get("tenant_id")
    ok = await _execution_store.unpin_memory_message(tenant_id=str(tenant_id) if tenant_id else None, message_id=str(message_id))
    if not ok:
        raise HTTPException(status_code=404, detail="pin_not_found")
    return {"status": "unpinned", "message_id": str(message_id)}


@api_router.get("/memory/stats")
async def get_memory_stats():
    """Get memory statistics"""
    stats = await _memory_manager.get_stats()
    counts = _memory_manager.get_session_count()
    return {
        "total_sessions": stats.total_sessions,
        "active_sessions": stats.active_sessions,
        "idle_sessions": stats.idle_sessions,
        "ended_sessions": stats.ended_sessions,
        "total_messages": stats.total_messages,
        "storage_size_mb": stats.storage_size_mb,
        "today_queries": stats.today_queries
    }


@api_router.post("/memory/cleanup")
async def cleanup_memory(request: dict):
    """Cleanup memory"""
    max_messages = request.get("max_messages", 100)
    cleaned = await _memory_manager.cleanup_memory(max_messages)
    return {"status": "cleaned", "sessions_cleaned": cleaned}


@api_router.get("/memory/export")
async def export_memory():
    """Export memory data"""
    counts = _memory_manager.get_session_count()
    stats = await _memory_manager.get_stats()
    return {
        "total_sessions": counts["total"],
        "stats": {
            "active": counts["active"],
            "idle": counts["idle"],
            "ended": counts["ended"],
            "total_messages": stats.total_messages
        }
    }


@api_router.post("/memory/import")
async def import_memory(request: dict):
    """Import memory data"""
    sessions = request.get("sessions", [])
    imported = 0
    for s in sessions:
        agent_type = s.get("agent_type", "default")
        user_id = s.get("user_id", "system")
        await _memory_manager.create_session(agent_type=agent_type, user_id=user_id, metadata=s.get("metadata"))
        imported += 1
    return {"status": "imported", "sessions_imported": imported}


# ==================== Knowledge Management ====================

@api_router.get("/knowledge/collections")
async def list_collections(limit: int = 100, offset: int = 0):
    """List knowledge collections"""
    collections = await _knowledge_manager.list_collections(limit=limit, offset=offset)
    counts = _knowledge_manager.get_collection_count()
    
    return {
        "collections": [
            {
                "collection_id": c.id,
                "name": c.name,
                "description": c.description,
                "status": c.status,
                "document_count": c.document_count,
                "created_at": c.created_at.isoformat() if c.created_at else None,
                "updated_at": c.updated_at.isoformat() if c.updated_at else None,
            }
            for c in collections
        ],
        "total": counts["total"]
    }


@api_router.post("/knowledge/collections")
async def create_collection(request: CollectionCreateRequest):
    """Create knowledge collection"""
    collection = await _knowledge_manager.create_collection(
        name=request.name,
        description=request.description,
        metadata=request.metadata
    )
    return {"collection_id": collection.id, "status": "created"}


@api_router.get("/knowledge/collections/{collection_id}")
async def get_collection(collection_id: str):
    """Get collection details"""
    collection = await _knowledge_manager.get_collection(collection_id)
    if not collection:
        raise HTTPException(status_code=404, detail=f"Collection {collection_id} not found")
    
    return {
        "collection_id": collection.id,
        "name": collection.name,
        "description": collection.description,
        "status": collection.status,
        "config": collection.config,
        "document_count": collection.document_count,
        "total_size_mb": collection.total_size_mb,
        "created_at": collection.created_at.isoformat() if collection.created_at else None,
        "updated_at": collection.updated_at.isoformat() if collection.updated_at else None,
        "metadata": collection.metadata
    }


@api_router.put("/knowledge/collections/{collection_id}")
async def update_collection(collection_id: str, request: dict):
    """Update collection"""
    collection = await _knowledge_manager.update_collection(
        collection_id,
        name=request.get("name"),
        description=request.get("description"),
        config=request.get("config")
    )
    if not collection:
        raise HTTPException(status_code=404, detail=f"Collection {collection_id} not found")
    return {"status": "updated", "collection_id": collection_id}


@api_router.delete("/knowledge/collections/{collection_id}")
async def delete_collection(collection_id: str):
    """Delete collection"""
    success = await _knowledge_manager.delete_collection(collection_id)
    if not success:
        raise HTTPException(status_code=404, detail=f"Collection {collection_id} not found")
    return {"status": "deleted", "collection_id": collection_id}


@api_router.post("/knowledge/collections/{collection_id}/reindex")
async def reindex_collection(collection_id: str):
    """Reindex collection"""
    success = await _knowledge_manager.reindex_collection(collection_id)
    if not success:
        raise HTTPException(status_code=404, detail=f"Collection {collection_id} not found")
    
    docs = await _knowledge_manager.list_documents(collection_id)
    return {"status": "reindexed", "documents_reindexed": len(docs)}


@api_router.post("/knowledge/documents")
async def create_document(request: DocumentCreateRequest):
    """Create document"""
    collection_id = request.metadata.get("collection_id") if request.metadata else None
    if collection_id:
        collection = await _knowledge_manager.get_collection(collection_id)
        if not collection:
            raise HTTPException(status_code=404, detail=f"Collection {collection_id} not found")
    
    doc = await _knowledge_manager.upload_document(
        collection_id=collection_id or "default",
        name=request.metadata.get("name", "untitled") if request.metadata else "untitled",
        doc_type=request.metadata.get("type", "txt") if request.metadata else "txt",
        content=b"",
        metadata=request.metadata
    )
    return {"document_id": doc.id, "status": "created"}


@api_router.get("/knowledge/documents/{document_id}")
async def get_document(document_id: str):
    """Get document"""
    doc = await _knowledge_manager.get_document(document_id)
    if not doc:
        raise HTTPException(status_code=404, detail=f"Document {document_id} not found")
    return {
        "document_id": doc.id,
        "collection_id": doc.collection_id,
        "name": doc.name,
        "type": doc.type,
        "size_mb": doc.size_mb,
        "status": doc.status,
        "chunks": doc.chunks,
        "created_at": doc.created_at.isoformat() if doc.created_at else None
    }


@api_router.get("/knowledge/collections/{collection_id}/documents")
async def list_documents(collection_id: str, limit: int = 100, offset: int = 0):
    """List documents"""
    collection = await _knowledge_manager.get_collection(collection_id)
    if not collection:
        raise HTTPException(status_code=404, detail=f"Collection {collection_id} not found")
    
    docs = await _knowledge_manager.list_documents(collection_id, limit=limit, offset=offset)
    return {
        "documents": [
            {
                "document_id": d.id,
                "name": d.name,
                "type": d.type,
                "status": d.status,
                "chunks": d.chunks
            }
            for d in docs
        ],
        "total": collection.document_count
    }


@api_router.delete("/knowledge/documents/{document_id}")
async def delete_document(document_id: str):
    """Delete document"""
    success = await _knowledge_manager.delete_document(document_id)
    if not success:
        raise HTTPException(status_code=404, detail=f"Document {document_id} not found")
    return {"status": "deleted", "document_id": document_id}


@api_router.post("/knowledge/search")
async def search_knowledge(request: SearchRequest):
    """Search knowledge"""
    results = await _knowledge_manager.search(
        collection_id=request.metadata.get("collection_id") if request.metadata else "",
        query=request.query,
        top_k=request.limit
    )
    return {
        "results": [
            {
                "content": r.content,
                "score": r.score,
                "metadata": r.metadata
            }
            for r in results
        ],
        "total": len(results)
    }


@api_router.get("/knowledge/collections/{collection_id}/search/logs")
async def get_search_logs(collection_id: str, limit: int = 100, offset: int = 0):
    """Get search logs"""
    return {"logs": [], "total": 0}


# ==================== Adapter Management ====================

@api_router.get("/adapters")
async def list_adapters(limit: int = 100, offset: int = 0):
    """List adapters"""
    adapters = await _adapter_manager.list_adapters(limit=limit, offset=offset)
    counts = _adapter_manager.get_adapter_count()
    
    return {
        "adapters": [
            {
                "adapter_id": a.id,
                "name": a.name,
                "provider": a.provider,
                "description": a.description,
                "status": a.status,
                "models": a.models
            }
            for a in adapters
        ],
        "total": counts["total"]
    }


@api_router.post("/adapters")
async def create_adapter(request: AdapterCreateRequest):
    """Create adapter"""
    adapter = await _adapter_manager.create_adapter(
        name=request.name,
        provider=request.provider,
        api_key=request.api_key,
        api_base_url=request.api_base_url,
        description=request.description
    )
    try:
        import hashlib

        api_key_hash = None
        if request.api_key:
            api_key_hash = hashlib.sha256(str(request.api_key).encode("utf-8")).hexdigest()
        await _record_changeset(
            name="adapter_create",
            target_type="adapter",
            target_id=str(adapter.id),
            args={"name": request.name, "provider": request.provider, "api_base_url": request.api_base_url},
            result={"adapter_id": str(adapter.id), "api_key_sha256": api_key_hash, "api_key_len": len(str(request.api_key or ""))},
        )
    except Exception:
        pass
    return {"adapter_id": adapter.id, "status": "created"}


@api_router.get("/adapters/{adapter_id}")
async def get_adapter(adapter_id: str):
    """Get adapter details"""
    adapter = await _adapter_manager.get_adapter(adapter_id)
    if not adapter:
        raise HTTPException(status_code=404, detail=f"Adapter {adapter_id} not found")
    
    return {
        "adapter_id": adapter.id,
        "name": adapter.name,
        "provider": adapter.provider,
        "description": adapter.description,
        "status": adapter.status,
        "api_base_url": adapter.api_base_url,
        "models": adapter.models,
        "rate_limit": adapter.rate_limit,
        "created_at": adapter.created_at.isoformat() if adapter.created_at else None
    }


@api_router.put("/adapters/{adapter_id}")
async def update_adapter(adapter_id: str, request: AdapterUpdateRequest):
    """Update adapter"""
    adapter = await _adapter_manager.update_adapter(
        adapter_id,
        name=request.name,
        description=request.description,
        api_key=request.api_key,
        api_base_url=request.api_base_url,
        rate_limit=request.rate_limit
    )
    if not adapter:
        raise HTTPException(status_code=404, detail=f"Adapter {adapter_id} not found")
    try:
        import hashlib

        api_key_hash = None
        if request.api_key:
            api_key_hash = hashlib.sha256(str(request.api_key).encode("utf-8")).hexdigest()
        await _record_changeset(
            name="adapter_update",
            target_type="adapter",
            target_id=str(adapter_id),
            args={"name": request.name, "api_base_url": request.api_base_url, "rate_limit": request.rate_limit},
            result={"api_key_sha256": api_key_hash, "api_key_len": len(str(request.api_key or "")) if request.api_key else 0},
        )
    except Exception:
        pass
    return {"status": "updated"}


@api_router.delete("/adapters/{adapter_id}")
async def delete_adapter(adapter_id: str):
    """Delete adapter"""
    success = await _adapter_manager.delete_adapter(adapter_id)
    if not success:
        raise HTTPException(status_code=404, detail=f"Adapter {adapter_id} not found")
    try:
        await _record_changeset(
            name="adapter_delete",
            target_type="adapter",
            target_id=str(adapter_id),
            args={},
            result={"status": "deleted"},
        )
    except Exception:
        pass
    return {"status": "deleted"}


@api_router.post("/adapters/{adapter_id}/test")
async def test_adapter(adapter_id: str, request: dict):
    """Test adapter"""
    result = await _adapter_manager.test_connection(adapter_id)
    return result


@api_router.post("/adapters/{adapter_id}/enable")
async def enable_adapter(adapter_id: str):
    """Enable adapter"""
    success = await _adapter_manager.enable_adapter(adapter_id)
    if not success:
        raise HTTPException(status_code=404, detail=f"Adapter {adapter_id} not found")
    try:
        await _record_changeset(
            name="adapter_enable",
            target_type="adapter",
            target_id=str(adapter_id),
            args={},
            result={"status": "enabled"},
        )
    except Exception:
        pass
    return {"status": "enabled"}


@api_router.post("/adapters/{adapter_id}/disable")
async def disable_adapter(adapter_id: str):
    """Disable adapter"""
    success = await _adapter_manager.disable_adapter(adapter_id)
    if not success:
        raise HTTPException(status_code=404, detail=f"Adapter {adapter_id} not found")
    try:
        await _record_changeset(
            name="adapter_disable",
            target_type="adapter",
            target_id=str(adapter_id),
            args={},
            result={"status": "disabled"},
        )
    except Exception:
        pass
    return {"status": "disabled"}


@api_router.get("/adapters/{adapter_id}/models")
async def list_adapter_models(adapter_id: str):
    """List adapter models"""
    adapter = await _adapter_manager.get_adapter(adapter_id)
    if not adapter:
        raise HTTPException(status_code=404, detail=f"Adapter {adapter_id} not found")
    return {"models": adapter.models}


@api_router.post("/adapters/{adapter_id}/models")
async def add_adapter_model(adapter_id: str, request: dict):
    """Add model to adapter"""
    success = await _adapter_manager.add_model(
        adapter_id,
        request.get("name", "default"),
        request.get("max_tokens", 4096),
        request.get("temperature", 0.7),
        request.get("enabled", True)
    )
    if not success:
        raise HTTPException(status_code=404, detail=f"Adapter {adapter_id} not found")
    try:
        await _record_changeset(
            name="adapter_model_add",
            target_type="adapter",
            target_id=str(adapter_id),
            args={
                "model": request.get("name", "default"),
                "max_tokens": request.get("max_tokens", 4096),
                "temperature": request.get("temperature", 0.7),
                "enabled": request.get("enabled", True),
            },
            result={"status": "added"},
        )
    except Exception:
        pass
    return {"status": "added"}


@api_router.put("/adapters/{adapter_id}/models/{model_name}")
async def update_adapter_model(adapter_id: str, model_name: str, request: ModelUpdateRequest):
    """Update adapter model"""
    return {"status": "updated"}


@api_router.delete("/adapters/{adapter_id}/models/{model_name}")
async def delete_adapter_model(adapter_id: str, model_name: str):
    """Delete adapter model"""
    success = await _adapter_manager.remove_model(adapter_id, model_name)
    if not success:
        raise HTTPException(status_code=404, detail=f"Adapter {adapter_id} not found")
    try:
        await _record_changeset(
            name="adapter_model_delete",
            target_type="adapter",
            target_id=str(adapter_id),
            args={"model": str(model_name)},
            result={"status": "deleted"},
        )
    except Exception:
        pass
    return {"status": "deleted"}


@api_router.get("/adapters/{adapter_id}/stats")
async def get_adapter_stats(adapter_id: str):
    """Get adapter stats"""
    stats = await _adapter_manager.get_call_stats(adapter_id)
    if not stats:
        raise HTTPException(status_code=404, detail=f"Adapter {adapter_id} not found")
    
    success_rate = stats.success_count / stats.total_calls if stats.total_calls > 0 else 0
    return {
        "total_calls": stats.total_calls,
        "success_count": stats.success_count,
        "failed_count": stats.failed_count,
        "success_rate": success_rate,
        "avg_duration_ms": stats.avg_duration_ms,
        "tokens_used": stats.tokens_used
    }


@api_router.get("/adapters/{adapter_id}/calls")
async def get_adapter_calls(adapter_id: str, limit: int = 100, offset: int = 0):
    """Get adapter calls"""
    calls = await _adapter_manager.get_call_history(adapter_id, limit=limit, offset=offset)
    return {
        "calls": [
            {
                "id": c.id,
                "model": c.model,
                "status": c.status,
                "duration_ms": c.duration_ms,
                "tokens": c.tokens,
                "timestamp": c.timestamp.isoformat() if c.timestamp else None
            }
            for c in calls
        ],
        "total": len(calls)
    }


@api_router.get("/adapters/{adapter_id}/model-distribution")
async def get_model_distribution(adapter_id: str):
    """Get model distribution"""
    distribution = await _adapter_manager.get_model_distribution(adapter_id)
    return {"distribution": distribution}


# ==================== Harness Management ====================

@api_router.get("/harness/status")
async def get_harness_status():
    """Get harness status"""
    status = await _harness_manager.get_status()
    return {
        "status": status.status,
        "components": status.components,
        "uptime_seconds": status.uptime_seconds
    }


@api_router.get("/harness/config")
async def get_harness_config():
    """Get harness config"""
    config = await _harness_manager.get_config()
    return {
        "max_iterations": config.max_iterations,
        "timeout_seconds": config.timeout_seconds,
        "retry_count": config.retry_count,
        "retry_interval_seconds": config.retry_interval_seconds
    }


@api_router.put("/harness/config")
async def update_harness_config(request: dict):
    """Update harness config"""
    config = await _harness_manager.update_config(
        max_iterations=request.get("max_iterations"),
        timeout_seconds=request.get("timeout_seconds"),
        retry_count=request.get("retry_count"),
        retry_interval_seconds=request.get("retry_interval_seconds")
    )
    return {"status": "updated", "config": config}


@api_router.get("/harness/metrics")
async def get_harness_metrics():
    """Get harness metrics"""
    metrics = await _harness_manager.get_metrics()
    return {"metrics": metrics}


@api_router.get("/harness/logs")
async def get_harness_logs(limit: int = 100):
    """Get harness logs"""
    logs = await _harness_manager.get_execution_logs(limit=limit)
    return {
        "logs": [
            {
                "id": l.id,
                "agent": l.agent,
                "status": l.status,
                "duration_ms": l.duration_ms,
                "start_time": l.start_time.isoformat() if l.start_time else None,
                "error": l.error
            }
            for l in logs
        ]
    }


@api_router.get("/harness/hooks")
async def list_hooks():
    """List hooks"""
    hooks = await _harness_manager.get_hooks()
    return {
        "hooks": [
            {
                "id": h.id,
                "name": h.name,
                "type": h.type,
                "priority": h.priority,
                "enabled": h.enabled
            }
            for h in hooks
        ]
    }


@api_router.post("/harness/hooks")
async def create_hook(request: HookCreateRequest):
    """Create hook"""
    hook = await _harness_manager.add_hook(
        name=request.name,
        hook_type=request.type,
        priority=request.priority,
        config=request.config
    )
    return {"hook_id": hook.id, "status": "created"}


@api_router.delete("/harness/hooks/{hook_id}")
async def delete_hook(hook_id: str):
    """Delete hook"""
    success = await _harness_manager.delete_hook(hook_id)
    if not success:
        raise HTTPException(status_code=404, detail=f"Hook {hook_id} not found")
    return {"status": "deleted"}


@api_router.put("/harness/hooks/{hook_id}")
async def update_hook(hook_id: str, request: HookUpdateRequest):
    """Update hook"""
    hook = await _harness_manager.update_hook(
        hook_id,
        name=request.name,
        priority=request.priority,
        enabled=request.enabled,
        config=request.config
    )
    if not hook:
        raise HTTPException(status_code=404, detail=f"Hook {hook_id} not found")
    return {"status": "updated"}


@api_router.get("/harness/executions/{execution_id}")
async def get_harness_execution(execution_id: str):
    """Get harness execution"""
    execution = await _harness_manager.get_execution(execution_id)
    if not execution:
        raise HTTPException(status_code=404, detail=f"Execution {execution_id} not found")
    return {
        "id": execution.id,
        "agent": execution.agent,
        "status": execution.status,
        "duration_ms": execution.duration_ms,
        "steps": execution.steps,
        "error": execution.error
    }


@api_router.get("/harness/coordinators")
async def list_coordinators():
    """List coordinators"""
    coordinators = await _harness_manager.list_coordinators()
    return {
        "coordinators": [
            {
                "id": c.id,
                "pattern": c.pattern,
                "agents": c.agents,
                "status": c.status,
                "created_at": c.created_at.isoformat() if c.created_at else None
            }
            for c in coordinators
        ]
    }


@api_router.post("/harness/coordinators")
async def create_coordinator(request: CoordinatorCreateRequest):
    """Create coordinator"""
    coordinator = await _harness_manager.create_coordinator(
        pattern=request.pattern,
        agents=request.agents,
        config=request.config
    )
    return {"coordinator_id": coordinator.id, "status": "created"}


@api_router.get("/harness/coordinators/{coordinator_id}")
async def get_coordinator(coordinator_id: str):
    """Get coordinator"""
    coordinator = await _harness_manager.get_coordinator(coordinator_id)
    if not coordinator:
        raise HTTPException(status_code=404, detail=f"Coordinator {coordinator_id} not found")
    return {
        "coordinator_id": coordinator.id,
        "pattern": coordinator.pattern,
        "agents": coordinator.agents,
        "status": coordinator.status,
        "config": coordinator.config
    }


@api_router.put("/harness/coordinators/{coordinator_id}")
async def update_coordinator(coordinator_id: str, request: dict):
    """Update coordinator"""
    return {"status": "updated"}


@api_router.delete("/harness/coordinators/{coordinator_id}")
async def delete_coordinator(coordinator_id: str):
    """Delete coordinator"""
    success = await _harness_manager.delete_coordinator(coordinator_id)
    if not success:
        raise HTTPException(status_code=404, detail=f"Coordinator {coordinator_id} not found")
    return {"status": "deleted"}


@api_router.get("/harness/feedback/config")
async def get_feedback_config():
    """Get feedback config"""
    config = await _harness_manager.get_feedback_config()
    return {
        "config": {
            "local": config.local,
            "push": config.push,
            "prod": config.prod
        }
    }


@api_router.put("/harness/feedback/config")
async def update_feedback_config(request: FeedbackConfigUpdateRequest):
    """Update feedback config"""
    config = await _harness_manager.update_feedback_config(
        local=request.local,
        push=request.push,
        prod=request.prod
    )
    return {"status": "updated"}


@api_router.get("/tools")
async def list_tools(limit: int = 100, offset: int = 0, available_only: bool = False):
    """List all tools"""
    registry = get_tool_registry()
    tools = registry.list_tools()
    result = []
    for t in tools[offset:offset+limit]:
        tool = registry.get(t)
        info: Dict[str, Any] = {"name": t}
        if tool:
            avail = registry.get_availability(t) if hasattr(registry, "get_availability") else {"available": True, "reason": None}
            info["available"] = bool(avail.get("available"))
            info["unavailable_reason"] = avail.get("reason")
            if available_only and not info["available"]:
                continue
            info["description"] = tool.get_description()
            info["category"] = getattr(tool._config, 'category', 'general') if hasattr(tool, '_config') else 'general'
            # Tools are code-defined engine capabilities; do not edit via UI/API.
            info["protected"] = True
            info["scope"] = "engine"
            stats = tool.get_stats() if hasattr(tool, 'get_stats') else None
            if stats:
                info["stats"] = stats
            info["config"] = {}
            if hasattr(tool, '_config'):
                cfg = tool._config
                info["config"] = {
                    "name": cfg.name if hasattr(cfg, 'name') else t,
                    "description": cfg.description if hasattr(cfg, 'description') else '',
                    "timeout_seconds": cfg.timeout_seconds if hasattr(cfg, 'timeout_seconds') else None,
                    "max_concurrent": cfg.max_concurrent if hasattr(cfg, 'max_concurrent') else None,
                }
            info["parameters"] = tool._config.parameters if hasattr(tool, '_config') and hasattr(tool._config, 'parameters') else {}
            info["status"] = "enabled" if info.get("available", True) else "unavailable"
            info["enabled"] = True
        result.append(info)
    return {"tools": result, "total": len(tools)}


@api_router.get("/tools/{tool_name}")
async def get_tool(tool_name: str):
    """Get tool details"""
    registry = get_tool_registry()
    tool = registry.get(tool_name)
    if not tool:
        raise HTTPException(status_code=404, detail=f"Tool {tool_name} not found")
    
    info: Dict[str, Any] = {"name": tool_name}
    info["description"] = tool.get_description()
    if hasattr(registry, "get_availability"):
        avail = registry.get_availability(tool_name)
        info["available"] = bool(avail.get("available"))
        info["unavailable_reason"] = avail.get("reason")
    info["category"] = getattr(tool._config, 'category', 'general') if hasattr(tool, '_config') else 'general'
    info["protected"] = True
    info["scope"] = "engine"
    
    stats = tool.get_stats() if hasattr(tool, 'get_stats') else None
    if stats:
        info["stats"] = stats
    
    if hasattr(tool, '_config'):
        cfg = tool._config
        info["config"] = {
            "name": cfg.name if hasattr(cfg, 'name') else tool_name,
            "description": cfg.description if hasattr(cfg, 'description') else '',
            "timeout_seconds": cfg.timeout_seconds if hasattr(cfg, 'timeout_seconds') else None,
            "max_concurrent": cfg.max_concurrent if hasattr(cfg, 'max_concurrent') else None,
        }
    
    info["parameters"] = tool._config.parameters if hasattr(tool, '_config') and hasattr(tool._config, 'parameters') else {}
    info["status"] = "enabled"
    info["enabled"] = True
    
    return info


@api_router.put("/tools/{tool_name}")
async def update_tool_config(tool_name: str, request: dict):
    """Update tool configuration"""
    raise HTTPException(status_code=403, detail="Tools are engine-defined and cannot be edited via API. Use configuration files/feature flags instead.")


@api_router.post("/tools/{tool_name}/execute")
async def execute_tool(tool_name: str, request: dict, http_request: Request):
    """Execute a tool with given parameters"""
    harness = get_harness()
    payload = _inject_http_request_context(dict(request or {}), http_request, entrypoint="api")
    deny = await _rbac_guard(http_request=http_request, payload=payload, action="execute", resource_type="tool", resource_id=str(tool_name))
    if deny:
        return deny
    ctx0 = payload.get("context") if isinstance(payload.get("context"), dict) else {}
    user_id = payload.get("user_id") or (ctx0.get("actor_id") if isinstance(ctx0, dict) else None) or "system"
    session_id = payload.get("session_id") or (ctx0.get("session_id") if isinstance(ctx0, dict) else None) or "default"
    exec_req = ExecutionRequest(
        kind="tool",
        target_id=tool_name,
        payload=payload,
        user_id=str(user_id),
        session_id=str(session_id),
    )
    result = await harness.execute(exec_req)
    resp = _wrap_execution_result_as_run_summary(result)
    # Keep legacy behavior: tool execute returns 200 even when failed, but carries {ok:false,error:{...}}.
    try:
        await _audit_execute(http_request=http_request, payload=payload, resource_type="tool", resource_id=str(tool_name), resp=resp)
    except Exception:
        pass
    return JSONResponse(status_code=200, content=resp)


# ==================== Gateway / Channels (Roadmap-3) ====================


@api_router.post("/gateway/execute")
async def gateway_execute(request: GatewayExecuteRequest, http_request: Request):
    """
    Unified external entry for multi-channel integrations.

    This endpoint is intentionally thin: it reuses HarnessIntegration.execute()
    so that toolset / approvals / tracing policies apply consistently.
    """
    harness = get_harness()
    payload = dict(request.payload or {})
    if request.options is not None:
        try:
            payload.setdefault("options", request.options)
        except Exception:
            pass
    # Inject channel context for observability.
    try:
        ctx = payload.get("context") if isinstance(payload.get("context"), dict) else {}
        ctx = dict(ctx) if isinstance(ctx, dict) else {}
        ctx.setdefault("source", "gateway")
        ctx.setdefault("entrypoint", "gateway")
        ctx.setdefault("channel", request.channel)
        if request.tenant_id:
            ctx.setdefault("tenant_id", str(request.tenant_id))
        else:
            # Allow tenant_id to come from header when client doesn't send it in body.
            h_tenant = http_request.headers.get("X-AIPLAT-TENANT-ID") or http_request.headers.get("x-aiplat-tenant-id")
            if h_tenant:
                ctx.setdefault("tenant_id", str(h_tenant))
        # platform identity passthrough (optional)
        try:
            actor_id = http_request.headers.get("X-AIPLAT-ACTOR-ID") or http_request.headers.get("x-aiplat-actor-id")
            actor_role = http_request.headers.get("X-AIPLAT-ACTOR-ROLE") or http_request.headers.get("x-aiplat-actor-role")
            if actor_id:
                ctx.setdefault("actor_id", str(actor_id))
            if actor_role:
                ctx.setdefault("actor_role", str(actor_role))
        except Exception:
            pass
        # preserve external identity if present
        if request.channel_user_id:
            ctx.setdefault("channel_user_id", request.channel_user_id)
        payload["context"] = ctx
    except Exception:
        pass

    deny = await _rbac_guard(http_request=http_request, payload=payload, action="execute", resource_type="gateway", resource_id=str(request.target_id))
    if deny:
        return deny

    # Optional auth (Roadmap-3): require token when configured.
    # - Env AIPLAT_GATEWAY_REQUIRE_AUTH=true to enable.
    # - Accept X-AiPlat-Gateway-Token header and validate against ExecutionStore gateway_tokens
    #   or env AIPLAT_GATEWAY_TOKEN.
    if os.getenv("AIPLAT_GATEWAY_REQUIRE_AUTH", "false").lower() in ("1", "true", "yes", "y"):
        token = http_request.headers.get("x-aiplat-gateway-token") or http_request.headers.get("X-AiPlat-Gateway-Token")
        if not token:
            raise HTTPException(status_code=401, detail="missing gateway token")
        ok = False
        if os.getenv("AIPLAT_GATEWAY_TOKEN") and token == os.getenv("AIPLAT_GATEWAY_TOKEN"):
            ok = True
        elif _execution_store:
            try:
                ok = (await _execution_store.validate_gateway_token(token=token)) is not None
            except Exception:
                ok = False
        if not ok:
            raise HTTPException(status_code=403, detail="invalid gateway token")

    # Pairing resolution: if user_id/session_id not provided, resolve using (channel, channel_user_id).
    resolved_user = request.user_id
    resolved_session = request.session_id
    resolved_tenant = request.tenant_id
    channel_user_id = (
        request.channel_user_id
        or (payload.get("channel_user_id") if isinstance(payload, dict) else None)
        or (payload.get("sender_id") if isinstance(payload, dict) else None)
        or ((payload.get("context") or {}).get("channel_user_id") if isinstance(payload.get("context"), dict) else None)
    )
    if _execution_store and (not resolved_user or not resolved_session) and channel_user_id:
        try:
            pairing = await _execution_store.resolve_gateway_pairing(channel=request.channel, channel_user_id=str(channel_user_id))
        except Exception:
            pairing = None
        if pairing:
            resolved_user = resolved_user or pairing.get("user_id")
            resolved_session = resolved_session or pairing.get("session_id")
            resolved_tenant = resolved_tenant or pairing.get("tenant_id")
            # enrich context for observability
            try:
                ctx = payload.get("context") if isinstance(payload.get("context"), dict) else {}
                ctx = dict(ctx) if isinstance(ctx, dict) else {}
                ctx.setdefault("pairing_id", pairing.get("id"))
                if pairing.get("tenant_id"):
                    ctx.setdefault("tenant_id", pairing.get("tenant_id"))
                payload["context"] = ctx
            except Exception:
                pass

    # Platform contract: idempotency key from platform (recommended).
    # - If present and already mapped, return the existing run summary.
    # - If present and new, reserve a run_id and persist mapping BEFORE execution.
    request_id = (
        http_request.headers.get("x-aiplat-request-id")
        or http_request.headers.get("X-AiPlat-Request-Id")
        or http_request.headers.get("X-AIPLAT-REQUEST-ID")
    )
    request_id = str(request_id).strip() if isinstance(request_id, str) else None
    if not request_id:
        request_id = new_prefixed_id("req")
    # surface request_id into payload.context for downstream syscalls/audit
    try:
        if isinstance(payload, dict):
            ctx = payload.get("context") if isinstance(payload.get("context"), dict) else {}
            ctx = dict(ctx) if isinstance(ctx, dict) else {}
            ctx.setdefault("request_id", str(request_id))
            payload["context"] = ctx
    except Exception:
        pass

    reserved_run_id = None
    if _execution_store and request_id:
        try:
            existing_run_id = await _execution_store.get_run_id_for_request(
                request_id=request_id, tenant_id=str(resolved_tenant) if resolved_tenant else None
            )
        except Exception:
            existing_run_id = None
        if existing_run_id:
            run = await _execution_store.get_run_summary(run_id=str(existing_run_id))
            try:
                await _execution_store.add_audit_log(
                    action="gateway_execute_dedup",
                    status="ok",
                    tenant_id=str(resolved_tenant) if resolved_tenant else None,
                    actor_id=str(resolved_user) if resolved_user else None,
                    resource_type="run",
                    resource_id=str(existing_run_id),
                    request_id=request_id,
                    run_id=str(existing_run_id),
                    trace_id=(run or {}).get("trace_id"),
                    detail={"channel": request.channel, "kind": request.kind, "target_id": request.target_id},
                )
            except Exception:
                pass
            return {
                "ok": True,
                "status": RunStatus.completed.value,
                "legacy_status": "deduped",
                "request_id": request_id,
                "run_id": str(existing_run_id),
                "trace_id": (run or {}).get("trace_id"),
                "run": run,
            }
        # Reserve a run_id so upstream retries can dedupe immediately.
        reserved_run_id = new_prefixed_id("run")
        try:
            await _execution_store.remember_request_run_id(
                request_id=request_id,
                run_id=reserved_run_id,
                tenant_id=str(resolved_tenant) if resolved_tenant else None,
            )
        except Exception:
            pass

    exec_req = ExecutionRequest(
        kind=str(request.kind) if request.kind else "agent",  # type: ignore[arg-type]
        target_id=str(request.target_id),
        payload=payload,
        user_id=str(resolved_user or "system"),
        session_id=str(resolved_session or "default"),
        request_id=request_id,
        run_id=reserved_run_id,
    )
    result = await harness.execute(exec_req)
    # Best-effort ensure request_id mapping exists even if reservation was skipped.
    if _execution_store and request_id and result.run_id:
        try:
            await _execution_store.remember_request_run_id(
                request_id=request_id,
                run_id=str(result.run_id),
                tenant_id=str(resolved_tenant) if resolved_tenant else None,
            )
        except Exception:
            pass

    # Audit (best-effort)
    try:
        # prefer actor identity from headers when present
        actor0 = _rbac_actor_from_http(http_request, payload)
        if _execution_store:
            await _execution_store.add_audit_log(
                action="gateway_execute",
                status="ok" if result.ok else "failed",
                tenant_id=str(resolved_tenant) if resolved_tenant else (str(actor0.get("tenant_id") or "") or None),
                actor_id=str(resolved_user) if resolved_user else (str(actor0.get("actor_id") or "") or None),
                actor_role=str(actor0.get("actor_role") or "") or None,
                resource_type=str(request.kind or "agent"),
                resource_id=str(request.target_id),
                request_id=request_id,
                run_id=str(result.run_id) if result.run_id else reserved_run_id,
                trace_id=str(result.trace_id) if result.trace_id else None,
                detail={"channel": request.channel, "channel_user_id": request.channel_user_id},
            )
    except Exception:
        pass
    # Normalize: always include trace_id/run_id.
    resp = dict(result.payload or {})
    # Prefer payload status for ok semantics (agent/skill often return ok=True but status=failed).
    status = resp.get("status")
    if isinstance(status, str) and status.lower() == "failed":
        resp.setdefault("ok", False)
    else:
        resp.setdefault("ok", bool(result.ok))

    # Normalize error contract:
    # - `error` is structured {code,message}
    # - `error_message` is legacy string
    # - keep `error_detail` as backward compatible alias
    if resp.get("ok") is False:
        resp.setdefault("status", "failed")
        # bring forward error_detail if present
        if "error_detail" not in resp:
            resp["error_detail"] = getattr(result, "error_detail", None)
        # If payload still used legacy string error, move it to error_message.
        if isinstance(resp.get("error"), str):
            resp.setdefault("error_message", resp.get("error"))
            resp["error"] = resp.get("error_detail") or {"code": "EXECUTION_FAILED", "message": str(resp.get("error_message") or "Execution failed")}
        else:
            # If error already structured, still populate error_message for convenience.
            if "error_message" not in resp:
                try:
                    resp["error_message"] = str((resp.get("error") or {}).get("message") or result.error or "")
                except Exception:
                    resp["error_message"] = result.error or ""
        # If error is still missing (e.g., payload had no error field), fill it.
        if not isinstance(resp.get("error"), dict):
            resp["error"] = resp.get("error_detail") or {
                "code": "EXECUTION_FAILED",
                "message": str(resp.get("error_message") or result.error or "Execution failed"),
            }
        # Ensure alias
        resp.setdefault("error_detail", resp.get("error"))
    resp.setdefault("trace_id", result.trace_id)
    resp.setdefault("run_id", result.run_id)
    resp.setdefault("request_id", request_id)
    # PR-02: normalize run status machine while preserving legacy status string.
    try:
        legacy_status = resp.get("status")
        err_code = None
        if isinstance(resp.get("error"), dict):
            err_code = (resp.get("error") or {}).get("code")
        err_code = err_code or resp.get("error_code")
        resp["legacy_status"] = legacy_status
        resp["status"] = _normalize_run_status_v2(ok=bool(resp.get("ok")), legacy_status=legacy_status, error_code=err_code)
        resp.setdefault("output", resp.get("output"))
    except Exception:
        pass
    return resp


@api_router.post("/gateway/webhook/message")
async def gateway_webhook_message(http_request: Request, body: Dict[str, Any]):
    """
    Minimal webhook adapter (Roadmap-3):
    - Accept a generic incoming message event
    - Convert to GatewayExecuteRequest
    - Reuse /gateway/execute so pairing/auth/toolset/tracing stay consistent

    Request body (minimal):
    {
      "channel": "slack|webchat|api|...",
      "channel_user_id": "U123",
      "text": "hello",
      "kind": "agent|skill|tool",
      "target_id": "...",
      "user_id": "...",        # optional (otherwise pairing)
      "session_id": "...",     # optional (otherwise pairing/default)
      "payload": {...},        # optional (if absent, derived from text)
      "options": {...},        # optional
      "context": {...}         # optional extra context
    }
    """
    payload = body.get("payload") if isinstance(body.get("payload"), dict) else None
    if payload is None:
        payload = {"input": {"message": body.get("text") or "", "text": body.get("text") or ""}}
    # merge additional context
    try:
        ctx = payload.get("context") if isinstance(payload.get("context"), dict) else {}
        ctx = dict(ctx) if isinstance(ctx, dict) else {}
        extra_ctx = body.get("context") if isinstance(body.get("context"), dict) else {}
        ctx.update(extra_ctx or {})
        if body.get("channel_user_id"):
            ctx.setdefault("channel_user_id", body.get("channel_user_id"))
        payload["context"] = ctx
    except Exception:
        pass

    req = GatewayExecuteRequest(
        channel=str(body.get("channel") or "webhook"),
        kind=str(body.get("kind") or "agent"),
        target_id=str(body.get("target_id") or ""),
        user_id=str(body.get("user_id")) if body.get("user_id") else None,
        session_id=str(body.get("session_id")) if body.get("session_id") else None,
        channel_user_id=str(body.get("channel_user_id")) if body.get("channel_user_id") else None,
        tenant_id=str(body.get("tenant_id")) if body.get("tenant_id") else None,
        payload=payload,
        options=body.get("options") if isinstance(body.get("options"), dict) else None,
    )
    if not req.target_id:
        raise HTTPException(status_code=400, detail="target_id is required")
    return await gateway_execute(req, http_request)


def _verify_slack_signature(http_request: Request, raw_body: bytes) -> None:
    """
    Optional Slack request verification.
    Enable by setting env AIPLAT_SLACK_SIGNING_SECRET.
    """
    secret = os.getenv("AIPLAT_SLACK_SIGNING_SECRET")
    if not secret:
        return
    import hmac
    import hashlib
    import time as _time

    ts = http_request.headers.get("x-slack-request-timestamp") or http_request.headers.get("X-Slack-Request-Timestamp")
    sig = http_request.headers.get("x-slack-signature") or http_request.headers.get("X-Slack-Signature")
    if not ts or not sig:
        raise HTTPException(status_code=401, detail="missing slack signature headers")
    try:
        ts_i = int(ts)
    except Exception:
        raise HTTPException(status_code=401, detail="invalid slack timestamp")
    # prevent replay
    if abs(int(_time.time()) - ts_i) > 60 * 5:
        raise HTTPException(status_code=401, detail="stale slack request")
    base = f"v0:{ts}:{raw_body.decode('utf-8')}".encode("utf-8")
    expected = "v0=" + hmac.new(secret.encode("utf-8"), base, hashlib.sha256).hexdigest()
    if not hmac.compare_digest(expected, sig):
        raise HTTPException(status_code=403, detail="invalid slack signature")


async def _post_slack_response(response_url: str, text: str) -> None:
    import aiohttp

    async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=8)) as sess:
        async with sess.post(response_url, json={"text": text}) as resp:
            await resp.text()


@api_router.post("/gateway/slack/command")
async def gateway_slack_command(http_request: Request):
    """
    Slack slash command adapter (minimal).
    - Accept x-www-form-urlencoded payload
    - (optional) verify signature
    - Execute via gateway_execute (pairing/auth/toolset enforced)
    - (optional) post final response to response_url
    """
    import urllib.parse

    raw = await http_request.body()
    _verify_slack_signature(http_request, raw)
    form = urllib.parse.parse_qs(raw.decode("utf-8"), keep_blank_values=True)

    def _one(k: str) -> Optional[str]:
        v = form.get(k)
        if not v:
            return None
        return str(v[0])

    user_id = _one("user_id")
    text = _one("text") or ""
    response_url = _one("response_url")
    team_id = _one("team_id")
    channel_id = _one("channel_id")

    target_id = os.getenv("AIPLAT_SLACK_DEFAULT_TARGET_ID", "agent_1")
    kind = os.getenv("AIPLAT_SLACK_DEFAULT_KIND", "agent")

    req = GatewayExecuteRequest(
        channel="slack",
        kind=kind,
        target_id=target_id,
        channel_user_id=user_id,
        payload={
            "input": {"message": text, "text": text},
            "context": {"source": "slack_command", "slack": {"team_id": team_id, "channel_id": channel_id}},
        },
    )
    resp = await gateway_execute(req, http_request)

    # If slack provides response_url, send the final answer there (best-effort)
    if response_url:
        try:
            out = resp.get("output")
            if resp.get("ok") is False:
                err = resp.get("error") if isinstance(resp.get("error"), dict) else None
                err_msg = resp.get("error_message") or (err.get("message") if err else None) or "执行失败"
                err_code = (err.get("code") if err else None) or (resp.get("error_detail") or {}).get("code")
                text_out = f"{f'[{err_code}] ' if err_code else ''}{err_msg}"
            else:
                if isinstance(out, str):
                    text_out = out
                else:
                    import json as _json

                    text_out = _json.dumps(out, ensure_ascii=False) if out is not None else "ok"
            await _post_slack_response(response_url, text_out[:3500])
        except Exception:
            pass

    # Respond quickly to Slack (ack)
    return {"ok": True, "trace_id": resp.get("trace_id"), "run_id": resp.get("run_id")}


@api_router.post("/gateway/slack/events")
async def gateway_slack_events(http_request: Request, body: Dict[str, Any]):
    """
    Slack Events API adapter (minimal):
    - url_verification -> return challenge
    - event_callback(message/app_mention) -> fire-and-forget execute via gateway_execute (no reply)
    """
    raw = await http_request.body()
    _verify_slack_signature(http_request, raw)

    if body.get("type") == "url_verification":
        return {"challenge": body.get("challenge")}

    if body.get("type") == "event_callback":
        event = body.get("event") if isinstance(body.get("event"), dict) else {}
        # ignore bot messages
        if event.get("bot_id"):
            return {"ok": True}
        user_id = event.get("user")
        text = event.get("text") or ""
        team_id = body.get("team_id")
        channel_id = event.get("channel")

        target_id = os.getenv("AIPLAT_SLACK_DEFAULT_TARGET_ID", "agent_1")
        kind = os.getenv("AIPLAT_SLACK_DEFAULT_KIND", "agent")
        req = GatewayExecuteRequest(
            channel="slack",
            kind=kind,
            target_id=target_id,
            channel_user_id=str(user_id) if user_id else None,
            payload={
                "input": {"message": text, "text": text},
                "context": {"source": "slack_event", "slack": {"team_id": team_id, "channel_id": channel_id, "event": event}},
            },
        )
        # best-effort (no external reply in minimal version)
        try:
            await gateway_execute(req, http_request)
        except Exception:
            pass
        return {"ok": True}

    return {"ok": True}


def _require_gateway_admin(http_request: Request) -> None:
    """
    Optional admin guard for gateway management endpoints.
    If AIPLAT_GATEWAY_ADMIN_TOKEN is set, callers must provide X-AiPlat-Admin-Token.
    """
    admin = os.environ.get("AIPLAT_GATEWAY_ADMIN_TOKEN")
    if not admin:
        return
    got = http_request.headers.get("x-aiplat-admin-token") or http_request.headers.get("X-AiPlat-Admin-Token")
    if not got or got != admin:
        raise HTTPException(status_code=403, detail="admin token required")


@api_router.get("/gateway/pairings")
async def list_gateway_pairings(http_request: Request, channel: Optional[str] = None, user_id: Optional[str] = None, limit: int = 100, offset: int = 0):
    if not _execution_store:
        raise HTTPException(status_code=503, detail="ExecutionStore not initialized")
    _require_gateway_admin(http_request)
    return await _execution_store.list_gateway_pairings(channel=channel, user_id=user_id, limit=limit, offset=offset)


@api_router.post("/gateway/pairings")
async def upsert_gateway_pairing(http_request: Request, body: Dict[str, Any]):
    if not _execution_store:
        raise HTTPException(status_code=503, detail="ExecutionStore not initialized")
    _require_gateway_admin(http_request)
    channel = str(body.get("channel") or "default")
    channel_user_id = str(body.get("channel_user_id") or "").strip()
    user_id = str(body.get("user_id") or "").strip()
    if not channel_user_id or not user_id:
        raise HTTPException(status_code=400, detail="channel_user_id and user_id are required")
    return await _execution_store.upsert_gateway_pairing(
        channel=channel,
        channel_user_id=channel_user_id,
        user_id=user_id,
        session_id=body.get("session_id"),
        tenant_id=body.get("tenant_id"),
        metadata=body.get("metadata") if isinstance(body.get("metadata"), dict) else {},
    )


@api_router.delete("/gateway/pairings")
async def delete_gateway_pairing(http_request: Request, channel: str, channel_user_id: str):
    if not _execution_store:
        raise HTTPException(status_code=503, detail="ExecutionStore not initialized")
    _require_gateway_admin(http_request)
    ok = await _execution_store.delete_gateway_pairing(channel=channel, channel_user_id=channel_user_id)
    if not ok:
        raise HTTPException(status_code=404, detail="pairing not found")
    return {"status": "deleted", "channel": channel, "channel_user_id": channel_user_id}


@api_router.get("/gateway/tokens")
async def list_gateway_tokens(http_request: Request, enabled: Optional[bool] = None, limit: int = 100, offset: int = 0):
    if not _execution_store:
        raise HTTPException(status_code=503, detail="ExecutionStore not initialized")
    _require_gateway_admin(http_request)
    return await _execution_store.list_gateway_tokens(limit=limit, offset=offset, enabled=enabled)


@api_router.post("/gateway/tokens")
async def create_gateway_token(http_request: Request, body: Dict[str, Any]):
    if not _execution_store:
        raise HTTPException(status_code=503, detail="ExecutionStore not initialized")
    _require_gateway_admin(http_request)
    name = str(body.get("name") or "token")
    token = str(body.get("token") or "")
    if not token:
        raise HTTPException(status_code=400, detail="token is required")
    rec = await _execution_store.create_gateway_token(
        name=name,
        token=token,
        tenant_id=body.get("tenant_id"),
        enabled=bool(body.get("enabled", True)),
        metadata=body.get("metadata") if isinstance(body.get("metadata"), dict) else {},
    )
    # do not return raw token or sha
    rec.pop("token_sha256", None)
    return rec


@api_router.delete("/gateway/tokens/{token_id}")
async def delete_gateway_token(http_request: Request, token_id: str):
    if not _execution_store:
        raise HTTPException(status_code=503, detail="ExecutionStore not initialized")
    _require_gateway_admin(http_request)
    ok = await _execution_store.delete_gateway_token(token_id=token_id)
    if not ok:
        raise HTTPException(status_code=404, detail="token not found")
    return {"status": "deleted", "token_id": token_id}


# ==================== Skill Packs + Long-term Memory (Roadmap-4 minimal) ====================

def _normalize_skill_pack_manifest(manifest: Any) -> Dict[str, Any]:
    """
    Validate + normalize Skill Pack manifest (minimal contract).

    Supported manifest.skills forms:
    - ["skill_id", ...]
    - [{"id": "...", "display_name": "...", "category": "...", "description": "...", "version": "...", "sop_markdown": "..."}, ...]
    """
    if manifest is None:
        return {}
    if not isinstance(manifest, dict):
        raise HTTPException(status_code=400, detail="manifest must be an object")

    out = dict(manifest)
    skills = out.get("skills")
    if skills is None:
        return out
    if not isinstance(skills, list):
        raise HTTPException(status_code=400, detail="manifest.skills must be an array")

    norm_skills: List[Dict[str, Any]] = []
    for it in skills:
        if isinstance(it, str):
            sid = it.strip()
            if not sid:
                raise HTTPException(status_code=400, detail="manifest.skills contains empty string id")
            if " " in sid:
                raise HTTPException(status_code=400, detail=f"invalid skill id (contains spaces): {sid}")
            norm_skills.append({"id": sid})
            continue
        if isinstance(it, dict):
            sid = str(it.get("id") or it.get("skill_id") or "").strip()
            if not sid:
                raise HTTPException(status_code=400, detail="manifest.skills contains an item without id")
            if " " in sid:
                raise HTTPException(status_code=400, detail=f"invalid skill id (contains spaces): {sid}")
            spec = dict(it)
            spec["id"] = sid
            norm_skills.append(spec)
            continue
        raise HTTPException(status_code=400, detail="manifest.skills items must be string or object")

    out["skills"] = norm_skills
    return out


@api_router.get("/skill-packs")
async def list_skill_packs(limit: int = 100, offset: int = 0):
    if not _execution_store:
        raise HTTPException(status_code=503, detail="ExecutionStore not initialized")
    return await _execution_store.list_skill_packs(limit=limit, offset=offset)


@api_router.post("/skill-packs")
async def create_skill_pack(request: SkillPackCreateRequest):
    if not _execution_store:
        raise HTTPException(status_code=503, detail="ExecutionStore not initialized")
    manifest = _normalize_skill_pack_manifest(request.manifest)
    return await _execution_store.create_skill_pack(
        {"name": request.name, "description": request.description, "manifest": manifest}
    )


@api_router.get("/skill-packs/{pack_id}")
async def get_skill_pack(pack_id: str):
    if not _execution_store:
        raise HTTPException(status_code=503, detail="ExecutionStore not initialized")
    pack = await _execution_store.get_skill_pack(pack_id)
    if not pack:
        raise HTTPException(status_code=404, detail="Skill pack not found")
    return pack


@api_router.put("/skill-packs/{pack_id}")
async def update_skill_pack(pack_id: str, request: SkillPackUpdateRequest):
    if not _execution_store:
        raise HTTPException(status_code=503, detail="ExecutionStore not initialized")
    patch = request.model_dump(exclude_unset=True)
    if "manifest" in patch:
        patch["manifest"] = _normalize_skill_pack_manifest(patch.get("manifest"))
    updated = await _execution_store.update_skill_pack(pack_id, patch)
    if not updated:
        raise HTTPException(status_code=404, detail="Skill pack not found")
    return updated


@api_router.delete("/skill-packs/{pack_id}")
async def delete_skill_pack(pack_id: str):
    if not _execution_store:
        raise HTTPException(status_code=503, detail="ExecutionStore not initialized")
    ok = await _execution_store.delete_skill_pack(pack_id)
    if not ok:
        raise HTTPException(status_code=404, detail="Skill pack not found")
    return {"status": "deleted", "id": pack_id}


@api_router.post("/skill-packs/{pack_id}/publish")
async def publish_skill_pack(pack_id: str, request: SkillPackPublishRequest):
    if not _execution_store:
        raise HTTPException(status_code=503, detail="ExecutionStore not initialized")
    try:
        # Validate manifest before publishing a version snapshot.
        pack = await _execution_store.get_skill_pack(pack_id)
        if not pack:
            raise ValueError("Skill pack not found")
        _normalize_skill_pack_manifest(pack.get("manifest"))
        # Gate: referenced skills should be verified (workspace skills) when enforcement enabled.
        try:
            manifest = pack.get("manifest") if isinstance(pack, dict) else None
            manifest = _normalize_skill_pack_manifest(manifest if isinstance(manifest, dict) else {})
            skills = manifest.get("skills") if isinstance(manifest, dict) else []
            targets: list[tuple[str, str]] = []
            if isinstance(skills, list):
                for it in skills:
                    if not isinstance(it, dict):
                        continue
                    sid = str(it.get("id") or "").strip()
                    if sid:
                        targets.append(("skill", sid))
            await _require_targets_verified(list({(t[0], t[1]) for t in targets}))
        except HTTPException:
            raise
        except Exception:
            pass
        return await _execution_store.publish_skill_pack_version(pack_id=pack_id, version=request.version)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        # likely UNIQUE(pack_id, version)
        raise HTTPException(status_code=409, detail=str(e))


@api_router.get("/skill-packs/{pack_id}/versions")
async def list_skill_pack_versions(pack_id: str, limit: int = 100, offset: int = 0):
    if not _execution_store:
        raise HTTPException(status_code=503, detail="ExecutionStore not initialized")
    return await _execution_store.list_skill_pack_versions(pack_id=pack_id, limit=limit, offset=offset)


@api_router.post("/skill-packs/{pack_id}/install")
async def install_skill_pack(pack_id: str, request: SkillPackInstallRequest):
    if not _execution_store:
        raise HTTPException(status_code=503, detail="ExecutionStore not initialized")
    try:
        # Gate: referenced skills should be verified before install (workspace apply) when enforcement enabled.
        try:
            manifest = None
            if request.version:
                vrec = await _execution_store.get_skill_pack_version(pack_id=pack_id, version=request.version)
                manifest = vrec.get("manifest") if isinstance(vrec, dict) else None
            if manifest is None:
                pack = await _execution_store.get_skill_pack(pack_id)
                manifest = pack.get("manifest") if isinstance(pack, dict) else None
            manifest = _normalize_skill_pack_manifest(manifest if isinstance(manifest, dict) else {})
            skills = manifest.get("skills") if isinstance(manifest, dict) else []
            targets: list[tuple[str, str]] = []
            if isinstance(skills, list):
                for it in skills:
                    if not isinstance(it, dict):
                        continue
                    sid = str(it.get("id") or "").strip()
                    if sid:
                        targets.append(("skill", sid))
            await _require_targets_verified(list({(t[0], t[1]) for t in targets}))
        except HTTPException:
            raise
        except Exception:
            pass
        install = await _execution_store.install_skill_pack(
            pack_id=pack_id,
            version=request.version,
            scope=request.scope,
            metadata=request.metadata or {},
        )
        # Apply install (best-effort): materialize/enable skills declared by manifest.
        applied: List[Dict[str, Any]] = []
        try:
            manifest = None
            if request.version:
                vrec = await _execution_store.get_skill_pack_version(pack_id=pack_id, version=request.version)
                manifest = vrec.get("manifest") if isinstance(vrec, dict) else None
            if manifest is None:
                pack = await _execution_store.get_skill_pack(pack_id)
                manifest = pack.get("manifest") if isinstance(pack, dict) else None
            manifest = _normalize_skill_pack_manifest(manifest if isinstance(manifest, dict) else {})
            skills = manifest.get("skills") if isinstance(manifest, dict) else []
            if not isinstance(skills, list):
                skills = []

            scope = str(request.scope or "workspace")
            target_mgr = _workspace_skill_manager if scope == "workspace" else _skill_manager
            for item in skills:
                try:
                    # Skill spec: "skill_id" | {id,display_name,category,description,version,sop_markdown}
                    if not isinstance(item, dict):
                        continue
                    sid = str(item.get("id") or "").strip()
                    spec = dict(item)
                    if not sid:
                        continue
                    if not target_mgr:
                        applied.append({"skill_id": sid, "status": "skipped", "reason": "skill_manager_unavailable"})
                        continue

                    if scope == "workspace":
                        # Import into workspace (explicit id) so it becomes executable.
                        try:
                            await target_mgr.import_skill_from_pack(
                                skill_id=sid,
                                display_name=spec.get("display_name") or spec.get("name"),
                                category=spec.get("category") or "general",
                                description=spec.get("description") or "",
                                version=spec.get("version") or "1.0.0",
                                sop_markdown=spec.get("sop_markdown") or spec.get("sop") or "",
                                pack_metadata={"pack_id": pack_id, "version": request.version, "scope": scope},
                            )
                        except Exception as e:
                            applied.append({"skill_id": sid, "status": "skipped", "reason": str(e)})
                            continue

                    # Enable/restore
                    ok = await target_mgr.enable_skill(sid)
                    if not ok:
                        ok = await target_mgr.restore_skill(sid)
                    applied.append({"skill_id": sid, "status": "enabled" if ok else "skipped"})
                except Exception as e:
                    applied.append({"skill_id": str(item), "status": "skipped", "reason": str(e)})
        except Exception:
            applied = applied or []

        return {"install": install, "applied": applied}
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@api_router.get("/skill-packs/installs")
async def list_skill_pack_installs(scope: Optional[str] = None, limit: int = 100, offset: int = 0):
    if not _execution_store:
        raise HTTPException(status_code=503, detail="ExecutionStore not initialized")
    return await _execution_store.list_skill_pack_installs(scope=scope, limit=limit, offset=offset)


# ==================== Packages Registry (P0 MVP) ====================


def _sha256_file(p: Path) -> str:
    h = hashlib.sha256()
    with p.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def _packages_registry_dir() -> Path:
    return (Path.home() / ".aiplat" / "registry" / "packages").resolve()


def _is_approval_resolved_approved(approval_request_id: str) -> bool:
    if not approval_request_id or not _approval_manager:
        return False
    from core.harness.infrastructure.approval.types import RequestStatus

    r = _approval_manager.get_request(str(approval_request_id))
    if not r:
        return False
    return r.status in (RequestStatus.APPROVED, RequestStatus.AUTO_APPROVED)


async def _require_package_approval(*, operation: str, user_id: str, details: str, metadata: Dict[str, Any]) -> str:
    from core.harness.infrastructure.approval.types import ApprovalContext, ApprovalRule, RuleType

    if not _approval_manager:
        raise HTTPException(status_code=503, detail="Approval manager not available")
    rule = ApprovalRule(
        rule_id=f"packages_{operation}",
        rule_type=RuleType.SENSITIVE_OPERATION,
        name=f"Packages {operation} 审批",
        description=f"{operation} package 需要审批",
        priority=1,
        metadata={"sensitive_operations": [f"packages:{operation}"]},
    )
    _approval_manager.register_rule(rule)
    ctx = ApprovalContext(
        user_id=user_id,
        operation=f"packages:{operation}",
        operation_context={"details": details},
        metadata=metadata or {},
    )
    req = _approval_manager.create_request(ctx, rule=rule)
    try:
        await _approval_manager._persist(req)  # type: ignore[attr-defined]
    except Exception:
        pass
    return req.request_id


async def _require_onboarding_approval(*, operation: str, user_id: str, details: str, metadata: Dict[str, Any]) -> str:
    """
    Onboarding operations are global-impact changes (default routing/policies),
    so by default they should go through approvals.
    """
    from core.harness.infrastructure.approval.types import ApprovalContext, ApprovalRule, RuleType

    if not _approval_manager:
        raise HTTPException(status_code=503, detail="Approval manager not available")
    rule = ApprovalRule(
        rule_id=f"onboarding_{operation}",
        rule_type=RuleType.SENSITIVE_OPERATION,
        name=f"Onboarding {operation} 审批",
        description=f"{operation} onboarding 需要审批",
        priority=1,
        metadata={"sensitive_operations": [f"onboarding:{operation}"]},
    )
    _approval_manager.register_rule(rule)
    ctx = ApprovalContext(
        user_id=user_id,
        operation=f"onboarding:{operation}",
        operation_context={"details": details},
        metadata=metadata or {},
    )
    req = _approval_manager.create_request(ctx, rule=rule)
    try:
        await _approval_manager._persist(req)  # type: ignore[attr-defined]
    except Exception:
        pass
    return req.request_id


def _find_filesystem_package(pkg_name: str):
    p = _workspace_package_manager.get_package(pkg_name) if _workspace_package_manager else None
    if not p and _package_manager:
        p = _package_manager.get_package(pkg_name)
    return p


def _build_bundle_dir_for_package(pkg: Dict[str, Any], out_bundle_dir: Path) -> None:
    """
    Build a normalized bundle directory for publishing.
    Prefers <package_dir>/bundle when present; otherwise materializes from source dirs.
    """
    pkg_dir = Path(str(pkg.get("package_dir") or ""))
    existing_bundle = pkg_dir / "bundle"
    if existing_bundle.exists() and existing_bundle.is_dir():
        # copy existing bundle
        shutil.copytree(existing_bundle, out_bundle_dir, dirs_exist_ok=True)
        return

    # materialize from sources based on manifest resources
    repo_root = Path(__file__).resolve().parent
    engine_agents = (repo_root / "engine" / "agents").resolve()
    engine_skills = (repo_root / "engine" / "skills").resolve()
    engine_mcps = (repo_root / "engine" / "mcps").resolve()
    wk_agents = (Path.home() / ".aiplat" / "agents").resolve()
    wk_skills = (Path.home() / ".aiplat" / "skills").resolve()
    wk_mcps = (Path.home() / ".aiplat" / "mcps").resolve()
    wk_hooks = (Path.home() / ".aiplat" / "hooks").resolve()

    (out_bundle_dir / "agents").mkdir(parents=True, exist_ok=True)
    (out_bundle_dir / "skills").mkdir(parents=True, exist_ok=True)
    (out_bundle_dir / "mcps").mkdir(parents=True, exist_ok=True)
    (out_bundle_dir / "hooks").mkdir(parents=True, exist_ok=True)

    resources = pkg.get("resources") or []
    if not isinstance(resources, list):
        resources = []
    for r in resources:
        if not isinstance(r, dict):
            continue
        kind = str(r.get("kind") or "")
        rid = str(r.get("id") or "")
        scope = str(r.get("scope") or "engine").lower()
        if not kind or not rid:
            continue
        if kind == "agent":
            src = (engine_agents / rid) if scope == "engine" else (wk_agents / rid)
            dst = out_bundle_dir / "agents" / rid
            if src.exists() and src.is_dir():
                shutil.copytree(src, dst, dirs_exist_ok=True)
        elif kind == "skill":
            src = (engine_skills / rid) if scope == "engine" else (wk_skills / rid)
            dst = out_bundle_dir / "skills" / rid
            if src.exists() and src.is_dir():
                shutil.copytree(src, dst, dirs_exist_ok=True)
        elif kind == "mcp":
            src = (engine_mcps / rid) if scope == "engine" else (wk_mcps / rid)
            dst = out_bundle_dir / "mcps" / rid
            if src.exists() and src.is_dir():
                shutil.copytree(src, dst, dirs_exist_ok=True)
        elif kind == "hook":
            src = wk_hooks / f"{rid}.py"
            dst = out_bundle_dir / "hooks" / f"{rid}.py"
            if src.exists() and src.is_file():
                dst.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(src, dst)


@api_router.get("/packages/{pkg_name}/versions")
async def list_package_versions(pkg_name: str, limit: int = 100, offset: int = 0):
    if not _execution_store:
        raise HTTPException(status_code=503, detail="ExecutionStore not initialized")
    return await _execution_store.list_package_versions(package_name=pkg_name, limit=limit, offset=offset)


@api_router.get("/packages/{pkg_name}/versions/{version}")
async def get_package_version(pkg_name: str, version: str):
    if not _execution_store:
        raise HTTPException(status_code=503, detail="ExecutionStore not initialized")
    v = await _execution_store.get_package_version(package_name=pkg_name, version=version)
    if not v:
        raise HTTPException(status_code=404, detail="package_version_not_found")
    return v


@api_router.post("/packages/{pkg_name}/publish")
async def publish_package(pkg_name: str, request: PackagePublishRequest):
    if not _execution_store:
        raise HTTPException(status_code=503, detail="ExecutionStore not initialized")

    # Optional approval
    if request.require_approval:
        if not request.approval_request_id:
            rid = await _require_package_approval(
                operation="publish",
                user_id="admin",
                details=request.details or f"publish package {pkg_name}@{request.version}",
                metadata={"package_name": pkg_name, "version": request.version},
            )
            return {"status": "approval_required", "approval_request_id": rid}
        if not _is_approval_resolved_approved(request.approval_request_id):
            raise HTTPException(status_code=409, detail="not_approved")

    pkg = _find_filesystem_package(pkg_name)
    if not pkg:
        raise HTTPException(status_code=404, detail="package_not_found")

    # Build archive from bundle
    reg_dir = _packages_registry_dir() / pkg_name
    reg_dir.mkdir(parents=True, exist_ok=True)
    archive_path = reg_dir / f"{request.version}.tar.gz"

    with tempfile.TemporaryDirectory(prefix="aiplat_pkg_publish_") as td:
        td_path = Path(td)
        root = td_path / "pkg"
        root.mkdir(parents=True, exist_ok=True)
        bundle_dir = root / "bundle"
        _build_bundle_dir_for_package(pkg.__dict__ if hasattr(pkg, "__dict__") else (pkg if isinstance(pkg, dict) else {}), bundle_dir)
        # write package.yaml snapshot
        manifest = {
            "name": pkg.name if hasattr(pkg, "name") else pkg_name,
            "version": request.version,
            "description": getattr(pkg, "description", "") if hasattr(pkg, "description") else "",
            "resources": getattr(pkg, "resources", []) if hasattr(pkg, "resources") else (pkg.get("resources") if isinstance(pkg, dict) else []),
        }
        (root / "package.yaml").write_text(yaml.safe_dump(manifest, sort_keys=False, allow_unicode=True), encoding="utf-8")

        # create tar.gz
        with tarfile.open(str(archive_path), "w:gz") as tar:
            tar.add(str(root / "package.yaml"), arcname="package.yaml")
            tar.add(str(bundle_dir), arcname="bundle")

    sha = _sha256_file(archive_path)
    rec = await _execution_store.publish_package_version(
        package_name=pkg_name,
        version=request.version,
        manifest=manifest,
        artifact_path=str(archive_path),
        artifact_sha256=sha,
        approval_request_id=request.approval_request_id,
    )
    return {"status": "published", "package_version": rec}


@api_router.post("/packages/{pkg_name}/install")
async def install_package(pkg_name: str, http_request: Request, request: PackageInstallRequest):
    if not _execution_store:
        raise HTTPException(status_code=503, detail="ExecutionStore not initialized")
    if not _workspace_package_manager:
        raise HTTPException(status_code=503, detail="Workspace package manager not available")

    version = (request.version or "").strip() or None

    # Optional approval
    if request.require_approval:
        if not request.approval_request_id:
            rid = await _require_package_approval(
                operation="install",
                user_id="admin",
                details=request.details or f"install package {pkg_name}@{version or 'filesystem'}",
                metadata={"package_name": pkg_name, "version": version},
            )
            return {"status": "approval_required", "approval_request_id": rid}
        if not _is_approval_resolved_approved(request.approval_request_id):
            raise HTTPException(status_code=409, detail="not_approved")

    applied_record: Dict[str, Any] = {}
    manifest: Dict[str, Any] = {}
    artifact_sha256: Optional[str] = None

    if version:
        v = await _execution_store.get_package_version(package_name=pkg_name, version=version)
        if not v:
            raise HTTPException(status_code=404, detail="package_version_not_found")
        artifact_path = v.get("artifact_path")
        if not artifact_path or not Path(artifact_path).exists():
            raise HTTPException(status_code=404, detail="package_artifact_missing")
        manifest = v.get("manifest") or {}
        artifact_sha256 = v.get("artifact_sha256")

        with tempfile.TemporaryDirectory(prefix="aiplat_pkg_install_") as td:
            td_path = Path(td)
            with tarfile.open(str(artifact_path), "r:gz") as tar:
                tar.extractall(path=str(td_path))
            bundle_dir = td_path / "bundle"
            if not bundle_dir.exists():
                # some tar may have nested root; try one level
                nested = td_path / "pkg" / "bundle"
                bundle_dir = nested if nested.exists() else bundle_dir
            if not bundle_dir.exists():
                raise HTTPException(status_code=500, detail="invalid_package_artifact_bundle")
            applied_record = _workspace_package_manager.install_bundle(
                pkg_name=pkg_name,
                pkg_version=version,
                manifest=manifest,
                bundle_dir=bundle_dir,
                allow_overwrite=bool(request.allow_overwrite),
            )
    else:
        # Install directly from filesystem-defined package (engine/workspace)
        mgr = _workspace_package_manager if (_workspace_package_manager and _workspace_package_manager.get_package(pkg_name)) else _package_manager
        if not mgr:
            raise HTTPException(status_code=404, detail="package_not_found")
        applied_record = mgr.install(pkg_name=pkg_name, allow_overwrite=bool(request.allow_overwrite))
        manifest = (mgr.get_package(pkg_name).resources if mgr.get_package(pkg_name) else [])  # best-effort

    # Persist install record (DB)
    install_rec = await _execution_store.record_package_install(
        package_name=pkg_name,
        version=version,
        scope=str(request.scope or "workspace"),
        metadata={"record": applied_record, **(request.metadata or {}), "artifact_sha256": artifact_sha256},
        approval_request_id=request.approval_request_id,
    )

    # Reload managers + sync MCP runtime
    _reload_workspace_managers()
    await _sync_mcp_runtime()

    # Verification: mark pending + enqueue autosmoke
    try:
        if _execution_store is not None and _job_scheduler is not None:
            from core.harness.smoke import enqueue_autosmoke

            tenant_id = http_request.headers.get("X-AIPLAT-TENANT-ID", "ops_smoke")
            actor_id = http_request.headers.get("X-AIPLAT-ACTOR-ID", "admin")
            for it in (applied_record.get("applied") or []):
                k = str(it.get("kind") or "")
                rid = str(it.get("id") or "")
                if k not in {"agent", "skill", "mcp"} or not rid:
                    continue

                # pending
                try:
                    if k == "agent" and _workspace_agent_manager:
                        await _workspace_agent_manager.update_agent(
                            rid,
                            metadata={"verification": {"status": "pending", "updated_at": time.time(), "source": "package"}},
                        )
                    elif k == "skill" and _workspace_skill_manager:
                        await _workspace_skill_manager.update_skill(
                            rid,
                            {"metadata": {"verification": {"status": "pending", "updated_at": time.time(), "source": "package"}}},
                        )
                    elif k == "mcp" and _workspace_mcp_manager:
                        s = _workspace_mcp_manager.get_server(rid)
                        if s:
                            m = dict(s.metadata or {})
                            m["verification"] = {"status": "pending", "updated_at": time.time(), "source": "package"}
                            s.metadata = m
                            _workspace_mcp_manager.upsert_server(s)
                except Exception:
                    pass

                async def _on_complete(job_run: Dict[str, Any], *, _k=k, _rid=rid):
                    st = str(job_run.get("status") or "")
                    ver = {
                        "status": "verified" if st == "completed" else "failed",
                        "updated_at": time.time(),
                        "source": "package",
                        "job_id": str(job_run.get("job_id") or ""),
                        "job_run_id": str(job_run.get("id") or ""),
                        "reason": str(job_run.get("error") or ""),
                    }
                    try:
                        if _k == "agent" and _workspace_agent_manager:
                            await _workspace_agent_manager.update_agent(_rid, metadata={"verification": ver})
                        elif _k == "skill" and _workspace_skill_manager:
                            await _workspace_skill_manager.update_skill(_rid, {"metadata": {"verification": ver}})
                        elif _k == "mcp" and _workspace_mcp_manager:
                            s2 = _workspace_mcp_manager.get_server(_rid)
                            if s2:
                                m2 = dict(s2.metadata or {})
                                m2["verification"] = ver
                                s2.metadata = m2
                                _workspace_mcp_manager.upsert_server(s2)
                    except Exception:
                        pass

                await enqueue_autosmoke(
                    execution_store=_execution_store,
                    job_scheduler=_job_scheduler,
                    resource_type=k,
                    resource_id=rid,
                    tenant_id=tenant_id or "ops_smoke",
                    actor_id=actor_id or "admin",
                    detail={"op": "package_install", "package": pkg_name, "version": version},
                    on_complete=_on_complete,
                )
    except Exception:
        pass

    return {"status": "installed", "install": install_rec, "record": applied_record}


@api_router.get("/packages/installs")
async def list_package_installs(scope: Optional[str] = None, limit: int = 100, offset: int = 0):
    if not _execution_store:
        raise HTTPException(status_code=503, detail="ExecutionStore not initialized")
    return await _execution_store.list_package_installs(scope=scope, limit=limit, offset=offset)


@api_router.post("/packages/{pkg_name}/uninstall")
async def uninstall_package(pkg_name: str, request: PackageUninstallRequest):
    """
    Uninstall a registry-installed package from workspace (best-effort, uses filesystem install record).
    """
    if not _execution_store:
        raise HTTPException(status_code=503, detail="ExecutionStore not initialized")
    if not _workspace_package_manager:
        raise HTTPException(status_code=503, detail="Workspace package manager not available")

    # Optional approval
    if request.require_approval:
        if not request.approval_request_id:
            rid = await _require_package_approval(
                operation="uninstall",
                user_id="admin",
                details=request.details or f"uninstall package {pkg_name}",
                metadata={"package_name": pkg_name},
            )
            try:
                await _record_changeset(
                    name="package_uninstall",
                    target_type="package",
                    target_id=str(pkg_name),
                    status="approval_required",
                    args={"package_name": pkg_name, "keep_modified": bool(request.keep_modified)},
                    approval_request_id=rid,
                )
            except Exception:
                pass
            return {"status": "approval_required", "approval_request_id": rid}
        if not _is_approval_resolved_approved(request.approval_request_id):
            raise HTTPException(status_code=409, detail="not_approved")

    try:
        res = _workspace_package_manager.uninstall(pkg_name=pkg_name, keep_modified=bool(request.keep_modified))
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))

    try:
        await _record_changeset(
            name="package_uninstall",
            target_type="package",
            target_id=str(pkg_name),
            args={"package_name": pkg_name, "keep_modified": bool(request.keep_modified)},
            result={"removed": len((res or {}).get("removed") or []), "kept": len((res or {}).get("kept") or [])},
            approval_request_id=request.approval_request_id,
        )
    except Exception:
        pass

    _reload_workspace_managers()
    await _sync_mcp_runtime()
    return {"status": "uninstalled", "result": res, "approval_request_id": request.approval_request_id}


# ==================== Onboarding (core) ====================


@api_router.get("/onboarding/state")
async def get_core_onboarding_state():
    if not _execution_store:
        raise HTTPException(status_code=503, detail="ExecutionStore not initialized")
    default_llm = await _execution_store.get_global_setting(key="default_llm")
    autosmoke = await _execution_store.get_global_setting(key="autosmoke")
    tenants = await _execution_store.list_tenants(limit=50, offset=0)
    # adapters summary is already available via /adapters
    try:
        from core.harness.infrastructure.crypto import is_configured as secret_configured

        secrets = {"configured": bool(secret_configured())}
    except Exception:
        secrets = {"configured": False}
    return {
        "default_llm": default_llm["value"] if default_llm else None,
        "autosmoke": autosmoke["value"] if autosmoke else None,
        "tenants": tenants,
        "secrets": secrets,
    }


@api_router.post("/onboarding/default-llm")
async def set_default_llm(request: OnboardingDefaultLLMRequest):
    if not _execution_store:
        raise HTTPException(status_code=503, detail="ExecutionStore not initialized")

    if request.require_approval:
        if not request.approval_request_id:
            rid = await _require_onboarding_approval(
                operation="default_llm",
                user_id="admin",
                details=request.details or f"set default llm to {request.adapter_id}:{request.model}",
                metadata={"adapter_id": request.adapter_id, "model": request.model},
            )
            try:
                await _record_changeset(
                    name="global_setting_upsert_default_llm",
                    target_type="global_setting",
                    target_id="default_llm",
                    status="approval_required",
                    args={"adapter_id": request.adapter_id, "model": request.model},
                    approval_request_id=rid,
                )
            except Exception:
                pass
            return {"status": "approval_required", "approval_request_id": rid}
        if not _is_approval_resolved_approved(request.approval_request_id):
            try:
                await _record_changeset(
                    name="global_setting_upsert_default_llm",
                    target_type="global_setting",
                    target_id="default_llm",
                    status="failed",
                    args={"adapter_id": request.adapter_id, "model": request.model},
                    error="not_approved",
                    approval_request_id=request.approval_request_id,
                )
            except Exception:
                pass
            raise HTTPException(status_code=409, detail="not_approved")

    # validate adapter exists
    ad = await _execution_store.get_adapter(request.adapter_id)
    if not ad:
        try:
            await _record_changeset(
                name="global_setting_upsert_default_llm",
                target_type="global_setting",
                target_id="default_llm",
                status="failed",
                args={"adapter_id": request.adapter_id, "model": request.model},
                error="adapter_not_found",
                approval_request_id=request.approval_request_id,
            )
        except Exception:
            pass
        raise HTTPException(status_code=404, detail="adapter_not_found")

    try:
        res = await _execution_store.upsert_global_setting(
            key="default_llm",
            value={"adapter_id": request.adapter_id, "model": request.model},
        )
    except Exception as e:
        try:
            await _record_changeset(
                name="global_setting_upsert_default_llm",
                target_type="global_setting",
                target_id="default_llm",
                status="failed",
                args={"adapter_id": request.adapter_id, "model": request.model},
                error=f"exception:{type(e).__name__}",
                approval_request_id=request.approval_request_id,
            )
        except Exception:
            pass
        raise
    try:
        await _record_changeset(
            name="global_setting_upsert_default_llm",
            target_type="global_setting",
            target_id="default_llm",
            args={"adapter_id": request.adapter_id, "model": request.model},
            result={"updated_at": res.get("updated_at") if isinstance(res, dict) else None},
            approval_request_id=request.approval_request_id,
        )
    except Exception:
        pass
    return {"status": "updated", "default_llm": res}


@api_router.post("/onboarding/init-tenant")
async def init_default_tenant(request: OnboardingInitTenantRequest):
    if not _execution_store:
        raise HTTPException(status_code=503, detail="ExecutionStore not initialized")

    if request.require_approval:
        if not request.approval_request_id:
            rid = await _require_onboarding_approval(
                operation="init_tenant",
                user_id="admin",
                details=request.details or f"init tenant {request.tenant_id} (policies={request.init_policies})",
                metadata={"tenant_id": request.tenant_id, "init_policies": request.init_policies},
            )
            try:
                await _record_changeset(
                    name="tenant_init",
                    target_type="tenant",
                    target_id=str(request.tenant_id),
                    status="approval_required",
                    args={"tenant_id": str(request.tenant_id), "init_policies": bool(request.init_policies)},
                    approval_request_id=rid,
                )
            except Exception:
                pass
            return {"status": "approval_required", "approval_request_id": rid}
        if not _is_approval_resolved_approved(request.approval_request_id):
            try:
                await _record_changeset(
                    name="tenant_init",
                    target_type="tenant",
                    target_id=str(request.tenant_id),
                    status="failed",
                    args={"tenant_id": str(request.tenant_id), "init_policies": bool(request.init_policies)},
                    error="not_approved",
                    approval_request_id=request.approval_request_id,
                )
            except Exception:
                pass
            raise HTTPException(status_code=409, detail="not_approved")

    try:
        tenant = await _execution_store.upsert_tenant(tenant_id=request.tenant_id, name=request.tenant_name)
    except Exception as e:
        try:
            await _record_changeset(
                name="tenant_init",
                target_type="tenant",
                target_id=str(request.tenant_id),
                status="failed",
                args={"tenant_id": str(request.tenant_id), "init_policies": bool(request.init_policies)},
                error=f"exception:{type(e).__name__}",
                approval_request_id=request.approval_request_id,
            )
        except Exception:
            pass
        raise

    policy_res = None
    if request.init_policies:
        # Minimal baseline policy-as-code compatible with PolicyGate
        baseline_policy = {
            "tool_policy": {
                "deny_tools": [],
                "approval_required_tools": ["*"] if bool(request.strict_tool_approval) else [],
            }
        }
        try:
            policy_res = await _execution_store.upsert_tenant_policy(tenant_id=request.tenant_id, policy=baseline_policy)
        except Exception as e:
            try:
                await _record_changeset(
                    name="tenant_init",
                    target_type="tenant",
                    target_id=str(request.tenant_id),
                    status="failed",
                    args={"tenant_id": str(request.tenant_id), "init_policies": True},
                    error=f"exception:{type(e).__name__}",
                    approval_request_id=request.approval_request_id,
                )
            except Exception:
                pass
            raise

    try:
        await _record_changeset(
            name="tenant_init",
            target_type="tenant",
            target_id=str(request.tenant_id),
            args={
                "tenant_id": str(request.tenant_id),
                "init_policies": bool(request.init_policies),
                "strict_tool_approval": bool(request.strict_tool_approval),
            },
            result={"policy_version": policy_res.get("version") if isinstance(policy_res, dict) else None},
            approval_request_id=request.approval_request_id,
        )
    except Exception:
        pass
    return {"status": "initialized", "tenant": tenant, "tenant_policy": policy_res}


@api_router.post("/onboarding/autosmoke")
async def set_autosmoke_config(request: OnboardingAutosmokeConfigRequest):
    if not _execution_store:
        raise HTTPException(status_code=503, detail="ExecutionStore not initialized")

    if request.require_approval:
        if not request.approval_request_id:
            rid = await _require_onboarding_approval(
                operation="autosmoke",
                user_id="admin",
                details=request.details or f"set autosmoke enabled={request.enabled} enforce={request.enforce}",
                metadata={"enabled": request.enabled, "enforce": request.enforce, "dedup_seconds": request.dedup_seconds},
            )
            try:
                await _record_changeset(
                    name="global_setting_upsert_autosmoke",
                    target_type="global_setting",
                    target_id="autosmoke",
                    status="approval_required",
                    args={"enabled": bool(request.enabled), "enforce": bool(request.enforce), "dedup_seconds": request.dedup_seconds},
                    approval_request_id=rid,
                )
            except Exception:
                pass
            return {"status": "approval_required", "approval_request_id": rid}
        if not _is_approval_resolved_approved(request.approval_request_id):
            try:
                await _record_changeset(
                    name="global_setting_upsert_autosmoke",
                    target_type="global_setting",
                    target_id="autosmoke",
                    status="failed",
                    args={"enabled": bool(request.enabled), "enforce": bool(request.enforce), "dedup_seconds": request.dedup_seconds},
                    error="not_approved",
                    approval_request_id=request.approval_request_id,
                )
            except Exception:
                pass
            raise HTTPException(status_code=409, detail="not_approved")

    value: Dict[str, Any] = {"enabled": bool(request.enabled), "enforce": bool(request.enforce)}
    if request.webhook_url is not None:
        value["webhook_url"] = str(request.webhook_url)
    if request.dedup_seconds is not None:
        value["dedup_seconds"] = int(request.dedup_seconds)
    try:
        res = await _execution_store.upsert_global_setting(key="autosmoke", value=value)
    except Exception as e:
        try:
            await _record_changeset(
                name="global_setting_upsert_autosmoke",
                target_type="global_setting",
                target_id="autosmoke",
                status="failed",
                args=value,
                error=f"exception:{type(e).__name__}",
                approval_request_id=request.approval_request_id,
            )
        except Exception:
            pass
        raise
    try:
        await _record_changeset(
            name="global_setting_upsert_autosmoke",
            target_type="global_setting",
            target_id="autosmoke",
            args=value,
            result={"updated_at": res.get("updated_at") if isinstance(res, dict) else None},
            approval_request_id=request.approval_request_id,
        )
    except Exception:
        pass
    return {"status": "updated", "autosmoke": res}


@api_router.post("/onboarding/exec-backend")
async def set_exec_backend(request: OnboardingExecBackendRequest):
    if not _execution_store:
        raise HTTPException(status_code=503, detail="ExecutionStore not initialized")

    backend = str(request.backend or "local").strip()
    if backend not in {"local", "docker"}:
        raise HTTPException(status_code=400, detail="invalid_backend")

    if request.require_approval:
        if not request.approval_request_id:
            rid = await _require_onboarding_approval(
                operation="exec_backend",
                user_id="admin",
                details=request.details or f"set exec backend to {backend}",
                metadata={"backend": backend},
            )
            try:
                await _record_changeset(
                    name="global_setting_upsert_exec_backend",
                    target_type="global_setting",
                    target_id="exec_backend",
                    status="approval_required",
                    args={"backend": backend},
                    approval_request_id=rid,
                )
            except Exception:
                pass
            return {"status": "approval_required", "approval_request_id": rid}
        if not _is_approval_resolved_approved(request.approval_request_id):
            try:
                await _record_changeset(
                    name="global_setting_upsert_exec_backend",
                    target_type="global_setting",
                    target_id="exec_backend",
                    status="failed",
                    args={"backend": backend},
                    error="not_approved",
                    approval_request_id=request.approval_request_id,
                )
            except Exception:
                pass
            raise HTTPException(status_code=409, detail="not_approved")

    res = await _execution_store.upsert_global_setting(key="exec_backend", value={"backend": backend})
    try:
        await _record_changeset(
            name="global_setting_upsert_exec_backend",
            target_type="global_setting",
            target_id="exec_backend",
            args={"backend": backend},
            result={"updated_at": res.get("updated_at") if isinstance(res, dict) else None},
            approval_request_id=request.approval_request_id,
        )
    except Exception:
        pass
    return {"status": "updated", "exec_backend": res}


@api_router.post("/onboarding/trusted-skill-keys")
async def set_trusted_skill_keys(request: OnboardingTrustedSkillKeysRequest):
    """
    Configure trusted public keys for skill signature verification (P1-3).
    """
    if not _execution_store:
        raise HTTPException(status_code=503, detail="ExecutionStore not initialized")

    keys_in = request.keys if isinstance(request.keys, list) else []
    keys_out: list[dict] = []
    from core.harness.infrastructure.crypto.signature import key_id_for_public_key

    for it in keys_in:
        if not isinstance(it, dict):
            continue
        pk = str(it.get("public_key") or "").strip()
        if not pk:
            continue
        kid = str(it.get("key_id") or "").strip() or key_id_for_public_key(pk)
        keys_out.append({"key_id": kid, "public_key": pk})

    if request.require_approval:
        if not request.approval_request_id:
            rid = await _require_onboarding_approval(
                operation="trusted_skill_keys",
                user_id="admin",
                details=request.details or f"set trusted skill keys: {len(keys_out)} keys",
                metadata={"keys_count": len(keys_out), "key_ids": [k.get("key_id") for k in keys_out][:20]},
            )
            try:
                await _record_changeset(
                    name="global_setting_upsert_trusted_skill_keys",
                    target_type="global_setting",
                    target_id="trusted_skill_pubkeys",
                    status="approval_required",
                    args={"keys_count": len(keys_out)},
                    approval_request_id=rid,
                )
            except Exception:
                pass
            return {"status": "approval_required", "approval_request_id": rid}
        if not _is_approval_resolved_approved(request.approval_request_id):
            try:
                await _record_changeset(
                    name="global_setting_upsert_trusted_skill_keys",
                    target_type="global_setting",
                    target_id="trusted_skill_pubkeys",
                    status="failed",
                    args={"keys_count": len(keys_out)},
                    error="not_approved",
                    approval_request_id=request.approval_request_id,
                )
            except Exception:
                pass
            raise HTTPException(status_code=409, detail="not_approved")

    res = await _execution_store.upsert_global_setting(key="trusted_skill_pubkeys", value={"keys": keys_out})
    try:
        await _record_changeset(
            name="global_setting_upsert_trusted_skill_keys",
            target_type="global_setting",
            target_id="trusted_skill_pubkeys",
            args={"keys_count": len(keys_out), "key_ids": [k.get("key_id") for k in keys_out][:20]},
            result={"updated_at": res.get("updated_at") if isinstance(res, dict) else None},
            approval_request_id=request.approval_request_id,
        )
    except Exception:
        pass
    return {"status": "updated", "trusted_skill_pubkeys": {"keys_count": len(keys_out), "key_ids": [k.get("key_id") for k in keys_out]}}


@api_router.get("/onboarding/secrets/status")
async def get_secrets_status():
    if not _execution_store:
        raise HTTPException(status_code=503, detail="ExecutionStore not initialized")
    st = await _execution_store.get_adapter_secrets_status()
    try:
        from core.harness.infrastructure.crypto.secretbox import is_configured

        st["encryption_configured"] = bool(is_configured())
    except Exception:
        st["encryption_configured"] = False
    return st


@api_router.post("/onboarding/secrets/migrate")
async def migrate_secrets(request: OnboardingSecretsMigrateRequest):
    if not _execution_store:
        raise HTTPException(status_code=503, detail="ExecutionStore not initialized")

    if request.require_approval:
        if not request.approval_request_id:
            rid = await _require_onboarding_approval(
                operation="secrets_migrate",
                user_id="admin",
                details=request.details or "migrate adapter api_key to encrypted storage",
                metadata={},
            )
            try:
                await _record_changeset(
                    name="secrets_migrate",
                    target_type="adapters",
                    target_id="api_key",
                    status="approval_required",
                    args={},
                    approval_request_id=rid,
                )
            except Exception:
                pass
            return {"status": "approval_required", "approval_request_id": rid}
        if not _is_approval_resolved_approved(request.approval_request_id):
            try:
                await _record_changeset(
                    name="secrets_migrate",
                    target_type="adapters",
                    target_id="api_key",
                    status="failed",
                    args={},
                    error="not_approved",
                    approval_request_id=request.approval_request_id,
                )
            except Exception:
                pass
            raise HTTPException(status_code=409, detail="not_approved")

    try:
        res = await _execution_store.migrate_adapter_secrets_to_encrypted()
    except Exception as e:
        try:
            await _record_changeset(
                name="secrets_migrate",
                target_type="adapters",
                target_id="api_key",
                status="failed",
                args={},
                error=f"exception:{type(e).__name__}",
                approval_request_id=request.approval_request_id,
            )
        except Exception:
            pass
        raise HTTPException(status_code=400, detail=str(e))
    st = await _execution_store.get_adapter_secrets_status()
    try:
        await _record_changeset(
            name="secrets_migrate",
            target_type="adapters",
            target_id="api_key",
            args={},
            result={
                "migrated_count": res.get("migrated") if isinstance(res, dict) else None,
                "plaintext_after": st.get("plaintext") if isinstance(st, dict) else None,
            },
            approval_request_id=request.approval_request_id,
        )
    except Exception:
        pass
    return {"status": "migrated", "result": res, "secrets_status": st}


@api_router.post("/onboarding/strong-gate")
async def set_strong_gate(request: OnboardingStrongGateRequest):
    """
    Toggle strong gate for a tenant by setting tenant policy:
      tool_policy.approval_required_tools contains "*"
    This provides a safe, approval-guarded rollback switch.
    """
    if not _execution_store:
        raise HTTPException(status_code=503, detail="ExecutionStore not initialized")

    tenant_id = str(request.tenant_id or "default")
    enabled = bool(request.enabled)

    if request.require_approval:
        if not request.approval_request_id:
            rid = await _require_onboarding_approval(
                operation="strong_gate",
                user_id="admin",
                details=request.details or f"set strong gate enabled={enabled} for tenant={tenant_id}",
                metadata={"tenant_id": tenant_id, "enabled": enabled},
            )
            try:
                await _record_changeset(
                    name="strong_gate_set",
                    target_type="tenant_policy",
                    target_id=str(tenant_id),
                    status="approval_required",
                    args={"tenant_id": str(tenant_id), "enabled": bool(enabled)},
                    approval_request_id=rid,
                )
            except Exception:
                pass
            return {"status": "approval_required", "approval_request_id": rid}
        if not _is_approval_resolved_approved(request.approval_request_id):
            try:
                await _record_changeset(
                    name="strong_gate_set",
                    target_type="tenant_policy",
                    target_id=str(tenant_id),
                    status="failed",
                    args={"tenant_id": str(tenant_id), "enabled": bool(enabled)},
                    error="not_approved",
                    approval_request_id=request.approval_request_id,
                )
            except Exception:
                pass
            raise HTTPException(status_code=409, detail="not_approved")

    # ensure tenant exists (best-effort)
    try:
        await _execution_store.upsert_tenant(tenant_id=tenant_id, name=tenant_id)
    except Exception:
        pass

    cur = await _execution_store.get_tenant_policy(tenant_id=tenant_id)
    policy = (cur or {}).get("policy") if isinstance(cur, dict) else None
    if not isinstance(policy, dict):
        policy = {"tool_policy": {"deny_tools": [], "approval_required_tools": []}}
    tp = policy.get("tool_policy")
    if not isinstance(tp, dict):
        tp = {}
        policy["tool_policy"] = tp
    deny_tools = tp.get("deny_tools") if isinstance(tp.get("deny_tools"), list) else []
    approval_tools = tp.get("approval_required_tools") if isinstance(tp.get("approval_required_tools"), list) else []

    # normalize
    deny_tools = [str(x) for x in deny_tools if x]
    approval_tools = [str(x) for x in approval_tools if x]

    if enabled:
        if "*" not in approval_tools:
            approval_tools.insert(0, "*")
    else:
        approval_tools = [x for x in approval_tools if x != "*"]

    tp["deny_tools"] = deny_tools
    tp["approval_required_tools"] = approval_tools

    try:
        saved = await _execution_store.upsert_tenant_policy(tenant_id=tenant_id, policy=policy, version=None)
    except Exception as e:
        try:
            await _record_changeset(
                name="strong_gate_set",
                target_type="tenant_policy",
                target_id=str(tenant_id),
                status="failed",
                args={"tenant_id": str(tenant_id), "enabled": bool(enabled)},
                error=f"exception:{type(e).__name__}",
                approval_request_id=request.approval_request_id,
            )
        except Exception:
            pass
        raise
    try:
        await _record_changeset(
            name="strong_gate_set",
            target_type="tenant_policy",
            target_id=str(tenant_id),
            args={"tenant_id": str(tenant_id), "enabled": bool(enabled)},
            result={"version": saved.get("version") if isinstance(saved, dict) else None},
            approval_request_id=request.approval_request_id,
        )
    except Exception:
        pass
    return {"status": "updated", "tenant_policy": saved, "enabled": enabled}


@api_router.post("/memory/longterm")
async def add_long_term_memory(request: LongTermMemoryAddRequest):
    if not _execution_store:
        raise HTTPException(status_code=503, detail="ExecutionStore not initialized")
    return await _execution_store.add_long_term_memory(
        user_id=request.user_id or "system",
        key=request.key,
        content=request.content,
        metadata=request.metadata or {},
    )


@api_router.post("/memory/longterm/search")
async def search_long_term_memory(request: LongTermMemorySearchRequest):
    if not _execution_store:
        raise HTTPException(status_code=503, detail="ExecutionStore not initialized")
    items = await _execution_store.search_long_term_memory(
        user_id=request.user_id or "system",
        query=request.query,
        limit=request.limit,
    )
    return {"items": items, "total": len(items)}


# ==================== Jobs / Cron (Roadmap-3) ====================


@api_router.get("/jobs")
async def list_jobs(limit: int = 100, offset: int = 0, enabled: Optional[bool] = None):
    if not _execution_store:
        raise HTTPException(status_code=503, detail="ExecutionStore not initialized")
    return await _execution_store.list_jobs(limit=limit, offset=offset, enabled=enabled)


@api_router.post("/jobs")
async def create_job(request: JobCreateRequest):
    if not _execution_store:
        raise HTTPException(status_code=503, detail="ExecutionStore not initialized")
    now = time.time()
    try:
        next_run = next_run_from_cron(request.cron, from_ts=now) if request.enabled else None
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Invalid cron: {e}")
    job = await _execution_store.create_job(
        {
            "name": request.name,
            "enabled": request.enabled,
            "cron": request.cron,
            "timezone": request.timezone,
            "kind": request.kind,
            "target_id": request.target_id,
            "user_id": request.user_id or "system",
            "session_id": request.session_id or "default",
            "payload": request.payload or {},
            "options": request.options or {},
            "delivery": request.delivery or {},
            "next_run_at": next_run,
        }
    )
    return job


@api_router.get("/jobs/{job_id}")
async def get_job(job_id: str):
    if not _execution_store:
        raise HTTPException(status_code=503, detail="ExecutionStore not initialized")
    job = await _execution_store.get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    return job


@api_router.put("/jobs/{job_id}")
async def update_job(job_id: str, request: JobUpdateRequest):
    if not _execution_store:
        raise HTTPException(status_code=503, detail="ExecutionStore not initialized")
    patch = request.model_dump(exclude_unset=True)
    # recompute next_run_at if cron/enabled changed
    try:
        existing = await _execution_store.get_job(job_id)
        if not existing:
            raise HTTPException(status_code=404, detail="Job not found")
        enabled = bool(patch.get("enabled")) if "enabled" in patch else bool(existing.get("enabled"))
        cron = str(patch.get("cron") or existing.get("cron") or "* * * * *")
        if enabled:
            patch["next_run_at"] = next_run_from_cron(cron, from_ts=time.time())
        else:
            patch["next_run_at"] = None
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Invalid cron: {e}")

    updated = await _execution_store.update_job(job_id, patch)
    if not updated:
        raise HTTPException(status_code=404, detail="Job not found")
    return updated


@api_router.delete("/jobs/{job_id}")
async def delete_job(job_id: str):
    if not _execution_store:
        raise HTTPException(status_code=503, detail="ExecutionStore not initialized")
    ok = await _execution_store.delete_job(job_id)
    if not ok:
        raise HTTPException(status_code=404, detail="Job not found")
    return {"status": "deleted", "job_id": job_id}


@api_router.post("/jobs/{job_id}/enable")
async def enable_job(job_id: str):
    if not _execution_store:
        raise HTTPException(status_code=503, detail="ExecutionStore not initialized")
    job = await _execution_store.get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    next_run = next_run_from_cron(str(job.get("cron") or "* * * * *"), from_ts=time.time())
    updated = await _execution_store.update_job(job_id, {"enabled": True, "next_run_at": next_run})
    return updated


@api_router.post("/jobs/{job_id}/disable")
async def disable_job(job_id: str):
    if not _execution_store:
        raise HTTPException(status_code=503, detail="ExecutionStore not initialized")
    updated = await _execution_store.update_job(job_id, {"enabled": False, "next_run_at": None})
    if not updated:
        raise HTTPException(status_code=404, detail="Job not found")
    return updated


@api_router.post("/jobs/{job_id}/run")
async def run_job_now(job_id: str):
    if not _job_scheduler:
        raise HTTPException(status_code=503, detail="JobScheduler not running")
    try:
        return await _job_scheduler.run_job_once(job_id)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except RuntimeError as e:
        raise HTTPException(status_code=409, detail=str(e))


@api_router.get("/jobs/{job_id}/runs/{run_id}")
async def get_job_run(job_id: str, run_id: str):
    if not _execution_store:
        raise HTTPException(status_code=503, detail="ExecutionStore not initialized")
    run = await _execution_store.get_job_run(run_id)
    if not run or str(run.get("job_id")) != str(job_id):
        raise HTTPException(status_code=404, detail="Job run not found")
    return run


@api_router.get("/jobs/{job_id}/runs")
async def list_job_runs(job_id: str, limit: int = 100, offset: int = 0):
    if not _execution_store:
        raise HTTPException(status_code=503, detail="ExecutionStore not initialized")
    return await _execution_store.list_job_runs(job_id=job_id, limit=limit, offset=offset)


@api_router.get("/jobs/dlq")
async def list_job_delivery_dlq(status: Optional[str] = None, job_id: Optional[str] = None, limit: int = 100, offset: int = 0):
    if not _execution_store:
        raise HTTPException(status_code=503, detail="ExecutionStore not initialized")
    return await _execution_store.list_job_delivery_dlq(status=status, job_id=job_id, limit=limit, offset=offset)


@api_router.post("/jobs/dlq/{dlq_id}/retry")
async def retry_job_delivery_dlq(dlq_id: str):
    if not _job_scheduler:
        raise HTTPException(status_code=503, detail="JobScheduler not running")
    try:
        return await _job_scheduler.retry_dlq_delivery(dlq_id)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except RuntimeError as e:
        raise HTTPException(status_code=409, detail=str(e))


@api_router.delete("/jobs/dlq/{dlq_id}")
async def delete_job_delivery_dlq(dlq_id: str):
    if not _execution_store:
        raise HTTPException(status_code=503, detail="ExecutionStore not initialized")
    ok = await _execution_store.delete_job_delivery_dlq_item(dlq_id)
    if not ok:
        raise HTTPException(status_code=404, detail="DLQ item not found")
    return {"status": "deleted", "dlq_id": dlq_id}


# ==================== Diagnostics: E2E Smoke ====================


@api_router.post("/diagnostics/e2e/smoke")
async def run_e2e_smoke(request: Dict[str, Any]):
    """
    Production-grade full-chain smoke.

    Notes:
    - DeepSeek key is read from ENV (DEEPSEEK_API_KEY / AIPLAT_LLM_API_KEY) by core at runtime.
    - This endpoint performs best-effort cleanup of created resources immediately.
    """
    harness = get_harness()
    run_id = new_prefixed_id("run")
    exec_req = ExecutionRequest(
        kind="smoke_e2e",
        target_id="smoke_e2e",
        payload=request or {},
        user_id=str((request or {}).get("actor_id") or "admin"),
        session_id=str((request or {}).get("session_id") or "ops_smoke"),
        request_id=run_id,
        run_id=run_id,
    )
    result = await harness.execute(exec_req)
    if not result.ok:
        raise HTTPException(status_code=result.http_status, detail=result.error or "Smoke failed")
    return result.payload


# ==================== Diagnostics: Context / Prompt Assembly ====================


@api_router.get("/diagnostics/context/config")
async def get_context_config():
    """
    Return context/prompt assembly configuration for observability (no secrets).
    """
    from core.harness.context.engine import DefaultContextEngine

    enable_session_search = os.getenv("AIPLAT_ENABLE_SESSION_SEARCH", "false").lower() in ("1", "true", "yes", "y")
    return {
        "context_engine": "default_v1",
        "enable_session_search": bool(enable_session_search),
        "project_context": {
            "supported_files": ["AGENTS.md", "AIPLAT.md"],
            "max_context_chars": int(getattr(DefaultContextEngine, "_MAX_CONTEXT_CHARS", 20000)),
        },
        "security": {"has_injection_detection": True},
    }


@api_router.post("/diagnostics/prompt/assemble")
async def diagnostics_prompt_assemble(request: DiagnosticsPromptAssembleRequest):
    """
    Assemble prompt + context and return metadata for debugging.
    NOTE: This endpoint is for diagnostics and should not be used on hot paths.
    """
    from core.harness.assembly.prompt_assembler import PromptAssembler
    from core.harness.kernel.execution_context import (
        ActiveRequestContext,
        ActiveWorkspaceContext,
        reset_active_request_context,
        reset_active_workspace_context,
        set_active_request_context,
        set_active_workspace_context,
    )

    msgs: List[Dict[str, Any]] = []
    if request.messages and isinstance(request.messages, list):
        msgs = request.messages  # type: ignore[assignment]
    elif request.session_id and _execution_store:
        sess = await _execution_store.get_memory_session(session_id=str(request.session_id))
        if not sess:
            raise HTTPException(status_code=404, detail="session_not_found")
        res = await _execution_store.list_memory_messages(session_id=str(request.session_id), limit=200, offset=0)
        msgs = [
            {"role": m.get("role"), "content": m.get("content"), "metadata": (m.get("metadata") or {})}
            for m in (res.get("items") or [])
        ]
    else:
        raise HTTPException(status_code=400, detail="messages_or_session_id_required")

    meta: Dict[str, Any] = {"enable_project_context": bool(request.enable_project_context)}

    # Optional toggle override (best-effort; restore after)
    env_prev = os.getenv("AIPLAT_ENABLE_SESSION_SEARCH")
    env_set = None
    if request.enable_session_search is not None:
        env_set = "true" if request.enable_session_search else "false"
        os.environ["AIPLAT_ENABLE_SESSION_SEARCH"] = env_set

    t1 = None
    t2 = None
    try:
        t1 = set_active_workspace_context(ActiveWorkspaceContext(repo_root=request.repo_root))
        t2 = set_active_request_context(
            ActiveRequestContext(user_id=str(request.user_id), session_id=str(request.session_id or "default"))
        )
        out = PromptAssembler().assemble(msgs, metadata=meta)
        return {
            "status": "ok",
            "prompt_version": out.prompt_version,
            "workspace_context_hash": out.workspace_context_hash,
            "stable_prompt_version": out.stable_prompt_version,
            "stable_cache_key": out.stable_cache_key,
            "stable_cache_hit": bool(out.stable_cache_hit),
            "metadata": out.metadata,
            "system_layers": {
                "stable_system_prompt_chars": len(out.stable_system_prompt or ""),
                "ephemeral_overlay_chars": len(out.ephemeral_overlay or ""),
            },
            "message_count": len(out.messages or []),
        }
    finally:
        if t2 is not None:
            try:
                reset_active_request_context(t2)
            except Exception:
                pass
        if t1 is not None:
            try:
                reset_active_workspace_context(t1)
            except Exception:
                pass
        if env_set is not None:
            try:
                if env_prev is None:
                    os.environ.pop("AIPLAT_ENABLE_SESSION_SEARCH", None)
                else:
                    os.environ["AIPLAT_ENABLE_SESSION_SEARCH"] = env_prev
            except Exception:
                pass


# ==================== Prompt Templates (platformization MVP) ====================


@api_router.get("/prompts")
async def list_prompt_templates(limit: int = 100, offset: int = 0):
    if not _execution_store:
        raise HTTPException(status_code=503, detail="ExecutionStore not initialized")
    return await _execution_store.list_prompt_templates(limit=int(limit), offset=int(offset))


@api_router.get("/prompts/{template_id}")
async def get_prompt_template(template_id: str):
    if not _execution_store:
        raise HTTPException(status_code=503, detail="ExecutionStore not initialized")
    tpl = await _execution_store.get_prompt_template(template_id=str(template_id))
    if not tpl:
        raise HTTPException(status_code=404, detail="not_found")
    return tpl


@api_router.post("/prompts")
async def upsert_prompt_template(request: PromptTemplateUpsertRequest, http_request: Request):
    if not _execution_store:
        raise HTTPException(status_code=503, detail="ExecutionStore not initialized")

    prev = None
    try:
        prev = await _execution_store.get_prompt_template(template_id=str(request.template_id))
    except Exception:
        prev = None

    if request.require_approval:
        if not request.approval_request_id:
            rid = await _require_onboarding_approval(
                operation="prompt_template_upsert",
                user_id="admin",
                details=request.details or f"upsert prompt template {request.template_id}",
                metadata={"template_id": request.template_id, "name": request.name},
            )
            try:
                await _record_changeset(
                    name="prompt_template_upsert",
                    target_type="prompt_template",
                    target_id=str(request.template_id),
                    status="approval_required",
                    args={"template_id": request.template_id, "name": request.name},
                    approval_request_id=rid,
                )
            except Exception:
                pass
            return {"status": "approval_required", "approval_request_id": rid}
        if not _is_approval_resolved_approved(request.approval_request_id):
            try:
                await _record_changeset(
                    name="prompt_template_upsert",
                    target_type="prompt_template",
                    target_id=str(request.template_id),
                    status="failed",
                    args={"template_id": request.template_id, "name": request.name},
                    error="not_approved",
                    approval_request_id=request.approval_request_id,
                )
            except Exception:
                pass
            raise HTTPException(status_code=409, detail="not_approved")

    try:
        res = await _execution_store.upsert_prompt_template(
            template_id=request.template_id,
            name=request.name,
            template=request.template,
            metadata=request.metadata or {},
            increment_version=bool(request.increment_version),
        )
    except Exception as e:
        try:
            await _record_changeset(
                name="prompt_template_upsert",
                target_type="prompt_template",
                target_id=str(request.template_id),
                status="failed",
                args={"template_id": request.template_id, "name": request.name},
                error=f"exception:{type(e).__name__}",
                approval_request_id=request.approval_request_id,
            )
        except Exception:
            pass
        raise

    # Audit as a "changeset" syscall event (no secret content, hash only)
    try:
        import hashlib

        await _record_changeset(
            name="prompt_template_upsert",
            target_type="prompt_template",
            target_id=str(request.template_id),
            status="success",
            args={
                "template_id": request.template_id,
                "name": request.name,
                "prev_version": (prev or {}).get("version") if isinstance(prev, dict) else None,
            },
            result={
                "version": res.get("version") if isinstance(res, dict) else None,
                "template_sha256": hashlib.sha256(str(request.template).encode("utf-8")).hexdigest(),
                "template_len": len(str(request.template)),
            },
            approval_request_id=request.approval_request_id,
        )
    except Exception:
        pass

    # Verification: mark pending + enqueue autosmoke (best-effort)
    try:
        if _execution_store is not None and _job_scheduler is not None:
            from core.harness.smoke import enqueue_autosmoke

            await _execution_store.update_prompt_template_metadata(
                template_id=str(request.template_id),
                patch={"verification": {"status": "pending", "updated_at": time.time(), "source": "autosmoke"}},
                merge=True,
            )

            tenant_id = http_request.headers.get("X-AIPLAT-TENANT-ID", "ops_smoke")
            actor_id = http_request.headers.get("X-AIPLAT-ACTOR-ID", "admin")

            async def _on_complete(job_run: Dict[str, Any]):
                st = str(job_run.get("status") or "")
                ver = {
                    "status": "verified" if st == "completed" else "failed",
                    "updated_at": time.time(),
                    "source": "autosmoke",
                    "job_id": str(job_run.get("job_id") or ""),
                    "job_run_id": str(job_run.get("id") or ""),
                    "trace_id": str(job_run.get("trace_id") or "") or None,
                    "reason": str(job_run.get("error") or ""),
                }
                try:
                    await _execution_store.update_prompt_template_metadata(
                        template_id=str(request.template_id), patch={"verification": ver}, merge=True
                    )
                except Exception:
                    pass

            await enqueue_autosmoke(
                execution_store=_execution_store,
                job_scheduler=_job_scheduler,
                resource_type="prompt_template",
                resource_id=str(request.template_id),
                tenant_id=tenant_id or "ops_smoke",
                actor_id=actor_id or "admin",
                detail={"op": "prompt_template_upsert", "template_id": str(request.template_id)},
                on_complete=_on_complete,
            )
    except Exception:
        pass
    return {"status": "updated", "template": res}


@api_router.post("/prompts/{template_id}/rollback")
async def rollback_prompt_template(template_id: str, request: PromptTemplateRollbackRequest, http_request: Request):
    if not _execution_store:
        raise HTTPException(status_code=503, detail="ExecutionStore not initialized")

    if request.template_id and str(request.template_id) != str(template_id):
        raise HTTPException(status_code=400, detail="template_id_mismatch")

    if request.require_approval:
        if not request.approval_request_id:
            rid = await _require_onboarding_approval(
                operation="prompt_template_rollback",
                user_id="admin",
                details=request.details or f"rollback prompt template {template_id} to {request.version}",
                metadata={"template_id": str(template_id), "version": str(request.version)},
            )
            try:
                await _record_changeset(
                    name="prompt_template_rollback",
                    target_type="prompt_template",
                    target_id=str(template_id),
                    status="approval_required",
                    args={"template_id": str(template_id), "version": str(request.version)},
                    approval_request_id=rid,
                )
            except Exception:
                pass
            return {"status": "approval_required", "approval_request_id": rid}
        if not _is_approval_resolved_approved(request.approval_request_id):
            try:
                await _record_changeset(
                    name="prompt_template_rollback",
                    target_type="prompt_template",
                    target_id=str(template_id),
                    status="failed",
                    args={"template_id": str(template_id), "version": str(request.version)},
                    error="not_approved",
                    approval_request_id=request.approval_request_id,
                )
            except Exception:
                pass
            raise HTTPException(status_code=409, detail="not_approved")

    try:
        tpl = await _execution_store.rollback_prompt_template_version(template_id=str(template_id), version=str(request.version))
    except KeyError:
        try:
            await _record_changeset(
                name="prompt_template_rollback",
                target_type="prompt_template",
                target_id=str(template_id),
                status="failed",
                args={"template_id": str(template_id), "version": str(request.version)},
                error="version_not_found",
                approval_request_id=request.approval_request_id,
            )
        except Exception:
            pass
        raise HTTPException(status_code=404, detail="version_not_found")
    except Exception as e:
        try:
            await _record_changeset(
                name="prompt_template_rollback",
                target_type="prompt_template",
                target_id=str(template_id),
                status="failed",
                args={"template_id": str(template_id), "version": str(request.version)},
                error=f"exception:{type(e).__name__}",
                approval_request_id=request.approval_request_id,
            )
        except Exception:
            pass
        raise

    try:
        await _record_changeset(
            name="prompt_template_rollback",
            target_type="prompt_template",
            target_id=str(template_id),
            status="success",
            args={"template_id": str(template_id), "version": str(request.version)},
            result={"status": "rolled_back"},
            approval_request_id=request.approval_request_id,
        )
    except Exception:
        pass

    # Verification: mark pending + enqueue autosmoke (best-effort)
    try:
        if _execution_store is not None and _job_scheduler is not None:
            from core.harness.smoke import enqueue_autosmoke

            await _execution_store.update_prompt_template_metadata(
                template_id=str(template_id),
                patch={"verification": {"status": "pending", "updated_at": time.time(), "source": "autosmoke"}},
                merge=True,
            )
            tenant_id = http_request.headers.get("X-AIPLAT-TENANT-ID", "ops_smoke")
            actor_id = http_request.headers.get("X-AIPLAT-ACTOR-ID", "admin")

            async def _on_complete(job_run: Dict[str, Any]):
                st = str(job_run.get("status") or "")
                ver = {
                    "status": "verified" if st == "completed" else "failed",
                    "updated_at": time.time(),
                    "source": "autosmoke",
                    "job_id": str(job_run.get("job_id") or ""),
                    "job_run_id": str(job_run.get("id") or ""),
                    "trace_id": str(job_run.get("trace_id") or "") or None,
                    "reason": str(job_run.get("error") or ""),
                }
                try:
                    await _execution_store.update_prompt_template_metadata(
                        template_id=str(template_id), patch={"verification": ver}, merge=True
                    )
                except Exception:
                    pass

            await enqueue_autosmoke(
                execution_store=_execution_store,
                job_scheduler=_job_scheduler,
                resource_type="prompt_template",
                resource_id=str(template_id),
                tenant_id=tenant_id or "ops_smoke",
                actor_id=actor_id or "admin",
                detail={"op": "prompt_template_rollback", "template_id": str(template_id), "version": str(request.version)},
                on_complete=_on_complete,
            )
    except Exception:
        pass
    return {"status": "rolled_back", "template": tpl}


@api_router.get("/prompts/{template_id}/versions")
async def list_prompt_template_versions(template_id: str, limit: int = 100, offset: int = 0):
    if not _execution_store:
        raise HTTPException(status_code=503, detail="ExecutionStore not initialized")
    return await _execution_store.list_prompt_template_versions(template_id=str(template_id), limit=int(limit), offset=int(offset))


@api_router.get("/prompts/{template_id}/diff")
async def diff_prompt_template(template_id: str, from_version: Optional[str] = None, to_version: Optional[str] = None):
    """
    Diff prompt template content between two versions.
    Defaults:
      - to_version: current version
      - from_version: previous version (if exists)
    """
    import difflib
    import hashlib
    if not _execution_store:
        raise HTTPException(status_code=503, detail="ExecutionStore not initialized")

    cur = await _execution_store.get_prompt_template(template_id=str(template_id))
    if not cur:
        raise HTTPException(status_code=404, detail="not_found")
    cur_ver = str(cur.get("version") or "")
    cur_tpl = str(cur.get("template") or "")

    # Resolve to_version
    resolved_to_ver = str(to_version) if to_version else cur_ver
    if resolved_to_ver == cur_ver:
        to_tpl = cur_tpl
    else:
        v = await _execution_store.get_prompt_template_version(template_id=str(template_id), version=str(resolved_to_ver))
        if not v:
            raise HTTPException(status_code=404, detail="to_version_not_found")
        to_tpl = str(v.get("template") or "")

    # Resolve from_version
    resolved_from_ver = str(from_version) if from_version else ""
    if not resolved_from_ver:
        # previous version: first version in list that is not resolved_to_ver
        vers = await _execution_store.list_prompt_template_versions(template_id=str(template_id), limit=20, offset=0)
        for it in (vers.get("items") or []):
            vv = str((it or {}).get("version") or "")
            if vv and vv != resolved_to_ver:
                resolved_from_ver = vv
                break
    if not resolved_from_ver:
        resolved_from_ver = resolved_to_ver
    if resolved_from_ver == cur_ver:
        from_tpl = cur_tpl
    else:
        v2 = await _execution_store.get_prompt_template_version(template_id=str(template_id), version=str(resolved_from_ver))
        if not v2:
            raise HTTPException(status_code=404, detail="from_version_not_found")
        from_tpl = str(v2.get("template") or "")

    diff_lines = list(
        difflib.unified_diff(
            from_tpl.splitlines(),
            to_tpl.splitlines(),
            fromfile=f"{template_id}@{resolved_from_ver}",
            tofile=f"{template_id}@{resolved_to_ver}",
            lineterm="",
        )
    )
    diff_text = "\n".join(diff_lines)

    return {
        "status": "ok",
        "template_id": str(template_id),
        "from_version": resolved_from_ver,
        "to_version": resolved_to_ver,
        "from_sha256": hashlib.sha256(from_tpl.encode("utf-8")).hexdigest(),
        "to_sha256": hashlib.sha256(to_tpl.encode("utf-8")).hexdigest(),
        "diff_sha256": hashlib.sha256(diff_text.encode("utf-8")).hexdigest(),
        "diff": diff_text,
        "diff_len": len(diff_text),
    }


@api_router.delete("/prompts/{template_id}")
async def delete_prompt_template(template_id: str, http_request: Request, require_approval: bool = True, approval_request_id: Optional[str] = None, details: Optional[str] = None):
    if not _execution_store:
        raise HTTPException(status_code=503, detail="ExecutionStore not initialized")

    if require_approval:
        if not approval_request_id:
            rid = await _require_onboarding_approval(
                operation="prompt_template_delete",
                user_id="admin",
                details=details or f"delete prompt template {template_id}",
                metadata={"template_id": str(template_id)},
            )
            try:
                await _record_changeset(
                    name="prompt_template_delete",
                    target_type="prompt_template",
                    target_id=str(template_id),
                    status="approval_required",
                    args={},
                    approval_request_id=rid,
                )
            except Exception:
                pass
            return {"status": "approval_required", "approval_request_id": rid}
        if not _is_approval_resolved_approved(approval_request_id):
            try:
                await _record_changeset(
                    name="prompt_template_delete",
                    target_type="prompt_template",
                    target_id=str(template_id),
                    status="failed",
                    args={},
                    error="not_approved",
                    approval_request_id=approval_request_id,
                )
            except Exception:
                pass
            raise HTTPException(status_code=409, detail="not_approved")

    ok = await _execution_store.delete_prompt_template(template_id=str(template_id))
    try:
        await _record_changeset(
            name="prompt_template_delete",
            target_type="prompt_template",
            target_id=str(template_id),
            args={},
            result={"status": "deleted" if ok else "not_found"},
            approval_request_id=approval_request_id,
        )
    except Exception:
        pass

    # Verification: mark pending + enqueue autosmoke (best-effort)
    try:
        if ok and _execution_store is not None and _job_scheduler is not None:
            from core.harness.smoke import enqueue_autosmoke

            tenant_id = http_request.headers.get("X-AIPLAT-TENANT-ID", "ops_smoke")
            actor_id = http_request.headers.get("X-AIPLAT-ACTOR-ID", "admin")

            await enqueue_autosmoke(
                execution_store=_execution_store,
                job_scheduler=_job_scheduler,
                resource_type="prompt_template",
                resource_id=str(template_id),
                tenant_id=tenant_id or "ops_smoke",
                actor_id=actor_id or "admin",
                detail={"op": "prompt_template_delete", "template_id": str(template_id)},
            )
    except Exception:
        pass
    return {"status": "deleted" if ok else "not_found"}


@api_router.get("/diagnostics/exec/backends")
async def diagnostics_exec_backends():
    """
    Exec backend diagnostics (P1-1).
    """
    from core.apps.exec_drivers.registry import get_exec_backend, healthcheck_backends

    backend = await get_exec_backend()
    health = await healthcheck_backends()
    return {
        "status": "ok",
        "current_backend": backend,
        "backends": health.get("backends") if isinstance(health, dict) else [],
        "non_local_requires_approval": True,
    }


# ==================== Repo Changeset (repo-aware workflow MVP) ====================


@api_router.post("/diagnostics/repo/changeset/preview")
async def diagnostics_repo_changeset_preview(request: RepoChangesetPreviewRequest):
    """
    Repo-aware workflow MVP: summarize git working tree changes (no arbitrary commands).
    Returns status + numstat + hashes. Optionally includes full patch (include_patch=true).
    """
    import subprocess
    import hashlib
    from pathlib import Path

    repo_root = str(request.repo_root or "").strip()
    if not repo_root:
        raise HTTPException(status_code=400, detail="repo_root_required")
    p = Path(repo_root)
    if not p.exists() or not p.is_dir():
        raise HTTPException(status_code=404, detail="repo_root_not_found")
    if not (p / ".git").exists():
        raise HTTPException(status_code=400, detail="not_a_git_repo")

    def _run(args: list[str], timeout_s: int = 5) -> str:
        cp = subprocess.run(args, capture_output=True, text=True, timeout=timeout_s)
        if cp.returncode != 0:
            raise RuntimeError((cp.stderr or cp.stdout or "").strip()[:500])
        return (cp.stdout or "").strip()

    try:
        head = _run(["git", "-C", repo_root, "rev-parse", "HEAD"])
    except Exception:
        head = ""
    try:
        branch = _run(["git", "-C", repo_root, "rev-parse", "--abbrev-ref", "HEAD"])
    except Exception:
        branch = ""
    last_commit = {}
    try:
        # sha<TAB>author<TAB>author_date<TAB>subject
        line = _run(["git", "-C", repo_root, "log", "-1", "--pretty=format:%H%x09%an%x09%ad%x09%s"])
        parts = (line or "").split("\t")
        if len(parts) >= 4:
            last_commit = {"sha": parts[0], "author": parts[1], "date": parts[2], "subject": "\t".join(parts[3:])}
    except Exception:
        last_commit = {}

    status = _run(["git", "-C", repo_root, "status", "--porcelain=v1"])
    # numstat: "added\tdeleted\tpath"
    numstat = _run(["git", "-C", repo_root, "diff", "--numstat"])
    staged_numstat = _run(["git", "-C", repo_root, "diff", "--cached", "--numstat"])
    patch = ""
    if bool(request.include_patch):
        patch = _run(["git", "-C", repo_root, "diff"], timeout_s=10)
    diff_hash = hashlib.sha256((numstat + "\n" + staged_numstat + "\n" + patch).encode("utf-8")).hexdigest()

    def _summarize(ns: str) -> dict:
        files = 0
        added = 0
        deleted = 0
        for line in (ns or "").splitlines():
            parts = line.split("\t")
            if len(parts) < 3:
                continue
            files += 1
            a, d = parts[0], parts[1]
            try:
                if a.isdigit():
                    added += int(a)
            except Exception:
                pass
            try:
                if d.isdigit():
                    deleted += int(d)
            except Exception:
                pass
        return {"files_changed": files, "lines_added": added, "lines_deleted": deleted}

    out = {
        "repo_root": repo_root,
        "branch": branch,
        "head": head,
        "last_commit": last_commit,
        "status_lines": len(status.splitlines()) if status else 0,
        "working_tree": _summarize(numstat),
        "staged": _summarize(staged_numstat),
        "diff_sha256": diff_hash,
    }
    if bool(request.include_patch):
        out["patch"] = patch
        out["patch_len"] = len(patch)
    return out


@api_router.post("/diagnostics/repo/tests/run")
async def diagnostics_repo_tests_run(request: RepoTestsRunRequest):
    """
    Repo-aware workflow MVP: run repo tests with an allowlisted command.
    Security: command is controlled by env AIPLAT_REPO_TEST_CMD, not user input.
    """
    import subprocess
    import time as _time
    import hashlib
    import shlex
    from pathlib import Path

    repo_root = str(request.repo_root or "").strip()
    if not repo_root:
        raise HTTPException(status_code=400, detail="repo_root_required")
    p = Path(repo_root)
    if not p.exists() or not p.is_dir():
        raise HTTPException(status_code=404, detail="repo_root_not_found")
    if not (p / ".git").exists():
        raise HTTPException(status_code=400, detail="not_a_git_repo")

    cmd = str(os.getenv("AIPLAT_REPO_TEST_CMD", "")).strip()
    if not cmd:
        raise HTTPException(status_code=400, detail="AIPLAT_REPO_TEST_CMD_not_set")

    args = shlex.split(cmd)
    t0 = _time.time()
    try:
        cp = subprocess.run(args, cwd=repo_root, capture_output=True, text=True, timeout=600)
    except subprocess.TimeoutExpired:
        duration_ms = int((_time.time() - t0) * 1000)
        await _record_changeset(
            name="repo_tests_run",
            target_type="repo",
            target_id=repo_root,
            status="failed",
            args={"cmd": cmd, "note": str(request.note or "").strip()},
            error="timeout",
            result={"duration_ms": duration_ms},
        )
        raise HTTPException(status_code=408, detail="tests_timeout")
    duration_ms = int((_time.time() - t0) * 1000)

    def _tail(s: str, n: int = 8000) -> str:
        s = s or ""
        return s[-n:] if len(s) > n else s

    stdout_tail = _tail(cp.stdout or "")
    stderr_tail = _tail(cp.stderr or "")
    out = {
        "cmd": cmd,
        "exit_code": int(cp.returncode),
        "duration_ms": duration_ms,
        "stdout_tail": stdout_tail,
        "stderr_tail": stderr_tail,
        "stdout_sha256": hashlib.sha256(stdout_tail.encode("utf-8")).hexdigest(),
        "stderr_sha256": hashlib.sha256(stderr_tail.encode("utf-8")).hexdigest(),
    }

    await _record_changeset(
        name="repo_tests_run",
        target_type="repo",
        target_id=repo_root,
        status="success" if cp.returncode == 0 else "failed",
        args={"cmd": cmd, "note": str(request.note or "").strip()},
        error=None if cp.returncode == 0 else f"exit_code:{cp.returncode}",
        result={
            "exit_code": int(cp.returncode),
            "duration_ms": duration_ms,
            "stdout_sha256": out["stdout_sha256"],
            "stderr_sha256": out["stderr_sha256"],
            "stdout_tail_len": len(stdout_tail),
            "stderr_tail_len": len(stderr_tail),
        },
    )
    return {"status": "ok", "result": out}


@api_router.post("/diagnostics/repo/staged/preview")
async def diagnostics_repo_staged_preview(request: RepoStagedPreviewRequest):
    """
    Repo-aware workflow: preview staged changes (git diff --cached) and suggest a commit message.
    Security: read-only git commands only.
    """
    import subprocess
    import hashlib
    from pathlib import Path

    repo_root = str(request.repo_root or "").strip()
    if not repo_root:
        raise HTTPException(status_code=400, detail="repo_root_required")
    p = Path(repo_root)
    if not p.exists() or not p.is_dir():
        raise HTTPException(status_code=404, detail="repo_root_not_found")
    if not (p / ".git").exists():
        raise HTTPException(status_code=400, detail="not_a_git_repo")

    def _run(args: list[str], timeout_s: int = 5) -> str:
        cp = subprocess.run(args, capture_output=True, text=True, timeout=timeout_s)
        if cp.returncode != 0:
            raise RuntimeError((cp.stderr or cp.stdout or "").strip()[:500])
        return (cp.stdout or "").strip()

    staged_numstat = _run(["git", "-C", repo_root, "diff", "--cached", "--numstat"])
    staged_files: list[str] = []
    adds = 0
    dels = 0
    for line in (staged_numstat or "").splitlines():
        parts = line.split("\t")
        if len(parts) < 3:
            continue
        a, d, path = parts[0], parts[1], parts[2]
        staged_files.append(path)
        if a.isdigit():
            adds += int(a)
        if d.isdigit():
            dels += int(d)

    patch = ""
    if bool(request.include_patch):
        patch = _run(["git", "-C", repo_root, "diff", "--cached"], timeout_s=10)
    patch_sha = hashlib.sha256((patch or staged_numstat or "").encode("utf-8")).hexdigest()

    # Simple, deterministic commit message suggestion (no LLM).
    scope = "repo"
    if any(f.startswith("aiPlat-core/") for f in staged_files):
        scope = "core"
    elif any(f.startswith("aiPlat-management/") for f in staged_files):
        scope = "management"
    elif any(f.startswith("docs/") or f.endswith(".md") for f in staged_files):
        scope = "docs"

    subject = ""
    if len(staged_files) == 1:
        subject = f"update {staged_files[0].split('/')[-1]}"
    elif len(staged_files) > 1:
        subject = f"update {len(staged_files)} files"
    else:
        subject = "no staged changes"

    suggested = f"chore({scope}): {subject}"

    out = {
        "repo_root": repo_root,
        "staged": {"files_changed": len(staged_files), "lines_added": adds, "lines_deleted": dels},
        "staged_files": staged_files,
        "patch_sha256": patch_sha,
        "suggested_commit_message": suggested,
    }
    if bool(request.include_patch):
        out["patch"] = patch
        out["patch_len"] = len(patch)
    return out


@api_router.post("/diagnostics/repo/changeset/record")
async def diagnostics_repo_changeset_record(request: RepoChangesetPreviewRequest):
    """
    Record the repo changeset summary as a changeset audit event.
    """
    preview = await diagnostics_repo_changeset_preview(request)
    staged_preview: dict | None = None
    try:
        staged_preview = await diagnostics_repo_staged_preview(
            RepoStagedPreviewRequest(repo_root=request.repo_root, include_patch=False)
        )
    except Exception:
        staged_preview = None

    tests_summary = None
    try:
        if bool(getattr(request, "run_tests", False)):
            tr = await diagnostics_repo_tests_run(RepoTestsRunRequest(repo_root=request.repo_root, note=request.note))
            tests_summary = (tr or {}).get("result") if isinstance(tr, dict) else None
    except Exception as e:
        # If tests failed hard, still record the repo changeset with a failure marker.
        try:
            await _record_changeset(
                name="repo_changeset_record",
                target_type="repo",
                target_id=str(preview.get("repo_root") or ""),
                status="failed",
                args={"branch": preview.get("branch"), "head": preview.get("head"), "note": str(request.note or "").strip()},
                error=f"tests_exception:{type(e).__name__}",
                result={
                    "diff_sha256": preview.get("diff_sha256"),
                    "staged_patch_sha256": (staged_preview or {}).get("patch_sha256") if isinstance(staged_preview, dict) else None,
                    "staged_files_count": len((staged_preview or {}).get("staged_files") or []) if isinstance(staged_preview, dict) else 0,
                    "staged_files_sample": ((staged_preview or {}).get("staged_files") or [])[:20] if isinstance(staged_preview, dict) else [],
                    "tests": {"error": str(e)[:200]},
                },
            )
        except Exception:
            pass
        raise
    try:
        await _record_changeset(
            name="repo_changeset_record",
            target_type="repo",
            target_id=str(preview.get("repo_root") or ""),
            args={"branch": preview.get("branch"), "head": preview.get("head"), "note": str(request.note or "").strip()},
            result={
                "working_tree": preview.get("working_tree"),
                "staged": preview.get("staged"),
                "diff_sha256": preview.get("diff_sha256"),
                "staged_patch_sha256": (staged_preview or {}).get("patch_sha256") if isinstance(staged_preview, dict) else None,
                "staged_files_count": len((staged_preview or {}).get("staged_files") or []) if isinstance(staged_preview, dict) else 0,
                "staged_files_sample": ((staged_preview or {}).get("staged_files") or [])[:20] if isinstance(staged_preview, dict) else [],
                "suggested_commit_message": (staged_preview or {}).get("suggested_commit_message") if isinstance(staged_preview, dict) else None,
                "tests": {
                    "exit_code": (tests_summary or {}).get("exit_code") if isinstance(tests_summary, dict) else None,
                    "duration_ms": (tests_summary or {}).get("duration_ms") if isinstance(tests_summary, dict) else None,
                    "stdout_sha256": (tests_summary or {}).get("stdout_sha256") if isinstance(tests_summary, dict) else None,
                    "stderr_sha256": (tests_summary or {}).get("stderr_sha256") if isinstance(tests_summary, dict) else None,
                }
            },
        )
    except Exception:
        pass
    return {
        "status": "recorded",
        "preview": preview,
        "tests": tests_summary,
        "staged": staged_preview,
    }


# ==================== Health Check ====================

@api_router.get("/health")
async def health_check():
    """Health check endpoint"""
    return {"status": "healthy"}


@api_router.get("/")
async def root():
    """Root endpoint"""
    return {"message": "aiPlat-core API", "version": "0.1.0"}


app.include_router(api_router)


def run_server(host: str = "0.0.0.0", port: int = 8002):
    """Run the server"""
    uvicorn.run(app, host=host, port=port)


if __name__ == "__main__":
    run_server()
