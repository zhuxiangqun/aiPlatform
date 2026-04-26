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
import asyncio
import time
import os
import shutil
from pathlib import Path
import uvicorn

from core.utils.ids import new_prefixed_id
from core.security.rbac import check_permission as rbac_check_permission, should_enforce as rbac_should_enforce
from core.api.deps.rbac import actor_from_http as _actor_from_http_dep, rbac_guard as _rbac_guard_dep
from core.api.utils import governance as _gov

from core.schemas import RunStatus
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
from core.apps.skills import get_skill_registry
from core.apps.plugins.manager import PluginManager
from core.services import get_execution_store
from core.services.trace_service import TraceService, TraceServiceTracer
from core.harness.integration import get_harness, KernelRuntime
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

_skill_executions: Dict[str, Dict[str, Any]] = {}
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
_plugin_manager: Optional[PluginManager] = None
_ops_prune_task: Optional[asyncio.Task] = None


async def _get_trusted_skill_pubkeys_map() -> Dict[str, str]:
    """
    Global trusted public keys for skill signature verification.
    Stored in global_setting: trusted_skill_pubkeys = {"keys":[{"key_id","public_key"}]}
    """
    from core.security.skill_signature_gate import get_trusted_skill_pubkeys_map

    return await get_trusted_skill_pubkeys_map(_execution_store)


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
    from core.security.skill_signature_gate import require_skill_signature_gate_approval

    return await require_skill_signature_gate_approval(
        approval_manager=_approval_manager,
        user_id=user_id,
        skill_id=skill_id,
        action=action,
        details=details,
        metadata=metadata,
    )


def _signature_gate_eval(*, metadata: Optional[Dict[str, Any]], trusted_keys_count: int) -> Dict[str, Any]:
    """
    Determine whether signature gate should trigger.
    Rule: require approval unless signature_verified == True.
    """
    from core.security.skill_signature_gate import signature_gate_eval

    return signature_gate_eval(metadata=metadata, trusted_keys_count=int(trusted_keys_count or 0))


