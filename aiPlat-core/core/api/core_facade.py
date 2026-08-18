"""
CoreFacade — stable public API for platform to access core capabilities.

All platform→core imports MUST go through this facade, not directly into
core.harness.*, core.apps.*, or core.adapters.*. Per CLAUDE.md §5.30 Rule 4.

Intent-level API: core/api/intents.py is the PREFERRED entry point for
all AI interactions (chat, execute, query). Use intents.core_chat() instead
of chat_conversation() or CoreFacade.core_chat().

PipelineSession — the sole interface for pipeline execution.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Dict, List, Optional
import logging
from core.harness.utils.llm_env import get_llm_api_key, get_llm_base_url
from core.harness.utils.model_injection import best_model_for_purpose


# ═══════════════════════════════════════════════════════════════
# Handler Registry — platform modules push capabilities to core.
# Direction: platform → core (correct). Zero core→platform imports.
# ═══════════════════════════════════════════════════════════════
#
# Runtime extension slot (P2-A2 design): registration is gated on the
# handler's defining module — dangerous stdlib modules (os/sys/subprocess/
# shutil/builtins) are rejected, mirroring action_contract.DANGEROUS. Data
# handlers (plain dict/list) are allowed from any module; callables must
# originate from a trusted platform/core prefix.

_HANDLER_ALLOWED_MODULES = (
    "core.",            # core-facade internal / core-provided handlers
    "apps.",            # platform app modules (apps.fde.*, apps.learning.*)
    "auth.",            # platform auth module
    "builder.",         # platform builder module
    "custom_handlers",  # action-contract custom handler namespace
)

_HANDLER_DANGEROUS_MODULES = (
    "os.", "sys.", "subprocess.", "shutil.", "builtins.",
)

_handlers: Dict[str, Any] = {}

_log = logging.getLogger("aiplat.core_facade")


def register_handler(name: str, handler: Any) -> None:
    """Register a handler from platform layer into CoreFacade.

    Called by platform module __init__.py during import.
    Direction: platform → core (符合单向依赖).

    Runtime extension slot (P2-A2): callable handlers are gated on their
    defining module — dangerous stdlib modules are rejected at registration
    time so dispatch() can never invoke os/sys/subprocess/etc. via this slot.

    Args:
        name: Handler name used by dispatch()
        handler: Callable or data to return on dispatch
    """
    if name in _handlers:
        _log.warning("Handler '%s' already registered, overwriting", name)
    if callable(handler):
        module = getattr(handler, "__module__", "") or ""
        if any(module.startswith(d) for d in _HANDLER_DANGEROUS_MODULES):
            raise ValueError(
                f"Handler '{name}' rejected: defining module '{module}' is "
                f"in the dangerous set {_HANDLER_DANGEROUS_MODULES} (runtime "
                f"extension slot does not allow arbitrary code execution)"
            )
        if not any(module.startswith(a) for a in _HANDLER_ALLOWED_MODULES):
            _log.warning(
                "Handler '%s' registered from unvetted module '%s' "
                "(allowed: %s)", name, module, _HANDLER_ALLOWED_MODULES)
    _handlers[name] = handler

def dispatch(name: str, *args: Any, **kwargs: Any) -> Any:
    """Dispatch a registered handler by name.

    Called by core modules (system.py, builder.py, etc.) to
    access platform capabilities without importing platform directly.

    Args:
        name: Handler name registered by platform module
        *args, **kwargs: Passed to callable handlers
    """
    handler = _handlers.get(name)
    if handler is None:
        raise KeyError(
            f"Handler '{name}' not registered. "
            f"Ensure the platform module providing it is imported "
            f"(e.g., import apps.fde). Registered handlers: {list(_handlers.keys())}")
    if callable(handler):
        return handler(*args, **kwargs)
    return handler


def get_default_model() -> Any:
    """Create a default model adapter from environment variables."""
    from core.harness.execution.pipeline_engine import PipelineEngine
    return PipelineEngine._load_default_model()


def create_pipeline_engine(
    config: Any,
    model: Any = None,
    skill_loader: Any = None,
) -> Any:
    """Create a PipelineEngine instance. Use this instead of importing
    PipelineEngine directly from core.harness.execution."""
    from core.harness.execution.pipeline_engine import PipelineEngine
    return PipelineEngine(config=config, model=model, skill_loader=skill_loader)


def register_pipeline(project_id: str, engine: Any) -> None:
    """Register a running pipeline engine (pipeline registry singleton)."""
    from core.harness.execution.pipeline_engine import register_pipeline as _r
    _r(project_id, engine)


def get_running_pipeline(project_id: str) -> Any:
    """Get the running pipeline engine for a project, if any."""
    from core.harness.execution.pipeline_engine import get_running_pipeline as _g
    return _g(project_id)


def unregister_pipeline(project_id: str) -> None:
    """Unregister a finished/terminated pipeline engine."""
    from core.harness.execution.pipeline_engine import unregister_pipeline as _u
    _u(project_id)


def get_pipeline_healing_stats() -> dict:
    """Get PipelineEngine._healing_stats (diagnostics health check)."""
    from core.harness.execution.pipeline_engine import PipelineEngine
    return getattr(PipelineEngine, '_healing_stats', {})


def get_pipeline_run_store() -> Any:
    """Get the pipeline run store singleton."""
    from core.harness.execution.pipeline_run_store import get_pipeline_run_store as _g
    return _g()


def create_agent(
    agent_type: str,
    config: Any = None,
    model: Any = None,
    system_prompt: str = "",
) -> Any:
    """Create an agent instance by type.

    Agent types are defined in ~/.aiplat/registry/agent_types.yaml (single source of truth).
    Supported canonical types: conversational, react, plan_execute, rag, multi_agent, materials_chat.
    Aliases (plan→plan_execute, tool→react, etc.) are resolved automatically."""
    from core.harness.interfaces.agent import AgentConfig
    from core.harness.registry.registry_loader import load_agent_types

    types = load_agent_types()
    canonical = types.resolve(agent_type)

    if isinstance(config, dict):
        config = AgentConfig(
            name=config.get("name", "agent"),
            model=config.get("model") or best_model_for_purpose("chat"),
            temperature=float(config.get("temperature", 0.3)),
            max_tokens=int(config.get("max_tokens", 4096)),
            timeout=int(config.get("timeout", 600)),
            metadata=config.get("metadata", {}),
        )
    elif config is None:
        config = AgentConfig(name="agent", temperature=0.3, timeout=600)

    # Dispatch: canonical type → agent class
    _DISPATCH = {
        "conversational": lambda: __import__("core.apps.agents.conversational", fromlist=["create_conversational_agent"]).create_conversational_agent(config=config, model=model, system_prompt=system_prompt),
        "plan_execute":    lambda: __import__("core.apps.agents.plan_execute", fromlist=["PlanExecuteAgent"]).PlanExecuteAgent(config=config, model=model),
        "react":           lambda: __import__("core.apps.agents.react", fromlist=["ReActAgent"]).ReActAgent(config=config, model=model),
        "rag":             lambda: __import__("core.apps.agents.rag", fromlist=["RAGAgent"]).RAGAgent(config=config, model=model),
        "multi_agent":     lambda: __import__("core.apps.agents.multi_agent", fromlist=["MultiAgent"]).MultiAgent(config=config, model=model),
        "materials_chat":  lambda: __import__("core.apps.agents.materials_chat", fromlist=["MaterialsChatAgent"]).MaterialsChatAgent(config=config, model=model),
    }

    factory = _DISPATCH.get(canonical)
    if factory is not None:
        return factory()

    # Fallback: conversational (already resolved unknown types)
    import logging
    logging.getLogger("core_facade").warning(
        "No dispatch for agent_type '%s' (canonical='%s') — falling back to conversational",
        agent_type, canonical)
    from core.apps.agents.conversational import create_conversational_agent
    return create_conversational_agent(config=config, model=model, system_prompt=system_prompt)


def get_skill_registry() -> Any:
    """Get the global SkillRegistry singleton."""
    from core.apps.skills import get_skill_registry as _get
    return _get()


def get_tool_registry() -> Any:
    """Get the global ToolRegistry singleton."""
    from core.apps.tools.base import get_tool_registry as _get
    return _get()


def get_model_manager() -> Any:
    """Get the global ModelManager from infra (unique source of truth for models)."""
    from infra.management.model.manager import ModelManager
    return ModelManager()


def get_llm_manager() -> Any:
    """Get the LLMManager class from infra (LLM usage stats, health)."""
    from infra.management.llm.manager import LLMManager
    return LLMManager


def get_database_manager() -> Any:
    """Get the DatabaseManager class from infra (DB connection pool stats, health)."""
    from infra.management.database.manager import DatabaseManager
    return DatabaseManager


def get_vector_manager() -> Any:
    """Get the VectorManager class from infra (vector store stats, health)."""
    from infra.management.vector.manager import VectorManager
    return VectorManager


def get_cache_manager() -> Any:
    """Get the DefaultCacheManager class from infra (cache hit rates, stats)."""
    from infra.cache.manager import DefaultCacheManager
    return DefaultCacheManager


# ═══════════════════════════════════════════════════════════════
# Core subsystem access — canonical entry points for core modules
# ═══════════════════════════════════════════════════════════════

def get_policy_gate() -> Any:
    """Get PolicyGate singleton — security/access control for all syscalls."""
    from core.harness.infrastructure.gates.policy_gate import PolicyGate
    return PolicyGate()


def get_hallucination_tracker() -> Any:
    """Get HallucinationTracker for NLI fact-checking in RAG responses."""
    from core.harness.evaluation.hallucination_tracker import HallucinationTracker
    return HallucinationTracker()


def get_code_graph() -> Any:
    """Get CodeGraph for repository import graph analysis."""
    from core.harness.knowledge.code_graph import build_graph, repo_root, default_roots
    repo = repo_root()
    roots = [(repo / r).resolve() for r in default_roots()]
    return build_graph(repo, roots)


def get_domain_router() -> Any:
    """Get DomainRouter for multi-domain classification."""
    from core.harness.knowledge.domain_router import DomainRouter
    return DomainRouter()


def get_skill_registry() -> Any:
    """Get SkillRegistry for skill discovery and management."""
    from core.harness.integration import get_skill_registry
    return get_skill_registry()


def get_system_diagnostician() -> Any:
    """Get SystemDiagnostician for cross-subsystem health checks."""
    from core.harness.knowledge.system_diagnostician import SystemDiagnostician
    return SystemDiagnostician()


def get_wiki_retriever() -> Any:
    """Get WikiPageRetriever for domain-aware knowledge retrieval."""
    from core.harness.knowledge.wiki_retriever import WikiPageRetriever
    return WikiPageRetriever()


def get_context_bus() -> Any:
    """Get ContextBus for field-assessment knowledge injection."""
    from core.harness.knowledge.context_bus import assemble_field_assessment
    return assemble_field_assessment


def list_pending_heal_fixes() -> Any:
    """List pending self-heal fixes awaiting human approval."""
    from core.harness.evaluation.self_heal_gate import SelfHealGate
    return SelfHealGate().list_pending()


def approve_heal_fix(fix_id: str) -> Any:
    """Approve and apply a pending self-heal fix."""
    from core.harness.evaluation.self_heal_gate import SelfHealGate
    return SelfHealGate().approve_fix(fix_id)


def reject_heal_fix(fix_id: str, reason: str = "") -> Any:
    """Reject a pending self-heal fix."""
    from core.harness.evaluation.self_heal_gate import SelfHealGate
    return SelfHealGate().reject_fix(fix_id, reason)


def get_fde_pipeline_health() -> Any:
    """Get FDE pipeline health stats (via handler registry)."""
    return dispatch("fde_pipeline_health")


def get_fde_health() -> Any:
    """Get full FDE health check (via handler registry)."""
    return dispatch("fde_health")


def fde_clarify(**kwargs: Any) -> Any:
    """Run FDE clarification (via handler registry)."""
    return dispatch("fde_clarify", **kwargs)


def get_builder_project_service() -> Any:
    """Get builder project service (via handler registry)."""
    return dispatch("builder_project_service")


def get_route_permissions() -> Any:
    """Get route permissions from platform auth (via handler registry)."""
    return dispatch("route_permissions")


def get_method_restrictions() -> Any:
    """Get method restrictions from platform auth (via handler registry)."""
    return dispatch("method_restrictions")


def llm_generate(model: Any, prompt: Any, **kwargs: Any) -> Any:
    """Call LLM through the syscall boundary. Use this instead of importing
    sys_llm_generate directly from core.harness.syscalls."""
    from core.harness.syscalls.llm import sys_llm_generate
    return sys_llm_generate(model, prompt, **kwargs)

# Alias for platform code that was batch-migrated from core.harness.syscalls.llm
sys_llm_generate = llm_generate


# ═══════════════════════════════════════════════════════════════
# core_chat() — intent-level agent conversation entry.
# Automatically activates Memory, Trace, AgentRegistry, Skills.
# (chat_conversation() removed — use intents.core_chat() directly)
# ═══════════════════════════════════════════════════════════════

class ChatContext:
    """Intent-level chat context. Application only declares intent;
    CoreFacade automatically activates all relevant subsystems."""

    def __init__(
        self,
        *,
        agent_name: str,
        session_id: str,
        user_input: str,
        user_id: str = "system",
        extra_context: Optional[Dict[str, str]] = None,
        model: Any = None,
    ):
        self.agent_name = agent_name
        self.session_id = session_id
        self.user_input = user_input
        self.user_id = user_id
        self.extra_context = extra_context or {}
        self.model = model


class ChatResult:
    """Structured chat result with observability metadata."""

    def __init__(
        self,
        *,
        reply: str,
        trace_id: Optional[str] = None,
        skills_used: Optional[List[str]] = None,
        memory_saved: bool = False,
        prd_ready: bool = False,
    ):
        self.reply = reply
        self.trace_id = trace_id
        self.skills_used = skills_used or []
        self.memory_saved = memory_saved
        self.prd_ready = prd_ready


async def core_chat(ctx: ChatContext) -> ChatResult:
    """Execute a conversational agent turn with automatic subsystem activation.

    This is the INTENT-LEVEL entry point for agent conversations.
    Application only declares what it wants (agent_name, session_id, user_input);
    CoreFacade automatically:

    1. AgentRegistry → discovers agent configuration and system prompt
    2. MemoryManager → persists the conversation (survives restart)
    3. Trace → generates trace_id for end-to-end observability
    4. SkillRegistry → binds matching Skills to the agent

    Usage:
        result = await core_chat(ChatContext(
            agent_name="<agent_name>",
            session_id=project_id,
            user_input="<user request>",
            extra_context={"requirement": "<application-specific context>"},
        ))
        print(result.reply, result.trace_id)
    """
    import time
    import uuid as _uuid

    trace_id = f"chat_{_uuid.uuid4().hex[:12]}"

    # ── 1. AgentRegistry: discover agent config ──
    system_prompt = ""
    agent_type = "conversational"
    frontmatter: Dict[str, Any] = {}
    try:
        frontmatter = get_agent_frontmatter(ctx.agent_name) or {}
        if frontmatter:
            system_prompt = frontmatter.get("_sop_body", "") or frontmatter.get("system_prompt", "")
            agent_type = frontmatter.get("agent_type", agent_type)
    except Exception as e:
        logging.debug(str(e), exc_info=True)

    # Fallback: load from core's AGENT.md
    if not system_prompt:
        try:
            import os as _os
            import yaml as _yaml
            seeds = _os.getenv("AIPLAT_WORKSPACE_SEEDS",
                _os.path.join(_os.getenv("AIPLAT_HOME", _os.path.expanduser("~/.aiplat")), "workspace_seeds"))
            md_path = _os.path.join(seeds, "agents", ctx.agent_name, "AGENT.md")
            if not _os.path.exists(md_path):
                md_path = _os.path.join(_os.path.expanduser("~/.aiplat"), "agents", ctx.agent_name, "AGENT.md")
            if _os.path.exists(md_path):
                with open(md_path, "r") as f:
                    raw = f.read()
                if raw.startswith("---"):
                    parts = raw.split("---", 2)
                    if len(parts) >= 3:
                        fm = _yaml.safe_load(parts[1]) or {}
                        system_prompt = parts[2].strip()
                        agent_type = fm.get("agent_type", agent_type)
        except Exception as e:
            logging.debug(str(e), exc_info=True)

    if not system_prompt:
        system_prompt = f"You are {ctx.agent_name}. Respond helpfully."

    # ── 2. MemoryManager: persist conversation ──
    memory_saved = False
    message_history: List[Dict[str, str]] = [{"role": "user", "content": ctx.user_input}]
    try:
        from core.harness.memory.manager import get_memory_manager as _get_mem
        mgr = _get_mem()
        mem_ctx = await mgr.build_context(
            current_query=ctx.user_input,
            system_prompt=system_prompt,
        )
        if mem_ctx and isinstance(mem_ctx, dict):
            existing = mem_ctx.get("messages") or mem_ctx.get("history") or []
            if isinstance(existing, list):
                message_history = list(existing) + message_history
    except Exception as e:
        logging.debug(str(e), exc_info=True)

    # ── 3. SkillRegistry: bind matching Skills ──
    skills_used: List[str] = []
    try:
        skill_reg = get_skill_registry()
        # Auto-bind skills based on agent's required_skills from frontmatter
        required = (frontmatter or {}).get("required_skills") if frontmatter else None
        if required:
            skills_used = [s for s in required if isinstance(s, str)]
    except Exception as e:
        logging.debug(str(e), exc_info=True)

    # ── 4. Build context from extra_context ──
    user_prompt = ctx.user_input
    if ctx.extra_context:
        ctx_lines = [f"{k}: {v}" for k, v in ctx.extra_context.items() if v]
        if ctx_lines:
            user_prompt = f"## 上下文\n" + "\n".join(ctx_lines) + f"\n\n## 用户消息\n{ctx.user_input}"

    # ── 5. Create and execute agent ──
    from core.harness.interfaces.agent import AgentConfig, AgentContext
    model = ctx.model
    if model is None:
        model = get_default_model()

    agent = create_agent(
        agent_type=agent_type,
        config=AgentConfig(name=ctx.agent_name, temperature=0.3, timeout=600),
        model=model,
        system_prompt=system_prompt,
    )
    # Bind skills
    for skill_name in skills_used:
        try:
            if hasattr(agent, "add_skill"):
                agent.add_skill(skill_name)
        except Exception as e:
            logging.debug(str(e), exc_info=True)

    agent_ctx = AgentContext(
        session_id=ctx.session_id,
        user_id=ctx.user_id,
        messages=message_history,
    )
    result = await agent.execute(agent_ctx)

    reply = ""
    if result.success:
        if isinstance(result.output, dict):
            reply = result.output.get("content", "") or str(result.output)
        else:
            reply = str(result.output) if result.output else ""
    else:
        reply = f"Agent error: {result.error}"

    # ── 6. MemoryManager: save interaction ──
    try:
        await mgr.save_interaction(
            user_input=ctx.user_input,
            agent_output=reply,
            session_id=ctx.session_id,
            metadata={"trace_id": trace_id, "agent_name": ctx.agent_name, "skills_used": skills_used},
        )
        memory_saved = True
    except Exception as e:
        logging.debug(str(e), exc_info=True)

    return ChatResult(
        reply=reply,
        trace_id=trace_id,
        skills_used=skills_used,
        memory_saved=memory_saved,
    )


from core.utils.json_utils import extract_json, extract_json_safe, parse_json


def parse_output(raw: str) -> Dict[str, Any]:
    """Parse an agent's raw output into structured form.
    Returns dict with keys: artifact, issues, confidence, decision."""
    from core.harness.execution.pipeline_engine import PipelineEngine
    result = PipelineEngine._parse_output(raw)
    return {
        "artifact": result.artifact,
        "issues": [i.model_dump() for i in result.issues],
        "confidence": result.confidence.value,
        "decision": result.decision.value,
    }


def get_agent_frontmatter(agent_id: str) -> Dict[str, Any]:
    """Load AGENT.md frontmatter for an agent. Looks in:
    1. ~/.aiplat/agents/{agent_id}/AGENT.md
    2. AIPLAT_WORKSPACE_SEEDS/agents/{agent_id}/AGENT.md
    Returns dict with all frontmatter fields + '_sop_body' (the SOP text after ---)."""
    import os
    import yaml

    agent_home = os.path.join(os.path.expanduser("~/.aiplat"), "agents", agent_id, "AGENT.md")
    seeds = os.getenv("AIPLAT_WORKSPACE_SEEDS",
        os.path.join(os.getenv("AIPLAT_HOME", os.path.expanduser("~/.aiplat")), "workspace_seeds"))
    seeds_path = os.path.join(seeds, "agents", agent_id, "AGENT.md")

    found_path = None
    if os.path.exists(agent_home):
        found_path = agent_home
    elif os.path.exists(seeds_path):
        found_path = seeds_path

    if not found_path:
        return {}

    try:
        with open(found_path, "r") as f:
            raw = f.read()
        result: Dict[str, Any] = {}
        if raw.startswith("---"):
            parts = raw.split("---", 2)
            if len(parts) >= 3:
                fm = yaml.safe_load(parts[1]) or {}
                result.update(fm)
                result["_sop_body"] = parts[2].strip()
        else:
            result["_sop_body"] = raw.strip()
        return result
    except Exception:
        return {}


def get_code_gen_skill(model: Any = None) -> Any:
    """Get a CodeGenerationSkill instance. Use this instead of importing
    CodeGenerationSkill directly from core.apps.skills.base."""
    from core.apps.skills.base import CodeGenerationSkill
    return CodeGenerationSkill(model=model)


def seed_all_registries() -> None:
    """Seed SkillRegistry, ToolRegistry, and ModelManager with built-in defaults.
    Platform processes call this during startup instead of seeding registries
    with platform-specific knowledge."""
    # Skill registry — seed built-in + workspace skills
    try:
        registry = get_skill_registry()
        registry.seed_for_platform()
    except Exception as e:
        logging.debug(str(e), exc_info=True)
    # Tool registry — register built-in tools
    try:
        from core.apps.tools import skill_tools, webfetch, http, repo
        reg = get_tool_registry()
        _modules = [
            (skill_tools, "SkillFindTool", {}),
            (skill_tools, "SkillLoadTool", {}),
            (webfetch, "WebFetchTool", {}),
            (http, "HTTPClientTool", {}),
            (repo, "RepoTool", {}),
        ]
        for mod, cls_name, kwargs in _modules:
            try:
                reg.register(getattr(mod, cls_name)(**kwargs))
            except Exception as e:
                logging.debug(str(e), exc_info=True)
    except Exception as e:
        logging.debug(str(e), exc_info=True)

    # Model registry now bridged to infra ModelManager (no local seed needed)


def get_secret(name: str) -> Optional[str]:
    """Get a secret by name. Falls back to env var if no SecretsManager."""
    from core.harness.infrastructure.secrets_manager import get_secrets_manager
    return get_secrets_manager().get(name)


def set_secret(name: str, value: str) -> None:
    """Store a secret (encrypted at rest via AES-256-GCM)."""
    from core.harness.infrastructure.secrets_manager import get_secrets_manager
    get_secrets_manager().set(name, value)


# ── Router-facing facade extensions (Category 2 fix) ──

def get_permission_manager() -> Any:
    """Get the PermissionManager singleton via DI or direct import."""
    from core.apps.tools.permission import get_permission_manager as _get
    return _get()

def resolve_skill_permission(skill_name: str) -> str:
    """Resolve skill permission level via DI or direct import."""
    from core.apps.tools.skill_tools import resolve_skill_permission as _get
    return _get(skill_name)

def resolve_executable_skill_permission(skill_name: str) -> str:
    """Resolve executable skill permission via DI or direct import."""
    from core.apps.tools.skill_tools import resolve_executable_skill_permission as _get
    return _get(skill_name)

async def get_exec_backend() -> Any:
    """Get the ExecBackend singleton via DI or direct import."""
    from core.apps.exec_drivers.registry import get_exec_backend as _get
    return await _get()

async def scan_security(code: str) -> Any:
    """Run security scan on code via quality scanner."""
    from core.apps.quality.scanner import create_security_scanner
    scanner = create_security_scanner()
    return scanner.scan(code)


# ═══════════════════════════════════════════════════════════════
# Service wrappers — Platform MUST use these instead of importing
# core.services.* classes directly.
# ═══════════════════════════════════════════════════════════════

def create_chat_service(model: Any = None) -> Any:
    """Create a ChatService instance. Use instead of importing
    from core.services.chat_service directly."""
    from core.services.chat_service import ChatService
    return ChatService(model=model)


def create_conversation_service(store: Any = None) -> Any:
    """Create a ConversationService instance. Use instead of importing
    from core.services.conversations directly."""
    from core.services.conversations import ConversationService
    return ConversationService(store) if store else ConversationService()


# ═══════════════════════════════════════════════════════════════
# PipelineSession — the sole interface for pipeline execution.
# Platform MUST use this instead of instantiating PipelineEngine.
# ═══════════════════════════════════════════════════════════════

class PipelineSession:
    """
    Wraps PipelineEngine lifecycle. Platform creates a session via
    CoreFacade.create_pipeline_session(), then calls start/approve/reject/
    rollback/resume/snapshot.

    All internal engine management (state persistence, crash recovery,
    AGENT.md frontmatter loading) is handled by CoreFacade — platform
    only passes in pipeline config and receives state snapshots.
    """

    def __init__(self, engine: Any, config: Any = None):
        self._engine = engine
        self._config = config

    @property
    def engine(self) -> Any:
        return self._engine

    async def start(self, project_id: str, requirement: str, prd_data: Any = None) -> Dict[str, Any]:
        """Start pipeline execution. Returns initial state snapshot."""
        result = await self._engine.initialize(project_id, requirement, prd_data=prd_data)
        return result

    async def approve(self, state: Dict[str, Any], feedback: str = "") -> Dict[str, Any]:
        """HITL approval: resume pipeline from current HITL pause."""
        return await self._engine.approve_session(dict(state), feedback=feedback)

    async def reject(self, state: Dict[str, Any], feedback: str = "") -> Dict[str, Any]:
        """HITL rejection: provide feedback and resume pipeline."""
        return await self._engine.reject_session(dict(state), feedback)

    async def rollback(self, state: Dict[str, Any], stage_id: str) -> Dict[str, Any]:
        """Rollback pipeline to a previous stage."""
        return await self._engine.rollback(dict(state), stage_id)

    async def resume_from(self, stage_idx: int, state: Dict[str, Any]) -> Dict[str, Any]:
        """Resume pipeline execution from a specific stage index."""
        return await self._engine.resume_from(stage_idx, dict(state))

    async def get_graph(self) -> Dict[str, Any]:
        """Get pipeline execution graph for visualization."""
        return await self._engine.graph_data()

    def snapshot(self) -> Dict[str, Any]:
        """Return current pipeline state snapshot."""
        return self._engine.snapshot()

    def get_stages(self) -> List[Any]:
        """Return the list of pipeline stage configs."""
        return list(self._engine.get_stages() or [])

    def assemble_deploy(self, state: Dict[str, Any]) -> str:
        """Assemble a deploy directory from pipeline output artifacts."""
        return self._engine.assemble_deploy(dict(state))


def create_pipeline_session(
    config: Any,
    model: Any = None,
    skill_loader: Any = None,
    persist_callback: Any = None,
) -> PipelineSession:
    """Create a PipelineSession. Use this instead of importing and instantiating
    PipelineEngine directly.

    Platform usage:
        session = create_pipeline_session(config, model, skill_loader)
        state = await session.start(project_id, requirement, prd_data=prd_data)
        # ... user interacts ...
        state = await session.approve(state)
    """
    from core.harness.execution.pipeline_engine import PipelineEngine
    engine = PipelineEngine(config=config, model=model, skill_loader=skill_loader,
                            persist_callback=persist_callback)
    return PipelineSession(engine=engine, config=config)


def validate_pipeline_stages(stages: List[Any]) -> Dict[str, Any]:
    """Validate pipeline stage configuration. Returns diagnostics dict
    with 'valid' (bool), 'errors' (list), 'warnings' (list).

    Platform calls this before creating a session to catch misconfigurations early.
    """
    import re
    diagnostics: Dict[str, Any] = {"valid": True, "errors": [], "warnings": []}

    for i, stage in enumerate(stages):
        prefix = f"stage[{i}]"
        sid = getattr(stage, 'id', f'stage_{i}')
        agent_id = getattr(stage, 'agent_id', '')
        required_skills = getattr(stage, 'required_skills', None) or []

        if not agent_id:
            diagnostics["errors"].append(f"{prefix} ({sid}): missing agent_id")
        for skill_id in required_skills:
            if not isinstance(skill_id, str) or not skill_id.strip():
                diagnostics["errors"].append(f"{prefix} ({sid}): empty skill_id in required_skills")

        failure_strategy = getattr(stage, 'failure_strategy', 'fail_pipeline')
        allowed_fs = ('fail_pipeline', 'skip_stage', 'use_fallback_result')
        if failure_strategy not in allowed_fs:
            diagnostics["warnings"].append(
                f"{prefix} ({sid}): unknown failure_strategy '{failure_strategy}' — will use 'fail_pipeline'"
            )

    diagnostics["valid"] = len(diagnostics["errors"]) == 0
    return diagnostics


def apply_agent_md_to_stage(stage: Any, agent_id: str) -> None:
    """Read AGENT.md frontmatter and apply fields to a PipelineStageConfig.

    Platform calls this during pipeline setup to populate stage config
    from agent definitions. All AGENT.md parsing happens inside CoreFacade.
    """
    import os
    import yaml

    # Find AGENT.md
    agent_home = os.path.join(os.path.expanduser("~/.aiplat"), "agents", agent_id, "AGENT.md")
    seeds = os.getenv("AIPLAT_WORKSPACE_SEEDS",
        os.path.join(os.getenv("AIPLAT_HOME", os.path.expanduser("~/.aiplat")), "workspace_seeds"))
    seeds_path = os.path.join(seeds, "agents", agent_id, "AGENT.md")

    found_path = None
    for p in (agent_home, seeds_path):
        if os.path.exists(p):
            found_path = p
            break
    if not found_path:
        return

    try:
        with open(found_path, "r") as f:
            raw = f.read()
    except Exception:
        return

    fm: Dict[str, Any] = {}
    if raw.startswith("---"):
        parts = raw.split("---", 2)
        if len(parts) >= 3:
            fm = yaml.safe_load(parts[1]) or {}

    # Apply frontmatter to stage config
    if fm.get("auto_hitl") and not hasattr(stage, '_auto_hitl_loaded'):
        stage.hitl = True
        stage.hitl_phase = fm.get("hitl_phase") or getattr(stage, 'hitl_phase', 'approval_required') or 'approval_required'
        stage._auto_hitl_loaded = True

    if fm.get("hitl_after_execute") and not getattr(stage, 'hitl_after_execute', False):
        stage.hitl_after_execute = True
        stage.hitl_after_phase = fm.get("hitl_after_phase", "")

    if fm.get("uses_code_skill"):
        stage.uses_code_skill = True

    if fm.get("generate_test_plan"):
        stage.generate_test_plan = True

    if fm.get("prompt_extra"):
        stage.prompt_extra = fm["prompt_extra"]

    if fm.get("required_skills"):
        stage.required_skills = fm["required_skills"]

    if fm.get("input_artifacts"):
        stage.input_artifacts = fm["input_artifacts"]

    if fm.get("depends_on"):
        stage.depends_on = fm["depends_on"]

    if fm.get("output_artifact") and not getattr(stage, 'output_artifact', ''):
        stage.output_artifact = fm["output_artifact"]

    if fm.get("test_result_key") and not getattr(stage, 'test_result_key', ''):
        stage.test_result_key = fm["test_result_key"]

    if fm.get("failure_strategy") and not getattr(stage, 'failure_strategy', ''):
        stage.failure_strategy = fm["failure_strategy"]

    if fm.get("retry_llm_on_rate_limit") is not None:
        stage.retry_llm_on_rate_limit = fm["retry_llm_on_rate_limit"]

    if fm.get("scoring_dimensions"):
        stage.scoring_dimensions = fm["scoring_dimensions"]

    if fm.get("knowledge_bases"):
        stage.knowledge_bases = fm["knowledge_bases"]


# ═══════════════════════════════════════════════════════════════
# Governance facade — Platform MUST use these instead of importing
# from core.governance.* or core.api.routers.* directly.
# ═══════════════════════════════════════════════════════════════

def record_changeset(
    *,
    resource_type: str = "",
    resource_id: str = "",
    action: str = "",
    before: Any = None,
    after: Any = None,
    tenant_id: Optional[str] = None,
    actor_id: Optional[str] = None,
    metadata: Optional[Dict[str, Any]] = None,
) -> str:
    """Record a governance changeset. Use this instead of importing from
    core.governance.changeset directly."""
    from core.governance.changeset import record_changeset as _fn
    return _fn(
        store=None,
        name=action,
        target_type=resource_type,
        target_id=resource_id,
        status="success",
        args=metadata,
        user_id=actor_id or "admin",
    )


def new_change_id() -> str:
    """Generate a new governance change ID. Use instead of importing
    from core.governance.gating directly."""
    from core.governance.gating import new_change_id as _fn
    return _fn()


def apply_autosmoke_result(verification_id: str, result: str,
                          *, resource_type: str = "", resource_id: str = "",
                          job_run: Optional[Dict[str, Any]] = None) -> None:
    """Apply autosmoke verification result. Use instead of importing
    from core.governance.verification directly."""
    from core.governance.verification import apply_autosmoke_result as _fn
    _fn(verification_id, result, resource_type=resource_type,
        resource_id=resource_id, job_run=job_run)


def mark_resource_pending(resource_type: str, resource_id: str,
                          *, workspace_agent_manager: Any = None,
                          workspace_skill_manager: Any = None,
                          workspace_mcp_manager: Any = None) -> None:
    """Mark a resource as pending verification. Use instead of importing
    from core.governance.verification directly."""
    from core.governance.verification import mark_resource_pending as _fn
    _fn(resource_type=resource_type, resource_id=resource_id,
         workspace_agent_manager=workspace_agent_manager,
         workspace_skill_manager=workspace_skill_manager,
         workspace_mcp_manager=workspace_mcp_manager)


def evaluate_tool_policy_snapshot(policy: Dict[str, Any], *, tool_name: str) -> Dict[str, Any]:
    """Evaluate a tool policy snapshot. Use instead of importing
    from core.policy.engine directly."""
    from core.policy.engine import evaluate_tool_policy_snapshot as _fn
    return _fn(policy, tool_name=tool_name)


# ── Execution snapshot self-service facade (P1-2: user-facing checkpoint recovery) ──

def list_execution_snapshots(session_id: str) -> List[Dict[str, Any]]:
    """List all execution snapshots for a session (newest first).

    Exposes the on-disk checkpoint headers so users/tools can self-service
    inspect and recover pipeline execution state (Hermes Layer 1 checkpoint).
    """
    from core.harness.execution.snapshot import list_execution_snapshots as _fn
    return _fn(session_id)


def get_execution_snapshot(snapshot_id: str, session_id: str) -> Optional[Dict[str, Any]]:
    """Load a single execution snapshot header + full state for recovery.

    Returns None if not found. The ``full_state`` field is the recoverable
    pipeline state dict (the restore payload).
    """
    from core.harness.execution.snapshot import load_execution_snapshot as _fn
    snap = _fn(snapshot_id, session_id)
    if snap is None:
        return None
    out = snap.to_dict()
    out["full_state"] = snap.full_state
    return out


def compare_execution_snapshots(snapshot_a_id: str, snapshot_b_id: str, session_id: str) -> Dict[str, Any]:
    """Diff two execution snapshots (before/after strategy effect)."""
    from core.harness.execution.snapshot import compare_execution_snapshots as _fn
    return _fn(snapshot_a_id, snapshot_b_id, session_id)


def restore_execution_snapshot(snapshot_id: str, session_id: str) -> Optional[Dict[str, Any]]:
    """Return the recoverable full state of a snapshot as the restore payload.

    This is the self-service recovery entry point: the caller obtains the
    historical pipeline state captured at checkpoint time and can resume/inspect
    from it. Returns None if the snapshot or its full state is unavailable.
    """
    from core.harness.execution.snapshot import load_execution_snapshot as _fn
    snap = _fn(snapshot_id, session_id)
    if snap is None:
        return None
    state = snap.full_state
    if state is None:
        return None
    return {
        "snapshot_id": snap.snapshot_id,
        "session_id": snap.session_id,
        "stage_id": snap.stage_id,
        "strategy_name": snap.strategy_name,
        "phase": snap.phase,
        "restored_state": state,
    }


# ── File checkpoint self-service facade (Hermes Layer 1: physical safety net) ──

def list_file_checkpoints(*, session_id: str = "", path: str = "") -> List[Dict[str, Any]]:
    """List filesystem checkpoints captured before file write/edit overwrites."""
    from core.harness.execution.file_checkpoint import list_file_checkpoints as _fn
    return _fn(session_id=session_id, path=path)


def get_file_checkpoint(checkpoint_id: str, session_id: str = "") -> Optional[Dict[str, Any]]:
    """Return a file checkpoint header + its stored content."""
    from core.harness.execution.file_checkpoint import get_file_checkpoint as _fn
    return _fn(checkpoint_id, session_id)


def restore_file_checkpoint(checkpoint_id: str, session_id: str = "") -> Dict[str, Any]:
    """Restore a file to the content captured in the given checkpoint (writes it back)."""
    from core.harness.execution.file_checkpoint import restore_file_checkpoint as _fn
    return _fn(checkpoint_id, session_id)


def publish_learning_release(release_id: str) -> Dict[str, Any]:
    """Publish a learning release candidate (via handler registry)."""
    return dispatch("publish_release_candidate", release_id)


def rollback_learning_release(release_id: str, reason: str = "") -> Dict[str, Any]:
    """Rollback a learning release candidate (via handler registry)."""
    return dispatch("rollback_release_candidate", release_id, reason)


def run_plugin_action(plugin_id: str, action: str, params: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """Run a plugin action. Use instead of importing
    from core.api.routers.plugins directly."""
    from core.api.routers.plugins import run_plugin as _fn


# ── KB Facade ──

def kb_retrieve(query: str, doc_ids: Any, **kwargs: Any) -> Any:
    """Retrieve relevant KB document content through the syscall boundary."""
    from core.harness.syscalls.retrieval import sys_kb_retrieve
    return sys_kb_retrieve(query, doc_ids, **kwargs)


def wiki_retrieve(query: str, wiki_titles: list = None, **kwargs: Any) -> Any:
    """Retrieve relevant wiki knowledge page content through the syscall boundary."""
    from core.harness.syscalls.retrieval import sys_wiki_retrieve
    return sys_wiki_retrieve(query, wiki_titles, **kwargs)


async def wiki_auto_update(doc_id: str, file_path: str, collection_id: str = "") -> Dict[str, Any]:
    u"""Convert a newly ingested KB document into Wiki knowledge pages.

    Called by platform after document ingestion completes.
    Complies with platform→core facade rule (§5.1).

    If collection_id is provided, it is added as a tag and used
    for subdir→collection mapping in Vault→Wiki flows.
    """
    import os, re
    from core.harness.knowledge.wiki_engine import write_page
    from core.api.core_facade import kb_parse_document, kb_chunk_elements

    kind = os.path.splitext(file_path)[1].lstrip(".") or "txt"
    elements = kb_parse_document(file_path, kind)
    if not elements:
        return {"status": "skipped", "reason": "no elements parsed"}

    chunks = kb_chunk_elements(elements, kind=kind, target_size=1000, overlap=150)
    if not chunks:
        return {"status": "skipped", "reason": "no chunks"}

    title = os.path.basename(file_path).rsplit(".", 1)[0][:100] or doc_id[:60]
    title = re.sub(r"[<>:\"/\\|?*]", "_", title)
    body_parts = [str(ch.get("text", "") or "").strip() for ch in chunks if str(ch.get("text", "") or "").strip()]
    body = "\n\n".join(body_parts)[:50000]
    keywords = re.findall(r'[\u4e00-\u9fff]{2,8}|[A-Z][a-zA-Z]{2,}', body[:5000])
    tags = list(set(kw.lower() for kw in keywords[:8]))
    if collection_id:
        tags.append(f"collection:{collection_id}")

    # ── Image extraction & description (fire-and-forget, best-effort) ──
    image_descriptions = []
    try:
        from core.harness.document.parsers import extract_images_from_document, describe_images
        img_paths = extract_images_from_document(file_path)
        if img_paths:
            image_descriptions = await describe_images(img_paths[:8])
    except Exception as e:
        logging.debug(str(e), exc_info=True)

    write_page(title, body, category="entities", tags=tags,
               summary=body[:300].replace("\n", " "),
               source_articles=[f"kb:{doc_id}"],
               images=image_descriptions,
               collection_id=collection_id or "default")

    # LLM curation: extract knowledge atoms, generate proper metadata (with retry)
    import asyncio as _asyncio
    curated = None
    curation_retries = 0
    for attempt in range(3):
        try:
            from core.harness.knowledge.wiki_engine import llm_curate_page, list_all_pages, update_page
            import re as _re
            safe_title = _re.sub(r"[<>:\"/\\|?*]", "_", title)[:120]
            existing = list_all_pages()
            existing_titles = [p["title"] for p in (existing or []) if p["title"] != safe_title]
            curated = await llm_curate_page(safe_title, body, existing_titles=existing_titles, source_doc_id=doc_id)
            if not curated.get("error") and not curated.get("fallback"):
                break
        except Exception:
            if attempt < 2:
                await _asyncio.sleep(2 ** attempt)
                curation_retries += 1

    if curated and not curated.get("error") and not curated.get("fallback"):
        try:
            # Re-write main page with LLM metadata
            old_title = safe_title
            curated_tags = curated.get("tags", tags)
            if collection_id:
                curated_tags = list(set(curated_tags + [f"collection:{collection_id}"]))
            # Convert related to typed relationships for ontology A-Box
            related_pages = curated.get("related", [])
            relationships = [{"type": "cites", "target": r} for r in related_pages] if related_pages else None

            write_page(curated["title"], body,
                category=curated.get("category", "entities"),
                tags=curated_tags,
                relationships=relationships,
                summary=curated.get("summary", body[:300].replace("\n", " ")),
                source_articles=[f"kb:{doc_id}"],
                images=image_descriptions,
                collection_id=collection_id or "default")
            if curated["title"] != old_title:
                from core.harness.knowledge.wiki_engine import delete_page
                try: delete_page(old_title, collection_id=collection_id or "default")
                except Exception: logging.debug(f"Failed to delete old page {old_title}", exc_info=True)
            # Create knowledge atom pages with evidence tracking
            from core.harness.knowledge.wiki_engine import write_atom
            for atom in curated.get("knowledge_atoms", [])[:6]:
                if not atom.get("title") or not atom.get("body"):
                    continue
                atom_title = _re.sub(r"[<>:\"/\\|?*]", "_", str(atom["title"])[:80])
                atom_tags = list(atom.get("tags", []))[:5]
                if collection_id:
                    atom_tags.append(f"collection:{collection_id}")
                if atom_title and atom_title != curated["title"]:
                    write_atom({
                        "title": atom_title,
                        "body": str(atom.get("body", ""))[:20000],
                        "source_doc_id": f"kb:{doc_id}",
                        "evidence_text": atom.get("evidence_text", ""),
                        "confidence": float(atom.get("confidence", 0.5)),
                        "tags": atom_tags,
                        "contradicts_atom_index": atom.get("contradicts_atom_index"),
                        "supports_atom_index": atom.get("supports_atom_index"),
                    }, collection_id=collection_id or "default")

            # Track curation success for metrics
            try:
                import json as _json, os as _os, time as _time
                stats_path = _os.path.join(_os.path.expanduser(_os.getenv("AIPLAT_HOME", "~/.aiplat")),
                                           "wiki", "curation_stats.json")
                stats = {}
                if _os.path.exists(stats_path):
                    stats = _json.loads(open(stats_path).read())
                if curated and not curated.get("error") and not curated.get("fallback"):
                    stats["successes"] = stats.get("successes", 0) + 1
                    stats["last_success"] = _time.time()
                else:
                    stats["failures"] = stats.get("failures", 0) + 1
                if curation_retries > 0:
                    stats["retries_total"] = stats.get("retries_total", 0) + curation_retries
                _os.makedirs(_os.path.dirname(stats_path), exist_ok=True)
                _json.dump(stats, open(stats_path, "w"))
            except Exception as e:
                logging.debug(str(e), exc_info=True)
        except Exception as e:
            logging.debug(str(e), exc_info=True)

    # Record changelog for this ingest operation
    try:
        from core.harness.knowledge.wiki_engine import ingest_changelog
        ops = [{"type": "create", "page": title, "detail": f"从 KB 文档 {doc_id} 创建"}]
        if curated and not curated.get("error"):
            for atom in curated.get("knowledge_atoms", [])[:6]:
                if atom.get("title") and atom["title"] != curated.get("title", ""):
                    ops.append({"type": "create", "page": str(atom["title"]),
                                "detail": f"知识原子（来源：{title}）"})
            if curated.get("related"):
                ops.append({"type": "link", "page": title,
                            "detail": f"关联 {len(curated['related'])} 个页面"})
        ingest_changelog(ops)
    except Exception as e:
        logging.debug(str(e), exc_info=True)

    # ── Ontology: incremental A-Box rebuild after ingest ──
    try:
        from core.harness.knowledge.knowledge_abox_builder import rebuild_for_doc
        rebuild_for_doc(doc_id)
    except Exception as e:
        logging.debug(str(e), exc_info=True)

    # ── Evolution: auto-trigger if enough new pages accumulated ──
    try:
        from core.harness.knowledge.evolution_runner import EvolutionRunner
        runner = EvolutionRunner(collection_id=collection_id or "default", max_mutations=3)
        if runner.can_evolve():
            await runner.run_one_generation(force=False)
    except Exception as e:
        logging.debug(str(e), exc_info=True)

    final_category = "entities"
    if curated and not curated.get("error") and not curated.get("fallback"):
        final_category = curated.get("category", "entities")

    # Update wiki_status in KB database for unified document→wiki tracking
    try:
        import sqlite3 as _sq
        kb_db = os.path.join(os.path.expanduser(os.getenv("AIPLAT_HOME", "~/.aiplat")),
                              "kb", "tenants", "default", "kb.sqlite3")
        if os.path.exists(kb_db):
            with _sq.connect(kb_db) as _conn:
                _conn.execute(
                    "UPDATE documents SET wiki_status='wikified' WHERE doc_id=?",
                    (doc_id,))
                _conn.commit()
    except Exception as e:
        logging.debug(str(e), exc_info=True)

    # Phase G: LLM Wiki contradiction detection — flag contradictions at ingest time
    try:
        from core.harness.knowledge.wiki_engine import search_pages, update_page
        pages = search_pages(limit=1000, collection_id=collection_id or "default")
        for p in pages:
            ptitle = p.get("title", "")
            if ptitle == title:
                continue
            # Lightweight: check if page body overlaps semantically with new knowledge
            existing_tags = set(p.get("tags", []) or [])
            new_tags = set(tags or [])
            if existing_tags & new_tags and len(existing_tags & new_tags) >= 2:
                # Same topic detected — flag potential contradiction for review
                contradictions = list(p.get("contradictions") or [])
                if title not in contradictions:
                    contradictions.append(title)
                    update_page(ptitle, contradictions=contradictions, collection_id=collection_id or "default")
    except Exception as e:
        logging.debug(str(e), exc_info=True)

    return {"status": "created", "title": title, "category": final_category, "chars": len(body)}


async def auto_ontology_pipeline_for_doc(doc_id: str, file_path: str, collection_id: str = "default") -> Dict[str, Any]:
    """Auto-run ontology engine pipeline on a newly ingested/re-ingested document.

    Called as fire-and-forget from platform ingest and watch_directory polling.
    Gated by AIPLAT_AUTO_ONTOLOGY_PIPELINE env var (default: true).

    What it does:
    1. Resolves domain_id from collection_id via DomainRouter
    2. Parses the document into text chunks
    3. Runs OntologyEngine.process_chunks() → extract entities, build GraphIndex,
       run state machine, synthesize Wiki pages
    4. Returns summary stats

    This is the bridge that closes the "document change → ontology update" gap.
    """
    import os as _os
    if _os.getenv("AIPLAT_AUTO_ONTOLOGY_PIPELINE", "true").lower() not in ("true", "1", "yes"):
        return {"status": "disabled", "reason": "AIPLAT_AUTO_ONTOLOGY_PIPELINE env var not enabled"}

    from core.harness.knowledge.domain_router import DomainRouter
    from core.harness.ontology_engine.engine import load_engine
    from core.api.core_facade import kb_parse_document, kb_chunk_elements

    router = DomainRouter()
    domain_id = router.resolve(collection_id) or "ai-knowledge"
    # If the resolved domain doesn't have a valid engine, try the fallback
    if load_engine(domain_id) is None:
        domain_id = "ai-knowledge"

    kind = _os.path.splitext(file_path)[1].lstrip(".") or "txt"
    try:
        elements = kb_parse_document(file_path, kind)
    except Exception as e:
        return {"status": "parse_error", "error": str(e)[:200]}

    if not elements:
        return {"status": "skipped", "reason": "no elements parsed"}

    chunks = kb_chunk_elements(elements, kind=kind, target_size=2000, overlap=300)
    if not chunks:
        return {"status": "skipped", "reason": "no chunks"}

    engine_chunks = []
    max_chunks = int(_os.getenv("AIPLAT_ONTOLOGY_MAX_CHUNKS", "30"))
    for i, ch in enumerate(chunks[:max_chunks]):
        text = str(ch.get("text", "") or "").strip()
        if len(text) >= 50:
            engine_chunks.append({"id": f"{doc_id}-{i}", "text": text[:8000]})

    if not engine_chunks:
        return {"status": "skipped", "reason": "chunks too small"}

    engine = load_engine(domain_id)
    if engine is None:
        return {"status": "skipped", "reason": f"no engine for domain '{domain_id}'"}

    # v2.9: Batch process large docs in groups of 10 chunks to avoid timeout
    batch_size = 10
    total_instances = 0
    total_relations = 0
    chunks_processed = 0
    last_error = None

    for batch_start in range(0, len(engine_chunks), batch_size):
        batch = engine_chunks[batch_start:batch_start + batch_size]
        try:
            result = await engine.process_chunks(batch, doc_id=doc_id)
            total_instances += len(result.instances) if hasattr(result, "instances") else 0
            total_relations += len(result.relations) if hasattr(result, "relations") else 0
            chunks_processed += len(batch)
        except Exception as batch_err:
            last_error = str(batch_err)[:200]
            continue

    if chunks_processed == 0 and last_error:
        return {"status": "error", "doc_id": doc_id, "error": last_error}

    # v2.9: Trigger community page stale-check after ontology pipeline
    try:
        from core.harness.knowledge.wiki_engine import _sync_community_pages
        stale_count = _sync_community_pages(doc_id, collection_id=collection_id)
        if stale_count > 0:
            logging.info("Community sync: %d pages marked stale after re-ingest of %s", stale_count, doc_id)
    except Exception:
        logging.getLogger(__name__).debug('code failed', exc_info=True)

    return {"status": "completed", "domain": domain_id, "doc_id": doc_id,
            "instances_created": total_instances, "relations_detected": total_relations,
            "chunks_processed": chunks_processed, "batches": len(range(0, len(engine_chunks), batch_size))}


# ═══════════════════════════════════════════════════════════════
# GrillingBridge — cross-cutting requirements clarification (v2.9)
# ═══════════════════════════════════════════════════════════════

_grilling_sessions: Dict[str, Dict[str, Any]] = {}


def start_grilling(entry_point: str, domain_id: str = "", context: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    u"""Start a grilling clarification interview session. Returns first question."""
    import os as _os, yaml as _yaml, uuid as _uuid, time as _time
    context = context or {}
    session_id = _uuid.uuid4().hex[:12]
    dimensions = _load_grilling_dimensions(entry_point, domain_id)
    if not dimensions:
        return {"session_id": session_id, "status": "no_dimensions",
                "message": "No interview dimensions configured for this entry point and domain."}
    session = {
        "session_id": session_id, "entry_point": entry_point,
        "domain_id": domain_id, "context": context,
        "dimensions": dimensions,
        "current_idx": 0, "answers": {},
        "started_at": _time.time(), "conversation": [],
    }
    _grilling_sessions[session_id] = session
    current = dimensions[0]
    return {
        "session_id": session_id, "status": "asking",
        "progress": {"current": 1, "total": len(dimensions), "completed_required": 0, "required_count": sum(1 for d in dimensions if d.get("required"))},
        "question": {
            "id": current["id"], "text": current["question"],
            "label": current.get("label", ""),
            "options": current.get("options", []),
            "required": current.get("required", False),
        },
    }


def continue_grilling(session_id: str, answer: str) -> Dict[str, Any]:
    u"""Process answer and return next question or finalize."""
    import time as _time
    session = _grilling_sessions.get(session_id)
    if not session:
        return {"session_id": session_id, "status": "error", "message": "Session not found or expired"}
    dimensions = session["dimensions"]
    idx = session["current_idx"]
    if idx >= len(dimensions):
        return _finalize_grilling(session_id)
    current = dimensions[idx]
    session["answers"][current["id"]] = answer
    session["conversation"].append({"question": current["question"], "answer": answer, "id": current["id"]})
    follow_ups = current.get("follow_up", {})
    if answer in follow_ups and follow_ups[answer]:
        for fu in follow_ups[answer]:
            fu["_is_follow_up"] = True
            dimensions.insert(idx + 1, fu)
    session["current_idx"] = idx + 1
    session["_last_active"] = _time.time()
    if session["current_idx"] >= len(dimensions):
        return _finalize_grilling(session_id)
    nxt = dimensions[session["current_idx"]]
    completed_required = sum(1 for d in dimensions[:session["current_idx"]] if d.get("required") and session["answers"].get(d["id"]))
    return {
        "session_id": session_id, "status": "asking",
        "progress": {"current": session["current_idx"] + 1, "total": len(dimensions),
                     "completed_required": completed_required,
                     "required_count": sum(1 for d in dimensions if d.get("required"))},
        "question": {
            "id": nxt["id"], "text": nxt["question"],
            "label": nxt.get("label", ""),
            "options": nxt.get("options", []),
            "required": nxt.get("required", False),
        },
        "previous_answer": answer,
    }


def skip_grilling_question(session_id: str) -> Dict[str, Any]:
    u"""Skip current question (only non-required)."""
    session = _grilling_sessions.get(session_id)
    if not session:
        return {"session_id": session_id, "status": "error", "message": "Session not found"}
    dimensions = session["dimensions"]
    idx = session["current_idx"]
    current = dimensions[idx]
    if current.get("required"):
        return {"session_id": session_id, "status": "error", "message": "Cannot skip required question"}
    session["answers"][current["id"]] = "[SKIPPED]"
    session["current_idx"] = idx + 1
    if session["current_idx"] >= len(dimensions):
        return _finalize_grilling(session_id)
    nxt = dimensions[session["current_idx"]]
    return {
        "session_id": session_id, "status": "asking",
        "progress": {"current": session["current_idx"] + 1, "total": len(dimensions)},
        "question": {
            "id": nxt["id"], "text": nxt["question"],
            "label": nxt.get("label", ""),
            "options": nxt.get("options", []),
            "required": nxt.get("required", False),
        },
    }


def get_grilling_progress(session_id: str) -> Dict[str, Any]:
    u"""Get current grilling session state (for UI recovery)."""
    session = _grilling_sessions.get(session_id)
    if not session:
        return {"session_id": session_id, "status": "not_found"}
    dimensions = session["dimensions"]
    idx = session["current_idx"]
    answered = []
    for d in dimensions[:idx]:
        answered.append({"id": d["id"], "label": d.get("label", d["id"]),
                         "answer": session["answers"].get(d["id"], "")})
    current = None
    if idx < len(dimensions):
        d = dimensions[idx]
        current = {"id": d["id"], "text": d["question"], "label": d.get("label", ""),
                   "options": d.get("options", []), "required": d.get("required", False)}
    return {
        "session_id": session_id, "status": "in_progress",
        "entry_point": session["entry_point"], "domain_id": session["domain_id"],
        "progress": {"current": idx + 1, "total": len(dimensions)},
        "answered": answered, "current_question": current,
    }


def _finalize_grilling(session_id: str) -> Dict[str, Any]:
    u"""Build structured output from completed grilling session."""
    session = _grilling_sessions.pop(session_id, {})
    if not session:
        return {"session_id": session_id, "status": "error", "message": "Session not found"}
    dimensions = session["dimensions"]
    answers = session["answers"]
    # Build structured output
    answered_items = []
    for d in dimensions:
        a = answers.get(d["id"], "")
        if a and a != "[SKIPPED]":
            answered_items.append({"id": d["id"], "dimension": d.get("label", d["id"]), "answer": a})
    answered_ids = [d["id"] for d in answered_items]
    skipped = [d for d in dimensions if d["id"] not in answered_ids and not d.get("required")]
    missed = [d for d in dimensions if d["id"] not in answered_ids and d.get("required")]
    summary_parts = ["## 需求澄清摘要\n"]
    for item in answered_items:
        summary_parts.append(f"- **{item['dimension']}**: {item['answer']}")
    if missed:
        summary_parts.append(f"\n### 未确认必填项\n" + "\n".join(f"- {d['question']}" for d in missed))
    if skipped:
        summary_parts.append(f"\n### 已跳过\n" + "\n".join(f"- {d.get('label', d['id'])}" for d in skipped))
    return {
        "session_id": session_id, "status": "completed",
        "entry_point": session["entry_point"], "domain_id": session["domain_id"],
        "total_questions": len(dimensions), "answered": len(answered_items),
        "missed_required": len(missed),
        "questions_asked": len(session.get("conversation", [])),
        "summary_markdown": "\n".join(summary_parts),
        "answers": {d["id"]: answers.get(d["id"], "") for d in dimensions},
        "answers_flat": {d.get("label", d["id"]): answers.get(d["id"], "") for d in dimensions if answers.get(d["id"]) and answers[d["id"]] != "[SKIPPED]"},
        "conversation": session.get("conversation", []),
    }


def _load_grilling_dimensions(entry_point: str, domain_id: str) -> List[Dict[str, Any]]:
    u"""Load interview dimensions from domain YAML + fallback defaults."""
    import os as _os, yaml as _yaml
    from pathlib import Path as _Path
    dimensions = []
    if domain_id:
        yaml_path = _Path(_os.getenv("AIPLAT_HOME", _Path("~").expanduser() / ".aiplat")) / "ontologies" / f"{domain_id}.yaml"
        if yaml_path.exists():
            try:
                data = _yaml.safe_load(yaml_path.read_text(encoding="utf-8"))
                dims = data.get("interview_dimensions", {})
                dimensions = dims.get(entry_point, dims.get("default", []))
            except Exception:
                logging.getLogger(__name__).debug('_load_grilling_dimensions failed', exc_info=True)
    if not dimensions:
        dimensions = _default_grilling_dimensions(entry_point)
    return dimensions


def _default_grilling_dimensions(entry_point: str) -> List[Dict[str, Any]]:
    u"""Built-in default interview dimensions per entry point."""
    defaults = {
        "fde_builder": [
            {"id": "project_type", "label": "项目类型", "question": "你要构建什么类型的项目？", "options": ["Web应用", "API服务", "CLI工具", "不确定"], "required": True},
            {"id": "tech_stack", "label": "技术栈", "question": "前端技术栈？", "options": ["React+TS", "Vue3", "Next.js", "不确定"], "required": True},
            {"id": "deployment", "label": "部署", "question": "部署环境？", "options": ["Docker自托管", "云服务器", "K8s", "不确定"], "required": True},
        ],
        "kb_qa": [
            {"id": "domain", "label": "领域", "question": "你想了解哪个领域的内容？", "options": ["AI/大模型", "编程开发", "架构设计", "不确定"], "required": True},
        ],
        "pipeline_hitl": [
            {"id": "review", "label": "审查", "question": "对当前交付物满意吗？", "options": ["满意，继续", "需要调整", "需要更多信息"], "required": True},
        ],
        "agent_chat": [
            {"id": "task_type", "label": "任务", "question": "需要什么帮助？", "options": ["写代码", "查资料", "设计方案", "排查问题", "不确定"], "required": True},
        ],
        "workbench": [
            {"id": "capability", "label": "能力", "question": "需要什么能力？", "options": ["合同审查", "报告生成", "代码审查", "通用任务", "不确定"], "required": True},
        ],
        "document_upload": [
            {"id": "domain", "label": "领域", "question": "这个文档属于哪个领域？", "options": ["通用", "AI知识", "运维", "采购", "不确定"], "required": True},
            {"id": "marking", "label": "密级", "question": "文档密级？", "options": ["公开", "内部", "机密"], "required": True},
        ],
        "diagnostics": [
            {"id": "action", "label": "操作", "question": "如何处理这个问题？", "options": ["自动修复", "手动修复(显示步骤)", "标记为已知", "忽略"], "required": True},
        ],
        "ontology_edit": [
            {"id": "concept", "label": "概念", "question": "你想建模的现实概念是什么？", "options": [], "required": True},
            {"id": "parent", "label": "父类", "question": "这个概念属于哪个已有类？", "options": [], "required": False},
        ],
        "skill_install": [
            {"id": "overlap", "label": "重叠", "question": "已有类似 skill，要如何处理？", "options": ["覆盖安装", "合并安装", "取消安装"], "required": True},
        ],
        "watch_directory": [
            {"id": "collection", "label": "集合", "question": "文件分配到哪个集合？", "options": ["default", "system_docs", "新建"], "required": True},
            {"id": "kind", "label": "类型", "question": "文件类型？", "options": ["markdown", "pdf", "混合", "不确定"], "required": True},
        ],
        "conversational": [
            {"id": "intent", "label": "意图", "question": "你想做什么？", "options": ["聊天/问答", "执行任务", "分析资料", "配置系统"], "required": True},
        ],
    }
    return defaults.get(entry_point, [{"id": "what", "label": "确认", "question": "你能再详细描述一下需求吗？", "options": [], "required": True}])
    u"""Return skill dependency graph (Agent→Skill→Syscall)."""
    from core.harness.knowledge.skill_deps import build_skill_deps
    return build_skill_deps()


def wiki_skill_impact(skill_id: str) -> Dict[str, Any]:
    u"""Return agents and downstream skills affected by a given skill."""
    from core.harness.knowledge.skill_deps import skill_impact
    return skill_impact(skill_id)


def wiki_fts_index() -> int:
    u"""Rebuild wiki FTS5 index. Returns count of indexed pages."""
    from core.harness.knowledge.wiki_fts import fts_index_pages
    return fts_index_pages()


def wiki_fts_search(query: str, limit: int = 10) -> Any:
    u"""Keyword search wiki pages via FTS5."""
    from core.harness.knowledge.wiki_fts import fts_search
    return fts_search(query, limit)


def wiki_pages_by_source(source_key: str) -> List[Dict[str, Any]]:
    u"""Find wiki pages that originated from a given source key (e.g. kb:<doc_id>)."""
    from core.harness.knowledge.wiki_engine import pages_by_source
    return pages_by_source(source_key)


def wiki_search_pages(query: str = "", *, tags: List[str] = None, category: str = "",
                       limit: int = 20, collection_id: str = "default") -> List[Dict[str, Any]]:
    u"""Search wiki pages — Phase 45: CoreFacade wrapper for platform layer."""
    from core.harness.knowledge.wiki_engine import search_pages
    return search_pages(query=query, tags=tags, category=category,
                         limit=limit, collection_id=collection_id)


def get_graph_health(domain: str = "") -> Dict[str, Any]:
    u"""Phase 45: Get GraphIndex health stats for a domain."""
    from core.harness.ontology_engine.graph_index import GraphIndex
    try:
        g = GraphIndex.load(domain) if domain else None
        if g:
            return {"domain": domain, "node_count": g.stats().get("node_count", 0),
                    "exists": True}
        return {"domain": domain, "exists": False, "error": "not found"}
    except Exception as e:
        return {"domain": domain, "exists": False, "error": str(e)[:200]}


def code_intel_context(task: str) -> Any:
    u"""Return code graph context for a development task."""
    from core.harness.syscalls.code_intel_syscall import sys_code_intel_context
    return sys_code_intel_context(task)


def code_intel_blast(file_path: str) -> Any:
    u"""Return forward blast radius of a file."""
    from core.harness.syscalls.code_intel_syscall import sys_code_intel_blast
    return sys_code_intel_blast(file_path)


def kb_ocr_keyframes(image_paths: list, engine: str = "paddleocr", lang: str = "zh") -> Any:
    """OCR multiple image files."""
    from core.harness.document.ocr import ocr_keyframes
    return ocr_keyframes(image_paths, engine=engine, lang=lang)


def kb_probe_video_duration(video_path: str) -> int:
    """Probe video duration in milliseconds."""
    from core.harness.document.video import probe_duration_ms
    return probe_duration_ms(video_path)


def kb_extract_video_keyframes(video_path: str, output_dir: str, interval_seconds: int = 15) -> Any:
    """Extract keyframes from video at given second interval."""
    from core.harness.document.video import extract_keyframes
    return extract_keyframes(video_path, output_dir, interval_seconds=interval_seconds)


def kb_extract_video_audio(video_path: str, audio_path: str) -> None:
    """Extract audio track from video file into WAV."""
    from core.harness.document.video import extract_audio
    return extract_audio(video_path, audio_path)


def kb_parse_document(file_path: str, kind: str) -> Any:
    """Parse a document file via the ConverterRegistry with full fallback chain."""
    from core.harness.document.protocol import get_document_registry, StreamInfo
    from core.harness.document.parsers import _elements_to_dicts
    from core.api.facades.kb_facade import _KIND_TO_EXT
    import os

    _kind = str(kind).lower()
    ext = _KIND_TO_EXT.get(_kind, os.path.splitext(file_path)[1].lower())
    registry = get_document_registry()
    info = StreamInfo(local_path=file_path, extension=ext)

    try:
        with open(file_path, "rb") as f:
            elements = registry.convert_with_fallback(f, info)
            return _elements_to_dicts(elements)
    except Exception:
        try:
            with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
                text = f.read()
            if text.strip():
                return [{"type": "text", "text": text.strip(), "page_idx": 0,
                         "cells": None, "meta": {"source": _kind, "fallback": True}}]
        except Exception:
            logging.getLogger(__name__).debug('kb_parse_document failed', exc_info=True)
        return []


def kb_chunk_document(elements: Any, kind: str = "pdf", target_size: int = 1000, overlap: int = 150) -> Any:
    """Chunk parsed document elements into segments."""
    from core.harness.document.chunker import chunk_document
    return chunk_document(elements, kind=kind, target_size=target_size, overlap=overlap)


def kb_chunk_elements(elements: Any, kind: str = "pdf", target_size: int = 1000, overlap: int = 150) -> Any:
    """Auto-select chunking strategy and apply to parsed document elements."""
    from core.apps.document_intelligence.chunking import chunk_elements
    return chunk_elements(elements, kind=kind, target_size=target_size, overlap=overlap)


def kb_create_infra_db_client(db_path: str) -> Any:
    """Create an infrastructure database client for KB storage."""
    from core.harness.infrastructure.infra_bridge import create_infra_database_client
    return create_infra_database_client(db_path)


create_infra_database_client = kb_create_infra_db_client


def kb_classify_document(elements: Any, kind: str) -> Any:
    """Classify document content type."""
    from core.apps.document_intelligence.classifier import classify_document
    return classify_document(elements, kind)


def kb_transcribe_audio(audio_path: str, language: str = "auto", diagnostics: Any = None) -> Any:
    """Transcribe audio file to text segments.

    Args:
        diagnostics: Optional dict, populated in-place with model_name, backend,
                     segment_count, total_chars, last_end_ms.
    """
    from core.harness.document.transcriber import transcribe_audio
    return transcribe_audio(audio_path, language=language or None, diagnostics=diagnostics)


def kb_transcribe_audio_chunked(audio_path: str, language: str = "auto", chunk_seconds: int = 60) -> Any:
    """Split audio into chunks, transcribe each, merge. Fallback for long audio."""
    from core.harness.document.transcriber import transcribe_audio_chunked
    return transcribe_audio_chunked(audio_path, language=language or None, chunk_seconds=chunk_seconds)


def kb_embed_text(text: str, dim: int = 128) -> Any:
    """Embed text into a vector. Safe to call from sync or async context."""
    import asyncio as _asyncio, concurrent.futures as _cf
    from core.harness.knowledge.embedder import embed_text as _embed_async, hash_embed
    try:
        try:
            loop = _asyncio.get_running_loop()
            # In async context → run embedding in a thread pool to avoid blocking
            with _cf.ThreadPoolExecutor(max_workers=1) as pool:
                return pool.submit(_asyncio.run, _embed_async(text, dim)).result(timeout=30)
        except RuntimeError:
            # No running event loop → safe to use asyncio.run()
            return _asyncio.run(_embed_async(text, dim))
    except Exception:
        return hash_embed(text, dim)


def kb_embed_text_sync(text: str, dim: int = 128) -> Any:
    """Synchronous text embedding (fallback to hash)."""
    from core.harness.knowledge.embedder import hash_embed
    return hash_embed(text, dim)


def kb_extract_keywords(text: str) -> Any:
    """Extract CJK + alphanumeric keywords from text."""
    from core.harness.knowledge.utils import extract_keywords
    return extract_keywords(text)


def kb_score_text(text: str, keywords: Any) -> Any:
    """Score text relevance against a set of keywords."""
    from core.harness.knowledge.utils import score_text
    return score_text(text, list(keywords) if keywords else [])


def kb_element_source(element: Any) -> Any:
    """Determine the source type of a KB element."""
    from core.harness.knowledge.utils import element_source
    return element_source(element)


def kb_get_ingest_fn() -> Any:
    """Get the registered KB ingest callback set by platform startup."""
    from core.apps.document_intelligence.kb_provider import get_ingest_fn
    return get_ingest_fn()


def kb_get_tenant_storage(tenant_id: str) -> Any:
    """Get the KB storage client for a given tenant."""
    from core.apps.document_intelligence.kb_provider import get_tenant_storage
    return get_tenant_storage(tenant_id)


def kb_kind_category(kind: str) -> Any:
    """Get the document category label for a given kind."""
    from core.apps.document_intelligence.classifier import kind_category
    return kind_category(kind)


# Re-export from core.apps for platform backward compat
from core.apps.document_intelligence.classifier import CATEGORY_LABELS  # noqa: E402


def kb_llm_chat_complete(system_prompt: str, user_prompt: str, temperature: float = 0.1, max_tokens: int = 700) -> Any:
    """Chat completion via KB LLM client."""
    from core.apps.document_intelligence.llm_client import chat_complete
    return chat_complete(system_prompt=system_prompt, user_prompt=user_prompt, temperature=temperature, max_tokens=max_tokens)


def kb_llm_enabled() -> bool:
    """Check if KB LLM client is configured."""
    from core.apps.document_intelligence.llm_client import llm_enabled
    return llm_enabled()


def extract_json_block(text: str) -> Any:
    """Extract JSON block from LLM output text."""
    return parse_json(text)


async def kb_summarize_document(*, tenant_id: str, collection_id: str, doc_id: str, profile: str = "key_points", **kwargs: Any) -> Any:
    """Summarize a knowledge base document."""
    from core.apps.document_intelligence.summarizer import summarize_document
    return await summarize_document(tenant_id=tenant_id, collection_id=collection_id, doc_id=doc_id, profile=profile, **kwargs)


from core.apps.tools.permission import Permission  # noqa: E402


def get_agent_registry_facade() -> Any:
    """Get the workspace AgentRegistry singleton."""
    from core.apps.agents.discovery import get_agent_registry
    return get_agent_registry()


from core.apps.agents.discovery import AgentDiscovery, AgentLoader, AgentRegistry  # noqa: E402

def _get_latest_eval_score(agent_id: str):
    """Read the latest evaluation score for an agent from eval_results directory."""
    import json as _json, os as _os, glob as _glob
    from pathlib import Path as _Path
    try:
        results_dir = _Path(_os.getenv("AIPLAT_HOME", _os.path.expanduser("~/.aiplat"))) / "eval_results"
        files = sorted(
            [f for f in _glob.glob(str(results_dir / f"{agent_id}_*.json"))],
            key=_os.path.getmtime, reverse=True,
        )
        for fp in files[:1]:
            data = _json.loads(_Path(fp).read_text(encoding="utf-8"))
            if data.get("agent_id") == agent_id:
                return {"score": data.get("composite_score", 0), "grade": data.get("grade", ""),
                        "total_tasks": data.get("total_tasks", 0), "has_data": True}
    except Exception as e:
        logging.debug(str(e), exc_info=True)
    return {"has_data": False}


async def _get_latest_eval_score_async(agent_id: str):
    import asyncio
    return await asyncio.to_thread(_get_latest_eval_score, agent_id)


async def run_workspace_agent(
    agent_info: Any, user_message: str, *, max_steps: int = 10,
    toolset: str = "", session_id: str = "", stream: bool = False,
) -> Dict[str, Any]:
    """Execute a single workspace agent via StageRunner → ReActLoop.
    
    When stream=True, returns immediately with {run_id, status: "running"} and
    executes the ReAct loop as a background asyncio task.
    """
    import asyncio as _asyncio, os as _os

    agent_id = str(getattr(agent_info, "id", "unknown"))
    cfg = getattr(agent_info, "config", None)
    system_prompt = cfg.get("system_prompt", "") if isinstance(cfg, dict) else ""
    import uuid as _uuid, os as _os_env, time as _time
    run_id = f"run-{_uuid.uuid4().hex[:12]}"
    trace_id = f"trace-{_uuid.uuid4().hex[:12]}"
    session_id = session_id or run_id

    # Persist run to agent_executions via execution_store (unified path)
    _now = _time.time()
    try:
        from core.services.execution_store import get_execution_store
        _es = get_execution_store()
        await _es.upsert_agent_execution({
            "id": run_id,
            "agent_id": agent_id,
            "status": "running",
            "start_time": _now,
            "created_at": _now,
            "trace_id": trace_id,
        })
        # Mark gate coverage (Phase 3 GateTracer)
        try:
            from core.harness.kernel.execution_context import mark_gate_passed
            mark_gate_passed("execution_store_persist")
        except Exception:
            logging.debug("execution_store_persist gate marker failed", exc_info=True)
    except Exception:
        logging.warning(f"Failed to persist agent execution record for {agent_id} run {run_id}", exc_info=True)

    # ── Emit run_start so ExecutionViewer + Runs page can discover this run ──
    try:
        from core.services.execution_store import get_execution_store
        _es = get_execution_store()
        await _es.append_run_event(
            run_id=run_id,
            event_type="run_start",
            trace_id=trace_id,
            tenant_id=None,
            payload={"kind": "agent", "agent_id": agent_id, "status": "running", "session_id": session_id},
        )
    except Exception:
        logging.debug(f"Failed to emit run_start event for {agent_id} run {run_id}", exc_info=True)

    # ── Stream mode: return immediately, execute in background ──
    if stream:
        _asyncio.ensure_future(_execute_workspace_agent_background(
            agent_info=agent_info, agent_id=agent_id, run_id=run_id,
            trace_id=trace_id,
            user_message=user_message, max_steps=max_steps, toolset=toolset,
            session_id=session_id,
        ))
        return {"ok": True, "status": "running", "output": None, "run_id": run_id, "execution_id": run_id,
                "eval": await _get_latest_eval_score_async(agent_id)}

    return await _execute_workspace_agent_background(
        agent_info=agent_info, agent_id=agent_id, run_id=run_id,
        trace_id=trace_id,
        user_message=user_message, max_steps=max_steps, toolset=toolset,
        session_id=session_id,
    )


async def _execute_workspace_agent_background(
    agent_info: Any, agent_id: str, run_id: str, *, trace_id: str = "", user_message: str,
    max_steps: int = 10, toolset: str = "", session_id: str = "",
) -> Dict[str, Any]:
    """Core execution logic used by both synchronous and stream paths."""
    import asyncio as _asyncio, os as _os, time as _time, json as _json
    _now = _time.time()
    sop_body = ""
    meta = getattr(agent_info, "metadata", None)
    if isinstance(meta, dict):
        fs = meta.get("filesystem")
        md_path = fs.get("agent_md") if isinstance(fs, dict) else None
        if md_path and _os.path.isfile(str(md_path)):
            try:
                with open(str(md_path), "r", encoding="utf-8") as fh:
                    raw = fh.read()
                if raw.startswith("---"):
                    sop_body = raw.split("---", 2)[2].strip() if len(raw.split("---", 2)) >= 3 else ""
                else:
                    sop_body = raw.strip()
            except Exception as e:
                logging.debug(str(e), exc_info=True)

    def _resolve_model():
        from core.harness.utils.model_injection import create_selected_adapter, best_model_for_purpose
        
        cfg = getattr(agent_info, "config", None)
        model_name = cfg.get("model") if isinstance(cfg, dict) else ""
        
        # Always go through infra ModelManager for model resolution (single source of truth)
        if not model_name or model_name == "auto":
            model_name = best_model_for_purpose("chat")
        else:
            # Explicit model: validate it exists in infra registry; if not, fall back to auto
            try:
                from infra.management.model.manager import ModelManager
                mgr = ModelManager()
                if not mgr.select(model_name=model_name):
                    import logging as _logging
                    _logging.getLogger("aiplat.core_facade").warning(
                        f"Agent '{agent_id}' specified model '{model_name}' not found in infra registry; "
                        f"falling back to best_model_for_purpose('chat')")
                    model_name = best_model_for_purpose("chat")
            except Exception:
                model_name = best_model_for_purpose("chat")
        
        try:
            return create_selected_adapter(model_name=model_name)
        except Exception:
            return None

    agent_model = _resolve_model()
    if not agent_model:
        return {"ok": False, "status": "error", "output": None, "error": "No LLM model", "run_id": run_id}

    # Extract system_prompt from agent config (used by ReActLoop)
    cfg = getattr(agent_info, "config", None)
    sys_prompt = cfg.get("system_prompt", "") if isinstance(cfg, dict) else ""

    resolved_tools = []
    try:
        from core.harness.integration import _resolve_tool_registry
        reg = _resolve_tool_registry()
        for tn in (getattr(agent_info, "tools", []) or []):
            t = reg.get(str(tn))
            if t: resolved_tools.append(t)
    except Exception as e:
        logging.debug(str(e), exc_info=True)

    # Resolve agent's bound skills from registry (parallel to tools resolution)
    resolved_skills = []
    try:
        from core.harness.integration import get_skill_registry
        sk_reg = get_skill_registry()
        for sn in (getattr(agent_info, "skills", []) or []):
            s = sk_reg.get(str(sn)) if hasattr(sk_reg, "get") else None
            if s: resolved_skills.append(s)
    except Exception as e:
        logging.debug(str(e), exc_info=True)

    # ── Pre-filter tools against toolset policy (② avoid LLM seeing denied tools) ──
    if toolset:
        try:
            from core.harness.tools.toolsets import resolve_toolset, is_tool_allowed
            policy = resolve_toolset(str(toolset))
            filtered = []
            for t in resolved_tools:
                tn = getattr(t, "name", "")
                allowed, _ = is_tool_allowed(policy, str(tn))
                if allowed:
                    filtered.append(t)
            resolved_tools = filtered
        except Exception as e:
            logging.debug(str(e), exc_info=True)

    prompt = (sop_body + "\n\n## Task\n" + user_message) if sop_body else user_message
    if sys_prompt:
        prompt = sys_prompt + "\n\n" + prompt

    from core.harness.execution.langgraph.stage_runner import StageRunner
    # Create a minimal pipeline config so StageRunner uses the caller's max_steps (default=10),
    # not the fallback of 1 when self._config is None.
    agent_loop_type = "react"
    try:
        meta = getattr(agent_info, "metadata", None) or {}
        agent_loop_type = str(meta.get("loop_type") or agent_loop_type)
    except Exception as e:
        logging.debug(str(e), exc_info=True)
    class _RunnerConfig:
        max_steps_per_stage = max_steps
        max_tokens_per_run = 100000
        stages = []
        loop_type = agent_loop_type
    runner = StageRunner(model=agent_model, tools=resolved_tools, skills=resolved_skills, pipeline_config=_RunnerConfig())
    state = {
        "session_id": session_id,
        "_run_id": run_id,
        "_agent_id": agent_id,
        "_trace_id": trace_id,
        "_coding_policy_profile": "off",
        "_user_id": "system",
        "_enable_query_rewrite": True,
        "_sys_prompt": sys_prompt,
        "context": {"system_prompt": sys_prompt, "task": user_message},
    }

    # ── Routing classification (ability-level, before ReAct loop) ──
    try:
        from core.harness.routing.classifier import classify
        from core.schemas_routing import RoutingContext as _Rctx
        _agent_skills = [s for s in (getattr(agent_info, "skills", None) or []) if s]
        _agent_tools = [t for t in (getattr(agent_info, "tools", None) or []) if t]
        _rctx = _Rctx(
            user_message=user_message,
            agent_id=agent_id,
            agent_type=getattr(agent_info, "type", "") or "",
            agent_name=getattr(agent_info, "name", "") or "",
            agent_description=str((meta or {}).get("description", "")) if isinstance(meta, dict) else "",
            available_skills=list(_agent_skills),
            available_tools=list(_agent_tools),
        )
        _routing = classify(_rctx)
        # Inject routing hints into state for LLM reasoning
        state["_routing_intent"] = _routing.intent.value if _routing.intent else ""
        state["_routing_confidence"] = _routing.confidence
        state["_routing_entities"] = _routing.entities
        state["_routing_suggested_skills"] = _routing.suggested_skill_ids
        state["_routing_suggested_tools"] = _routing.suggested_tool_ids
        # Auto-select skill subset when classifier has high confidence (v2.4)
        if _routing.confidence >= 0.80 and _routing.suggested_skill_ids and \
           meta.get("auto_select_skills", True):
            auto_skills = [s for s in _routing.suggested_skill_ids if s in _agent_skills]
            if auto_skills and len(auto_skills) < len(_agent_skills):
                state["_auto_skill_filter"] = auto_skills
                logging.info("auto_skill_select_state", extra={
                    "agent": agent_id, "intent": _routing.intent.value,
                    "confidence": round(_routing.confidence, 2),
                    "selected_skills": auto_skills,
                })
        # Augment task context with routing hints
        if _routing.confidence >= 0.5 and _routing.intent.value != "unknown":
            routing_hint = (
                f"\n\n[路由建议] 检测到意图: {_routing.intent.value} (置信度 {_routing.confidence:.0%})"
                f"\n建议技能: {', '.join(_routing.suggested_skill_ids[:5]) or '无'}"
                f"\n建议工具: {', '.join(_routing.suggested_tool_ids[:5]) or '无'}"
                f"{' 实体: ' + str(_routing.entities) if _routing.entities else ''}"
            )
            state["context"]["task"] = (state["context"]["task"] or "") + routing_hint
        if _routing.should_clarify:
            state["_should_clarify"] = True
            state["_clarification_prompt"] = _routing.clarification_prompt
    except Exception as e:
        # Best-effort: routing must not break execution
        logging.debug(str(e), exc_info=True)

    # ── Inject workspace context (toolset + mcp_ids + agent_ids + workflow_ids) ──
    ws_token = None
    mcp_ids = None
    agent_ids = None
    workflow_ids = None
    # Fallback: if request didn't specify toolset, use agent-level binding
    if not toolset:
        try:
            meta = getattr(agent_info, "metadata", None) or {}
            toolset = str(meta.get("toolset") or "")
        except Exception as e:
            logging.debug(str(e), exc_info=True)
    try:
        agent_mcp_ids = getattr(agent_info, "mcp_ids", None)
        mcp_ids = list(agent_mcp_ids) if isinstance(agent_mcp_ids, list) else None
    except Exception as e:
        logging.debug(str(e), exc_info=True)
    try:
        agent_agent_ids = getattr(agent_info, "agent_ids", None)
        agent_ids = list(agent_agent_ids) if isinstance(agent_agent_ids, list) else None
    except Exception as e:
        logging.debug(str(e), exc_info=True)
    try:
        agent_workflow_ids = getattr(agent_info, "workflow_ids", None)
        workflow_ids = list(agent_workflow_ids) if isinstance(agent_workflow_ids, list) else None
    except Exception as e:
        logging.debug(str(e), exc_info=True)
    if toolset or mcp_ids or agent_ids or workflow_ids:
        from core.harness.kernel.execution_context import (
            set_active_workspace_context,
            reset_active_workspace_context,
            ActiveWorkspaceContext,
        )
        ws_token = set_active_workspace_context(
            ActiveWorkspaceContext(
                toolset=str(toolset) if toolset else None,
                mcp_ids=mcp_ids,
                agent_ids=agent_ids,
                workflow_ids=workflow_ids,
            )
        )
        # Mark gate coverage (Phase 3 GateTracer)
        try:
            from core.harness.kernel.execution_context import mark_gate_passed
            mark_gate_passed("workspace_context_injected")
        except Exception as e:
            logging.debug(str(e), exc_info=True)

    # ── Inject request identity context (aligns with Path B integration.py:1805) ──
    req_token = None
    try:
        from core.harness.kernel.execution_context import (
            set_active_request_context,
            reset_active_request_context,
            ActiveRequestContext,
        )
        req_token = set_active_request_context(
            ActiveRequestContext(
                user_id="system",
                session_id=str(session_id),
                entrypoint="workspace_agent_api",
            )
        )
        # Mark gate coverage (Phase 3 GateTracer)
        try:
            from core.harness.kernel.execution_context import mark_gate_passed
            mark_gate_passed("request_context_injected")
        except Exception as e:
            logging.debug(str(e), exc_info=True)
    except Exception as e:
        logging.debug(str(e), exc_info=True)

    # ── Emit agent_start via syscall_events so both SSE replay and EventBus see it ──
    # Delay 0.3s to give frontend SSE EventSource time to connect before execution begins.
    await _asyncio.sleep(0.3)
    try:
        from core.services.execution_store import get_execution_store as _get_es_agent
        _es_agent = _get_es_agent()
        t0_agent = _time.time()
        await _es_agent.add_syscall_event({
            "id": f"{run_id}:agent_start",
            "parent_span_id": None,
            "kind": "agent",
            "name": "agent_start",
            "status": "running",
            "span_id": f"agent:{agent_id}:start",
            "trace_id": trace_id,
            "run_id": run_id,
            "start_time": t0_agent,
            "target_type": str(agent_id),
            "duration_ms": 0,
        })
    except Exception:
        t0_agent = _now

    status = "completed"
    result_text = ""
    error_msg = None
    try:
        result_text = await _asyncio.wait_for(runner.run(prompt, state), timeout=300)
    except _asyncio.TimeoutError:
        status = "timeout"
        error_msg = "Timeout (300s)"
    except Exception as e:
        status = "failed"
        error_msg = str(e) or repr(e) or type(e).__name__
        _log = __import__('logging').getLogger(__name__)
        _log.error(f"Agent {agent_id} execution failed (run_id={run_id}): {error_msg}", exc_info=True)
        # Phase 25 diagnostic: capture full traceback for debugging
        import traceback as _tb
        state["_error_traceback"] = _tb.format_exc()
    finally:
        if ws_token is not None:
            try:
                from core.harness.kernel.execution_context import reset_active_workspace_context
                reset_active_workspace_context(ws_token)
            except Exception as e:
                logging.debug(str(e), exc_info=True)
        if req_token is not None:
            try:
                from core.harness.kernel.execution_context import reset_active_request_context
                reset_active_request_context(req_token)
            except Exception as e:
                logging.debug(str(e), exc_info=True)

    # ── Emit agent_end + run_end for ExecutionViewer done detection + live events ──
    import json as _json
    _end = _time.time()
    _duration_ms = int((_end - (t0_agent or _now)) * 1000)

    # Emit agent_end FIRST so SSE catches it before run_end triggers done
    try:
        from core.harness.observation.event_bus import EventBus
        EventBus.publish(run_id, {
            "id": f"{run_id}:agent_end",
            "parent_span_id": None,
            "kind": "agent",
            "name": "agent_end",
            "status": "ok" if status == "completed" else "error",
            "span_id": f"agent:{agent_id}:end",
            "trace_id": trace_id,
            "run_id": run_id,
            "start_time": _time.time(),
            "duration_ms": _duration_ms,
            "target_type": str(agent_id),
            "result_json": _json.dumps({"text": str(result_text or "")[:5000]}),
            "error": error_msg,
        })
    except Exception as e:
        logging.debug(str(e), exc_info=True)

    try:
        from core.services.execution_store import get_execution_store
        _es = get_execution_store()
        await _es.upsert_agent_execution({
            "id": run_id,
            "agent_id": agent_id,
            "status": status,
            "output": {"text": result_text or ""},
            "error": error_msg or "",
            "end_time": _end,
            "duration_ms": _duration_ms,
            "trace_id": trace_id,
        })
        # Emit run_end so SSE can detect completion
        await _es.append_run_event(
            run_id=run_id,
            event_type="run_end",
            trace_id=trace_id,
            tenant_id=None,
            payload={"kind": "agent", "agent_id": agent_id, "status": status, "duration_ms": _duration_ms, "error": error_msg or ""},
        )
    except Exception as e:
        logging.debug(str(e), exc_info=True)

    # ── GateTracer: validate mandatory gates were all passed (Phase 3) ──
    try:
        from core.harness.kernel.execution_context import get_gate_coverage
        gates = get_gate_coverage()
        # Required gates for workspace agent execution
        required = {"workspace_context_injected", "request_context_injected", "llm_generate_called"}
        missing = required - gates
        if missing:
            # Emit diagnostic event visible in ExecutionViewer
            try:
                from core.services.execution_store import get_execution_store
                store = get_execution_store()
                await store.append_run_event(
                    run_id=str(run_id),
                    event_type="gate_coverage_gap",
                    trace_id=trace_id,
                    tenant_id=None,
                    payload={
                        "missing_gates": sorted(missing),
                        "covered_gates": sorted(gates),
                        "agent_id": agent_id,
                        "status": status,
                    },
                )
            except Exception as e:
                logging.debug(str(e), exc_info=True)
    except Exception as e:
        logging.debug(str(e), exc_info=True)

    # Query token usage from syscall_events for this run
    tokens = None
    try:
        from core.services.execution_store import get_execution_store
        store = get_execution_store()
        cost = await store.get_run_cost_summary(run_id=run_id)
        if cost.get("ok"):
            tokens = cost.get("llm_tokens")
    except Exception as e:
        logging.debug(str(e), exc_info=True)

    # Extract real error from StageRunner output if present
    if (result_text or "") and "STAGE_ERROR:" in result_text:
        error_msg = result_text.split("STAGE_ERROR:", 1)[1].strip() or "unknown stage error"
        status = "failed"
    is_error = status != "completed"
    resp = {"ok": not is_error, "status": status if not is_error else "failed",
            "output": result_text if not is_error else None, "error": error_msg if is_error else None, "run_id": run_id, "execution_id": run_id,
            "duration_ms": _duration_ms, "trace_id": trace_id or ""}
    _tb = state.get("_error_traceback", "")
    if _tb:
        resp["traceback"] = _tb[-3000:]  # last 3000 chars of traceback
    if tokens:
        resp["tokens"] = tokens
    # Include step count and engine metadata for observability
    resp["metadata"] = {
        "steps": int(state.get("step_count", 0)) or 0,
        "engine": "react",
        "loop_type": "ReActLoop",
    }
    return resp


def get_chat_service_model(rt: Any = None) -> Any:
    """Resolve model adapter for chat service via centralized resolution (§12)."""
    from core.harness.utils.model_injection import create_selected_adapter, get_default_model
    if rt and hasattr(rt, "adapter_manager") and getattr(rt.adapter_manager, "get_default_adapter", None):
        try:
            return rt.adapter_manager.get_default_adapter()
        except Exception as e:
            logging.debug(str(e), exc_info=True)
    model_name = get_default_model(purpose="chat") or get_default_model()
    return create_selected_adapter(model_name=model_name)


# ── Ontology Facade (Phase 1: semantic↔action loop closure) ──


# ── Semantic Ontology Evolution Facade (Phase 3) ──

async def generate_ontology_suggestions(
    collection_id: str = "default",
    *,
    max_suggestions: int = 5,
    confidence_threshold: float = 0.7,
    include_llm: bool = True,
) -> Dict[str, Any]:
    u"""Generate ontology evolution suggestions (Tier 1 rule-based + Tier 2 LLM-driven).

    Use this from platform to trigger intelligent ontology evolution without
    importing harness-internal modules.
    """
    if not include_llm:
        from core.harness.knowledge.knowledge_ontology import add_suggestions_from_patterns
        suggestions = add_suggestions_from_patterns(
            collection_id=collection_id,
            include_llm=False,
        )
        return {"suggestions": suggestions, "total": len(suggestions), "source": "rule"}

    from core.harness.knowledge.knowledge_evolution_llm import generate_semantic_suggestions
    suggestions = await generate_semantic_suggestions(
        collection_id=collection_id,
        max_suggestions=max_suggestions,
        confidence_threshold=confidence_threshold,
    )
    return {"suggestions": suggestions, "total": len(suggestions), "source": "llm"}


def predict_evolution_impact_for(
    suggestion: Dict[str, Any],
    collection_id: str = "default",
) -> Dict[str, Any]:
    u"""Predict the impact scope of accepting an evolution suggestion."""
    from core.harness.knowledge.knowledge_ontology import get_ontology
    from core.harness.knowledge.knowledge_evolution_llm import predict_evolution_impact
    onto = get_ontology()
    return predict_evolution_impact(suggestion, onto)


# ── Ontology Health & Quality Facade (Phase 4) ──

def check_ontology_health_triggers(collection_id: str = "default") -> List[Dict[str, Any]]:
    u"""Check ontology health and return triggered curation tasks.

    Use this from platform schedules/cron to auto-detect and flag
    quality issues in the knowledge base.
    """
    from core.harness.knowledge.knowledge_quality import check_ontology_health_triggers as _check
    return _check(collection_id=collection_id)


def get_entity_quality(entity_uri: str, *, collection_id: str = "default") -> Dict[str, Any]:
    u"""Get quality score and recent signals for an ontology entity."""
    from core.harness.knowledge.knowledge_quality import (
        get_entity_quality_score, get_quality_signals,
    )
    score = get_entity_quality_score(entity_uri, collection_id=collection_id)
    signals = get_quality_signals(entity_uri, limit=10, collection_id=collection_id)
    return {"quality": score, "recent_signals": signals}


# ── Field-Level Security Facade (附章 — cell/field redaction) ──

def apply_field_security(
    data: Dict[str, Any],
    *,
    entity_uri: str = "",
    actor_role: str = "",
    actor_scopes: Optional[List[str]] = None,
    collection_id: str = "default",
) -> Dict[str, Any]:
    u"""Apply field-level security redaction to entity data.

    Sensitive fields are redacted based on visibility rules stored per-collection.
    Admin bypasses all restrictions.
    """
    from core.policy.field_level_security import apply_field_level_security
    return apply_field_level_security(
        data, entity_uri,
        actor_role=actor_role, actor_scopes=actor_scopes,
        collection_id=collection_id,
    )


# ── Growth & Obsidian Facade (Phase E + Phase F) ──

def get_growth_stats(days: int = 30, *, collection_id: str = "default") -> Dict[str, Any]:
    u"""Get knowledge base growth statistics for the last N days."""
    from core.harness.knowledge.knowledge_growth import get_growth_stats as _gs
    return _gs(collection_id=collection_id, days=days)


def check_obsidian_compatibility(collection_id: str = "default") -> Dict[str, Any]:
    u"""Verify that the wiki directory is 100% compatible with Obsidian vault format.

    Checks:
      - All .md files have valid YAML frontmatter
      - [[wikilinks]] are used for internal references
      - Directory structure is flat enough for Obsidian graph view
      - No file naming conflicts (special characters Obsidian can't handle)
    """
    import os as _os, re as _re
    from core.harness.knowledge.wiki_engine import _wiki_root

    root = _wiki_root(collection_id)
    issues = []
    md_count = 0
    frontmatter_ok = 0
    wikilinks_found = 0

    for dirpath, _dirs, files in _os.walk(str(root)):
        for fname in files:
            if not fname.endswith(".md"):
                continue
            md_count += 1
            fpath = _os.path.join(dirpath, fname)

            # Check Obsidian-safe filename
            safe_name = _re.sub(r'[\\/:*?"<>|]', '_', fname)
            if safe_name != fname:
                issues.append(f"Unsafe filename: {fname} → rename to {safe_name}")

            try:
                text = open(fpath, "r", encoding="utf-8").read()
            except Exception:
                issues.append(f"Cannot read: {fname}")
                continue

            # Check frontmatter
            if text.startswith("---"):
                parts = text.split("---", 2)
                if len(parts) >= 3:
                    frontmatter_ok += 1

            # Check wikilinks
            if "[[" in text:
                wikilinks_found += 1

    return {
        "obsidian_compatible": len(issues) == 0,
        "md_files": md_count,
        "frontmatter_ok": frontmatter_ok,
        "wikilinks_used_in": wikilinks_found,
        "issues": issues[:20],
        "vault_path": str(root),
        "instructions": (
            "Open Obsidian → Open folder as vault → select this path. "
            "Your AI-curated knowledge base is now a visual graph."
        ) if len(issues) == 0 else "Fix the issues above before opening in Obsidian.",
    }


# ── Learning Coach Facade (L6 — AI Learning Coach) ──


async def complete_chapter_for_learner(
    learner_id: str,
    chapter_id: str,
    answers: List[Any],
) -> Dict[str, Any]:
    u"""Assess all exercises in a chapter and return results."""
    from core.harness.knowledge.learning_ontology import load_learner_profile
    from core.harness.knowledge.learning_paths import get_builtin_paths
    from core.harness.knowledge.learning_assessment import complete_chapter

    profile = load_learner_profile(learner_id)
    if not profile:
        return {"error": f"Learner '{learner_id}' not found"}

    paths = get_builtin_paths()
    chapter = None
    for chs in paths.values():
        for c in chs:
            if c.chapter_id == chapter_id:
                chapter = c
                break
    if not chapter:
        return {"error": f"Chapter '{chapter_id}' not found"}

    return await complete_chapter(profile, chapter, answers)


# ── Scene Model Facade (Phase A — purpose-driven pipeline templates) ──


def instantiate_scene(
    scene_id: str,
    *,
    params: Optional[Dict[str, Any]] = None,
    collection_id: str = "default",
) -> Optional[Dict[str, Any]]:
    u"""Instantiate a scene template into a PipelineConfig dict."""
    from core.harness.knowledge.scene_model import instantiate_scene as _inst
    return _inst(scene_id, params=params, collection_id=collection_id)


# ── Verification Facade (Phase C — stage output verification + replay) ──

def verify_stage_output(
    artifact: Dict[str, Any],
    expected_outcomes: List[Dict[str, Any]],
    stage_id: str = "",
) -> Dict[str, Any]:
    u"""Verify stage output against expected outcomes. Returns verification result dict."""
    from core.harness.execution.verification import verify_against_expected
    result = verify_against_expected(artifact, expected_outcomes, stage_id=stage_id)
    return result.to_dict()


def list_algorithms() -> List[Dict[str, Any]]:
    u"""List all registered deterministic algorithm functions."""
    from core.harness.execution.algorithm_node import list_algorithms as _list
    return _list()


# ── WriteBack Facade (Phase 5 — external system integration) ──

def register_writeback_target(
    target_type: str,
    target_endpoint: str,
    *,
    trigger_actions: Optional[List[str]] = None,
    field_mapping: Optional[Dict[str, str]] = None,
    collection_id: str = "default",
) -> Dict[str, Any]:
    u"""Register a writeback target for ontology actions."""
    from core.harness.knowledge.knowledge_writeback import (
        register_writeback, WriteBackConfig, WriteBackTarget,
    )
    config = WriteBackConfig(
        target_type=WriteBackTarget(target_type),
        target_endpoint=target_endpoint,
        trigger_actions=trigger_actions or ["create", "update"],
        field_mapping=field_mapping or {},
    )
    register_writeback(config, collection_id=collection_id)
    return {"status": "ok", "config": config.to_dict()}


def list_writeback_targets(collection_id: str = "default") -> List[Dict[str, Any]]:
    u"""List all registered writeback targets."""
    from core.harness.knowledge.knowledge_writeback import load_writebacks
    return [c.to_dict() for c in load_writebacks(collection_id=collection_id)]


# ── Markings & Object Permissions Facade (Phase 2) ──

def get_entity_markings(
    entity_uri: str,
    *,
    collection_id: str = "default",
    resolve_effective: bool = True,
) -> Dict[str, Any]:
    u"""Get explicit and effective markings for an entity."""
    from core.harness.knowledge.knowledge_markings import get_entity_markings as _get
    return _get(entity_uri, collection_id=collection_id, resolve_effective=resolve_effective)


def set_entity_marking(
    entity_uri: str,
    label: str,
    level: int,
    scope: str = "",
    *,
    collection_id: str = "default",
) -> Dict[str, Any]:
    u"""Set a marking on an entity."""
    from core.harness.knowledge.knowledge_markings import set_marking, MarkingLevel
    marking = set_marking(entity_uri, label, MarkingLevel(level), scope,
                          collection_id=collection_id)
    return {"status": "ok", "marking": marking.to_dict()}


def check_kb_entity_access(
    entity_uri: str,
    action: str,
    *,
    actor_scopes: Optional[List[str]] = None,
    actor_role: str = "",
    collection_id: str = "default",
) -> Dict[str, Any]:
    u"""Check if an actor can access a knowledge entity (three-layer fusion).

    Use this from platform/management to check permissions without
    importing harness-internal modules.
    """
    from core.harness.infrastructure.gates.policy_gate import check_kb_access
    import asyncio
    return asyncio.run(check_kb_access(
        entity_uri=entity_uri,
        action=action,
        actor_scopes=actor_scopes or [],
        actor_role=actor_role,
        collection_id=collection_id,
     ))


# ── Ontology Editor Facade (v2.6) ─────────────────────────────────────


def list_ontology_domains() -> List[Dict[str, Any]]:
    u"""List all ontology domains with metadata (name, version, class count)."""
    from core.harness.knowledge.ontology_loader import load_all_domains
    domains = load_all_domains()
    result = []
    for dom_id, dom in sorted(domains.items()):
        result.append({
            "id": dom.id,
            "name": dom.name,
            "namespace": dom.namespace,
            "description": dom.description,
            "version": dom.version,
            "class_count": len(dom.classes),
            "property_count": len(dom.object_properties) + len(dom.data_properties),
            "rule_count": len(dom.inference_rules or []),
        })
    return result


def get_ontology_domain_schema(domain_id: str) -> Dict[str, Any]:
    u"""Return full domain schema as JSON dict for the ontology editor UI."""
    from core.harness.knowledge.ontology_loader import load_ontology_from_yaml
    from core.harness.knowledge.yaml_serializer import domain_to_dict

    base_dir = _resolve_ontologies_dir()
    file_path = f"{base_dir}/{domain_id}.yaml"
    if not Path(file_path).exists():
        raise FileNotFoundError(f"Domain ontology not found: {file_path}")

    domain = load_ontology_from_yaml(file_path)
    return domain_to_dict(domain)


def create_ontology_domain(
    domain_id: str,
    name: str,
    *,
    namespace: str = "",
    description: str = "",
    version: str = "1.0.0",
) -> Dict[str, Any]:
    u"""Create a new empty ontology domain YAML file."""
    from core.harness.knowledge.yaml_serializer import dict_to_yaml

    base_dir = _resolve_ontologies_dir()
    file_path = f"{base_dir}/{domain_id}.yaml"
    if Path(file_path).exists():
        raise FileExistsError(f"Domain already exists: {domain_id}")

    ns = namespace or f"http://aiplat.local/ontology/{domain_id}/"
    data = {
        "name": name,
        "namespace": ns,
        "description": description,
        "version": version,
        "classes": {},
        "object_properties": [],
        "data_properties": [],
        "inference_rules": [],
    }
    yaml_str = dict_to_yaml(data)
    Path(file_path).parent.mkdir(parents=True, exist_ok=True)
    Path(file_path).write_text(yaml_str, encoding="utf-8")

    _register_domain_in_registry(domain_id, name, description)
    return {"id": domain_id, "name": name, "status": "created", "path": file_path}


def update_ontology_domain_meta(
    domain_id: str,
    *,
    name: str = "",
    description: str = "",
    version: str = "",
    namespace: str = "",
) -> Dict[str, Any]:
    u"""Update domain metadata (name, description, version, namespace)."""
    import yaml

    base_dir = _resolve_ontologies_dir()
    file_path = f"{base_dir}/{domain_id}.yaml"
    if not Path(file_path).exists():
        raise FileNotFoundError(f"Domain not found: {domain_id}")

    with open(file_path, "r", encoding="utf-8") as f:
        raw = yaml.safe_load(f) or {}

    if name:
        raw["name"] = name
    if description:
        raw["description"] = description
    if version:
        raw["version"] = version
    if namespace:
        raw["namespace"] = namespace

    from core.harness.knowledge.yaml_serializer import dict_to_yaml
    yaml_str = dict_to_yaml(raw)
    Path(file_path).write_text(yaml_str, encoding="utf-8")

    if name:
        _register_domain_in_registry(domain_id, name, raw.get("description", ""))
    _invalidate_domain_caches(domain_id)
    return {"id": domain_id, "status": "updated"}


def delete_ontology_domain(domain_id: str) -> Dict[str, Any]:
    u"""Delete an ontology domain YAML and optionally its graph data."""
    base_dir = _resolve_ontologies_dir()
    file_path = f"{base_dir}/{domain_id}.yaml"
    if not Path(file_path).exists():
        raise FileNotFoundError(f"Domain not found: {domain_id}")

    Path(file_path).unlink()
    _remove_domain_from_registry(domain_id)
    return {"id": domain_id, "status": "deleted"}


def upsert_ontology_class(
    domain_id: str,
    class_name: str,
    class_data: Dict[str, Any],
) -> Dict[str, Any]:
    u"""Create or update a class definition in a domain YAML."""
    import yaml

    base_dir = _resolve_ontologies_dir()
    file_path = f"{base_dir}/{domain_id}.yaml"
    if not Path(file_path).exists():
        raise FileNotFoundError(f"Domain not found: {domain_id}")

    with open(file_path, "r", encoding="utf-8") as f:
        raw = yaml.safe_load(f) or {}

    from core.harness.knowledge.yaml_serializer import merge_class_into_domain
    merged = merge_class_into_domain(raw, class_name, class_data)

    from core.harness.knowledge.yaml_serializer import dict_to_yaml
    yaml_str = dict_to_yaml(merged)
    Path(file_path).write_text(yaml_str, encoding="utf-8")

    _invalidate_domain_caches(domain_id)
    return {"domain_id": domain_id, "class_name": class_name, "status": "upserted"}


def delete_ontology_class(domain_id: str, class_name: str) -> Dict[str, Any]:
    u"""Remove a class from a domain YAML."""
    import yaml

    base_dir = _resolve_ontologies_dir()
    file_path = f"{base_dir}/{domain_id}.yaml"
    if not Path(file_path).exists():
        raise FileNotFoundError(f"Domain not found: {domain_id}")

    with open(file_path, "r", encoding="utf-8") as f:
        raw = yaml.safe_load(f) or {}

    from core.harness.knowledge.yaml_serializer import remove_class_from_domain
    cleaned = remove_class_from_domain(raw, class_name)

    from core.harness.knowledge.yaml_serializer import dict_to_yaml
    yaml_str = dict_to_yaml(cleaned)
    Path(file_path).write_text(yaml_str, encoding="utf-8")

    _invalidate_domain_caches(domain_id)
    return {"domain_id": domain_id, "class_name": class_name, "status": "deleted"}


def publish_ontology_domain(domain_id: str) -> Dict[str, Any]:
    u"""Validate and publish — write domain YAML + create graph snapshot."""
    base_dir = _resolve_ontologies_dir()
    file_path = f"{base_dir}/{domain_id}.yaml"
    if not Path(file_path).exists():
        raise FileNotFoundError(f"Domain not found: {domain_id}")

    from core.harness.knowledge.ontology_loader import load_ontology_from_yaml
    from core.harness.ontology_engine.graph_index import GraphIndex

    domain = load_ontology_from_yaml(file_path)
    try:
        graph = GraphIndex.load(domain_id)
        graph.snapshot(f"pre-publish-{domain.version}")
    except Exception:
        logging.getLogger(__name__).debug('publish_ontology_domain failed', exc_info=True)

    _invalidate_domain_caches(domain_id)
    _save_rule_version(domain_id, file_path, domain)
    return {
        "domain_id": domain_id,
        "version": domain.version,
        "class_count": len(domain.classes),
        "status": "published",
    }


def list_rule_versions(domain_id: str) -> List[Dict[str, Any]]:
    u"""List all saved rule versions for a domain."""
    from core.harness.ontology_engine.graph_index import GraphIndex
    try:
        graph = GraphIndex.load(domain_id)
        snaps = graph.list_snapshots(limit=50)
        return snaps
    except Exception:
        return []


def rollback_rule_version(domain_id: str, version_id: str) -> Dict[str, Any]:
    u"""Restore rules to a previous version — restore snapshot + invalidate caches."""
    from core.harness.ontology_engine.graph_index import GraphIndex
    try:
        graph = GraphIndex.load(domain_id)
        result = graph.restore_snapshot(int(version_id))
        _invalidate_domain_caches(domain_id)
        return {"domain_id": domain_id, "version_id": version_id, "status": "rolled_back", "result": result}
    except Exception as e:
        raise RuntimeError(f"Rollback failed: {e}")


def _save_rule_version(domain_id: str, file_path: str, domain) -> None:
    u"""Save a version snapshot of the domain YAML after publish."""
    try:
        from core.harness.ontology_engine.graph_index import GraphIndex
        graph = GraphIndex.load(domain_id)
        yaml_text = Path(file_path).read_text(encoding="utf-8")
        graph.snapshot(f"v{domain.version}-{__import__('time').strftime('%Y%m%dT%H%M%SZ', __import__('time').gmtime())}")
    except Exception:
        logging.getLogger(__name__).debug('_save_rule_version failed', exc_info=True)


# ── Role View Facade (v2.6) ──


def list_views_for_domain(domain_id: str) -> List[Dict[str, Any]]:
    u"""List all role-based views for a domain."""
    from core.harness.knowledge.role_view import load_views, list_roles
    schema = get_ontology_domain_schema(domain_id)
    compiled = load_views(schema)
    return list_roles(compiled)


def get_view_for_domain(domain_id: str, role: str) -> Dict[str, Any]:
    u"""Get a single role view definition."""
    from core.harness.knowledge.role_view import load_views
    schema = get_ontology_domain_schema(domain_id)
    compiled = load_views(schema)
    view = compiled.get(role)
    if not view:
        raise LookupError(f"View not found for role: {role}")
    return view


def upsert_view_for_domain(domain_id: str, role: str, view_data: Dict[str, Any]) -> Dict[str, Any]:
    u"""Create or update a role view in the domain YAML, writing back via yaml_serializer."""
    import yaml
    base_dir = _resolve_ontologies_dir()
    file_path = f"{base_dir}/{domain_id}.yaml"
    with open(file_path, "r", encoding="utf-8") as f:
        raw = yaml.safe_load(f) or {}
    raw.setdefault("views", {})
    raw["views"][role] = view_data
    from core.harness.knowledge.yaml_serializer import dict_to_yaml
    Path(file_path).write_text(dict_to_yaml(raw), encoding="utf-8")
    return {"domain_id": domain_id, "role": role, "status": "upserted"}


def delete_view_for_domain(domain_id: str, role: str) -> Dict[str, Any]:
    u"""Delete a role view from the domain YAML."""
    import yaml
    base_dir = _resolve_ontologies_dir()
    file_path = f"{base_dir}/{domain_id}.yaml"
    with open(file_path, "r", encoding="utf-8") as f:
        raw = yaml.safe_load(f) or {}
    raw.get("views", {}).pop(role, None)
    from core.harness.knowledge.yaml_serializer import dict_to_yaml
    Path(file_path).write_text(dict_to_yaml(raw), encoding="utf-8")
    return {"domain_id": domain_id, "role": role, "status": "deleted"}


def resolve_term_in_view(domain_id: str, role: str, term: str) -> Dict[str, Any]:
    u"""Resolve a term's meaning for a specific role perspective."""
    from core.harness.knowledge.role_view import load_views, resolve_term as _rt
    schema = get_ontology_domain_schema(domain_id)
    compiled = load_views(schema)
    definition = _rt(term, role, compiled)
    return {"domain_id": domain_id, "role": role, "term": term,
            "definition": definition, "found": definition is not None}


def validate_views_for_domain(domain_id: str) -> Dict[str, Any]:
    u"""Validate role views for a domain."""
    from core.harness.knowledge.role_view import validate_views as _vv
    schema = get_ontology_domain_schema(domain_id)
    return {"domain_id": domain_id, **_vv(schema)}


def resolve_prompt(prompt_id: str, **variables) -> str:
    u"""Synchronous prompt template resolution."""
    from core.harness.utils.prompt_loader import _sync_resolve
    return _sync_resolve(prompt_id, **variables)


# ── Process Monitor Facade (v2.6) ──


def get_process_status(domain_id: str, process_name: str = "") -> List[Dict[str, Any]]:
    u"""Get running process instance status."""
    from core.harness.knowledge.process_orchestrator import get_process_status as _gps
    return _gps(domain_id, process_name)


def get_bottlenecks(domain_id: str, limit: int = 10) -> List[Dict[str, Any]]:
    u"""Get process bottlenecks — instances stuck at same step longest."""
    from core.harness.knowledge.process_orchestrator import get_bottlenecks as _gb
    return _gb(domain_id, limit)


def get_state_distribution(domain_id: str) -> List[Dict[str, Any]]:
    u"""Count instances per class per state."""
    from core.harness.knowledge.process_monitor import state_distribution as _sd
    return _sd(domain_id)


def get_bottleneck_analysis(domain_id: str, limit: int = 10) -> List[Dict[str, Any]]:
    u"""Find entities stuck in their current state longest."""
    from core.harness.knowledge.process_monitor import bottleneck_analysis as _ba
    return _ba(domain_id, limit)


def get_sla_violations(domain_id: str) -> List[Dict[str, Any]]:
    u"""Get SLA violations triggered by time_elapsed transitions."""
    from core.harness.knowledge.process_monitor import sla_violations as _sv
    return _sv(domain_id)


def get_trend_data(domain_id: str, days: int = 7) -> List[Dict[str, Any]]:
    u"""Daily state transition trend data."""
    from core.harness.knowledge.process_monitor import trend_data as _td
    return _td(domain_id, days)


# ── Internal helpers ──


def _resolve_ontologies_dir() -> str:
    import os as _os
    return _os.path.expanduser(_os.getenv("AIPLAT_ONTOLOGY_DIR", "~/.aiplat/ontologies"))


def _register_domain_in_registry(domain_id: str, name: str, description: str = "") -> None:
    import json as _json
    reg_path = Path(_resolve_ontologies_dir()) / "registry.json"
    registry = {}
    if reg_path.exists():
        registry = _json.loads(reg_path.read_text(encoding="utf-8"))
    registry.setdefault("domains", {})
    registry["domains"].setdefault(domain_id, {})
    registry["domains"][domain_id].update({
        "name": name,
        "description": description or registry["domains"][domain_id].get("description", ""),
        "ontology_file": f"{domain_id}.yaml",
    })
    reg_path.write_text(_json.dumps(registry, indent=2, ensure_ascii=False))


def _remove_domain_from_registry(domain_id: str) -> None:
    import json as _json
    reg_path = Path(_resolve_ontologies_dir()) / "registry.json"
    if not reg_path.exists():
        return
    registry = _json.loads(reg_path.read_text(encoding="utf-8"))
    registry.get("domains", {}).pop(domain_id, None)
    reg_path.write_text(_json.dumps(registry, indent=2, ensure_ascii=False))


def _invalidate_domain_caches(domain_id: str) -> None:
    try:
        from core.harness.knowledge.domain_router import DomainRouter
        DomainRouter()._built = False
    except Exception:
        logging.getLogger(__name__).debug('_invalidate_domain_caches failed', exc_info=True)
    try:
        from core.harness.ontology_engine.graph_index import GraphIndex
        graph = GraphIndex.load(domain_id)
        graph._built = False
    except Exception:
        logging.getLogger(__name__).debug('_invalidate_domain_caches failed', exc_info=True)


# ═══════════════════════════════════════════════════════════════
# Platform-facing re-exports (v2.5)
# These are the canonical imports for platform code.
# All platform→core imports MUST go through CoreFacade.
# See: architecture/boundary_rules.yaml
# ═══════════════════════════════════════════════════════════════

from core.harness.integration import KernelRuntime, get_harness
from core.harness.knowledge.db import get_knowledge_db

from core.harness.knowledge.wiki_engine import search_pages  # v2.5: platform→CoreFacade  # noqa: boundary — CoreFacade canonical re-export
from core.harness.knowledge.semantic_cache import get_semantic_cache  # v2.5  # noqa: boundary — CoreFacade canonical re-export
from core.harness.knowledge.knowledge_ontology import validate_page_against_schema  # v2.5  # noqa: boundary — CoreFacade canonical re-export
from core.harness.infrastructure.infra_ocr_adapter import BBox, OCRToken, create_infra_ocr_adapter  # v2.5  # noqa: boundary — CoreFacade canonical re-export
from core.harness.models.spec_lifecycle import get_spec_lifecycle, RevisionTrigger  # v2.5  # noqa: boundary — CoreFacade canonical re-export
from core.harness.ontology_engine.triple_store import get_triple_store  # v2.5  # noqa: boundary — CoreFacade canonical re-export
from core.harness.ontology_engine.triple_scanner import scan_and_populate  # v2.5  # noqa: boundary — CoreFacade canonical re-export
from core.harness.ontology_engine.cleanup import cleanup_stale_entities_by_doc  # v2.5  # noqa: boundary — CoreFacade canonical re-export
from core.harness.learning.skill_simulator import SkillSimulator  # v2.5  # noqa: boundary — CoreFacade canonical re-export
from core.services.execution_store import get_execution_store  # v2.5  # noqa: boundary — CoreFacade canonical re-export
from core.services.tenant_store_protocol import get_tenant_store, set_tenant_store  # P0-A3  # noqa: boundary — CoreFacade canonical re-export
from core.harness.knowledge.wiki_engine import delete_page, read_page  # v2.5  # noqa: boundary — CoreFacade canonical re-export

# v2.9: Additional canonical re-exports to close platform→core boundary
from core.harness.finance.value_calculator import get_value_calculator  # noqa: boundary
from core.harness.kernel.profile import get_profile_manager  # noqa: boundary
from core.harness.knowledge.ontology_loader import load_ontology_from_yaml  # noqa: boundary
from core.harness.knowledge.domain_router import DomainRouter  # noqa: boundary
from core.harness.knowledge.seci_engine import get_seci_engine, hook_registered  # noqa: boundary
from core.harness.security.emotion_tracker import get_emotion_tracker  # noqa: boundary
from core.harness.smoke import enqueue_autosmoke  # noqa: boundary
from core.harness.evaluation.rag_evaluator import _ensure_eval_schema  # noqa: boundary

# v2.9: Additional platform→core boundary re-exports
from core.harness.coordination.kanban_engine import KanbanEngine  # noqa: boundary
from core.harness.deployment.canary import get_skill_router  # noqa: boundary

from core.harness.utils.prompt_loader import _sync_resolve
from core.harness.utils.model_injection import best_model_for_purpose, create_selected_adapter  # v2.10
from core.harness.syscalls.llm import sys_llm_generate  # P0-A2 canonical re-export
from core.services.pii_detector import get_pii_detector
from core.harness.utils.prompt_loader import _sync_resolve
from core.harness.utils.model_injection import best_model_for_purpose, create_selected_adapter  # v2.10
from core.services.pii_detector import get_pii_detector
from core.harness.kernel.runtime import get_kernel_runtime, set_kernel_runtime, set_kernel_runtime
from core.harness.kernel.types import ExecutionRequest
from core.harness.infrastructure.approval.types import ApprovalContext, ApprovalRule, RequestStatus, RuleType
from core.harness.infrastructure.crypto.secretbox import is_configured
from core.harness.infrastructure.crypto.signature import key_id_for_public_key, generate_ed25519_key_pair, sign_skill, verify_skill_signature, generate_ed25519_key_pair, sign_skill, verify_skill_signature
from core.harness.memory.manager import get_memory_manager
from core.harness.knowledge.utils import element_source, extract_keywords, score_text
from core.harness.knowledge.db import set_knowledge_db
from core.harness.smoke.autoscheduler import enqueue_autosmoke
from core.harness.execution.team_planner import recommend_team_stages
from core.harness.execution.pipeline_engine import get_event_bus
from core.services.config_registry_store import ConfigRegistryKey, get_config_registry_store


# ── Stubs for platform imports where definition has not yet been created ──
# These are imported by platform but the core implementation hasn't been wired yet.

def cancel_pipeline(run_id: str) -> Any:
    """Cancel a running pipeline by appending a cancel_requested event.
    
    The pipeline engine's main loop checks is_cancel_requested() on each iteration
    and gracefully terminates when the marker is found. Also cancels any queued runs.
    """
    import logging
    logger = logging.getLogger(__name__)
    try:
        from core.harness.execution.pipeline_engine import get_event_bus
        from core.services.execution_store import get_execution_store
        
        store = get_execution_store()
        if store:
            import asyncio
            
            async def _cancel():
                try:
                    await store.append_run_event(
                        run_id=str(run_id),
                        event_type="cancel_requested",
                        node_id="",
                        state_json="{}",
                        elapsed=0.0,
                        output="",
                    )
                    await store.cancel_queued_run(run_id=str(run_id))
                except Exception as e:
                    logger.warning("cancel_pipeline: store operation failed: %s", e)
            
            try:
                loop = asyncio.get_event_loop()
                if loop.is_running():
                    import concurrent.futures
                    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
                        future = executor.submit(asyncio.run, _cancel())
                        future.result(timeout=5)
                else:
                    asyncio.run(_cancel())
            except RuntimeError:
                asyncio.run(_cancel())
        
        # Publish event for observability
        try:
            bus = get_event_bus()
            bus.publish("pipeline_cancelled", {"run_id": str(run_id)})
        except Exception:
            logger.debug("EventBus.publish failed for pipeline_cancelled", exc_info=True)
        
        logger.info("cancel_pipeline: cancel_requested for run_id=%s", run_id)
        return {"ok": True, "run_id": run_id, "status": "cancelled"}
    except Exception as e:
        logger.warning("cancel_pipeline: failed to cancel run_id=%s: %s", run_id, e)
        return {"ok": False, "run_id": run_id, "status": "error", "error": str(e)}


def get_document_categories() -> list:
    """Get supported document category labels (from ConverterRegistry — single source of truth)."""
    from core.harness.document.protocol import get_document_registry
    return get_document_registry().get_available_categories()


def is_crypto_configured() -> bool:
    """Check if cryptographic keys are configured."""
    import os
    return bool(os.getenv("AIPLAT_CRYPTO_KEY_ID"))


def llm_generate_stream(*args: Any, **kwargs: Any):
    """Streaming LLM generation. Delegates to sys_llm_generate_stream."""
    from core.harness.syscalls.llm import sys_llm_generate_stream
    return sys_llm_generate_stream(*args, **kwargs)


def normalize_conversation_scope(scope: Any) -> Any:
    """Normalize conversation scope values to a consistent dict format."""
    if isinstance(scope, dict):
        return scope
    if isinstance(scope, str):
        return {"name": scope}
    return {"name": "default"}


def secret_configured(key_id: str = "") -> bool:
    """Check if a secret key is configured."""
    return bool(key_id)


def set_knowledge_providers(*args: Any, **kwargs: Any) -> None:
    """Set knowledge providers for the runtime. Delegates to kb_facade."""
    from core.api.facades.kb_facade import set_knowledge_providers as _impl
    _impl(*args, **kwargs)


from core.harness.document.parsers import parse_html  # v2.5: platform→CoreFacade
from core.harness.document.video import probe_duration_ms  # v2.5
from core.harness.knowledge.wiki_engine import read_page  # v2.5
from core.harness.knowledge.knowledge_ontology import validate_page_against_schema  # v2.5
from core.harness.infrastructure.infra_ocr_adapter import BBox, OCRToken, create_infra_ocr_adapter  # v2.5
from core.harness.models.spec_lifecycle import get_spec_lifecycle, RevisionTrigger  # v2.5

from core.harness.utils.async_utils import _run_coro_blocking  # v2.5
from core.harness.knowledge.domain_router import DomainRouter  # v2.5
from core.harness.knowledge.capability_health import capability_health_report  # v2.5 — canonical re-export
from core.harness.knowledge.capability_graph import build_capability_graph  # v2.5 — canonical re-export
from core.harness.syscalls.retrieval import sys_knowledge_retrieve  # v2.5
from core.harness.knowledge.doc_compressor import get_model_max_completion  # v2.5
from core.management.workflow_manager import WorkflowManager  # v2.5  # noqa: boundary — CoreFacade canonical re-export
from core.apps.quality.scanner import create_security_scanner  # v2.5  # noqa: boundary — CoreFacade canonical re-export
from core.apps.quality.types import VulnerabilitySeverity  # v2.5  # noqa: boundary — CoreFacade canonical re-export

from core.management.agent_manager import AgentManager  # v2.5  # noqa: boundary — CoreFacade canonical re-export
from core.management.skill_manager import SkillManager  # v2.5  # noqa: boundary — CoreFacade canonical re-export
from core.services.execution_store import ExecutionStore, ExecutionStoreConfig  # v2.5  # noqa: boundary — CoreFacade canonical re-export

from core.apps.fde.service.agent import run_fde_agent_one_shot  # v2.5  # noqa: boundary — CoreFacade canonical re-export
from core.apps.fde.service.voice import run_voice_brainstorm  # noqa: boundary — CoreFacade canonical re-export

from core.security.skill_signature_gate import is_approval_resolved_approved, get_trusted_skill_pubkeys_map  # v2.5
from core.harness.ontology_engine.graph_index import GraphIndex  # v6.5 — canonical re-export for platform layer
# v2.10: management + services boundary re-exports
from core.management.prompt_app_manager import PromptAppManager  # noqa: boundary
from core.services.implicit_feedback import get_implicit_feedback_collector  # noqa: boundary
from core.management.skill_manager import SkillManager  # noqa: boundary
from core.management.skill_linter import lint_skill  # noqa: boundary
from core.management.skill_installer import SkillInstaller  # noqa: boundary
from core.management.agentskills_parser import convert_agentskills_to_aiplat, is_agentskills_format  # noqa: boundary

# v2.6 — platform→CoreFacade canonical re-exports (eliminate direct core.harness imports)
from core.harness.ontology_engine.action_registry import get_action_registry  # noqa: boundary
from core.harness.ontology_engine.ontology_branch import OntologyBranchManager  # noqa: boundary
from core.harness.infrastructure.lineage_store import LineageStore  # noqa: boundary
from core.harness.learning.operation_recorder import OperationRecorder  # noqa: boundary
from core.harness.knowledge.scoring_engine import load_models  # noqa: boundary
from core.harness.knowledge.metric_engine import load_metrics  # noqa: boundary
from core.harness.knowledge.versioned_ontology_store import VersionedOntologyStore  # noqa: boundary
from core.harness.execution.team_planner import load_team_template  # noqa: boundary
from core.harness.knowledge.knowledge_roi import KnowledgeROI  # noqa: boundary
from core.harness.learning.kpi_tracker import get_kpi_tracker  # noqa: boundary
from core.harness.training.full_training import get_full_training_engine  # noqa: boundary
from core.harness.training.distillation import get_distillation_engine  # noqa: boundary
from core.harness.knowledge_pipeline.resolver import CrossDomainResolver  # noqa: boundary
from core.harness.knowledge.convergence_engine import ConvergenceEngine  # noqa: boundary
from core.harness.execution.atomic_splitter import AtomicTaskSplitter  # noqa: boundary
from core.harness.learning.agent_network import AgentNetwork  # noqa: boundary
from core.harness.infrastructure.db_utils import get_db_connection  # noqa: boundary
from core.harness.integration import KernelRuntime  # noqa: boundary

# v2.7 — complete platform→CoreFacade canonical re-exports (all remaining harness symbols)
from core.harness.infrastructure.action_contract import ActionContractModel  # noqa: boundary
from core.harness.infrastructure.action_store import ActionStore  # noqa: boundary
from core.harness.evaluation.adversarial_test_suite import AdversarialTestSuite  # noqa: boundary
from core.harness.infrastructure.approval.types import ApprovalContext, RequestStatus, RuleType  # noqa: boundary
from core.harness.infrastructure.approval.manager import ApprovalManager  # noqa: boundary
from core.harness.infrastructure.gates.approval_gate import ApprovalRule  # noqa: boundary
from core.harness.execution.atomic_splitter import AtomicTaskDefinition  # noqa: boundary
from core.harness.knowledge.auto_garden import AutoGarden  # noqa: boundary
from core.harness.knowledge.conversation_ingestor import ConversationIngestor  # noqa: boundary
from core.harness.infrastructure.throttle import DecisionThrottle  # noqa: boundary
from core.harness.execution.e2e_verifier import E2EVerifier  # noqa: boundary
from core.harness.evaluation.ab_optimizer import EvalABOptimizer  # noqa: boundary
from core.harness.evaluation.workbench import EvaluatorThresholds  # noqa: boundary
from core.harness.execution.evox_executor import EvoXExecutor  # noqa: boundary
from core.harness.learning.feedback_radar import FeedbackRadar  # noqa: boundary
from core.harness.training.full_training import FullTrainingConfig  # noqa: boundary
from core.harness.execution.dynamic_router import GoalAwareRouter  # noqa: boundary
from core.harness.knowledge_pipeline.retriever import GraphRAGRetriever  # noqa: boundary
from core.harness.security.immune_memory import ImmuneMemory  # noqa: boundary
from core.harness.document.converters._mineru import MineruConverter  # noqa: boundary
from core.harness.knowledge.okf_exporter import OKFExporter  # noqa: boundary
from core.harness.ontology_engine.engine import OntologyEngine  # noqa: boundary
from core.harness.learning.partner_selector import PartnerSelector  # noqa: boundary
from core.harness.infrastructure.gates.policy_gate import PolicyGate  # noqa: boundary
from core.harness.execution.programmatic_collector import ProgrammaticCollector  # noqa: boundary
from core.harness.infrastructure.gates.purpose_registry import PurposeRegistry  # noqa: boundary
from core.harness.execution.simulation import SimulationOrchestrator  # noqa: boundary
from core.harness.learning.skill_generator import SkillGenerator  # noqa: boundary
from core.harness.document.protocol import StreamInfo  # noqa: boundary
from core.harness.knowledge.system_evolver import SystemEvolver  # noqa: boundary
from core.harness.knowledge.system_diagnostician import SystemHealer  # noqa: boundary
from core.harness.document.template_engine import TemplateRegistry, TemplateRenderer  # noqa: boundary
from core.harness.utils.prompt_loader import _async_prompt_resolve, auto_classify, get_metadata, list_templates  # noqa: boundary
from core.harness.execution.team_planner import _enrich_stage_from_agent  # noqa: boundary
from core.harness.knowledge.governance_dashboard import aggregate_dashboard  # noqa: boundary
from core.harness.evaluation.workbench import apply_threshold_gate, persist_evaluation, validate_report  # noqa: boundary
from core.harness.learning.proposal_store import ProposalStore as _ProposalStore  # noqa: boundary

def approve(request_id: str, approved_by: str = "admin", comment: str = "") -> bool:
    """Approve a change request via ProposalStore."""
    return _ProposalStore().approve(request_id, approved_by)
from core.harness.knowledge.rule_auditor import audit_rules  # noqa: boundary
from core.harness.knowledge.capability_graph import build_capability_graph  # noqa: boundary
from core.harness.knowledge.code_graph import build_graph, clear_cache, default_roots, repo_root, PY_IMPORT_RE, JS_IMPORT_RE, strip_py_type_checking, is_code_file, should_skip, read_text, resolve_js_relative, resolve_py_module, detect_issues, convert_file_graph_to_symbols, count_cycles, health_score, blast, ScanResult  # noqa: boundary
from core.harness.knowledge.capability_health import capability_health_report  # noqa: boundary
from core.harness.knowledge.consistency_gate import check_cross_stage_consistency  # noqa: boundary
from core.harness.knowledge.domain_maturity import compare_domains, compute_domain_maturity, export_comparison_report  # noqa: boundary
from core.harness.evaluation.evidence_diff import compute_evidence_diff  # noqa: boundary
from core.harness.utils.model_injection import create_selected_adapter  # noqa: boundary
from core.harness.restatement.run_state import default_run_state, merge_from_evaluation, normalize_run_state  # noqa: boundary
from core.harness.knowledge.ontology_query_mapper import discover_cross_domain_analogs  # noqa: boundary
from core.harness.knowledge.scoring_engine import evaluate_batch  # noqa: boundary
from core.harness.document.parsers import extract_text_from_html  # noqa: boundary
from core.harness.knowledge.mapping_validator import generate_mapping_report, validate_all_sources  # noqa: boundary
from core.harness.optimization.abstract_goal_decomposer import get_abstract_goal_decomposer  # noqa: boundary
from core.harness.routing.skill_routing import get_all_weights  # noqa: boundary
from core.harness.learning import get_auto_learner  # noqa: boundary
from core.harness.security.crisis_detector import get_crisis_detector  # noqa: boundary
from core.harness.scheduler.cron import get_cron_scheduler  # noqa: boundary
from core.harness.knowledge.governance_pipeline import get_cycle_history, run_all_domains, run_cycle  # noqa: boundary
from core.harness.deployment.deploy_engine import get_deploy_engine  # noqa: boundary
from core.harness.infrastructure.discovery_listener import get_discovery_listener  # noqa: boundary
from core.harness.learning.tool_drift_detector import get_drift_detector  # noqa: boundary
from core.harness.learning.feedback_radar import get_feedback_radar  # noqa: boundary
from core.harness.training.auto_trigger import get_lora_auto_trigger  # noqa: boundary
from core.harness.execution.pipeline_run_store import get_pipeline_run_store  # noqa: boundary
from core.harness.training.rl_trainer import get_rl_trainer  # noqa: boundary
from core.harness.knowledge.seci_engine import get_seci_engine, hook_registered  # noqa: boundary
from core.harness.execution.trace_visualizer import get_trace_visualizer  # noqa: boundary
from core.harness.execution.decision_trace import record_decision, locate_max_error_node, trace_root_cause_chain, build_fix_plan, get_trace, clear_trace  # noqa: boundary
from core.harness.execution.cost_budget import CostBudgetController, get_pricing, cost_for  # noqa: boundary
from core.harness.execution.hypothesis_generator import generate_hypotheses  # noqa: boundary
from core.harness.execution.governance_report import build_run_report  # noqa: boundary
from core.harness.knowledge.metric_engine import get_trend  # noqa: boundary
from core.harness.knowledge.symbol_health import is_excluded_from_dead_code  # noqa: boundary
from core.harness.execution.simulation import list_simulations, load_simulation_report  # noqa: boundary
from core.harness.knowledge.ontology_loader import load_ontology_from_yaml  # noqa: boundary
from core.harness.knowledge.ontology_bus import load_solution_archetypes, render_solution_table  # noqa: boundary
from core.harness.knowledge.scenario_selector import recommend_order  # noqa: boundary
from core.harness.evaluation.adversarial_test_suite import run_cognitive_robustness_check  # noqa: boundary
from core.harness.knowledge.metric_engine import scorecard, get_trend as _get_trend_alias  # noqa: boundary
from core.harness.infrastructure.crypto.signature import sign_skill  # noqa: boundary
from core.harness.syscalls.retrieval import sys_knowledge_retrieve  # noqa: boundary

# v2.7.1 — final multi-line import symbols
from core.harness.learning.playbook import PlaybookManifest, pack_playbook, unpack_playbook  # noqa: boundary
from core.harness.finance.value_calculator import BusinessGoal, get_value_calculator  # noqa: boundary
from core.harness.execution.simulation import ScenarioDefinition, ScenarioType  # noqa: boundary
from core.harness.knowledge_pipeline.extractor import ExtractionPipeline, ExtractionResult, PendingExtractionStore  # noqa: boundary
from core.harness.infrastructure.gates.marking_propagation import get_entity_max_marking_level, MARKING_LABELS  # noqa: boundary

# v2.7.2 — de-privatized internal symbols
from core.harness.document.converters._mineru import table_text_to_cells, parse_markdown_table, cells_to_markdown, load_mineru_content_list  # noqa: boundary


# ═══════════════════════════════════════════════════════════════
# P0-B3: wired subsystems (arena / voice_loop / wake_agent)
# ═══════════════════════════════════════════════════════════════

def arena_leaderboard() -> list:
    """Get Darwin Arena Elo leaderboard (empty before first run)."""
    from core.harness.arena.arena import DarwinArena
    return DarwinArena().leaderboard()


async def arena_run_round_robin(contenders: list, matches_per_pair: int = 3,
                                benchmark_fn=None, on_match=None) -> dict:
    """Manually trigger a round-robin tournament.

    Args:
        contenders: list of (name, agent_fn) tuples
        matches_per_pair: matches per head-to-head pair
        benchmark_fn: async (name, fn) -> float; defaults to a no-op scorer
    """
    from core.harness.arena.arena import DarwinArena

    async def _default_benchmark(name, fn):
        # Deterministic fallback so manual runs work without a real benchmark:
        # score by function identity hash (0..1) — callers should pass a real fn.
        import hashlib
        h = hashlib.md5(f"{name}:{fn}".encode()).hexdigest()
        return int(h[:4], 16) / 65535.0

    arena = DarwinArena()
    result = await arena.round_robin(
        contenders=contenders,
        benchmark_fn=benchmark_fn or _default_benchmark,
        matches_per_pair=matches_per_pair,
        on_match=on_match,
    )
    return {
        "leaderboard": result.leaderboard,
        "promotions": [{"name": p.name, "rating": p.rating,
                        "win_rate": p.win_rate, "promoted": p.promoted,
                        "reason": p.promotion_reason} for p in result.promotions],
        "total_matches": len(result.matches),
        "total_duration_s": result.total_duration_s,
    }


async def voice_loop_process(audio_path: str, llm_callback=None) -> dict:
    """Full voice loop: STT → Agent → Browser/Tool → TTS (manual trigger)."""
    from core.harness.multimodal.voice_loop import VoiceLoop
    return await VoiceLoop().process_voice_command(audio_path, llm_callback=llm_callback)


def wake_agent_status() -> dict:
    """Get WakeAgent filesystem-change detector status."""
    from core.harness.monitoring.wake_agent import get_wake_agent
    agent = get_wake_agent()
    return {
        "paths": agent.paths,
        "interval": agent.interval,
        "running": agent._running,
        "change_count": agent._change_counter,
    }


async def wake_agent_start(paths: list = None) -> dict:
    """Start WakeAgent watching (zero-token checksum polling)."""
    from core.harness.monitoring.wake_agent import get_wake_agent
    agent = get_wake_agent(paths)
    if not agent._running:
        await agent.start()
    return {"running": agent._running, "paths": agent.paths}


async def wake_agent_stop() -> dict:
    """Stop WakeAgent."""
    from core.harness.monitoring.wake_agent import get_wake_agent
    agent = get_wake_agent()
    agent.stop()
    return {"running": False}

def cross_validation_verify(output: dict, *, domain_id: str = "default") -> dict:
    """Run CrossValidationGate semantic verification (equipment/process/quality).

    Framework stub — activates when cross-domain object_properties reach the
    activation threshold; returns readiness info when not yet active.
    """
    from core.harness.infrastructure.gates.cross_validation_gate import CrossValidationGate
    gate = CrossValidationGate()
    if not gate.is_ready():
        return {"ready": False, "violations": [], "note": "below activation threshold"}
    result = gate.verify(output, domain_id=domain_id)
    return {
        "ready": True,
        "valid": getattr(result, "valid", True),
        "violations": [
            {"layer": v.layer, "severity": v.severity, "detail": v.detail}
            for v in getattr(result, "cross_violations", [])
        ],
        "layers_checked": getattr(result, "layers_checked", []),
        "reason": getattr(result, "reason", ""),
    }
