"""
aiPlat-core REST API Server

Provides REST API endpoints for agent, skill, tool, memory, knowledge, and harness management.
Runs on port 8002.
"""

from fastapi import FastAPI, HTTPException, APIRouter
from fastapi.middleware.cors import CORSMiddleware
from typing import Optional, List, Dict, Any
from contextlib import asynccontextmanager
from datetime import datetime
import os
import shutil
import uvicorn

from core.schemas import (
    AgentCreateRequest,
    AgentUpdateRequest,
    SkillCreateRequest,
    SkillExecuteRequest,
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
)
from core.management import (
    AgentManager,
    SkillManager,
    MemoryManager,
    KnowledgeManager,
    AdapterManager,
    HarnessManager,
)
from core.apps.tools.base import ToolRegistry, get_tool_registry, create_tool
from core.apps.tools.permission import PermissionManager, Permission, get_permission_manager
from core.apps.agents import get_agent_registry
from core.apps.skills import get_skill_registry, get_skill_executor
from core.services import get_execution_store
from core.services.trace_service import TraceService, TraceServiceTracer, SpanStatus
from core.harness.integration import get_harness, KernelRuntime
from core.harness.kernel.types import ExecutionRequest


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
        from core.adapters.llm import create_adapter
        return create_adapter(
            provider="openai",
            api_key="",
            model=model_name,
        )
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
    _memory_manager = MemoryManager(seed=True)
    _knowledge_manager = KnowledgeManager()
    _adapter_manager = AdapterManager()
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
    
    yield


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
            config=request.config,
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
async def create_workspace_agent(request: AgentCreateRequest):
    if not _workspace_agent_manager:
        raise HTTPException(status_code=503, detail="Workspace agent manager not available")
    try:
        agent = await _workspace_agent_manager.create_agent(
            name=request.name,
            agent_type=request.agent_type,
            config=request.config,
            skills=request.skills,
            tools=request.tools,
        )
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
        "metadata": agent.metadata,
    }


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
async def update_workspace_agent(agent_id: str, request: AgentUpdateRequest):
    """Update workspace agent."""
    if not _workspace_agent_manager:
        raise HTTPException(status_code=503, detail="Workspace agent manager not available")
    agent = await _workspace_agent_manager.update_agent(agent_id, config=request.config, metadata=request.metadata)
    if not agent:
        raise HTTPException(status_code=404, detail=f"Agent {agent_id} not found")
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
async def execute_workspace_agent(agent_id: str, request: dict):
    """Execute workspace agent."""
    if not _workspace_agent_manager:
        raise HTTPException(status_code=503, detail="Workspace agent manager not available")
    agent = await _workspace_agent_manager.get_agent(agent_id)
    if not agent:
        raise HTTPException(status_code=404, detail=f"Agent {agent_id} not found")
    harness = get_harness()
    exec_req = ExecutionRequest(
        kind="agent",
        target_id=agent_id,
        payload=request or {},
        user_id=(request or {}).get("user_id", "system"),
        session_id=(request or {}).get("session_id", "default"),
    )
    result = await harness.execute(exec_req)
    if not result.ok:
        raise HTTPException(status_code=result.http_status, detail=result.error or "Execution failed")
    return result.payload


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
async def execute_agent(agent_id: str, request: dict):
    """Execute agent"""
    harness = get_harness()
    exec_req = ExecutionRequest(
        kind="agent",
        target_id=agent_id,
        payload=request or {},
        user_id=(request or {}).get("user_id", "system"),
        session_id=(request or {}).get("session_id", "default"),
    )
    result = await harness.execute(exec_req)
    if not result.ok:
        raise HTTPException(status_code=result.http_status, detail=result.error or "Execution failed")
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
    return result.payload


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


@api_router.get("/approvals/{request_id}/audit")
async def get_approval_audit(request_id: str):
    """Return approval + related syscall events + related agent executions."""
    approval = await get_approval_request(request_id)
    return approval


@api_router.post("/approvals/{request_id}/approve")
async def approve_request(request_id: str, request: dict):
    if not _approval_manager:
        raise HTTPException(status_code=503, detail="ApprovalManager not initialized")
    approved_by = (request or {}).get("approved_by", "admin")
    comments = (request or {}).get("comments", "")
    updated = await _approval_manager.approve(request_id=request_id, approved_by=approved_by, comments=comments)
    if not updated:
        raise HTTPException(status_code=404, detail="Approval request not found")
    return {"status": updated.status.value, "request_id": updated.request_id}