def _reload_workspace_managers() -> None:
    """Deprecated: delegate to core.workspace.reload and sync KernelRuntime (best-effort)."""
    global _workspace_agent_manager, _workspace_skill_manager, _workspace_mcp_manager
    try:
        from core.workspace.reload import rebuild_workspace_managers
        from core.harness.kernel.runtime import get_kernel_runtime

        out = rebuild_workspace_managers(engine_agent_manager=_agent_manager, engine_skill_manager=_skill_manager, engine_mcp_manager=_mcp_manager)
        _workspace_agent_manager = out.get("workspace_agent_manager")
        _workspace_skill_manager = out.get("workspace_skill_manager")
        _workspace_mcp_manager = out.get("workspace_mcp_manager")

        rt = get_kernel_runtime()
        if rt is not None:
            setattr(rt, "workspace_agent_manager", _workspace_agent_manager)
            setattr(rt, "workspace_skill_manager", _workspace_skill_manager)
            setattr(rt, "workspace_mcp_manager", _workspace_mcp_manager)
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
    # Ensure ApprovalManager is store-backed (tests may swap db_path between runs)
    try:
        if _approval_manager is not None:
            setattr(_approval_manager, "_execution_store", _execution_store)
    except Exception:
        pass

    # Canary block auto-action (next-step): when the canary-block approval is approved,
    # automatically mark release_candidate as blocked (non-destructive) and record changeset.
    try:
        if _approval_manager is not None:
            import asyncio
            import time as _time
            from core.harness.canary.escalation import change_id_for_release_candidate

            async def _apply_canary_block_approved(req) -> None:
                try:
                    if not _execution_store:
                        return
                    op = str(getattr(req, "operation", "") or "")
                    meta = getattr(req, "metadata", None) if isinstance(getattr(req, "metadata", None), dict) else {}
                    request_id = str(getattr(req, "request_id", "") or "")
                    details = str(getattr(req, "details", "") or "")
                    now_ts = _time.time()

                    if op == "canary:block_release_candidate":
                        cand_id = str(meta.get("candidate_id") or "").strip()
                        if cand_id:
                            cand = await _execution_store.get_learning_artifact(cand_id)
                            if isinstance(cand, dict) and cand.get("kind") == "release_candidate":
                                md = cand.get("metadata") if isinstance(cand.get("metadata"), dict) else {}
                                md["blocked"] = True
                                md["blocked_via"] = "canary"
                                md["blocked_at"] = now_ts
                                md["blocked_approval_request_id"] = request_id
                                md["blocked_reason"] = details or str(meta.get("recommendation", {}) or "")
                                cand["metadata"] = md
                                await _execution_store.upsert_learning_artifact(cand)
                            # record a change-control event for the candidate stream
                            try:
                                await _execution_store.add_syscall_event(
                                    {
                                        "trace_id": str(meta.get("trace_id") or ""),
                                        "run_id": str(meta.get("run_id") or ""),
                                        "kind": "changeset",
                                        "name": "canary_block_release_candidate_approved",
                                        "status": "blocked",
                                        "args": {"candidate_id": cand_id, "source": "canary"},
                                        "result": {"approval_request_id": request_id, "details": details},
                                        "target_type": "change",
                                        "target_id": change_id_for_release_candidate(cand_id),
                                        "approval_request_id": request_id,
                                        "user_id": str(getattr(req, "user_id", None) or "system"),
                                        "session_id": str(meta.get("session_id") or "default"),
                                        "tenant_id": str(meta.get("project_id") or meta.get("tenant_id") or "") or None,
                                    }
                                )
                            except Exception:
                                pass
                    elif op == "canary:block_repo_changeset":
                        repo_change_id = str(meta.get("repo_change_id") or "").strip()
                        if repo_change_id:
                            try:
                                await _execution_store.add_syscall_event(
                                    {
                                        "trace_id": str(meta.get("trace_id") or ""),
                                        "run_id": str(meta.get("run_id") or ""),
                                        "kind": "changeset",
                                        "name": "canary_block_repo_changeset_approved",
                                        "status": "blocked",
                                        "args": {"repo_change_id": repo_change_id, "source": "canary"},
                                        "result": {"approval_request_id": request_id, "details": details},
                                        "target_type": "change",
                                        "target_id": repo_change_id,
                                        "approval_request_id": request_id,
                                        "user_id": str(getattr(req, "user_id", None) or "system"),
                                        "session_id": str(meta.get("session_id") or "default"),
                                        "tenant_id": str(meta.get("project_id") or meta.get("tenant_id") or "") or None,
                                    }
                                )
                            except Exception:
                                pass
                except Exception:
                    return

            def _on_approved(req) -> None:
                try:
                    asyncio.create_task(_apply_canary_block_approved(req))
                except Exception:
                    pass

            _approval_manager.register_callback("on_approved", _on_approved)
    except Exception:
        pass
    # Plugins
    try:
        global _plugin_manager
        _plugin_manager = PluginManager(execution_store=_execution_store)
    except Exception:
        _plugin_manager = None

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
                # P0-1: carry contract fields (schema/permissions/risk/approval) and SOP body into registry
                meta = {
                    "category": getattr(discovered, "category", "general"),
                    "version": getattr(discovered, "version", "1.0.0"),
                    "trigger_conditions": getattr(discovered, "trigger_conditions", []) or getattr(discovered, "trigger_keywords", []) or [],
                    "permissions": getattr(discovered, "permissions", []) or [],
                    "sop_markdown": getattr(discovered, "sop_markdown", "") or "",
                    # default posture for discovered SKILL.md skills
                    "skill_kind": str(getattr(discovered, "skill_kind", None) or "rule"),
                    "filesystem": {
                        "skill_dir": getattr(discovered, "skill_dir", None),
                        "skill_md": getattr(discovered, "skill_md_path", None),
                        "references_dir": getattr(discovered, "references_path", None),
                        "scripts_dir": getattr(discovered, "scripts_path", None),
                    },
                }
                # Optional governance fields
                if getattr(discovered, "auto_trigger_allowed", None) is not None:
                    meta["auto_trigger_allowed"] = bool(getattr(discovered, "auto_trigger_allowed"))
                if getattr(discovered, "requires_approval", None) is not None:
                    meta["requires_approval"] = bool(getattr(discovered, "requires_approval"))
                if getattr(discovered, "risk_level", None) is not None:
                    meta["risk_level"] = str(getattr(discovered, "risk_level"))

                # If handler.py exists and provides build_skill(), prefer registering the real implementation.
                handler_mod = None
                try:
                    handler_mod = _skill_discovery.load_handler(discovered)
                except Exception:
                    handler_mod = None
                if handler_mod is not None and hasattr(handler_mod, "build_skill"):
                    try:
                        build_fn = getattr(handler_mod, "build_skill")
                        skill_obj = None
                        try:
                            skill_obj = build_fn(discovered)
                        except TypeError:
                            skill_obj = build_fn()
                        if skill_obj is not None:
                            # Best-effort: merge discovered metadata (filesystem/SOP/permissions) into skill config.
                            try:
                                cfg0 = getattr(skill_obj, "_config", None) or (skill_obj.get_config() if hasattr(skill_obj, "get_config") else None)
                                if cfg0 is not None:
                                    m0 = dict(getattr(cfg0, "metadata", {}) or {})
                                    for k, v in meta.items():
                                        m0.setdefault(k, v)
                                    m0.setdefault("impl", "handler")
                                    setattr(cfg0, "metadata", m0)
                            except Exception:
                                pass
                            skill_registry.register(skill_obj)
                            continue
                    except Exception:
                        pass
                config = SkillConfig(
                    name=skill_name,
                    description=getattr(discovered, 'description', ''),
                    input_schema=getattr(discovered, "input_schema", {}) or {},
                    output_schema=getattr(discovered, "output_schema", {}) or {},
                    metadata=meta,
                )
                skill_instance = _GenericSkill(config)
                try:
                    config.metadata = dict(config.metadata or {})
                    config.metadata.setdefault("impl", "generic")
                except Exception:
                    pass
                skill_registry.register(skill_instance)
            except Exception:
                pass
        # Second pass: if handler-based implementation exists, prefer it (override generic fallback).
        # This also makes handler loading more robust in environments with import-order quirks.
        for skill_name, discovered in _skill_discovery._discovered.items():
            try:
                handler_mod = None
                try:
                    handler_mod = _skill_discovery.load_handler(discovered)
                except Exception:
                    handler_mod = None
                if handler_mod is None or not hasattr(handler_mod, "build_skill"):
                    continue
                cur = skill_registry.get(skill_name)
                if cur is not None and cur.__class__.__name__ != "_GenericSkill":
                    continue
                build_fn = getattr(handler_mod, "build_skill")
                try:
                    skill_obj = build_fn(discovered)
                except TypeError:
                    skill_obj = build_fn()
                if skill_obj is None:
                    continue
                # Merge discovered meta into handler config (same as first pass)
                try:
                    cfg0 = getattr(skill_obj, "_config", None) or (skill_obj.get_config() if hasattr(skill_obj, "get_config") else None)
                    if cfg0 is not None:
                        m0 = dict(getattr(cfg0, "metadata", {}) or {})
                        # Use the same meta fields as above (best-effort)
                        m0.setdefault("category", getattr(discovered, "category", "general"))
                        m0.setdefault("version", getattr(discovered, "version", "1.0.0"))
                        m0.setdefault("trigger_conditions", getattr(discovered, "trigger_conditions", []) or getattr(discovered, "trigger_keywords", []) or [])
                        m0.setdefault("permissions", getattr(discovered, "permissions", []) or [])
                        m0.setdefault("filesystem", {
                            "skill_dir": getattr(discovered, "skill_dir", None),
                            "skill_md": getattr(discovered, "skill_md_path", None),
                            "references_dir": getattr(discovered, "references_path", None),
                            "scripts_dir": getattr(discovered, "scripts_path", None),
                        })
                        m0.setdefault("impl", "handler")
                        setattr(cfg0, "metadata", m0)
                except Exception:
                    pass
                skill_registry.register(skill_obj)
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
    # NOTE: tool_search is used to discover tools on-demand when tool list is large.
    for tool_type in ["calculator", "search", "tool_search", "file_operations"]:
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
        ("core.apps.tools.repo", "RepoTool", {"timeout": 20000}),
        # OpenCode-style skills (discover + lazy load)
        ("core.apps.tools.skill_tools", "SkillFindTool", {}),
        ("core.apps.tools.skill_tools", "SkillLoadTool", {}),
        # P1-3: guarded script runner for skill scripts/
        ("core.apps.tools.skill_script_tools", "SkillRunScriptTool", {"timeout": 20000}),
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
    try:
        from core.mcp.runtime_sync import sync_mcp_runtime

        await sync_mcp_runtime(mcp_manager=_mcp_manager, workspace_mcp_manager=_workspace_mcp_manager)
    except Exception:
        pass

    # Phase-1: wire application runtime into HarnessIntegration (single entry execute)
    try:
        from core.harness.kernel.runtime import set_kernel_runtime

        harness = get_harness()
        rt = KernelRuntime(
            agent_manager=_agent_manager,
            skill_manager=_skill_manager,
            workspace_agent_manager=_workspace_agent_manager,
            workspace_skill_manager=_workspace_skill_manager,
            workspace_mcp_manager=_workspace_mcp_manager,
            mcp_manager=_mcp_manager,
            harness=harness,
            execution_store=_execution_store,
            trace_service=_trace_service,
            approval_manager=_approval_manager,
            plugin_manager=_plugin_manager,
            package_manager=_package_manager,
            workspace_package_manager=_workspace_package_manager,
            memory_manager=_memory_manager,
            knowledge_manager=_knowledge_manager,
            adapter_manager=_adapter_manager,
            harness_manager=_harness_manager,
        )
        # Make runtime available to syscalls / API routers via core.harness.kernel.runtime.get_kernel_runtime().
        set_kernel_runtime(rt)
        # Keep legacy behavior: also attach to harness when supported.
        if hasattr(harness, "attach_runtime"):
            harness.attach_runtime(rt)
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

            # Skill lint-scan cron (opt-out; graded enforcement is on enable, cron is for observability)
            try:
                enable_lint_cron = os.getenv("AIPLAT_ENABLE_SKILL_LINT_CRON", "true").lower() in ("1", "true", "yes", "y")
                if enable_lint_cron:
                    from core.management.job_scheduler import next_run_from_cron

                    job_id = "cron-skill-lint-scan"
                    cron = (os.getenv("AIPLAT_SKILL_LINT_CRON", "0 * * * *") or "0 * * * *").strip()
                    scopes_raw = (os.getenv("AIPLAT_SKILL_LINT_SCOPES", "workspace") or "workspace").strip()
                    scopes = [x.strip() for x in scopes_raw.split(",") if x.strip()]
                    now = time.time()
                    rec = await _execution_store.get_job(job_id)
                    patch = {
                        "name": "Skill Lint Scan",
                        "enabled": True,
                        "cron": cron,
                        "kind": "skill_lint_scan",
                        "target_id": "skill_lint_scan",
                        "user_id": "system",
                        "session_id": "ops",
                        "payload": {"scopes": scopes, "tenant_id": "ops", "actor_id": "system", "job_id": job_id, "cron": cron},
                        "next_run_at": next_run_from_cron(cron, from_ts=now),
                        "updated_at": now,
                    }
                    if rec is None:
                        await _execution_store.create_job({"id": job_id, "created_at": now, **patch})
                    else:
                        await _execution_store.update_job(job_id, patch)
            except Exception:
                pass
    except Exception:
        _job_scheduler = None

    # Update runtime in-place now that job_scheduler is available.
    try:
        from core.harness.kernel.runtime import get_kernel_runtime

        rt = get_kernel_runtime()
        if rt is not None:
            setattr(rt, "job_scheduler", _job_scheduler)
    except Exception:
        pass

    # PR-14: background retention pruning loop (opt-in)
    global _ops_prune_task
    try:
        enable_prune = os.getenv("AIPLAT_ENABLE_PRUNE_SCHEDULER", "false").lower() in ("1", "true", "yes", "y")
        interval = float(os.getenv("AIPLAT_PRUNE_INTERVAL_SECONDS", "3600") or "3600")
        if enable_prune and _execution_store is not None and interval > 0:
            async def _prune_loop():
                while True:
                    try:
                        await asyncio.sleep(interval)
                        await _execution_store.prune()
                    except asyncio.CancelledError:
                        raise
                    except Exception:
                        # best-effort: never crash the server due to pruning
                        continue

            _ops_prune_task = asyncio.create_task(_prune_loop())
    except Exception:
        _ops_prune_task = None

    # Phase 6.x: Learning metrics snapshot + optional auto-rollback loop (opt-in)
    global _learning_task
    try:
        enable_learning = os.getenv("AIPLAT_ENABLE_LEARNING_SCHEDULER", "false").lower() in ("1", "true", "yes", "y")
        interval = float(os.getenv("AIPLAT_LEARNING_INTERVAL_SECONDS", "600") or "600")
        enable_autorollback = os.getenv("AIPLAT_ENABLE_LEARNING_AUTOROLLBACK", "false").lower() in ("1", "true", "yes", "y")
        require_rb_approval = os.getenv("AIPLAT_LEARNING_AUTOROLLBACK_REQUIRE_APPROVAL", "true").lower() in ("1", "true", "yes", "y")
        if enable_learning and _execution_store is not None and interval > 0:
            from core.learning.autorollback import auto_rollback_regression, compute_exec_metrics

            async def _learning_loop():
                while True:
                    try:
                        await asyncio.sleep(interval)
                        # NOTE: multi-tenant support can be added by enumerating tenants; current default treats "" as tenant.
                        tenant_id = ""
                        rollouts = await _execution_store.list_release_rollouts(tenant_id=tenant_id, target_type="agent", limit=200, offset=0)
                        for ro in (rollouts.get("items") or []):
                            if not isinstance(ro, dict) or not ro.get("enabled"):
                                continue
                            agent_id = str(ro.get("target_id") or "")
                            candidate_id = str(ro.get("candidate_id") or "")
                            if not agent_id or not candidate_id:
                                continue
                            hist, _total = await _execution_store.list_agent_history(agent_id, limit=200, offset=0)
                            # Filter to runs that actually used this candidate (by run metadata.active_release.candidate_id)
                            rows = []
                            for r in hist:
                                meta = r.get("metadata") if isinstance(r.get("metadata"), dict) else {}
                                ar = meta.get("active_release") if isinstance(meta.get("active_release"), dict) else {}
                                cid = ar.get("candidate_id")
                                if cid == candidate_id:
                                    rows.append(r)
                                if len(rows) >= 50:
                                    break
                            m = compute_exec_metrics(rows)
                            if m.get("error_rate") is None:
                                continue
                            er = float(m.get("error_rate") or 0.0)
                            sr = 1.0 - er
                            dur = m.get("avg_duration_ms")
                            await _execution_store.add_release_metric_snapshot(
                                tenant_id=tenant_id,
                                candidate_id=candidate_id,
                                metric_key="error_rate",
                                value=float(er),
                                metadata={"source": "learning_scheduler", "samples": m.get("samples")},
                            )
                            await _execution_store.add_release_metric_snapshot(
                                tenant_id=tenant_id,
                                candidate_id=candidate_id,
                                metric_key="success_rate",
                                value=float(sr),
                                metadata={"source": "learning_scheduler", "samples": m.get("samples")},
                            )
                            if dur is not None:
                                await _execution_store.add_release_metric_snapshot(
                                    tenant_id=tenant_id,
                                    candidate_id=candidate_id,
                                    metric_key="avg_duration_ms",
                                    value=float(dur),
                                    metadata={"source": "learning_scheduler", "samples": m.get("samples")},
                                )
                            # Optional: auto-rollback by regression (best-effort; non-blocking)
                            if enable_autorollback and _approval_manager is not None:
                                try:
                                    await auto_rollback_regression(
                                        store=_execution_store,
                                        approval_manager=_approval_manager,
                                        agent_id=agent_id,
                                        candidate_id=candidate_id,
                                        require_approval=require_rb_approval,
                                        user_id="learning_scheduler",
                                        dry_run=False,
                                    )
                                except Exception:
                                    pass
                    except asyncio.CancelledError:
                        raise
                    except Exception:
                        # best-effort: never crash server due to learning loop
                        continue

            _learning_task = asyncio.create_task(_learning_loop())
    except Exception:
        _learning_task = None
    
    yield

    # Shutdown background services
    try:
        if _job_scheduler is not None:
            await _job_scheduler.stop()
    except Exception:
        pass
    try:
        if _ops_prune_task is not None:
            _ops_prune_task.cancel()
    except Exception:
        pass
    try:
        if _learning_task is not None:
            _learning_task.cancel()
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