@api_router.post("/approvals/{request_id}/reject")
async def reject_request(request_id: str, request: dict):
    if not _approval_manager:
        raise HTTPException(status_code=503, detail="ApprovalManager not initialized")
    rejected_by = (request or {}).get("rejected_by", "admin")
    comments = (request or {}).get("comments", "")
    updated = await _approval_manager.reject(request_id=request_id, rejected_by=rejected_by, comments=comments)
    if not updated:
        raise HTTPException(status_code=404, detail="Approval request not found")
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
    
    result = []
    for s in skills:
        if enabled_only and s.status != "enabled":
            continue
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
    result = []
    for s in skills:
        if enabled_only and s.status != "enabled":
            continue
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
async def create_workspace_skill(request: SkillCreateRequest):
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
        )
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
async def update_workspace_skill(skill_id: str, request: dict):
    if not _workspace_skill_manager:
        raise HTTPException(status_code=503, detail="Workspace skill manager not available")
    from core.schemas import SkillUpdateRequest

    r = SkillUpdateRequest(**(request or {}))
    skill = await _workspace_skill_manager.update_skill(skill_id, r.model_dump(exclude_unset=True))
    if not skill:
        raise HTTPException(status_code=404, detail=f"Skill {skill_id} not found")
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
async def enable_workspace_skill(skill_id: str):
    if not _workspace_skill_manager:
        raise HTTPException(status_code=503, detail="Workspace skill manager not available")
    ok = await _workspace_skill_manager.enable_skill(skill_id)
    if not ok:
        raise HTTPException(status_code=400, detail=f"Skill {skill_id} cannot be enabled (maybe deprecated; use restore)")
    return {"status": "enabled"}


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


@api_router.post("/workspace/skills/{skill_id}/execute")
async def execute_workspace_skill(skill_id: str, request: SkillExecuteRequest):
    """Execute workspace skill."""
    if not _workspace_skill_manager:
        raise HTTPException(status_code=503, detail="Workspace skill manager not available")
    skill = await _workspace_skill_manager.get_skill(skill_id)
    if not skill:
        raise HTTPException(status_code=404, detail=f"Skill {skill_id} not found")
    user_id = request.context.get("user_id", "system") if request.context else "system"
    harness = get_harness()
    exec_req = ExecutionRequest(
        kind="skill",
        target_id=skill_id,
        payload={"input": request.input, "context": request.context or {}, "mode": getattr(request, "mode", "inline")},
        user_id=user_id,
        session_id=(request.context or {}).get("session_id", "default"),
    )
    result = await harness.execute(exec_req)
    if not result.ok:
        raise HTTPException(status_code=result.http_status, detail=result.error or "Execution failed")
    return result.payload


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
                "allowed_tools": s.allowed_tools,
                "metadata": s.metadata,
            }
            for s in _workspace_mcp_manager.list_servers()
        ]
    }


@api_router.post("/workspace/mcp/servers/{server_name}/enable")
async def enable_workspace_mcp_server(server_name: str):
    if not _workspace_mcp_manager:
        raise HTTPException(status_code=503, detail="Workspace MCP manager not available")
    ok = _workspace_mcp_manager.set_enabled(server_name, True)
    if not ok:
        raise HTTPException(status_code=404, detail=f"MCP server {server_name} not found")
    return {"status": "enabled"}


@api_router.post("/workspace/mcp/servers/{server_name}/disable")
async def disable_workspace_mcp_server(server_name: str):
    if not _workspace_mcp_manager:
        raise HTTPException(status_code=503, detail="Workspace MCP manager not available")
    ok = _workspace_mcp_manager.set_enabled(server_name, False)
    if not ok:
        raise HTTPException(status_code=404, detail=f"MCP server {server_name} not found")
    return {"status": "disabled"}


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
async def execute_skill(skill_id: str, request: SkillExecuteRequest):
    """Execute skill"""
    user_id = request.context.get("user_id", "system") if request.context else "system"
    harness = get_harness()
    exec_req = ExecutionRequest(
        kind="skill",
        target_id=skill_id,
        payload={"input": request.input, "context": request.context or {}, "mode": getattr(request, "mode", "inline")},
        user_id=user_id,
        session_id=(request.context or {}).get("session_id", "default"),
    )
    result = await harness.execute(exec_req)
    if not result.ok:
        raise HTTPException(status_code=result.http_status, detail=result.error or "Execution failed")
    return result.payload


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
async def execute_compiled_react_graph(request: dict):
    """
    Execute internal CompiledGraph-based ReAct workflow (checkpoint/callback enabled).

    request:
      - messages: [{role, content}]
      - context: dict
      - max_steps: int
      - checkpoint_interval: int
    """
    harness = get_harness()
    exec_req = ExecutionRequest(
        kind="graph",
        target_id="compiled_react",
        payload=request or {},
        user_id=(request or {}).get("user_id", "system"),
        session_id=(request or {}).get("session_id", "default"),
    )
    result = await harness.execute(exec_req)
    if not result.ok:
        raise HTTPException(status_code=result.http_status, detail=result.error or "Execution failed")
    return result.payload


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
async def list_sessions(limit: int = 100, offset: int = 0):
    """List memory sessions"""
    sessions = await _memory_manager.list_sessions(limit=limit, offset=offset)
    
    result = []
    for s in sessions:
        result.append({
            "session_id": s.id,
            "metadata": s.metadata,
            "created_at": s.created_at.isoformat() if s.created_at else None,
            "updated_at": s.last_activity.isoformat() if s.last_activity else None,
            "message_count": s.message_count
        })
    
    counts = _memory_manager.get_session_count()
    return {
        "sessions": result,
        "total": counts["total"]
    }