# Incremental router split: routing observability endpoints live in a dedicated module.
from core.api.routers.routing_observability import router as routing_observability_router  # noqa: E402
from core.api.routers.approvals import router as approvals_router  # noqa: E402
from core.api.routers.change_control import router as change_control_router  # noqa: E402
from core.api.routers.autosmoke import router as autosmoke_router  # noqa: E402
from core.api.routers.learning_releases import router as learning_releases_router  # noqa: E402
from core.api.routers.plugins import router as plugins_router  # noqa: E402
from core.api.routers.learning_autocapture import router as learning_autocapture_router  # noqa: E402
from core.api.routers.mcp_admin import router as mcp_admin_router  # noqa: E402
from core.api.routers.workspace_packages import router as workspace_packages_router  # noqa: E402
from core.api.routers.workspace_skills import router as workspace_skills_router  # noqa: E402
from core.api.routers.workspace_skills_meta import router as workspace_skills_meta_router  # noqa: E402
from core.api.routers.engine_skills import router as engine_skills_router  # noqa: E402
from core.api.routers.skill_packs import router as skill_packs_router  # noqa: E402
from core.api.routers.packages_registry import router as packages_registry_router  # noqa: E402
from core.api.routers.onboarding import router as onboarding_router  # noqa: E402
from core.api.routers.jobs import router as jobs_router  # noqa: E402
from core.api.routers.diagnostics import router as diagnostics_router  # noqa: E402
from core.api.routers.diagnostics_repo import router as diagnostics_repo_router  # noqa: E402
from core.api.routers.prompt_templates import router as prompt_templates_router  # noqa: E402
from core.api.routers.personas import router as personas_router  # noqa: E402
from core.api.routers.skill_evals import router as skill_evals_router  # noqa: E402
from core.api.routers.agents import router as agents_router  # noqa: E402
from core.api.routers.workspace_agents import router as workspace_agents_router  # noqa: E402
from core.api.routers.syscalls import router as syscalls_router  # noqa: E402
from core.api.routers.runs import router as runs_router  # noqa: E402
from core.api.routers.traces_graphs import router as traces_graphs_router  # noqa: E402
from core.api.routers.audit_ops_export import router as audit_ops_export_router  # noqa: E402
from core.api.routers.policy import router as policy_router  # noqa: E402
from core.api.routers.tenant_policies import router as tenant_policies_router  # noqa: E402
from core.api.routers.quota import router as quota_router  # noqa: E402
from core.api.routers.permissions import router as permissions_router  # noqa: E402
from core.api.routers.memory import router as memory_router  # noqa: E402
from core.api.routers.knowledge import router as knowledge_router  # noqa: E402
from core.api.routers.adapters import router as adapters_router  # noqa: E402
from core.api.routers.harness_admin import router as harness_admin_router  # noqa: E402
from core.api.routers.evaluation_policies import router as evaluation_policies_router  # noqa: E402
from core.api.routers.learning_misc import router as learning_misc_router  # noqa: E402
from core.api.routers.tools import router as tools_router  # noqa: E402
from core.api.routers.executions_trace import router as executions_trace_router  # noqa: E402
from core.api.routers.gateway import router as gateway_router  # noqa: E402
from core.api.routers.channel_adapters import router as channel_adapters_router  # noqa: E402
from core.api.routers.catalog import router as catalog_router  # noqa: E402
from core.api.routers.gate_policies import router as gate_policies_router  # noqa: E402
from core.api.routers.code_intel import router as code_intel_router  # noqa: E402
from core.api.routers.health import router as health_router  # noqa: E402
from core.api.routers.ops_exports import router as ops_exports_router  # noqa: E402
from core.api.routers.root import router as root_router  # noqa: E402

api_router.include_router(routing_observability_router)
api_router.include_router(approvals_router)
api_router.include_router(change_control_router)
api_router.include_router(autosmoke_router)
api_router.include_router(learning_releases_router)
api_router.include_router(plugins_router)
api_router.include_router(learning_autocapture_router)
api_router.include_router(mcp_admin_router)
api_router.include_router(workspace_packages_router)
api_router.include_router(workspace_skills_router)
api_router.include_router(workspace_skills_meta_router)
api_router.include_router(engine_skills_router)
api_router.include_router(skill_packs_router)
api_router.include_router(packages_registry_router)
api_router.include_router(onboarding_router)
api_router.include_router(jobs_router)
api_router.include_router(diagnostics_router)
api_router.include_router(diagnostics_repo_router)
api_router.include_router(prompt_templates_router)
api_router.include_router(personas_router)
api_router.include_router(skill_evals_router)
api_router.include_router(agents_router)
api_router.include_router(workspace_agents_router)
api_router.include_router(syscalls_router)
api_router.include_router(runs_router)
api_router.include_router(traces_graphs_router)
api_router.include_router(audit_ops_export_router)
api_router.include_router(policy_router)
api_router.include_router(tenant_policies_router)
api_router.include_router(quota_router)
api_router.include_router(permissions_router)
api_router.include_router(memory_router)
api_router.include_router(knowledge_router)
api_router.include_router(adapters_router)
api_router.include_router(harness_admin_router)
api_router.include_router(evaluation_policies_router)
api_router.include_router(learning_misc_router)
api_router.include_router(tools_router)
api_router.include_router(executions_trace_router)
api_router.include_router(gateway_router)
api_router.include_router(channel_adapters_router)
api_router.include_router(catalog_router)
api_router.include_router(gate_policies_router)
api_router.include_router(code_intel_router)
api_router.include_router(health_router)
api_router.include_router(ops_exports_router)
api_router.include_router(root_router)