@api_router.post("/memory/sessions")
async def create_session(request: SessionCreateRequest):
    """Create memory session"""
    session = await _memory_manager.create_session(
        agent_type=request.metadata.get("agent_type", "default") if request.metadata else "default",
        user_id=request.metadata.get("user_id", "system") if request.metadata else "system",
        session_type=request.metadata.get("session_type", "short_term") if request.metadata else "short_term",
        metadata=request.metadata
    )
    return {"session_id": session.id, "status": "created"}


@api_router.get("/memory/sessions/{session_id}")
async def get_session(session_id: str):
    """Get session details"""
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
        "message_count": len(messages)
    }


@api_router.delete("/memory/sessions/{session_id}")
async def delete_session(session_id: str):
    """Delete session"""
    success = await _memory_manager.delete_session(session_id)
    if not success:
        raise HTTPException(status_code=404, detail=f"Session {session_id} not found")
    return {"status": "deleted", "session_id": session_id}


@api_router.get("/memory/sessions/{session_id}/context")
async def get_session_context(session_id: str):
    """Get session context"""
    context = await _memory_manager.get_context(session_id)
    if not context:
        raise HTTPException(status_code=404, detail=f"Session {session_id} not found")
    return {
        "session_id": session_id,
        "context": {
            "messages": context.get("messages", []),
            "message_count": len(context.get("messages", []))
        }
    }


@api_router.post("/memory/sessions/{session_id}/messages")
async def add_message(session_id: str, request: MessageCreateRequest):
    """Add message to session"""
    session = await _memory_manager.get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail=f"Session {session_id} not found")
    
    message = await _memory_manager.add_message(
        session_id=session_id,
        role=request.role,
        content=request.content,
        metadata=request.metadata
    )
    
    return {
        "status": "added",
        "message": {
            "role": message.role,
            "content": message.content,
            "timestamp": message.created_at.isoformat() if message.created_at else None
        }
    }


@api_router.post("/memory/search")
async def search_memory(request: SearchRequest):
    """Search memory"""
    results = await _memory_manager.search_memory(request.query, request.limit)
    return {"results": results, "total": len(results)}


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
    return {"status": "updated"}


@api_router.delete("/adapters/{adapter_id}")
async def delete_adapter(adapter_id: str):
    """Delete adapter"""
    success = await _adapter_manager.delete_adapter(adapter_id)
    if not success:
        raise HTTPException(status_code=404, detail=f"Adapter {adapter_id} not found")
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
    return {"status": "enabled"}


@api_router.post("/adapters/{adapter_id}/disable")
async def disable_adapter(adapter_id: str):
    """Disable adapter"""
    success = await _adapter_manager.disable_adapter(adapter_id)
    if not success:
        raise HTTPException(status_code=404, detail=f"Adapter {adapter_id} not found")
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
async def list_tools(limit: int = 100, offset: int = 0):
    """List all tools"""
    registry = get_tool_registry()
    tools = registry.list_tools()
    result = []
    for t in tools[offset:offset+limit]:
        tool = registry.get(t)
        info: Dict[str, Any] = {"name": t}
        if tool:
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
            info["status"] = "enabled"
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
async def execute_tool(tool_name: str, request: dict):
    """Execute a tool with given parameters"""
    harness = get_harness()
    exec_req = ExecutionRequest(
        kind="tool",
        target_id=tool_name,
        payload=request or {},
        user_id=(request or {}).get("user_id", "system"),
        session_id=(request or {}).get("session_id", "default"),
    )
    result = await harness.execute(exec_req)
    if not result.ok:
        # keep legacy behavior: return 200 with success=false
        return {"success": False, "error": result.error or "Execution failed", "latency": 0}
    return result.payload


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