def _runtime_env() -> str:
    """Runtime environment string for policy gates (dev/staging/prod)."""
    from core.mcp.prod_policy import runtime_env

    return runtime_env()


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
    return _actor_from_http_dep(http_request, payload)


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
    return await _rbac_guard_dep(
        http_request=http_request,
        payload=payload,
        action=action,
        resource_type=resource_type,
        resource_id=resource_id,
        run_id=run_id,
    )


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
    trace_id: str | None = None,
    run_id: str | None = None,
    user_id: str = "admin",
    session_id: str | None = None,
    approval_request_id: str | None = None,
    tenant_id: str | None = None,
) -> None:
    from core.governance.changeset import record_changeset

    return await record_changeset(
        store=_execution_store,
        name=name,
        target_type=target_type,
        target_id=target_id,
        status=status,
        args=args,
        result=result,
        error=error,
        trace_id=trace_id,
        run_id=run_id,
        user_id=user_id,
        session_id=session_id,
        approval_request_id=approval_request_id,
        tenant_id=tenant_id,
    )


def _new_change_id() -> str:
    return f"chg-{uuid.uuid4().hex[:12]}"


def _governance_links(
    *,
    change_id: str | None = None,
    approval_request_id: str | None = None,
    run_id: str | None = None,
    trace_id: str | None = None,
) -> Dict[str, Any]:
    return _gov.governance_links(
        change_id=str(change_id) if change_id else None,
        approval_request_id=str(approval_request_id) if approval_request_id else None,
        run_id=str(run_id) if run_id else None,
        trace_id=str(trace_id) if trace_id else None,
    )


def _change_links(change_id: str) -> Dict[str, Any]:
    return _gov.change_links(str(change_id))


def _is_approval_resolved_approved(approval_request_id: str) -> bool:
    """
    仅用于仍在 server.py 内的少量遗留端点（例如 signature gate）。
    Router 化的模块应各自通过 KernelRuntime.approval_manager 判断。
    """
    if not approval_request_id or not _approval_manager:
        return False
    from core.harness.infrastructure.approval.types import RequestStatus

    r = _approval_manager.get_request(str(approval_request_id))
    if not r:
        return False
    return r.status in (RequestStatus.APPROVED, RequestStatus.AUTO_APPROVED)


# ==================== Permission Management ====================
#
# Moved to: core.api.routers.permissions


# ==================== Agent / Workspace Agent Endpoints ====================
#
# Moved to:
# - core.api.routers.agents (engine scope: /agents*)
# - core.api.routers.workspace_agents (workspace scope: /workspace/agents*)
#
# ==================== Remaining Endpoints ====================
#
# All API endpoints have been moved to `core.api.routers.*`.
#
# `core/server.py` is now responsible only for:
# - constructing FastAPI app
# - wiring runtime dependencies (KernelRuntime)
# - including routers


# ==================== Skill Management ====================
#
# Engine scope (/skills*) endpoints are implemented in core.api.routers.engine_skills
#
# Workspace scope (/workspace/skills/meta/*, /workspace/skills/installer/*, /workspace/skills/governance-preview)
# endpoints are implemented in core.api.routers.workspace_skills_meta


# ==================== Trace / Graph Persistence ====================
#
# Moved to: core.api.routers.executions_trace


# ==================== Memory / Knowledge / Adapters / Harness ====================
#
# Moved to:
# - core.api.routers.memory
# - core.api.routers.knowledge
# - core.api.routers.adapters
# - core.api.routers.harness_admin


# /tools* endpoints moved to core.api.routers.tools


# ==================== Gateway / Channels (Roadmap-3) ====================
#
# Moved to: core.api.routers.gateway


# (migrated) Remaining /gateway/* endpoints moved to core.api.routers.gateway


# ==================== Skill Packs + Long-term Memory (Roadmap-4 minimal) ====================
#
# Moved to: core.api.routers.skill_packs


# /memory/longterm* endpoints moved to core.api.routers.memory

# ==================== Health Check ====================
#
# Moved to: core.api.routers.health


# ==================== Ops: Export / Retention (PR-14) ====================
#
# Moved to: core.api.routers.ops_exports
#
# Root endpoint moved to: core.api.routers.root


app.include_router(api_router)


def run_server(host: str = "0.0.0.0", port: int = 8002):
    """Run the server"""
    uvicorn.run(app, host=host, port=port)


if __name__ == "__main__":
    run_server()
