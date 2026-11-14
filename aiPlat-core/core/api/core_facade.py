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
from core.utils.paths import get_aiplat_home, get_aiplat_data_dir

import os
from pathlib import Path
from typing import Any, Dict, List, Optional
import logging
from core.harness.utils.llm_env import get_llm_api_key, get_llm_base_url
from core.harness.utils.model_injection import best_model_for_purpose
from core.harness.knowledge.ontology_yaml_gate import LiveYamlDirectWriteDenied, assert_live_yaml_write
from core.harness.knowledge.ontology_case_learning import OntologyCase  # noqa: F401 — facade re-export / wiring
from core.harness.evaluation.code_review_gold import GoldCase, GoldFinding  # noqa: F401 — facade re-export / wiring


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
    """Create a PipelineEngine instance. Use this instead of importing。

    Args:
        config: config 参数。
        model: 模型名。
        skill_loader: skill_loader 参数。
    """
    from core.harness.execution.pipeline_engine import PipelineEngine
    return PipelineEngine(config=config, model=model, skill_loader=skill_loader)


def register_pipeline(project_id: str, engine: Any) -> None:
    """Register a running pipeline engine (pipeline registry singleton).

    Args:
        project_id: project 标识。
        engine: engine 参数。
    """
    from core.harness.execution.pipeline_engine import register_pipeline as _r
    _r(project_id, engine)


def get_running_pipeline(project_id: str) -> Any:
    """Get the running pipeline engine for a project, if any.

    Args:
        project_id: project 标识。
    """
    from core.harness.execution.pipeline_engine import get_running_pipeline as _g
    return _g(project_id)


def unregister_pipeline(project_id: str) -> None:
    """Unregister a finished/terminated pipeline engine.

    Args:
        project_id: project 标识。
    """
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

    Args:
        agent_type: agent_type 参数。
        config: config 参数。
        model: 模型名。
        system_prompt: system_prompt 参数。
    """
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


def build_security_view(**kwargs: Any) -> Any:
    """Compile deterministic security view (secview.v1) from code_graph.

    Args:
        kwargs: kwargs 参数。
    """
    from core.harness.knowledge.security_view import build_security_view as _build

    return _build(**kwargs).to_dict()


def get_security_view(**kwargs: Any) -> Any:
    """Return cached-or-fresh security view dict (secview.v1).

    Args:
        kwargs: kwargs 参数。
    """
    return build_security_view(**kwargs)


def security_view_digest(**kwargs: Any) -> Any:
    """Token-budgeted digest for Agent plan stage.

    Args:
        kwargs: kwargs 参数。
    """
    from core.harness.knowledge.security_view import (
        build_security_view as _build,
        compact_security_digest,
    )

    sv = _build(**kwargs)
    return compact_security_digest(sv)


def _run_async_handler(coro: Any) -> Any:
    import asyncio
    import concurrent.futures

    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(coro)
    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
        return pool.submit(asyncio.run, coro).result()


def run_security_plan(**kwargs: Any) -> Any:
    """Phase B plan stage (deterministic handler). Returns filtered digest dict.

    Args:
        kwargs: kwargs 参数。
    """
    from core.engine.skills.security_plan.handler import execute as _plan_execute

    return _run_async_handler(_plan_execute(dict(kwargs)))


def run_security_review_dry(**kwargs: Any) -> Any:
    """Phase B(+optional C) dry-run: plan→trace→critique→report→evidence.

    Args:
        kwargs: kwargs 参数。
    """
    from core.engine.skills.security_critique.handler import execute as _critique
    from core.engine.skills.security_evidence.handler import (
        execute as _evidence,
        merge_evidence_into_report,
    )
    from core.engine.skills.security_plan.handler import execute as _plan
    from core.engine.skills.security_report.handler import execute as _report
    from core.engine.skills.security_trace.handler import execute as _trace

    phase_c = bool(kwargs.pop("phase_c_enabled", False) or kwargs.pop("enabled", False))
    plan_kwargs = dict(kwargs)

    plan = _run_async_handler(_plan(plan_kwargs))
    trace = _run_async_handler(_trace({"security_plan": plan}))
    critique = _run_async_handler(
        _critique({"security_plan": plan, "security_trace": trace})
    )
    report = _run_async_handler(
        _report(
            {
                "security_plan": plan,
                "security_trace": trace,
                "security_critique": critique,
            }
        )
    )
    evidence = _run_async_handler(
        _evidence(
            {
                "security_report": report,
                "security_critique": critique,
                "enabled": phase_c,
                "max_findings": int(kwargs.get("max_findings") or 5),
            }
        )
    )
    if evidence.get("enabled"):
        report = merge_evidence_into_report(report, evidence)
    return {
        "status": "ok",
        "phase": "C" if evidence.get("enabled") else "B",
        "security_plan": plan,
        "security_trace": trace,
        "security_critique": critique,
        "security_report": report,
        "security_evidence": evidence,
    }


def get_domain_router() -> Any:
    """Get DomainRouter for multi-domain classification (process singleton)."""
    from core.harness.knowledge.domain_router import get_domain_router as _get

    return _get()


def domain_router_route_stats() -> Dict[str, Any]:
    """Process-wide DomainRouter T1/T2/T3 + T2 boundary/reject + T3 latency (Ollaya Phase 0)."""
    from core.harness.knowledge.domain_router import get_domain_router as _get

    return dict(_get().route_stats() or {})


def decision_shadow_status() -> Dict[str, Any]:
    """Muted decision-shadow skeleton status (default off; classify not hooked)."""
    from core.harness.decision_shadow import get_shadow_dispatcher

    return dict(get_shadow_dispatcher().status() or {})


def decision_shadow_try_enqueue(payload: Dict[str, Any]) -> bool:
    """Non-blocking enqueue probe (honors enabled=false; no classify hook).

    Args:
        payload: 载荷 dict。
    """
    from core.harness.decision_shadow import get_shadow_dispatcher

    return bool(get_shadow_dispatcher().try_enqueue(dict(payload or {})))


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


def get_skill_marketplace(db_path: str = "") -> Any:
    """Get SkillMarketplace (P1-A5 agentskills.io 对接, CoreFacade canonical 入口).

    Args:
        db_path: db_path 参数。
    """
    from core.harness.knowledge.skill_marketplace import SkillMarketplace
    return SkillMarketplace(db_path=db_path) if db_path else SkillMarketplace()


def list_pending_heal_fixes() -> Any:
    """List pending self-heal fixes awaiting human approval."""
    from core.harness.evaluation.self_heal_gate import SelfHealGate
    return SelfHealGate().list_pending()


def approve_heal_fix(fix_id: str) -> Any:
    """Approve and apply a pending self-heal fix.

    Args:
        fix_id: fix 标识。
    """
    from core.harness.evaluation.self_heal_gate import SelfHealGate
    return SelfHealGate().approve_fix(fix_id)


def reject_heal_fix(fix_id: str, reason: str = "") -> Any:
    """Reject a pending self-heal fix.

    Args:
        fix_id: fix 标识。
        reason: reason 参数。
    """
    from core.harness.evaluation.self_heal_gate import SelfHealGate
    return SelfHealGate().reject_fix(fix_id, reason)


def get_fde_pipeline_health() -> Any:
    """Get FDE pipeline health stats (via handler registry)."""
    return dispatch("fde_pipeline_health")


def get_fde_health() -> Any:
    """Get full FDE health check (via handler registry)."""
    return dispatch("fde_health")


def fde_clarify(**kwargs: Any) -> Any:
    """Run FDE clarification (via handler registry).

    Args:
        kwargs: kwargs 参数。
    """
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
    """Call LLM through the syscall boundary. Use this instead of importing。

    Args:
        model: 模型名。
        prompt: prompt 参数。
        kwargs: kwargs 参数。
    """
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
        """初始化。

        Args:
            agent_name: agent_name 参数。
            session_id: 会话 ID。
            user_input: user_input 参数。
            user_id: 用户 ID。
            extra_context: extra_context 参数。
            model: 模型名。
        """
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
        """初始化。

        Args:
            reply: reply 参数。
            trace_id: trace 标识。
            skills_used: skills_used 参数。
            memory_saved: memory_saved 参数。
            prd_ready: prd_ready 参数。
        """
        self.reply = reply
        self.trace_id = trace_id
        self.skills_used = skills_used or []
        self.memory_saved = memory_saved
        self.prd_ready = prd_ready


async def core_chat(ctx: ChatContext) -> ChatResult:
    """Execute a conversational agent turn with automatic subsystem activation.

    Args:
        ctx: ctx 参数。
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
                get_aiplat_data_dir("workspace_seeds"))
            md_path = _os.path.join(seeds, "agents", ctx.agent_name, "AGENT.md")
            if not _os.path.exists(md_path):
                md_path = get_aiplat_data_dir(f"agents/{ctx.agent_name}/AGENT.md")
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

    Args:
        raw: raw 参数。
    """
    from core.harness.execution.pipeline_engine import PipelineEngine
    result = PipelineEngine._parse_output(raw)
    return {
        "artifact": result.artifact,
        "issues": [i.model_dump() for i in result.issues],
        "confidence": result.confidence.value,
        "decision": result.decision.value,
    }


def get_agent_frontmatter(agent_id: str) -> Dict[str, Any]:
    """Load AGENT.md frontmatter for an agent. Looks in:。

    Args:
        agent_id: Agent ID。
    """
    import os
    import yaml

    agent_home = get_aiplat_data_dir(f"agents/{agent_id}/AGENT.md")
    seeds = os.getenv("AIPLAT_WORKSPACE_SEEDS",
        get_aiplat_data_dir("workspace_seeds"))
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
    """Get a CodeGenerationSkill instance. Use this instead of importing。

    Args:
        model: 模型名。
    """
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
    """Get a secret by name. Falls back to env var if no SecretsManager.

    Args:
        name: name 参数。
    """
    from core.harness.infrastructure.secrets_manager import get_secrets_manager
    return get_secrets_manager().get(name)


def set_secret(name: str, value: str) -> None:
    """Store a secret (encrypted at rest via AES-256-GCM).

    Args:
        name: name 参数。
        value: value 参数。
    """
    from core.harness.infrastructure.secrets_manager import get_secrets_manager
    get_secrets_manager().set(name, value)


# ── Router-facing facade extensions (Category 2 fix) ──

def get_permission_manager() -> Any:
    """Get the PermissionManager singleton via DI or direct import."""
    from core.apps.tools.permission import get_permission_manager as _get
    return _get()

def resolve_skill_permission(skill_name: str) -> str:
    """Resolve skill permission level via DI or direct import.

    Args:
        skill_name: skill_name 参数。
    """
    from core.apps.tools.skill_tools import resolve_skill_permission as _get
    return _get(skill_name)

def resolve_executable_skill_permission(skill_name: str) -> str:
    """Resolve executable skill permission via DI or direct import.

    Args:
        skill_name: skill_name 参数。
    """
    from core.apps.tools.skill_tools import resolve_executable_skill_permission as _get
    return _get(skill_name)

async def get_exec_backend() -> Any:
    """Get the ExecBackend singleton via DI or direct import."""
    from core.apps.exec_drivers.registry import get_exec_backend as _get
    return await _get()

async def scan_security(code: str) -> Any:
    """Run security scan on code via quality scanner.

    Args:
        code: code 参数。
    """
    from core.apps.quality.scanner import create_security_scanner
    scanner = create_security_scanner()
    return scanner.scan(code)


# ═══════════════════════════════════════════════════════════════
# Service wrappers — Platform MUST use these instead of importing
# core.services.* classes directly.
# ═══════════════════════════════════════════════════════════════

def create_chat_service(model: Any = None) -> Any:
    """Create a ChatService instance. Use instead of importing。

    Args:
        model: 模型名。
    """
    from core.services.chat_service import ChatService
    return ChatService(model=model)


def create_conversation_service(store: Any = None) -> Any:
    """Create a ConversationService instance. Use instead of importing。

    Args:
        store: store 参数。
    """
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
        """初始化。

        Args:
            engine: engine 参数。
            config: config 参数。
        """
        self._engine = engine
        self._config = config

    @property
    def engine(self) -> Any:
        """engine。
        """
        return self._engine

    async def start(self, project_id: str, requirement: str, prd_data: Any = None) -> Dict[str, Any]:
        """Start pipeline execution. Returns initial state snapshot.

        Args:
            project_id: project 标识。
            requirement: requirement 参数。
            prd_data: prd_data 参数。
        """
        result = await self._engine.initialize(project_id, requirement, prd_data=prd_data)
        return result

    async def approve(self, state: Dict[str, Any], feedback: str = "") -> Dict[str, Any]:
        """HITL approval: resume pipeline from current HITL pause.

        Args:
            state: state 参数。
            feedback: feedback 参数。
        """
        return await self._engine.approve_session(dict(state), feedback=feedback)

    async def reject(self, state: Dict[str, Any], feedback: str = "") -> Dict[str, Any]:
        """HITL rejection: provide feedback and resume pipeline.

        Args:
            state: state 参数。
            feedback: feedback 参数。
        """
        return await self._engine.reject_session(dict(state), feedback)

    async def rollback(self, state: Dict[str, Any], stage_id: str) -> Dict[str, Any]:
        """Rollback pipeline to a previous stage.

        Args:
            state: state 参数。
            stage_id: stage 标识。
        """
        return await self._engine.rollback(dict(state), stage_id)

    async def resume_from(self, stage_idx: int, state: Dict[str, Any]) -> Dict[str, Any]:
        """Resume pipeline execution from a specific stage index.

        Args:
            stage_idx: stage_idx 参数。
            state: state 参数。
        """
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
        """Assemble a deploy directory from pipeline output artifacts.

        Args:
            state: state 参数。
        """
        return self._engine.assemble_deploy(dict(state))


def create_pipeline_session(
    config: Any,
    model: Any = None,
    skill_loader: Any = None,
    persist_callback: Any = None,
) -> PipelineSession:
    """Create a PipelineSession. Use this instead of importing and instantiating。

    Args:
        config: config 参数。
        model: 模型名。
        skill_loader: skill_loader 参数。
        persist_callback: persist_callback 参数。
    """
    from core.harness.execution.pipeline_engine import PipelineEngine
    engine = PipelineEngine(config=config, model=model, skill_loader=skill_loader,
                            persist_callback=persist_callback)
    return PipelineSession(engine=engine, config=config)


def validate_pipeline_stages(stages: List[Any]) -> Dict[str, Any]:
    """Validate pipeline stage configuration. Returns diagnostics dict。

    Args:
        stages: stages 参数。
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

    # ── Change Contract 产物 key 链校验（SBA 原则 12, 2026-08-26） ──
    # 语义翻译（PRD→stage）与实现绑定（stage 产物 key）由同一契约贯通：
    # 下游 stage 的 input_artifacts 引用必须存在于上游 output_artifact 中（或内置来源），
    # 防止"上游改了产物 key、下游仍读旧 key"的隐性断裂。
    output_keys = set()
    for st in stages:
        _oa = getattr(st, 'output_artifact', '') or ''
        if _oa:
            output_keys.add(_oa)
    _builtin_inputs = {"description", "user_input", "requirement", "start.inputs"}
    for st in stages:
        prefix = f"stage[{stages.index(st)}]"
        sid = getattr(st, 'id', f'stage_{stages.index(st)}')
        for ia in (getattr(st, 'input_artifacts', None) or []):
            if isinstance(ia, str) and ia.strip() and ia not in output_keys and ia not in _builtin_inputs:
                diagnostics["errors"].append(
                    f"{prefix} ({sid}): input_artifact '{ia}' 无上游 output_artifact 提供"
                    "（Change Contract 断裂——上游产物 key 与下游消费不一致）"
                )

    diagnostics["valid"] = len(diagnostics["errors"]) == 0
    return diagnostics


def apply_agent_md_to_stage(stage: Any, agent_id: str) -> None:
    """Read AGENT.md frontmatter and apply fields to a PipelineStageConfig.

    Args:
        stage: stage 参数。
        agent_id: Agent ID。
    """
    import os
    import yaml

    # Find AGENT.md
    agent_home = get_aiplat_data_dir(f"agents/{agent_id}/AGENT.md")
    seeds = os.getenv("AIPLAT_WORKSPACE_SEEDS",
        get_aiplat_data_dir("workspace_seeds"))
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

    # E1: optional architecture_profile on AGENT.md pins execution mix.
    _ap = str(fm.get("architecture_profile") or "").strip().lower()
    if _ap:
        stage.architecture_profile = _ap
        try:
            from core.schemas_builder import apply_architecture_profile

            apply_architecture_profile(stage)
        except Exception:
            logging.getLogger(__name__).debug(
                "apply_architecture_profile from AGENT.md skipped", exc_info=True
            )
    _eb = str(fm.get("execution_backend") or "").strip().lower()
    if _eb in ("llm", "agent") and not _ap:
        # Explicit backend without profile — still a pin (matrix §3).
        stage.execution_backend = _eb


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
    """Record a governance changeset. Use this instead of importing from。

    Args:
        resource_type: resource_type 参数。
        resource_id: resource 标识。
        action: action 参数。
        before: before 参数。
        after: after 参数。
        tenant_id: 租户 ID。
        actor_id: actor 标识。
        metadata: metadata 参数。
    """
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
    """Apply autosmoke verification result. Use instead of importing。

    Args:
        verification_id: verification 标识。
        result: result 参数。
        resource_type: resource_type 参数。
        resource_id: resource 标识。
        job_run: job_run 参数。
    """
    from core.governance.verification import apply_autosmoke_result as _fn
    _fn(verification_id, result, resource_type=resource_type,
        resource_id=resource_id, job_run=job_run)


def mark_resource_pending(resource_type: str, resource_id: str,
                          *, workspace_agent_manager: Any = None,
                          workspace_skill_manager: Any = None,
                          workspace_mcp_manager: Any = None) -> None:
    """Mark a resource as pending verification. Use instead of importing。

    Args:
        resource_type: resource_type 参数。
        resource_id: resource 标识。
        workspace_agent_manager: workspace_agent_manager 参数。
        workspace_skill_manager: workspace_skill_manager 参数。
        workspace_mcp_manager: workspace_mcp_manager 参数。
    """
    from core.governance.verification import mark_resource_pending as _fn
    _fn(resource_type=resource_type, resource_id=resource_id,
         workspace_agent_manager=workspace_agent_manager,
         workspace_skill_manager=workspace_skill_manager,
         workspace_mcp_manager=workspace_mcp_manager)


def evaluate_tool_policy_snapshot(policy: Dict[str, Any], *, tool_name: str) -> Dict[str, Any]:
    """Evaluate a tool policy snapshot. Use instead of importing。

    Args:
        policy: policy 参数。
        tool_name: tool_name 参数。
    """
    from core.policy.engine import evaluate_tool_policy_snapshot as _fn
    return _fn(policy, tool_name=tool_name)


# ── Execution snapshot self-service facade (P1-2: user-facing checkpoint recovery) ──

def list_execution_snapshots(session_id: str) -> List[Dict[str, Any]]:
    """List all execution snapshots for a session (newest first).

    Args:
        session_id: 会话 ID。
    """
    from core.harness.execution.snapshot import list_execution_snapshots as _fn
    return _fn(session_id)


def get_execution_snapshot(snapshot_id: str, session_id: str) -> Optional[Dict[str, Any]]:
    """Load a single execution snapshot header + full state for recovery.

    Args:
        snapshot_id: snapshot 标识。
        session_id: 会话 ID。
    """
    from core.harness.execution.snapshot import load_execution_snapshot as _fn
    snap = _fn(snapshot_id, session_id)
    if snap is None:
        return None
    out = snap.to_dict()
    out["full_state"] = snap.full_state
    return out


def compare_execution_snapshots(snapshot_a_id: str, snapshot_b_id: str, session_id: str) -> Dict[str, Any]:
    """Diff two execution snapshots (before/after strategy effect).

    Args:
        snapshot_a_id: snapshot_a 标识。
        snapshot_b_id: snapshot_b 标识。
        session_id: 会话 ID。
    """
    from core.harness.execution.snapshot import compare_execution_snapshots as _fn
    return _fn(snapshot_a_id, snapshot_b_id, session_id)


def restore_execution_snapshot(snapshot_id: str, session_id: str) -> Optional[Dict[str, Any]]:
    """Return the recoverable full state of a snapshot as the restore payload.

    Args:
        snapshot_id: snapshot 标识。
        session_id: 会话 ID。
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
    """List filesystem checkpoints captured before file write/edit overwrites.

    Args:
        session_id: 会话 ID。
        path: 路径。
    """
    from core.harness.execution.file_checkpoint import list_file_checkpoints as _fn
    return _fn(session_id=session_id, path=path)


def get_file_checkpoint(checkpoint_id: str, session_id: str = "") -> Optional[Dict[str, Any]]:
    """Return a file checkpoint header + its stored content.

    Args:
        checkpoint_id: checkpoint 标识。
        session_id: 会话 ID。
    """
    from core.harness.execution.file_checkpoint import get_file_checkpoint as _fn
    return _fn(checkpoint_id, session_id)


def restore_file_checkpoint(checkpoint_id: str, session_id: str = "") -> Dict[str, Any]:
    """Restore a file to the content captured in the given checkpoint (writes it back).

    Args:
        checkpoint_id: checkpoint 标识。
        session_id: 会话 ID。
    """
    from core.harness.execution.file_checkpoint import restore_file_checkpoint as _fn
    return _fn(checkpoint_id, session_id)


def get_howl_stats() -> Dict[str, Any]:
    """Howl stall-intervention counters (Agent KPI for Governance)."""
    from core.harness.intervention.howl import get_howl_stats as _fn
    return _fn()


def publish_learning_release(release_id: str) -> Dict[str, Any]:
    """Publish a learning release candidate (via handler registry).

    Args:
        release_id: release 标识。
    """
    return dispatch("publish_release_candidate", release_id)


def rollback_learning_release(release_id: str, reason: str = "") -> Dict[str, Any]:
    """Rollback a learning release candidate (via handler registry).

    Args:
        release_id: release 标识。
        reason: reason 参数。
    """
    return dispatch("rollback_release_candidate", release_id, reason)


def run_plugin_action(plugin_id: str, action: str, params: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """Run a plugin action. Use instead of importing。

    Args:
        plugin_id: plugin 标识。
        action: action 参数。
        params: params 参数。
    """
    from core.api.routers.plugins import run_plugin as _fn


# ── KB Facade ──

def kb_retrieve(query: str, doc_ids: Any, **kwargs: Any) -> Any:
    """Low-level KB chunk retrieve. Prefer kb_qa_retrieve for user-facing Q&A (W4).

    Args:
        query: 查询。
        doc_ids: doc_ids 参数。
        kwargs: kwargs 参数。
    """
    from core.harness.syscalls.retrieval import sys_kb_retrieve
    return sys_kb_retrieve(query, doc_ids, **kwargs)


async def kb_qa_retrieve(query: str, **kwargs: Any) -> Any:
    """Canonical KB Q&A retrieval via CRAG (sys_crag_retrieve). GraphRAG is L0 inside CRAG.

    Args:
        query: 查询。
        kwargs: kwargs 参数。
    """
    from core.api.facades.kb_facade import kb_qa_retrieve as _impl
    return await _impl(query, **kwargs)


def wiki_retrieve(query: str, wiki_titles: list = None, **kwargs: Any) -> Any:
    """Retrieve relevant wiki knowledge page content through the syscall boundary.

    Args:
        query: 查询。
        wiki_titles: wiki_titles 参数。
        kwargs: kwargs 参数。
    """
    from core.harness.syscalls.retrieval import sys_wiki_retrieve
    return sys_wiki_retrieve(query, wiki_titles, **kwargs)


async def wiki_auto_update(doc_id: str, file_path: str, collection_id: str = "") -> Dict[str, Any]:
    """Convert a newly ingested KB document into Wiki knowledge pages.

    Args:
        doc_id: doc 标识。
        file_path: file_path 参数。
        collection_id: collection 标识。
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
                stats_path = _os.path.join(get_aiplat_home(),
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
        kb_db = os.path.join(get_aiplat_home(),
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

    Args:
        doc_id: doc 标识。
        file_path: file_path 参数。
        collection_id: collection 标识。
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
    """Start a grilling clarification interview session. Returns first question.

    Args:
        entry_point: entry_point 参数。
        domain_id: domain 标识。
        context: context 参数。
    """
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
    """Process answer and return next question or finalize.

    Args:
        session_id: 会话 ID。
        answer: answer 参数。
    """
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
    """Skip current question (only non-required).

    Args:
        session_id: 会话 ID。
    """
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
    """Get current grilling session state (for UI recovery).

    Args:
        session_id: 会话 ID。
    """
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
        yaml_path = _Path(get_aiplat_home()) / "ontologies" / f"{domain_id}.yaml"
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
    """Return agents and downstream skills affected by a given skill.

    Args:
        skill_id: Skill ID。
    """
    from core.harness.knowledge.skill_deps import skill_impact
    return skill_impact(skill_id)


def wiki_fts_index() -> int:
    u"""Rebuild wiki FTS5 index. Returns count of indexed pages."""
    from core.harness.knowledge.wiki_fts import fts_index_pages
    return fts_index_pages()


def wiki_fts_search(query: str, limit: int = 10) -> Any:
    """Keyword search wiki pages via FTS5.

    Args:
        query: 查询。
        limit: 返回条数上限。
    """
    from core.harness.knowledge.wiki_fts import fts_search
    return fts_search(query, limit)


def wiki_pages_by_source(source_key: str) -> List[Dict[str, Any]]:
    """Find wiki pages that originated from a given source key (e.g. kb:<doc_id>).

    Args:
        source_key: source_key 参数。
    """
    from core.harness.knowledge.wiki_engine import pages_by_source
    return pages_by_source(source_key)


def wiki_search_pages(query: str = "", *, tags: List[str] = None, category: str = "",
                       limit: int = 20, collection_id: str = "default") -> List[Dict[str, Any]]:
    """Search wiki pages — Phase 45: CoreFacade wrapper for platform layer.

    Args:
        query: 查询。
        tags: tags 参数。
        category: category 参数。
        limit: 返回条数上限。
        collection_id: collection 标识。
    """
    from core.harness.knowledge.wiki_engine import search_pages
    return search_pages(query=query, tags=tags, category=category,
                         limit=limit, collection_id=collection_id)


def wiki_search_pages_api(query: str = "", *, tags: List[str] = None, category: str = "",
                          limit: int = 20, collection_id: str = "default") -> Dict[str, Any]:
    """Wiki search with ontology.api.v0 envelope (A1 contract).

    Args:
        query: 查询。
        tags: tags 参数。
        category: category 参数。
        limit: 返回条数上限。
        collection_id: collection 标识。
    """
    from core.harness.knowledge.ontology_api import attach_ontology_api, from_wiki_pages

    pages = wiki_search_pages(
        query, tags=tags, category=category, limit=limit, collection_id=collection_id
    ) or []
    out: Dict[str, Any] = {"items": pages, "total": len(pages)}
    return dict(
        attach_ontology_api(
            out,
            from_wiki_pages(pages, query=query, collection_id=collection_id),
        )
    )


def get_graph_health(domain: str = "") -> Dict[str, Any]:
    """Phase 45: Get GraphIndex health stats for a domain.

    Args:
        domain: domain 参数。
    """
    from core.harness.ontology_engine.graph_index import GraphIndex
    try:
        g = GraphIndex.load(domain) if domain else None
        if g:
            return {"domain": domain, "node_count": g.stats().get("node_count", 0),
                    "exists": True}
        return {"domain": domain, "exists": False, "error": "not found"}
    except Exception as e:
        return {"domain": domain, "exists": False, "error": str(e)[:200]}


def get_graph_health_api(domain: str = "") -> Dict[str, Any]:
    """Graph health with ontology.api.v0 envelope (A1 contract).

    Args:
        domain: domain 参数。
    """
    from core.harness.knowledge.ontology_api import attach_ontology_api, from_graph_health

    raw = get_graph_health(domain)
    out = dict(raw) if isinstance(raw, dict) else {"domain": domain, "payload": raw}
    return dict(attach_ontology_api(out, from_graph_health(out, domain_id=domain)))


def wiki_structured_query_api(query: str, *, domain_id: str = "") -> Dict[str, Any]:
    """Deterministic wiki structured query + ontology.api.v0 envelope.

    Args:
        query: 查询。
        domain_id: domain 标识。
    """
    from core.harness.knowledge.wiki_structured_query import structured_query
    from core.harness.knowledge.ontology_api import attach_ontology_api, from_structured_query

    raw = structured_query(query)
    out = dict(raw) if isinstance(raw, dict) else {"result": raw}
    return attach_ontology_api(out, from_structured_query(out, domain_id=domain_id))


def aiplat_healthz_payload(
    *,
    status: Any = "ok",
    version: str = "",
    hosted: Optional[List[str]] = None,
    checks: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Central host /healthz shape (aiPlat A1) + control_plane.v0 status envelope.

    Args:
        status: status 参数。
        version: version 参数。
        hosted: hosted 参数。
        checks: checks 参数。
    """
    from core.harness.meta.capability_version import resolve_capability_version
    from core.harness.meta.control_plane import (
        attach_control_plane,
        to_aiplat_healthz,
        to_control_plane_v0,
    )

    ver = str(version or "").strip() or resolve_capability_version("aiplat")
    out = to_aiplat_healthz(status=status, version=ver, hosted=hosted, checks=checks)
    return dict(
        attach_control_plane(
            out,
            to_control_plane_v0(kind="status", payload={"health": out.get("status")}),
        )
    )


def ontology_healthz_payload(*, version: str = "", mode: str = "read_only") -> Dict[str, Any]:
    """Ontology co-hosted healthz (product_id=ontology).

    Args:
        version: version 参数。
        mode: mode 参数。
    """
    from core.harness.knowledge.domain_router import DomainRouter
    from core.harness.knowledge.ontology_api import to_ontology_healthz
    from core.harness.meta.capability_version import resolve_capability_version

    ver = str(version or "").strip() or resolve_capability_version("ontology")
    domains = 0
    status = "ok"
    try:
        domains = len(DomainRouter().list_domains() or [])
    except Exception as e:
        logging.getLogger(__name__).warning("ontology_healthz domain count failed: %s", e)
        status = "degraded"
    return to_ontology_healthz(status=status, version=ver, domains=domains, mode=mode)


def evaluation_healthz_payload(*, version: str = "") -> Dict[str, Any]:
    """Evaluation co-hosted healthz (product_id=evaluation).

    Args:
        version: version 参数。
    """
    from core.harness.evaluation.eval_protocol import SCHEMA_VERSION, to_evaluation_healthz
    from core.harness.meta.capability_version import resolve_capability_version

    ver = str(version or "").strip() or resolve_capability_version("evaluation")
    return to_evaluation_healthz(status="ok", version=ver, protocol=SCHEMA_VERSION)


def fde_healthz_payload(*, version: str = "", mode: str = "field_d1") -> Dict[str, Any]:
    """FDE Field D1 healthz (ADR-FDE-FIELD-DEPLOY Accepted).

    Args:
        version: version 参数。
        mode: mode 参数。
    """
    from core.harness.meta.capability_version import resolve_capability_version

    ver = str(version or "").strip() or resolve_capability_version("fde")
    return {
        "status": "ok",
        "version": ver,
        "product_id": "fde",
        "capability_id": "fde",
        "deploy_unit": "field",
        "mode": str(mode or "field_d1"),
        "signoff": "POST /api/platform/apps/fde/acceptance/signoff",
        "field_d1_adr": "accepted",
        "production_field": True,
        "adr": "reports/five-products/ADR-FDE-FIELD-DEPLOY.md",
    }


def code_intel_context(task: str) -> Any:
    """Return code graph context for a development task.

    Args:
        task: task 参数。
    """
    from core.harness.syscalls.code_intel_syscall import sys_code_intel_context
    return sys_code_intel_context(task)


def code_intel_blast(file_path: str) -> Any:
    """Return forward blast radius of a file.

    Args:
        file_path: file_path 参数。
    """
    from core.harness.syscalls.code_intel_syscall import sys_code_intel_blast
    return sys_code_intel_blast(file_path)


def code_intel_hot_paths(entry_id: Any = None, max_paths: int = 20) -> Any:
    """Scored security hot_paths through the syscall boundary.

    Args:
        entry_id: entry 标识。
        max_paths: max_paths 参数。
    """
    from core.harness.syscalls.code_intel_syscall import sys_code_intel_hot_paths
    return sys_code_intel_hot_paths(entry_id, max_paths=int(max_paths or 20))


def kb_ocr_keyframes(image_paths: list, engine: str = "paddleocr", lang: str = "zh") -> Any:
    """OCR multiple image files.

    Args:
        image_paths: image_paths 参数。
        engine: engine 参数。
        lang: lang 参数。
    """
    from core.harness.document.ocr import ocr_keyframes
    return ocr_keyframes(image_paths, engine=engine, lang=lang)


def kb_probe_video_duration(video_path: str) -> int:
    """Probe video duration in milliseconds.

    Args:
        video_path: video_path 参数。
    """
    from core.harness.document.video import probe_duration_ms
    return probe_duration_ms(video_path)


def kb_extract_video_keyframes(video_path: str, output_dir: str, interval_seconds: int = 15) -> Any:
    """Extract keyframes from video at given second interval.

    Args:
        video_path: video_path 参数。
        output_dir: output_dir 参数。
        interval_seconds: interval_seconds 参数。
    """
    from core.harness.document.video import extract_keyframes
    return extract_keyframes(video_path, output_dir, interval_seconds=interval_seconds)


def kb_extract_video_audio(video_path: str, audio_path: str) -> None:
    """Extract audio track from video file into WAV.

    Args:
        video_path: video_path 参数。
        audio_path: audio_path 参数。
    """
    from core.harness.document.video import extract_audio
    return extract_audio(video_path, audio_path)


def kb_parse_document(file_path: str, kind: str) -> Any:
    """Parse a document file via the ConverterRegistry with full fallback chain.

    Args:
        file_path: file_path 参数。
        kind: kind 参数。
    """
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
    """Chunk parsed document elements into segments.

    Args:
        elements: elements 参数。
        kind: kind 参数。
        target_size: target_size 参数。
        overlap: overlap 参数。
    """
    from core.harness.document.chunker import chunk_document
    return chunk_document(elements, kind=kind, target_size=target_size, overlap=overlap)


def kb_chunk_elements(elements: Any, kind: str = "pdf", target_size: int = 1000, overlap: int = 150) -> Any:
    """Auto-select chunking strategy and apply to parsed document elements.

    Args:
        elements: elements 参数。
        kind: kind 参数。
        target_size: target_size 参数。
        overlap: overlap 参数。
    """
    from core.apps.document_intelligence.chunking import chunk_elements
    return chunk_elements(elements, kind=kind, target_size=target_size, overlap=overlap)


def kb_create_infra_db_client(db_path: str) -> Any:
    """Create an infrastructure database client for KB storage.

    Args:
        db_path: db_path 参数。
    """
    from core.harness.infrastructure.infra_bridge import create_infra_database_client
    return create_infra_database_client(db_path)


create_infra_database_client = kb_create_infra_db_client


def deploy_app_service(name: str, namespace: str, image: str,
                       config: Optional[Dict[str, Any]] = None) -> bool:
    """L5 v2: register a service deployment via infra bridge (platform → core → infra).

    Args:
        name: name 参数。
        namespace: namespace 参数。
        image: image 参数。
        config: config 参数。
    """
    from core.harness.infrastructure.infra_bridge import deploy_app_service as _bridge_deploy
    return _bridge_deploy(name, namespace, image, config)


def kb_classify_document(elements: Any, kind: str) -> Any:
    """Classify document content type.

    Args:
        elements: elements 参数。
        kind: kind 参数。
    """
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
    """Split audio into chunks, transcribe each, merge. Fallback for long audio.

    Args:
        audio_path: audio_path 参数。
        language: language 参数。
        chunk_seconds: chunk_seconds 参数。
    """
    from core.harness.document.transcriber import transcribe_audio_chunked
    return transcribe_audio_chunked(audio_path, language=language or None, chunk_seconds=chunk_seconds)


def kb_embed_text(text: str, dim: int = 128) -> Any:
    """Embed text into a vector. Safe to call from sync or async context.

    Args:
        text: text 参数。
        dim: dim 参数。
    """
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
    """Synchronous text embedding (fallback to hash).

    Args:
        text: text 参数。
        dim: dim 参数。
    """
    from core.harness.knowledge.embedder import hash_embed
    return hash_embed(text, dim)


def kb_extract_keywords(text: str) -> Any:
    """Extract CJK + alphanumeric keywords from text.

    Args:
        text: text 参数。
    """
    from core.harness.knowledge.utils import extract_keywords
    return extract_keywords(text)


def kb_score_text(text: str, keywords: Any) -> Any:
    """Score text relevance against a set of keywords.

    Args:
        text: text 参数。
        keywords: keywords 参数。
    """
    from core.harness.knowledge.utils import score_text
    return score_text(text, list(keywords) if keywords else [])


def kb_element_source(element: Any) -> Any:
    """Determine the source type of a KB element.

    Args:
        element: element 参数。
    """
    from core.harness.knowledge.utils import element_source
    return element_source(element)


def kb_get_ingest_fn() -> Any:
    """Get the registered KB ingest callback set by platform startup."""
    from core.apps.document_intelligence.kb_provider import get_ingest_fn
    return get_ingest_fn()


def kb_get_tenant_storage(tenant_id: str) -> Any:
    """Get the KB storage client for a given tenant.

    Args:
        tenant_id: 租户 ID。
    """
    from core.apps.document_intelligence.kb_provider import get_tenant_storage
    return get_tenant_storage(tenant_id)


def kb_kind_category(kind: str) -> Any:
    """Get the document category label for a given kind.

    Args:
        kind: kind 参数。
    """
    from core.apps.document_intelligence.classifier import kind_category
    return kind_category(kind)


# Re-export from core.apps for platform backward compat
from core.apps.document_intelligence.classifier import CATEGORY_LABELS  # noqa: E402


def kb_llm_chat_complete(system_prompt: str, user_prompt: str, temperature: float = 0.1, max_tokens: int = 700) -> Any:
    """Chat completion via KB LLM client.

    Args:
        system_prompt: system_prompt 参数。
        user_prompt: user_prompt 参数。
        temperature: temperature 参数。
        max_tokens: max_tokens 参数。
    """
    from core.apps.document_intelligence.llm_client import chat_complete
    return chat_complete(system_prompt=system_prompt, user_prompt=user_prompt, temperature=temperature, max_tokens=max_tokens)


def kb_llm_enabled() -> bool:
    """Check if KB LLM client is configured."""
    from core.apps.document_intelligence.llm_client import llm_enabled
    return llm_enabled()


def extract_json_block(text: str) -> Any:
    """Extract JSON block from LLM output text.

    Args:
        text: text 参数。
    """
    return parse_json(text)


async def kb_summarize_document(*, tenant_id: str, collection_id: str, doc_id: str, profile: str = "key_points", **kwargs: Any) -> Any:
    """Summarize a knowledge base document.

    Args:
        tenant_id: 租户 ID。
        collection_id: collection 标识。
        doc_id: doc 标识。
        profile: 评测 profile。
        kwargs: kwargs 参数。
    """
    from core.apps.document_intelligence.summarizer import summarize_document
    return await summarize_document(tenant_id=tenant_id, collection_id=collection_id, doc_id=doc_id, profile=profile, **kwargs)


from core.apps.tools.permission import Permission  # noqa: E402


# P0-B4 (2026-08-19): get_agent_registry_facade 已删除 — 0 调用者，与
# integration.py::get_agent_registry 重复（入口唯一性 §10），统一走后者。

from core.apps.agents.discovery import AgentDiscovery, AgentLoader, AgentRegistry  # noqa: E402

def _get_latest_eval_score(agent_id: str):
    """Read the latest evaluation score for an agent from eval_results directory."""
    import json as _json, os as _os, glob as _glob
    from pathlib import Path as _Path
    try:
        results_dir = Path(get_aiplat_data_dir("eval_results"))
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
    input_payload: Any = None,
) -> Dict[str, Any]:
    """Execute a single workspace agent via StageRunner → ReActLoop.

    Args:
        agent_info: agent_info 参数。
        user_message: user_message 参数。
        max_steps: max_steps 参数。
        toolset: toolset 参数。
        session_id: 会话 ID。
        stream: stream 参数。
        input_payload: input_payload 参数。
    """
    import asyncio as _asyncio, os as _os

    agent_id = str(getattr(agent_info, "id", "unknown"))
    # Phase B: Agent COMPAT gate — blocked denies all; needs_binding → chat-lite
    _compat_chat_lite = False
    try:
        from core.harness.maintenance.asset_compat import (
            agent_compat_error,
            is_agent_chat_ok,
            is_agent_fully_usable,
            resolve_agent_dir_from_info,
        )

        _adir = resolve_agent_dir_from_info(agent_info)
        if _adir is not None:
            if not is_agent_chat_ok(_adir):
                return agent_compat_error(_adir, agent_id=agent_id, mode="chat")
            if not is_agent_fully_usable(_adir):
                _compat_chat_lite = True
    except Exception:
        logging.debug("agent compat gate skipped", exc_info=True)
    cfg = getattr(agent_info, "config", None)
    system_prompt = cfg.get("system_prompt", "") if isinstance(cfg, dict) else ""
    import uuid as _uuid, os as _os_env, time as _time
    run_id = f"run-{_uuid.uuid4().hex[:12]}"
    trace_id = f"trace-{_uuid.uuid4().hex[:12]}"
    session_id = session_id or run_id
    # Persist original execute payload so status/review-output can restore input
    # after stream (FE lastInputRef alone is not authoritative).
    _stored_input: Any = input_payload if input_payload is not None else (
        {"message": user_message} if user_message else None
    )

    # Persist run to agent_executions via execution_store (unified path)
    _now = _time.time()
    try:
        from core.harness.utils.execute_session import agent_stream_timeout_seconds
        from core.services.execution_store import get_execution_store
        _es = get_execution_store()
        _agent_wall = float(agent_stream_timeout_seconds(int(max_steps or 10)))
        await _es.upsert_agent_execution({
            "id": run_id,
            "agent_id": agent_id,
            "status": "running",
            "input": _stored_input,
            "start_time": _now,
            "created_at": _now,
            "trace_id": trace_id,
            "metadata": {
                "stream": bool(stream),
                "timeout": _agent_wall,
                "max_steps": int(max_steps or 10),
            },
        })
        # Persist traces row so Diagnostics Links can resolve execution_id → trace
        try:
            await _es.upsert_trace({
                "trace_id": trace_id,
                "name": f"workspace_agent:{agent_id}",
                "status": "running",
                "start_time": _now,
                "end_time": None,
                "duration_ms": None,
                "attributes": {
                    "execution_id": run_id,
                    "agent_id": agent_id,
                    "session_id": session_id,
                    "source": "workspace_agent",
                },
            })
        except Exception:
            logging.debug("upsert_trace at agent start failed run_id=%s", run_id, exc_info=True)
        # Seed RunGraph meta (same as skill stream) so Links / status polling see has_graph.
        try:
            if hasattr(_es, "set_run_graph_status"):
                await _es.set_run_graph_status(str(run_id), "running")
        except Exception:
            logging.debug("seed run_graph_meta running failed run_id=%s", run_id, exc_info=True)
        # Mark gate coverage (Phase 3 GateTracer)
        try:
            from core.harness.kernel.execution_context import mark_gate_passed
            mark_gate_passed("execution_store_persist")
        except Exception:
            logging.debug("execution_store_persist gate marker failed", exc_info=True)
    except Exception:
        logging.warning(f"Failed to persist agent execution record for {agent_id} run {run_id}", exc_info=True)

    # Register TraceService in-memory so TraceGate.start_span(trace_id=…) succeeds
    # (SQLite upsert alone is not enough — start_span looks up _traces).
    try:
        from core.harness.kernel.runtime import get_kernel_runtime
        _rt = get_kernel_runtime()
        _ts = getattr(_rt, "trace_service", None) if _rt else None
        if _ts is not None:
            await _ts.start_trace(
                name=f"workspace_agent:{agent_id}",
                attributes={
                    "execution_id": run_id,
                    "agent_id": agent_id,
                    "session_id": session_id,
                    "source": "workspace_agent",
                },
                trace_id=trace_id,
            )
    except Exception:
        logging.debug("TraceService.start_trace for workspace agent failed run_id=%s", run_id, exc_info=True)

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

    # ── Stream mode: return immediately, execute off the API event loop ──
    # Running on the same Uvicorn loop starves SSE/poll while LLM is in-flight
    # (FE shows empty "loading steps"). Isolate in a daemon thread so observation
    # endpoints stay responsive; EventBus.publish is threadsafe.
    if stream:
        import threading as _threading

        # Pre-subscribe + seed agent_start BEFORE returning run_id so SSE Phase-1
        # replay / EventBus never race an empty window into premature type:done.
        try:
            from core.harness.observation.event_bus import EventBus as _EB
            _EB.subscribe(run_id)
        except Exception:
            logging.debug("EventBus pre-subscribe failed run_id=%s", run_id, exc_info=True)
        try:
            from core.harness.observation.run_graph import open_node as _rg_open
            await _rg_open(
                run_id,
                f"agent:{agent_id}:start",
                kind="agent",
                name="agent_start",
                label=str(agent_id),
                role="container",
                audit=True,
            )
        except Exception:
            logging.debug("seed agent_start run_graph failed run_id=%s", run_id, exc_info=True)

        # API-loop early watch: survives if bg thread hangs before StageRunner
        # (model resolve / skill load) — that was the stuck 「会话 进行中 · 0 步骤」case.
        try:
            import time as _time_seed
            from core.harness.utils.execute_session import watch_agent_no_progress

            _asyncio.create_task(
                watch_agent_no_progress(
                    run_id=str(run_id),
                    agent_id=str(agent_id),
                    start_time=_time_seed.time(),
                    input_payload=_stored_input,
                    trace_id=str(trace_id or ""),
                    source="api_loop_early_no_progress",
                )
            )
        except Exception:
            logging.debug("early no_progress watch schedule failed run_id=%s", run_id, exc_info=True)

        def _bg_runner() -> None:
            try:
                _asyncio.run(
                    _execute_workspace_agent_background(
                        agent_info=agent_info,
                        agent_id=agent_id,
                        run_id=run_id,
                        trace_id=trace_id,
                        user_message=user_message,
                        max_steps=max_steps,
                        toolset=toolset,
                        session_id=session_id,
                        input_payload=_stored_input,
                        chat_lite=_compat_chat_lite,
                    )
                )
            except Exception:
                logging.getLogger("aiplat.core_facade").exception(
                    "background agent run failed run_id=%s agent_id=%s", run_id, agent_id
                )

        _threading.Thread(
            target=_bg_runner,
            name=f"ws-agent-{run_id}",
            daemon=True,
        ).start()
        return {"ok": True, "status": "running", "output": None, "run_id": run_id, "execution_id": run_id,
                "eval": await _get_latest_eval_score_async(agent_id)}

    return await _execute_workspace_agent_background(
        agent_info=agent_info, agent_id=agent_id, run_id=run_id,
        trace_id=trace_id,
        user_message=user_message, max_steps=max_steps, toolset=toolset,
        session_id=session_id,
        input_payload=_stored_input,
        chat_lite=_compat_chat_lite,
    )


async def _execute_workspace_agent_background(
    agent_info: Any, agent_id: str, run_id: str, *, trace_id: str = "", user_message: str,
    max_steps: int = 10, toolset: str = "", session_id: str = "",
    input_payload: Any = None, chat_lite: bool = False,
) -> Dict[str, Any]:
    """Core execution logic used by both synchronous and stream paths."""
    import asyncio as _asyncio, os as _os, time as _time, json as _json
    _now = _time.time()
    _stored_input: Any = input_payload if input_payload is not None else (
        {"message": user_message} if user_message else None
    )
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
        from core.harness.utils.execute_session import resolve_workspace_agent_model_purpose
        
        cfg = getattr(agent_info, "config", None)
        model_name = cfg.get("model") if isinstance(cfg, dict) else ""
        purpose = resolve_workspace_agent_model_purpose(agent_info)
        
        # Always go through infra ModelManager for model resolution (single source of truth)
        if not model_name or model_name == "auto":
            model_name = best_model_for_purpose(purpose)
        else:
            # Explicit model: validate it exists in infra registry; if not, fall back to auto
            try:
                from core.harness.utils.model_injection import _get_cached_model_manager
                mgr = _get_cached_model_manager()
                if not mgr.select(model_name=model_name):
                    import logging as _logging
                    _logging.getLogger("aiplat.core_facade").warning(
                        f"Agent '{agent_id}' specified model '{model_name}' not found in infra registry; "
                        f"falling back to best_model_for_purpose('{purpose}')")
                    model_name = best_model_for_purpose(purpose)
            except Exception:
                model_name = best_model_for_purpose(purpose)
        
        try:
            return create_selected_adapter(model_name=model_name)
        except Exception:
            return None

    agent_model = None
    try:
        agent_model = await _asyncio.wait_for(
            _asyncio.to_thread(_resolve_model),
            timeout=45.0,
        )
    except _asyncio.TimeoutError:
        logging.getLogger("aiplat.core_facade").error(
            "model resolve timed out (45s) run_id=%s agent_id=%s", run_id, agent_id
        )
        try:
            from core.harness.utils.execute_session import mark_agent_no_progress_timeout

            await mark_agent_no_progress_timeout(
                run_id=str(run_id),
                agent_id=str(agent_id),
                start_time=_now,
                input_payload=_stored_input,
                trace_id=str(trace_id or ""),
                source="model_resolve_timeout",
            )
        except Exception:
            logging.debug("model_resolve_timeout mark failed", exc_info=True)
        return {
            "ok": False,
            "status": "timeout",
            "output": None,
            "error": "Timeout: model resolve hung >45s before first LLM",
            "run_id": run_id,
        }
    except Exception:
        logging.getLogger("aiplat.core_facade").exception(
            "model resolve failed run_id=%s agent_id=%s", run_id, agent_id
        )
        agent_model = None
    if not agent_model:
        return {"ok": False, "status": "error", "output": None, "error": "No LLM model", "run_id": run_id}

    # Extract system_prompt from agent config (used by ReActLoop)
    cfg = getattr(agent_info, "config", None)
    sys_prompt = cfg.get("system_prompt", "") if isinstance(cfg, dict) else ""

    # Phase B needs_binding: keep dialogue; strip tools/skills (full surface limited)
    resolved_tools = []
    resolved_skills = []
    if not chat_lite:
        try:
            from core.harness.integration import _resolve_tool_registry
            reg = _resolve_tool_registry()
            for tn in (getattr(agent_info, "tools", []) or []):
                t = reg.get(str(tn))
                if t:
                    resolved_tools.append(t)
        except Exception as e:
            logging.debug(str(e), exc_info=True)
        try:
            from core.harness.integration import get_skill_registry
            sk_reg = get_skill_registry()
            _want = []
            for sn in (getattr(agent_info, "skills", []) or []):
                if str(sn).strip():
                    _want.append(str(sn).strip())
            _m0 = getattr(agent_info, "metadata", None) or {}
            if isinstance(_m0, dict):
                for sn in (_m0.get("required_skills") or []):
                    s = str(sn).strip()
                    if s and s not in _want:
                        _want.append(s)
            for sn in _want:
                s = sk_reg.get(str(sn)) if hasattr(sk_reg, "get") else None
                if s:
                    resolved_skills.append(s)
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

    from core.harness.utils.execute_session import agent_stream_timeout_seconds
    _agent_wall = float(agent_stream_timeout_seconds(int(max_steps or 10)))
    _meta_skills = []
    try:
        _m = getattr(agent_info, "metadata", None) or {}
        if isinstance(_m, dict) and isinstance(_m.get("required_skills"), list):
            _meta_skills = [str(s).strip() for s in _m["required_skills"] if str(s).strip()]
    except Exception:
        _meta_skills = []
    _skill_names = [
        str(s).strip()
        for s in (getattr(agent_info, "skills", None) or [])
        if str(s).strip()
    ]
    for s in _meta_skills:
        if s not in _skill_names:
            _skill_names.append(s)
    _cfg = cfg if isinstance(cfg, dict) else {}
    _skill_delivery = str(_cfg.get("skill_delivery") or "").strip().lower()
    if not _skill_delivery and len(_skill_names) == 1:
        _skill_delivery = "once"
    # Soft preference only — do not bypass ReAct. Bound prompt-skills still skip
    # CLAUDE.md inside sys_skill_call (constitution); agent reason step stays on ReAct.
    if len(_skill_names) == 1:
        _sid = _skill_names[0]
        prompt = (
            f"{prompt}\n\n[执行提示] 本 Agent 仅绑定技能 `{_sid}`。\n"
            f"1) 第一轮必须调用该技能（skill_call），把用户任务/PRD 作为 input；\n"
            f"2) 技能返回可用产物后，下一轮必须输出 "
            f'{{\"type\":\"done\",\"answer\":...}} 或 DONE: 总结，禁止无故重复调用同一技能。'
        )
    elif _skill_delivery == "once" and _skill_names:
        prompt = (
            f"{prompt}\n\n[执行提示] skill_delivery=once：优先调用绑定技能 "
            f"({', '.join(_skill_names[:4])})；"
            f"任一主要技能成功产出后，下一轮必须 DONE，勿反复重跑同一技能。"
        )

    # Explicit frontmatter opt-in only (never infer from output_artifact).
    _meta0 = getattr(agent_info, "metadata", None) or {}
    if not isinstance(_meta0, dict):
        _meta0 = {}
    _explicit_skip_claude = _meta0.get("skip_claude_md") in (True, "1", "true", "yes")

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
        # Workspace trial agents are not code-gen by default; slim CLAUDE inject
        # is driven by this profile in sys_llm_generate (not by skipping Agent ReAct).
        "_coding_policy_profile": "off",
        # First-turn oral execute: never pay query-rewrite LLM before ReAct generate
        # (was True → rewrite_with_history could stall pre-LLM with Ollama idle).
        "_enable_query_rewrite": False,
        "_user_id": "system",
        "_sys_prompt": sys_prompt,
        "_skip_claude_md": _explicit_skip_claude,
        # StageRunner.resolve_stage_loop_type reads config + state; keep both in sync.
        "_loop_type": agent_loop_type,
        "_bound_skill_ids": list(_skill_names),
        "_skill_delivery": _skill_delivery,
        "_user_task": str(user_message or ""),
        "_execute_input": _stored_input if isinstance(_stored_input, dict) else {},
        # Agent-declared coding language (AGENT.md preferred_language). Injected
        # into code_generation; task text wins over preferred; preferred wins over
        # model-echoed schema default (often python).
        "_preferred_language": str(
            (_cfg.get("preferred_language") if isinstance(_cfg, dict) else None)
            or (_meta0.get("preferred_language") if isinstance(_meta0, dict) else None)
            or ""
        ).strip().lower(),
        "context": {"system_prompt": sys_prompt, "task": user_message},
    }
    # DONE Verify ring — AGENT.md quality_gate / done_verify / expected_outcomes
    try:
        from core.harness.execution.done_verify import build_done_verify_config

        _qg = _cfg.get("quality_gate") if isinstance(_cfg.get("quality_gate"), dict) else None
        if _qg is None and isinstance(_meta0.get("quality_gate"), dict):
            _qg = _meta0.get("quality_gate")
        _eo = _cfg.get("expected_outcomes") if isinstance(_cfg.get("expected_outcomes"), list) else None
        if _eo is None and isinstance(_meta0.get("expected_outcomes"), list):
            _eo = _meta0.get("expected_outcomes")
        _dv = _cfg.get("done_verify") if isinstance(_cfg.get("done_verify"), dict) else None
        if _dv is None and isinstance(_meta0.get("done_verify"), dict):
            _dv = _meta0.get("done_verify")
        state["_done_verify"] = build_done_verify_config(
            quality_gate=_qg,
            expected_outcomes=_eo,
            done_verify=_dv,
            review_gate=str(_cfg.get("review_gate") or _meta0.get("review_gate") or ""),
        )
        if isinstance(_qg, dict):
            state["quality_gate"] = _qg
        if isinstance(_eo, list):
            state["expected_outcomes"] = _eo
    except Exception:
        logging.debug("done_verify agent inject skipped", exc_info=True)

    # Coding closed loop for workspace Execute (same defaults as factory file-output stages).
    # Opt-in via uses_file_output / coding_closed_loop / coding_intensity — not agent_id.
    try:
        from core.schemas_builder import inject_workspace_coding_defaults

        _extra_coding = inject_workspace_coding_defaults(
            state,
            agent_cfg=_cfg,
            agent_meta=_meta0,
            skills=resolved_skills,
        )
        if _extra_coding:
            try:
                from core.harness.integration import get_skill_registry

                _sk_reg = get_skill_registry()
                for _sn in _extra_coding:
                    _sk = _sk_reg.get(str(_sn)) if hasattr(_sk_reg, "get") else None
                    if _sk is not None and _sk not in resolved_skills:
                        resolved_skills.append(_sk)
                runner._skills = list(resolved_skills)
            except Exception:
                logging.debug("workspace coding skill bind skipped", exc_info=True)
    except Exception:
        logging.debug("workspace coding defaults skipped", exc_info=True)

    # Code meta-tool — AGENT.md meta_tool: {enabled, auto_bind, force}
    try:
        from core.harness.execution.meta_tool import apply_meta_tool_config

        _mt = _cfg.get("meta_tool") if isinstance(_cfg.get("meta_tool"), dict) else None
        if _mt is None and isinstance(_meta0.get("meta_tool"), dict):
            _mt = _meta0.get("meta_tool")
        apply_meta_tool_config(state, _mt)
    except Exception:
        logging.debug("meta_tool agent inject skipped", exc_info=True)

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

    # ── Emit agent_start via RunGraph (authoritative) + audit syscall ──
    # Brief yield so HTTP response/SSE can flush before heavy work.
    await _asyncio.sleep(0.05)
    try:
        from core.harness.observation.run_graph import open_node as _rg_open
        t0_agent = _time.time()
        await _rg_open(
            run_id,
            f"agent:{agent_id}:start",
            kind="agent",
            name="agent_start",
            label=str(agent_id),
            role="container",
            audit=True,
        )
    except Exception:
        t0_agent = _now

    status = "completed"
    result_text = ""
    error_msg = None
    # Factory-in way4 Workspace Execute Pi bypass was merge-closed (2026-10-14):
    # blank_not_proven — coding_closed_loop already has sandbox + sys_file_*.
    # Offline CLI probes remain under packages/aiplat-pi-runtime/; see FACTORY_IN_EXPERIMENT.md §⓪.

    watch_task = None
    try:
        run_task = _asyncio.create_task(runner.run(prompt, state))
        # note: status may flip to approval_required / policy_denied after runner returns

        async def _agent_no_progress_watch() -> None:
            from core.harness.utils.execute_session import watch_agent_no_progress

            await watch_agent_no_progress(
                run_id=str(run_id),
                agent_id=str(agent_id),
                start_time=float(t0_agent or _now),
                input_payload=_stored_input,
                trace_id=str(trace_id or ""),
                cancel_cb=run_task.cancel,
                source="bg_loop_no_progress",
            )

        watch_task = _asyncio.create_task(_agent_no_progress_watch())
        try:
            result_text = await _asyncio.wait_for(run_task, timeout=_agent_wall)
        except _asyncio.CancelledError:
            status = "timeout"
            if not error_msg:
                error_msg = (
                    "Timeout (no_progress): hung before first LLM/skill syscall"
                )
        except _asyncio.TimeoutError:
            status = "timeout"
            error_msg = f"Timeout ({int(_agent_wall)}s)"
            try:
                from core.harness.utils.local_llm_recover import unload_local_llm_best_effort
                import anyio as _anyio

                await _anyio.to_thread.run_sync(unload_local_llm_best_effort)
            except Exception:
                logging.debug("agent timeout ollama unload failed", exc_info=True)
            try:
                from core.services.execution_store import get_execution_store as _ges

                _es_to = _ges()
                if hasattr(_es_to, "close_running_syscall_events"):
                    await _es_to.close_running_syscall_events(
                        str(run_id),
                        status="timeout",
                        error=error_msg,
                        error_code="AGENT_WALL_TIMEOUT",
                    )
            except Exception:
                logging.debug("agent timeout close syscalls failed", exc_info=True)
        except Exception as e:
            status = "failed"
            error_msg = str(e) or repr(e) or type(e).__name__
            _log = __import__('logging').getLogger(__name__)
            _log.error(f"Agent {agent_id} execution failed (run_id={run_id}): {error_msg}", exc_info=True)
            # Phase 25 diagnostic: capture full traceback for debugging
            import traceback as _tb
            state["_error_traceback"] = _tb.format_exc()
    finally:
        if watch_task is not None and not watch_task.done():
            watch_task.cancel()
            try:
                await watch_task
            except Exception:
                pass  # noqa: cleanup-best-effort
            except _asyncio.CancelledError:
                # Py3.8+: CancelledError is BaseException — must not escape finally
                # or the HTTP request becomes Starlette "No response returned" 500.
                pass  # noqa: normal-cancellation
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

    # ── Close agent root + agent_end via RunGraph, then mark_run_done ──
    _end = _time.time()
    _duration_ms = int((_end - (t0_agent or _now)) * 1000)
    _rg_status = "ok" if status == "completed" else "error"

    try:
        from core.harness.observation.run_graph import close_node as _rg_close, open_node as _rg_open2, mark_run_done as _rg_done
        await _rg_close(
            run_id,
            f"agent:{agent_id}:start",
            status=_rg_status,
            result={"text": str(result_text or "")[:5000]},
            error=error_msg,
            duration_ms=_duration_ms,
            audit=True,
        )
        await _rg_open2(
            run_id,
            f"agent:{agent_id}:end",
            kind="agent",
            name="agent_end",
            parent_id=f"agent:{agent_id}:start",
            label="完成",
            role="work",
            audit=True,
        )
        await _rg_close(
            run_id,
            f"agent:{agent_id}:end",
            status=_rg_status,
            result={"text": str(result_text or "")[:5000]},
            error=error_msg,
            duration_ms=_duration_ms,
            audit=True,
        )
        await _rg_done(run_id, status="completed" if status == "completed" else ("timeout" if status == "timeout" else "failed"))
    except Exception as e:
        logging.debug(str(e), exc_info=True)

    try:
        from core.services.execution_store import get_execution_store
        _es = get_execution_store()
        _final_meta: Dict[str, Any] = {"stream": True}
        try:
            existing = await _es.get_agent_execution(str(run_id)) if hasattr(_es, "get_agent_execution") else None
            if isinstance(existing, dict) and isinstance(existing.get("metadata"), dict):
                _final_meta = {**existing["metadata"], **_final_meta}
        except Exception:
            existing = None
        # Eager skill_delivery finalize may have already closed the row — do not
        # wipe a good product with empty result_text if runner hung after FINISHED.
        # Also respect orphan/QR failed seals (do not re-greenwash to completed).
        _already_done = False
        try:
            if isinstance(existing, dict):
                _est = str(existing.get("status") or "").lower()
                _emeta = (
                    existing.get("metadata")
                    if isinstance(existing.get("metadata"), dict)
                    else {}
                )
                _eout = existing.get("output")
                _etext = ""
                if isinstance(_eout, str):
                    _etext = _eout.strip()
                elif isinstance(_eout, dict):
                    # skill_delivery often stores {code, language, text} — do not
                    # miss a sealed product that only has ``code`` (HTTP 500 after
                    # DeepSeek FE pass when text key empty).
                    _etext = str(
                        _eout.get("text")
                        or _eout.get("code")
                        or _eout.get("output")
                        or _eout.get("answer")
                        or ""
                    ).strip()
                _force_fail = str(
                    _emeta.get("force_failed_status")
                    or _emeta.get("_force_failed_status")
                    or ""
                ).strip().lower()
                _fin_src = str(_emeta.get("finalize_source") or "")
                # Any sealed failure/timeout must stick — including force_failed /
                # LLM-exhausted seals that lack quality_block metadata.
                if _est in ("failed", "error", "timeout") and (
                    _est == "timeout"
                    or _force_fail in ("timeout", "failed", "error", "cancelled", "canceled")
                    or _emeta.get("quality_block_completed")
                    or _emeta.get("require_review_incomplete")
                    or _emeta.get("_finalize_hard_fail")
                    or str(_emeta.get("done_verify_reason") or "").startswith(
                        "done_verify:"
                    )
                    or _fin_src
                    in (
                        "observe_done_verify_blocked",
                        "observe_auto_followup_review_incomplete",
                        "status_orphan_watch",
                        "reason_llm_failure_exhausted",
                        "observe_primary_skill_timeout",
                    )
                    or "timeout" in _fin_src
                    or "llm_failure" in _fin_src
                ):
                    _already_done = True
                    if not str(result_text or "").strip() and _etext:
                        result_text = _etext
                    status = "failed" if _est != "timeout" else _est
                    error_msg = str(existing.get("error") or error_msg or "") or None
                elif _est in ("completed", "ok", "success", "done") and len(_etext) >= 20:
                    _already_done = True
                    if not str(result_text or "").strip():
                        result_text = _etext
                    status = "completed"
                    error_msg = None
        except Exception:
            _already_done = False
        _out_payload: Dict[str, Any] = {"text": result_text or ""}
        # Normalize architecture drafts so overview→context etc. land in stored
        # product + quality_review (local LLMs often omit the context key).
        try:
            from core.management.execution_quality_review import (
                ensure_architecture_section_fields,
                ensure_architecture_rollout_weeks,
                sanitize_architecture_third_party,
                _unwrap_output as _eq_unwrap,
                _input_text as _eq_input_text,
            )
            import json as _json_norm

            _before = _eq_unwrap(_out_payload)
            _eq_in = _eq_input_text(_stored_input)
            _normed = ensure_architecture_section_fields(_before)
            _normed = ensure_architecture_rollout_weeks(_normed, _eq_in)
            _normed = sanitize_architecture_third_party(_normed, _eq_in)
            if isinstance(_normed, dict) and _normed != _before:
                _out_payload = {"text": _json_norm.dumps(_normed, ensure_ascii=False)}
                result_text = _out_payload["text"]
        except Exception:
            logging.debug("architecture section normalize skipped", exc_info=True)
        if (not _already_done) and str(status or "").lower() in ("completed", "ok", "success"):
            try:
                from core.management.execution_quality_review import (
                    review_execution_output,
                    quality_review_blocks_success,
                )

                skills = list(
                    getattr(agent_info, "required_skills", None)
                    or getattr(agent_info, "skills", None)
                    or []
                )
                skill_hint = " ".join(str(s) for s in skills[:8])
                _qr = review_execution_output(
                    kind="agent",
                    asset_id=str(agent_id),
                    asset_name=str(
                        getattr(agent_info, "display_name", None)
                        or getattr(agent_info, "name", None)
                        or agent_id
                    ),
                    input_payload=_stored_input,
                    output=_out_payload,
                    status=str(status),
                    hints=f"{skill_hint} {getattr(agent_info, 'name', '')}",
                )
                _final_meta["quality_review"] = _qr
                if quality_review_blocks_success(_qr):
                    status = "failed"
                    error_msg = str(
                        (_qr.get("headline") if isinstance(_qr, dict) else None)
                        or error_msg
                        or "coding deliverable failed quality review"
                    )
                    _final_meta["quality_block_completed"] = True
                    logging.info(
                        "agent stream blocked by quality_review run_id=%s verdict=%s",
                        run_id,
                        (_qr or {}).get("verdict") if isinstance(_qr, dict) else None,
                    )
            except Exception as _qr_e:
                logging.warning(
                    "agent stream quality_review skipped run_id=%s: %s",
                    run_id,
                    _qr_e,
                    exc_info=True,
                )
        if not _already_done:
            await _es.upsert_agent_execution({
                "id": run_id,
                "agent_id": agent_id,
                "status": status,
                "input": _stored_input,
                "output": _out_payload,
                "error": error_msg or "",
                "start_time": float(t0_agent or _now),
                "end_time": _end,
                "duration_ms": _duration_ms,
                "trace_id": trace_id,
                "metadata": _final_meta,
            })
        try:
            await _es.upsert_trace({
                "trace_id": trace_id,
                "name": f"workspace_agent:{agent_id}",
                "status": "completed" if status == "completed" else status,
                "start_time": float(t0_agent or _now),
                "end_time": _end,
                "duration_ms": _duration_ms,
                "attributes": {
                    "execution_id": run_id,
                    "agent_id": agent_id,
                    "session_id": session_id,
                    "source": "workspace_agent",
                    "error": error_msg or "",
                },
            })
        except Exception:
            logging.debug("upsert_trace at agent end failed run_id=%s", run_id, exc_info=True)
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
    """Resolve model adapter for chat service via centralized resolution (§12).

    Args:
        rt: rt 参数。
    """
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
    """Generate ontology evolution suggestions (Tier 1 rule-based + Tier 2 LLM-driven).

    Args:
        collection_id: collection 标识。
        max_suggestions: max_suggestions 参数。
        confidence_threshold: confidence_threshold 参数。
        include_llm: include_llm 参数。
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


# ── Agent eval artifacts (scoring_dimensions + eval_metric/runner) ──


async def generate_agent_eval(
    agent_id: str,
    *,
    force: bool = False,
    max_traces: int = 50,
    run_runner: bool = True,
    use_llm: bool = True,
) -> Dict[str, Any]:
    """Unique Core entry: generate Agent eval code / scoring_dimensions.

    Args:
        agent_id: Agent ID。
        force: 是否强制。
        max_traces: max_traces 参数。
        run_runner: run_runner 参数。
        use_llm: use_llm 参数。
    """
    from core.apps.eval.agent_eval import generate_agent_eval as _impl

    return await _impl(
        agent_id,
        force=force,
        max_traces=max_traces,
        run_runner=run_runner,
        use_llm=use_llm,
    )


def inspect_agent_eval(agent_id: str) -> Dict[str, Any]:
    """Read-only: scoring_dimensions + eval files + traces for one Agent.

    Args:
        agent_id: Agent ID。
    """
    from core.apps.eval.agent_eval import inspect_agent_eval as _impl

    return _impl(agent_id)


def enqueue_listed_agent_eval(agent_id: str) -> None:
    """Fire-and-forget after Agent 上架 (listed). Never raises to caller.

    Args:
        agent_id: Agent ID。
    """
    from core.apps.eval.agent_eval import enqueue_listed_agent_eval as _impl

    _impl(agent_id)


def predict_evolution_impact_for(
    suggestion: Dict[str, Any],
    collection_id: str = "default",
) -> Dict[str, Any]:
    """Predict the impact scope of accepting an evolution suggestion.

    Args:
        suggestion: suggestion 参数。
        collection_id: collection 标识。
    """
    from core.harness.knowledge.knowledge_ontology import get_ontology
    from core.harness.knowledge.knowledge_evolution_llm import predict_evolution_impact
    onto = get_ontology()
    return predict_evolution_impact(suggestion, onto)


# ── Ontology Health & Quality Facade (Phase 4) ──

def check_ontology_health_triggers(collection_id: str = "default") -> List[Dict[str, Any]]:
    """Check ontology health and return triggered curation tasks.

    Args:
        collection_id: collection 标识。
    """
    from core.harness.knowledge.knowledge_quality import check_ontology_health_triggers as _check
    return _check(collection_id=collection_id)


def get_entity_quality(entity_uri: str, *, collection_id: str = "default") -> Dict[str, Any]:
    """Get quality score and recent signals for an ontology entity.

    Args:
        entity_uri: entity_uri 参数。
        collection_id: collection 标识。
    """
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
    """Apply field-level security redaction to entity data.

    Args:
        data: data 参数。
        entity_uri: entity_uri 参数。
        actor_role: actor_role 参数。
        actor_scopes: actor_scopes 参数。
        collection_id: collection 标识。
    """
    from core.policy.field_level_security import apply_field_level_security
    return apply_field_level_security(
        data, entity_uri,
        actor_role=actor_role, actor_scopes=actor_scopes,
        collection_id=collection_id,
    )


def check_graph_entity_acl(
    domain_id: str,
    entity_id: str,
    role: str,
    action: str = "read",
) -> bool:
    """GraphIndex ABox instance ACL (T9). Empty role → allow.

    Args:
        domain_id: domain 标识。
        entity_id: entity 标识。
        role: role 参数。
        action: action 参数。
    """
    from core.policy.graph_abox_acl import check_entity_acl
    return check_entity_acl(domain_id, entity_id, role, action)


def redact_graph_entity_fields(
    domain_id: str,
    entity_id: str,
    payload: Dict[str, Any],
    role: str,
) -> Dict[str, Any]:
    """GraphIndex ABox field redaction for a role.

    Args:
        domain_id: domain 标识。
        entity_id: entity 标识。
        payload: 载荷 dict。
        role: role 参数。
    """
    from core.policy.graph_abox_acl import redact_entity_fields
    return redact_entity_fields(domain_id, entity_id, payload, role)


def resolve_abox_actor_role(
    *,
    explicit_role: str = "",
    header_role: str = "",
    scopes: Optional[List[str]] = None,
) -> str:
    """Map identity / PolicyGate role+scopes onto ABox ACL role.

    Args:
        explicit_role: explicit_role 参数。
        header_role: header_role 参数。
        scopes: scopes 参数。
    """
    from core.policy.graph_abox_acl import resolve_abox_actor_role as _resolve
    return _resolve(
        explicit_role=explicit_role,
        header_role=header_role,
        scopes=scopes,
    )


def ingest_abox_webhook(
    source_id: str,
    payload: Dict[str, Any],
    *,
    secret: Optional[str] = None,
    domain_id: Optional[str] = None,
) -> Dict[str, Any]:
    """Path B production ingest (connector.json → GraphIndex).

    Args:
        source_id: source 标识。
        payload: 载荷 dict。
        secret: secret 参数。
        domain_id: domain 标识。
    """
    from core.apps.fde.service.abox_connector import ingest_webhook_payload
    return ingest_webhook_payload(
        source_id, payload, secret=secret, domain_id=domain_id
    )


def import_abox_table_map(
    domain_id: str,
    *,
    rows: Any = None,
    csv_text: Optional[str] = None,
    relation_rows: Any = None,
    use_sample: bool = False,
) -> Dict[str, Any]:
    """Path B table/CSV → GraphIndex (connector.table_map).

    Args:
        domain_id: domain 标识。
        rows: rows 参数。
        csv_text: csv_text 参数。
        relation_rows: relation_rows 参数。
        use_sample: use_sample 参数。
    """
    from core.apps.fde.service.abox_connector import import_table_map_payload
    from core.harness.ontology_engine.graph_index import GraphIndex

    GraphIndex._loaded_instances.clear()
    g = GraphIndex.load(domain_id)
    meta = import_table_map_payload(
        g,
        domain_id=domain_id,
        rows=rows,
        csv_text=csv_text,
        relation_rows=relation_rows,
        use_sample=use_sample,
    )
    if hasattr(g, "save"):
        g.save()
    return {"status": "imported", "domain_id": domain_id, "path": "B", **meta}


def get_ontology_pillars_view(domain_id: str) -> Dict[str, Any]:
    """获取 ontology_pillars_view。

    Args:
        domain_id: domain 标识。
    """
    from core.apps.fde.service.ontology_pillars import get_ontology_pillars
    return get_ontology_pillars(domain_id)


def review_ontology_owl_offline(domain_id: str) -> Dict[str, Any]:
    """review_ontology_owl_offline。

    Args:
        domain_id: domain 标识。
    """
    from core.apps.fde.service.offline_owl_review import review_domain_owl_offline
    return review_domain_owl_offline(domain_id)


def get_governance_scenario_loop() -> Dict[str, Any]:
    """Xingye-shaped 8-step governance map with aiPlat honest status (read-only)."""
    from core.apps.fde.service.governance_loop import get_governance_loop_map

    return get_governance_loop_map()


def governance_quality_view(domain_id: str = "data-gov") -> Dict[str, Any]:
    """Step ⑥ vertical: OCS + gate-2 actions + value links.

    Args:
        domain_id: domain 标识。
    """
    from core.apps.fde.service.governance_deepen import governance_quality_snapshot

    return governance_quality_snapshot(domain_id)


async def governance_locate_view(
    domain_id: str,
    query: str,
    *,
    top_k: int = 8,
    with_graphrag: bool = False,
) -> Dict[str, Any]:
    """Step ⑦ vertical: locate entities on GraphIndex (+ optional GraphRAG).

    Args:
        domain_id: domain 标识。
        query: 查询。
        top_k: top_k 参数。
        with_graphrag: with_graphrag 参数。
    """
    from core.apps.fde.service.governance_deepen import locate_via_ontology_async

    return await locate_via_ontology_async(
        domain_id, query, top_k=top_k, with_graphrag=with_graphrag
    )


def governance_fetch_view(
    domain_id: str,
    entity_id: str,
    *,
    purpose: str = "org_pilot",
) -> Dict[str, Any]:
    """Org L5 Phase 1: locate→fetch sandbox snapshot (no live DB; D3).

    Args:
        domain_id: domain 标识。
        entity_id: entity 标识。
        purpose: purpose 参数。
    """
    from core.apps.org.service.org_io import fetch_by_entity

    return fetch_by_entity(domain_id, entity_id, purpose=purpose)


def governance_write_preview(
    domain_id: str,
    entity_id: str,
    patch: Any = None,
) -> Dict[str, Any]:
    """Org L5 Phase 1: write dry-run (default blocked).

    Args:
        domain_id: domain 标识。
        entity_id: entity 标识。
        patch: patch 参数。
    """
    from core.apps.org.service.org_io import preview_write

    return preview_write(domain_id, entity_id, patch if isinstance(patch, dict) else {})


def org_list_goals(domain_id: str = "") -> Dict[str, Any]:
    """Org L5 Phase 2: list OrgGoals.

    Args:
        domain_id: domain 标识。
    """
    from core.apps.org.service.org_runtime import list_goals

    return list_goals(domain_id or "")


def org_set_goal_status(goal_id: str, status: str) -> Dict[str, Any]:
    """Org L5 Phase 2: activate/pause/done OrgGoal.

    Args:
        goal_id: goal 标识。
        status: status 参数。
    """
    from core.apps.org.service.org_runtime import set_goal_status

    return set_goal_status(goal_id, status)


def org_run_goal(
    goal_id: str = "",
    *,
    domain_id: str = "it-ops",
    dry_actions: bool = True,
    week_label: str = "",
) -> Dict[str, Any]:
    """Org L5 Phase 2: execute one OrgRun (locate→fetch→HITL gate).

    Args:
        goal_id: goal 标识。
        domain_id: domain 标识。
        dry_actions: dry_actions 参数。
        week_label: week_label 参数。
    """
    from core.apps.org.service.org_runtime import run_org_goal

    return run_org_goal(
        goal_id,
        domain_id=domain_id,
        dry_actions=dry_actions,
        week_label=week_label,
    )


def org_list_runs(goal_id: str = "", limit: int = 20) -> Dict[str, Any]:
    """org_list_runs。

    Args:
        goal_id: goal 标识。
        limit: 返回条数上限。
    """
    from core.apps.org.service.org_runtime import list_runs

    return list_runs(goal_id, limit=limit)


def org_get_run(run_id: str) -> Dict[str, Any]:
    """org_get_run。

    Args:
        run_id: 运行 ID。
    """
    from core.apps.org.service.org_runtime import get_run

    return get_run(run_id)


def org_replay_trace(trace_id: str = "", *, domain_id: str = "it-ops") -> Dict[str, Any]:
    """V1: read-only five-step replay. Does not write ontology, edges, or runs.

    Args:
        trace_id: trace 标识。
        domain_id: domain 标识。
    """
    from core.apps.org.service.v_wave_replay import replay_org_trace

    return replay_org_trace(trace_id, domain_id=domain_id)


def org_resume_run(
    run_id: str,
    *,
    approve: bool = True,
    resolution: str = "",
) -> Dict[str, Any]:
    """Org L5 Phase 2: resume needs_hitl run after human decision.

    Args:
        run_id: 运行 ID。
        approve: approve 参数。
        resolution: resolution 参数。
    """
    from core.apps.org.service.org_runtime import resume_run

    return resume_run(run_id, approve=approve, resolution=resolution)


def org_weekly_kpi(
    domain_id: str = "it-ops",
    goal_id: str = "",
    *,
    week: str = "",
) -> Dict[str, Any]:
    """Org L5: weekly KPI snapshot (D2) + Phase 3 attribution.

    Args:
        domain_id: domain 标识。
        goal_id: goal 标识。
        week: week 参数。
    """
    from core.apps.org.service.org_kpi import weekly_kpi_report

    return weekly_kpi_report(domain_id, goal_id, week=week)


def org_joint_health(domain_id: str = "it-ops") -> Dict[str, Any]:
    """Read-only joint health. Never writes live YAML.

    Args:
        domain_id: domain 标识。
    """
    from core.apps.org.service.org_kpi import joint_health_view

    return joint_health_view(domain_id or "it-ops")


def org_search_memory(
    query: str = "",
    *,
    domain_id: str = "",
    limit: int = 20,
) -> Dict[str, Any]:
    """Org L5 Phase 3: exception jurisprudence / run memory search.

    Args:
        query: 查询。
        domain_id: domain 标识。
        limit: 返回条数上限。
    """
    from core.apps.org.service.org_memory import search_exceptions

    return search_exceptions(query, domain_id=domain_id, limit=limit)


def org_list_memory(domain_id: str = "", limit: int = 50) -> Dict[str, Any]:
    """org_list_memory。

    Args:
        domain_id: domain 标识。
        limit: 返回条数上限。
    """
    from core.apps.org.service.org_memory import list_memory

    return list_memory(limit=limit, domain_id=domain_id)


def org_fleet_gate(
    goal_id: str = "",
    *,
    domain_id: str = "it-ops",
    project_id: str = "",
) -> Dict[str, Any]:
    """Org L5 Phase 4 W6: evaluate multi-agent fleet hard gate.

    Args:
        goal_id: goal 标识。
        domain_id: domain 标识。
        project_id: project 标识。
    """
    from core.apps.org.service.org_fleet import evaluate_fleet_gate

    return evaluate_fleet_gate(goal_id, domain_id=domain_id, project_id=project_id)


def org_set_allow_fleet(goal_id: str, allow: bool) -> Dict[str, Any]:
    """org_set_allow_fleet。

    Args:
        goal_id: goal 标识。
        allow: allow 参数。
    """
    from core.apps.org.service.org_fleet import set_allow_fleet

    return set_allow_fleet(goal_id, allow)


def org_sandbox_rehearsals(limit: int = 5) -> Dict[str, Any]:
    """List sandbox rehearsals. Does not start a fleet.

    Args:
        limit: 返回条数上限。
    """
    from core.apps.org.service.org_fleet import list_sandbox_rehearsals

    return list_sandbox_rehearsals(limit=limit)


async def org_sandbox_conflict_probe(
    *,
    domain_id: str = "it-ops",
    resource_id: str = "shared_interface",
) -> Dict[str, Any]:
    """Sandbox concurrent lock probe. No live write.

    Args:
        domain_id: domain 标识。
        resource_id: resource 标识。
    """
    from core.apps.org.service.org_fleet import probe_sandbox_conflict

    return await probe_sandbox_conflict(domain_id or "it-ops", resource_id=resource_id or "shared_interface")


async def org_sandbox_rehearsal_start(
    *,
    role: str,
    domain_id: str,
    roles: List[Any],
) -> Dict[str, Any]:
    """Record a sandbox handoff. Never flips allow_fleet.

    Args:
        role: role 参数。
        domain_id: domain 标识。
        roles: roles 参数。
    """
    from core.apps.org.service.org_fleet import start_sandbox_rehearsal

    return await start_sandbox_rehearsal(role=role, domain_id=domain_id, roles=roles)


def org_field_ops_checklist(domain_id: str = "it-ops") -> Dict[str, Any]:
    """Org L5 Phase 4 W7: field ops readiness checklist.

    Args:
        domain_id: domain 标识。
    """
    from core.apps.org.service.org_field_ops import field_ops_checklist

    return field_ops_checklist(domain_id)


def org_customer_signoff(domain_id: str = "it-ops") -> Dict[str, Any]:
    """V3: customer signoff layer. Read-only. m4_claim_allowed stays false.

    Args:
        domain_id: domain 标识。
    """
    from core.apps.org.service.org_field_ops import customer_signoff_view

    return customer_signoff_view(domain_id or "it-ops")


def org_signoff_prep(
    domain_id: str = "it-ops",
    goal_id: str = "goal-it-ops-alert-sla",
    *,
    as_markdown: bool = False,
) -> Dict[str, Any]:
    """Read-only signoff prep score. Never flips m4_claim_allowed.

    Args:
        domain_id: domain 标识。
        goal_id: goal 标识。
        as_markdown: as_markdown 参数。
    """
    from core.apps.org.service.org_field_ops import signoff_prep_view

    return signoff_prep_view(
        domain_id or "it-ops",
        goal_id or "goal-it-ops-alert-sla",
        as_markdown=bool(as_markdown),
    )


async def org_approval_inbox(
    *,
    role: str,
    domain_id: str = "it-ops",
    goal_id: str = "goal-it-ops-alert-sla",
    kind: str = "",
    offset: int = 0,
    limit: int = 20,
) -> Dict[str, Any]:
    """H1: read-only approval inbox. Does not approve.

    Args:
        role: role 参数。
        domain_id: domain 标识。
        goal_id: goal 标识。
        kind: kind 参数。
        offset: 分页偏移。
        limit: 返回条数上限。
    """
    from core.apps.org.service.org_approvals import list_approval_inbox

    return await list_approval_inbox(
        role=role,
        domain_id=domain_id or "it-ops",
        goal_id=goal_id or "goal-it-ops-alert-sla",
        kind=kind or "",
        offset=offset,
        limit=limit,
    )


def list_unattended_approval_inbox(
    *,
    visibility: str = "inbox",
    pending_only: bool = True,
    session_id: str = "",
    limit: int = 200,
) -> Dict[str, Any]:
    """OpenWorker P1: durable wait-queue for tool approvals (not org H1 inbox).

    Args:
        visibility: visibility 参数。
        pending_only: pending_only 参数。
        session_id: 会话 ID。
        limit: 返回条数上限。
    """
    from core.harness.infrastructure.gates.approval_inbox import (
        ApprovalInboxStore,
        get_approval_inbox,
    )

    store: ApprovalInboxStore = get_approval_inbox()
    items = store.list_items(
        visibility=visibility or None,
        pending_only=bool(pending_only),
        session_id=session_id or None,
        limit=limit,
    )
    return {"items": items, "total": len(items)}


def resolve_unattended_approval(
    item_id: str,
    resolution: str,
    *,
    resolved_by: str = "",
) -> Dict[str, Any]:
    """Resolve a parked unattended approval (first-responder wins).

    Args:
        item_id: item 标识。
        resolution: resolution 参数。
        resolved_by: resolved_by 参数。
    """
    from core.harness.infrastructure.gates.approval_inbox import (
        InboxItem,
        get_approval_inbox,
    )

    item = get_approval_inbox().resolve(
        str(item_id),
        str(resolution or ""),
        resolved_by=str(resolved_by or ""),
    )
    if item is None or not isinstance(item, InboxItem):
        return {"ok": False, "error": "not_found"}
    return {"ok": True, "item": item.to_dict()}


def set_unattended_attendance(session_id: str, mode: str) -> Dict[str, Any]:
    """Set attendance=attended|inbox|auto for a session (daemon/cron use inbox|auto).

    Args:
        session_id: 会话 ID。
        mode: mode 参数。
    """
    from core.harness.infrastructure.gates.approval_inbox import get_approval_inbox

    norm = get_approval_inbox().set_attendance(str(session_id or "default"), mode)
    return {"session_id": str(session_id or "default"), "attendance": norm}


def get_unattended_attendance(session_id: str) -> Dict[str, Any]:
    """获取 unattended_attendance。

    Args:
        session_id: 会话 ID。
    """
    from core.harness.infrastructure.gates.approval_inbox import get_approval_inbox

    sid = str(session_id or "default")
    return {"session_id": sid, "attendance": get_approval_inbox().get_attendance(sid)}


def list_session_write_provenance(session_id: str = "") -> Dict[str, Any]:
    """OpenWorker P3: paths written this session (audit / Pi hybrid diagnostics).

    Args:
        session_id: 会话 ID。
    """
    from typing import List, Optional

    from core.harness.infrastructure.gates.session_write_provenance import (
        OriginRecord,
        SessionWriteProvenance,
        get_session_write_provenance,
    )

    store: SessionWriteProvenance = get_session_write_provenance()
    sid = str(session_id or "default")
    records: List[OriginRecord] = []
    for path in sorted(store.known_paths(sid)):
        rec: Optional[OriginRecord] = store.lookup(sid, path)
        if rec is not None:
            records.append(rec)
    return {
        "session_id": sid,
        "count": len(records),
        "items": [
            {"path": r.path, "origin": r.origin, "step": r.step, "at": r.at}
            for r in records
        ],
    }


async def org_approval_snapshot(
    kind: str,
    item_id: str,
    *,
    role: str,
    domain_id: str = "it-ops",
) -> Dict[str, Any]:
    """H1: read-only approval snapshot. Does not approve.

    Args:
        kind: kind 参数。
        item_id: item 标识。
        role: role 参数。
        domain_id: domain 标识。
    """
    from core.apps.org.service.org_approvals import get_approval_snapshot

    return await get_approval_snapshot(
        kind, item_id, role=role, domain_id=domain_id or "it-ops"
    )


def org_evidence_pack(
    *,
    role: str,
    domain_id: str = "it-ops",
    goal_id: str = "goal-it-ops-alert-sla",
    week: str = "",
    max_traces: int = 5,
    sandbox_mode: bool = False,
    as_markdown: bool = False,
) -> Dict[str, Any]:
    """H2: read-only signoff evidence pack. Not a signature.

    Args:
        role: role 参数。
        domain_id: domain 标识。
        goal_id: goal 标识。
        week: week 参数。
        max_traces: max_traces 参数。
        sandbox_mode: sandbox_mode 参数。
        as_markdown: as_markdown 参数。
    """
    from core.apps.org.service.org_evidence_pack import build_evidence_pack

    return build_evidence_pack(
        role=role,
        domain_id=domain_id or "it-ops",
        goal_id=goal_id or "goal-it-ops-alert-sla",
        week=week or "",
        max_traces=max_traces,
        sandbox_mode=sandbox_mode,
        as_markdown=as_markdown,
    )


def org_value_translation(
    *,
    domain_id: str = "it-ops",
    goal_id: str = "goal-it-ops-alert-sla",
    week: str = "",
    tenant_id: str = "",
) -> Dict[str, Any]:
    """H3: audit-friendly value translation. Not a signature.

    Args:
        domain_id: domain 标识。
        goal_id: goal 标识。
        week: week 参数。
        tenant_id: 租户 ID。
    """
    from core.apps.org.service.org_value_translation import translate_org_value

    return translate_org_value(
        domain_id=domain_id or "it-ops",
        goal_id=goal_id or "goal-it-ops-alert-sla",
        week=week or "",
        tenant_id=tenant_id or "",
    )


def org_value_roi_preview(
    *,
    domain_id: str = "it-ops",
    goal_id: str = "goal-it-ops-alert-sla",
    week: str = "",
    trial_minutes_per_incident: float,
    trial_mtta_seconds: float,
) -> Dict[str, Any]:
    """What-if ROI. Never writes baseline; never flips m4.

    Args:
        domain_id: domain 标识。
        goal_id: goal 标识。
        week: week 参数。
        trial_minutes_per_incident: trial_minutes_per_incident 参数。
        trial_mtta_seconds: trial_mtta_seconds 参数。
    """
    from core.apps.org.service.org_value_translation import preview_value_roi

    return preview_value_roi(
        domain_id=domain_id or "it-ops",
        goal_id=goal_id or "goal-it-ops-alert-sla",
        week=week or "",
        trial_minutes_per_incident=trial_minutes_per_incident,
        trial_mtta_seconds=trial_mtta_seconds,
    )


def org_h4_rules(*, role: str) -> Dict[str, Any]:
    """H4: read-only view of queue auto-pass rules. Sandbox switch on when no file.

    Args:
        role: role 参数。
    """
    from core.apps.org.service.org_auto_pass import h4_rules_view

    return h4_rules_view(role=role)


def org_h4_auto_audit(*, role: str, limit: int = 50) -> Dict[str, Any]:
    """H4: today's auto-pass audit. Admin only.

    Args:
        role: role 参数。
        limit: 返回条数上限。
    """
    from core.apps.org.service.org_auto_pass import h4_auto_audit

    return h4_auto_audit(role=role, limit=limit)


async def org_h4_auto_pass(*, role: str, domain_id: str = "it-ops") -> Dict[str, Any]:
    """H4: sandbox queue status pass. Never writes live YAML or edges.

    Args:
        role: role 参数。
        domain_id: domain 标识。
    """
    from core.apps.org.service.org_auto_pass import run_h4_auto_pass
    from core.apps.org.service.org_h4_seed import ensure_approval_rules_seed

    try:
        ensure_approval_rules_seed()
    except Exception:  # noqa: cleanup-best-effort
        pass
    return await run_h4_auto_pass(role=role, domain_id=domain_id or "it-ops")


def org_h5_drafts(*, role: str, domain_id: str = "it-ops") -> Dict[str, Any]:
    """H5: list draft packs and skill_candidate cases. Not a listing.

    Args:
        role: role 参数。
        domain_id: domain 标识。
    """
    from core.apps.org.service.org_skill_draft import list_skill_drafts

    return list_skill_drafts(role=role, domain_id=domain_id or "it-ops")


def org_h5_create_draft(*, role: str, case_id: str, domain_id: str = "it-ops") -> Dict[str, Any]:
    """H5: write a draft pack. Does not register or write SKILL.md.

    Args:
        role: role 参数。
        case_id: case 标识。
        domain_id: domain 标识。
    """
    from core.apps.org.service.org_skill_draft import create_skill_draft

    return create_skill_draft(role=role, case_id=case_id, domain_id=domain_id or "it-ops")


def org_h5_approve_draft(*, role: str, draft_id: str) -> Dict[str, Any]:
    """H5: human approve then register on the existing marketplace.

    Args:
        role: role 参数。
        draft_id: draft 标识。
    """
    from core.apps.org.service.org_skill_draft import approve_skill_draft

    return approve_skill_draft(role=role, draft_id=draft_id)


def org_h5_reject_draft(*, role: str, draft_id: str) -> Dict[str, Any]:
    """H5: reject a draft. Does not register.

    Args:
        role: role 参数。
        draft_id: draft 标识。
    """
    from core.apps.org.service.org_skill_draft import reject_skill_draft

    return reject_skill_draft(role=role, draft_id=draft_id)


def org_gap_hints(*, domain_id: str = "it-ops") -> Dict[str, Any]:
    """Read-only: repeated action failures may draft via existing proposal path.

    Args:
        domain_id: domain 标识。
    """
    from core.apps.org.service.org_skill_draft import list_action_gap_hints

    return list_action_gap_hints(domain_id=domain_id or "it-ops")


def org_preview_schema_gaps(*, domain_id: str = "it-ops") -> Dict[str, Any]:
    """Read-only Diff for schema_gap cases. Does not create proposals.

    Args:
        domain_id: domain 标识。
    """
    from core.apps.fde.service.k_wave_propose import preview_schema_gaps

    return preview_schema_gaps(domain_id or "it-ops")


def org_list_cold_cases(*, domain_id: str = "it-ops", limit: int = 20) -> Dict[str, Any]:
    """Read-only cold case archive. Not injected.

    Args:
        domain_id: domain 标识。
        limit: 返回条数上限。
    """
    from core.harness.knowledge.ontology_case_learning import list_cold_cases

    return list_cold_cases(domain_id or "it-ops", limit=limit)


def org_archive_cold_cases(*, role: str, domain_id: str = "it-ops") -> Dict[str, Any]:
    """Move low-yield cases to cold store. Does not delete or change TBox.

    Args:
        role: role 参数。
        domain_id: domain 标识。
    """
    role_n = (role or "").strip().lower()
    if not role_n:
        return {"ok": False, "reason": "identity_missing", "deleted": False, "wrote_live_yaml": False}
    if role_n not in ("admin", "operator"):
        return {"ok": False, "reason": "archive_forbidden", "deleted": False, "wrote_live_yaml": False}
    from core.harness.knowledge.ontology_case_learning import archive_cold_cases

    return archive_cold_cases(domain_id or "it-ops")


async def org_draft_schema_gaps(*, role: str, domain_id: str = "it-ops") -> Dict[str, Any]:
    """Draft edge proposals from schema_gap cases. Does not apply.

    Args:
        role: role 参数。
        domain_id: domain 标识。
    """
    role_n = (role or "").strip().lower()
    if not role_n:
        return {"ok": False, "reason": "identity_missing", "wrote_live_yaml": False, "auto_apply": False}
    if role_n not in ("admin", "operator"):
        return {"ok": False, "reason": "draft_forbidden", "wrote_live_yaml": False, "auto_apply": False}
    from core.apps.fde.service.k_wave_propose import draft_schema_gaps

    return await draft_schema_gaps(domain_id or "it-ops")


def org_skill_bundle(*, role: str, draft_ids: list) -> Dict[str, Any]:
    """H5: assemble existing drafts. No SKILL.md.

    Args:
        role: role 参数。
        draft_ids: draft_ids 参数。
    """
    from core.apps.org.service.org_skill_draft import assemble_skill_bundle

    return assemble_skill_bundle(role=role, draft_ids=list(draft_ids or []))


def org_value_baseline_get(*, role: str, tenant_id: str = "") -> Dict[str, Any]:
    """S2: read tenant value baseline.

    Args:
        role: role 参数。
        tenant_id: 租户 ID。
    """
    from core.apps.org.service.org_value_translation import get_value_baseline_view

    return get_value_baseline_view(role=role, tenant_id=tenant_id or "")


def org_value_baseline_put(
    *,
    role: str,
    tenant_id: str,
    baseline_minutes_per_incident: float,
    baseline_mtta_seconds: float,
) -> Dict[str, Any]:
    """S2: write tenant value baseline.

    Args:
        role: role 参数。
        tenant_id: 租户 ID。
        baseline_minutes_per_incident: baseline_minutes_per_incident 参数。
        baseline_mtta_seconds: baseline_mtta_seconds 参数。
    """
    from core.apps.org.service.org_value_translation import save_value_baseline

    return save_value_baseline(
        role=role,
        tenant_id=tenant_id,
        baseline_minutes_per_incident=baseline_minutes_per_incident,
        baseline_mtta_seconds=baseline_mtta_seconds,
    )


def org_domain_packs() -> Dict[str, Any]:
    """S3: list installable domain packs."""
    from core.apps.org.service.domain_pack_install import list_domain_packs

    return list_domain_packs()


def org_domain_pack_install(
    *,
    role: str,
    template_id: str,
    domain_id: str,
    display_name: str = "",
) -> Dict[str, Any]:
    """S3: install a domain pack into AIPLAT_HOME.

    Args:
        role: role 参数。
        template_id: template 标识。
        domain_id: domain 标识。
        display_name: display_name 参数。
    """
    from core.apps.org.service.domain_pack_install import install_domain_pack

    return install_domain_pack(
        role=role,
        template_id=template_id,
        domain_id=domain_id,
        display_name=display_name or "",
    )


def org_signoff_progress_get(*, role: str) -> Dict[str, Any]:
    """S4: read signoff progress. Never claims M4.

    Args:
        role: role 参数。
    """
    from core.apps.org.service.org_signoff_progress import get_signoff_progress

    return get_signoff_progress(role=role)


def org_signoff_progress_put(*, role: str, body: Dict[str, Any]) -> Dict[str, Any]:
    """S4: write oncall / dual-sign progress. m4_claim_allowed stays false.

    Args:
        role: role 参数。
        body: 请求体。
    """
    from core.apps.org.service.org_signoff_progress import save_signoff_progress

    return save_signoff_progress(role=role, body=body or {})


def org_live_unlock_status(domain_id: str = "it-ops") -> Dict[str, Any]:
    """org_live_unlock_status。

    Args:
        domain_id: domain 标识。
    """
    from core.apps.org.service.org_field_ops import evaluate_live_unlock
    from core.apps.org.service.org_live_adapter import live_io_gates

    intent = evaluate_live_unlock()
    gates = live_io_gates(domain_id or "it-ops")
    intent["http_gates"] = {
        "status": gates.get("status"),
        "live_io_enabled": gates.get("live_io_enabled"),
        "base_url_reason": gates.get("base_url_reason"),
        "interface_ref": gates.get("interface_ref"),
        "adapter": (gates.get("adapter") or {}).get("adapter"),
    }
    return intent


def org_list_interfaces(domain_id: str = "") -> Dict[str, Any]:
    """Phase C1.5: list InterfaceSpecs (yaml, else connector.live read-compat).

    Args:
        domain_id: domain 标识。
    """
    from core.apps.org.service.org_interface import list_interface_specs

    return list_interface_specs(domain_id or "")


def org_get_interface(domain_id: str = "it-ops") -> Dict[str, Any]:
    """Phase C1: get + validate InterfaceSpec for domain.

    Args:
        domain_id: domain 标识。
    """
    from core.apps.org.service.org_interface import get_interface_spec

    return get_interface_spec(domain_id or "it-ops")


def org_assert_action_interface(domain_id: str, action_id: str) -> Dict[str, Any]:
    """Phase C1: whether action_id is bound to domain InterfaceSpec.

    Args:
        domain_id: domain 标识。
        action_id: action 标识。
    """
    from core.apps.org.service.org_interface import assert_action_bound

    return assert_action_bound(domain_id or "it-ops", action_id)


def org_materialize_interface(domain_id: str = "it-ops") -> Dict[str, Any]:
    """Phase C1.5: copy InterfaceSpec into AIPLAT_HOME yaml. Never writes connector.live.

    Args:
        domain_id: domain 标识。
    """
    from core.apps.org.service.org_interface import materialize_interface_yaml

    return materialize_interface_yaml(domain_id or "it-ops")


def org_usage_weekly(domain_id: str = "", week: str = "") -> Dict[str, Any]:
    """org_usage_weekly。

    Args:
        domain_id: domain 标识。
        week: week 参数。
    """
    from core.apps.org.service.org_usage import weekly_usage

    return weekly_usage(domain_id or "", week or "")


async def k1_confirm_extraction(extraction_id: str, *, actor: str = "") -> Dict[str, Any]:
    """Phase K1: confirm extraction → change signal. Does not write live YAML or edges.

    Args:
        extraction_id: extraction 标识。
        actor: 操作者身份。
    """
    from core.apps.fde.service.k_wave_signal import confirm_extraction_k1

    return await confirm_extraction_k1(extraction_id, actor=actor)


def k2_propose_arbitration(**kwargs: Any) -> Dict[str, Any]:
    """Phase K2: open arbitration ticket; never writes cross-domain edge.

    Args:
        kwargs: kwargs 参数。
    """
    from core.apps.fde.service.k_wave_arbit import propose_ticket

    return propose_ticket(**kwargs)


def k2_list_arbitration(
    status: str = "",
    domain_id: str = "",
    tenant_id: str = "",
) -> Dict[str, Any]:
    """k2_list_arbitration。

    Args:
        status: status 参数。
        domain_id: domain 标识。
        tenant_id: 租户 ID。
    """
    from core.apps.fde.service.k_wave_arbit import list_tickets

    return list_tickets(status=status, domain_id=domain_id, tenant_id=tenant_id)


def k2_decide_arbitration(
    ticket_id: str,
    *,
    decision: str,
    actor: str = "",
    note: str = "",
) -> Dict[str, Any]:
    """k2_decide_arbitration。

    Args:
        ticket_id: ticket 标识。
        decision: decision 参数。
        actor: 操作者身份。
        note: note 参数。
    """
    from core.apps.fde.service.k_wave_arbit import decide_ticket

    return decide_ticket(ticket_id, decision=decision, actor=actor, note=note)


def k2_apply_arbitration(ticket_id: str, *, actor: str = "") -> Dict[str, Any]:
    """k2_apply_arbitration。

    Args:
        ticket_id: ticket 标识。
        actor: 操作者身份。
    """
    from core.apps.fde.service.k_wave_arbit import apply_ticket

    return apply_ticket(ticket_id, actor=actor)


def k2_rollback_arbitration_edge(ticket_id: str, *, role: str) -> Dict[str, Any]:
    """E2: one PolicyGate decision, then restore that ticket's cross-domain mark.

    Args:
        ticket_id: ticket 标识。
        role: role 参数。
    """
    from core.apps.fde.service.k_wave_arbit import rollback_ticket_edge

    return rollback_ticket_edge(ticket_id, role=role)


async def k5_scan_repeat_failures(domain_id: str = "it-ops") -> Dict[str, Any]:
    """Phase K5: repeated failures → edge draft. auto_apply stays false.

    Args:
        domain_id: domain 标识。
    """
    from core.apps.fde.service.k_wave_propose import enqueue_repeat_failure_proposals

    return await enqueue_repeat_failure_proposals(domain_id or "it-ops")


async def approve_proposal_once(proposal_id: str, *, role: str) -> Dict[str, Any]:
    """V4: one PolicyGate decision. Does not apply live YAML.

    Args:
        proposal_id: proposal 标识。
        role: role 参数。
    """
    from core.apps.fde.service.k_wave_approve import approve_proposal_once as _once

    return await _once(proposal_id, role=role)


def org_list_posts() -> Dict[str, Any]:
    """org_list_posts。
    """
    from core.apps.org.service.org_post import list_posts

    return list_posts()


def org_get_post(post_id: str = "") -> Dict[str, Any]:
    """org_get_post。

    Args:
        post_id: post 标识。
    """
    from core.apps.org.service.org_post import get_post

    return get_post(post_id)


def org_ingress_status() -> Dict[str, Any]:
    """Phase C2: feishu ingress readiness (no secrets)."""
    from core.apps.org.service.org_ingress import ingress_status

    return ingress_status()


def org_authorize_console_run(
    *,
    role: str,
    domain_id: str = "",
    goal_id: str = "",
    post_id: str = "",
) -> Dict[str, Any]:
    """V2: one decision for the management run route. Not the Feishu path.

    Args:
        role: role 参数。
        domain_id: domain 标识。
        goal_id: goal 标识。
        post_id: post 标识。
    """
    from core.apps.org.service.org_post import authorize_console_run

    return authorize_console_run(
        role=role,
        domain_id=domain_id,
        goal_id=goal_id,
        post_id=post_id,
    )


def org_ingest_feishu(
    payload: Dict[str, Any],
    *,
    headers: Optional[Dict[str, str]] = None,
    raw_body: bytes = b"",
) -> Dict[str, Any]:
    """Phase C2: signed Feishu event → confirm gate → org_run_goal.

    Args:
        payload: 载荷 dict。
        headers: headers 参数。
        raw_body: raw_body 参数。
    """
    from core.apps.org.service.org_ingress import ingest_feishu_event

    return ingest_feishu_event(payload, headers=headers, raw_body=raw_body)


def org_event_previews(limit: int = 5) -> Dict[str, Any]:
    """List sandbox event previews. Does not start live IO.

    Args:
        limit: 返回条数上限。
    """
    from core.apps.org.service.org_ingress import list_event_previews

    return list_event_previews(limit=limit)


def org_event_preview_start(
    *,
    role: str,
    domain_id: str,
    event_type: str,
) -> Dict[str, Any]:
    """Whitelist event → dry OrgRun. No channel push.

    Args:
        role: role 参数。
        domain_id: domain 标识。
        event_type: event_type 参数。
    """
    from core.apps.org.service.org_ingress import start_event_preview

    return start_event_preview(role=role, domain_id=domain_id, event_type=event_type)


async def suggest_ontology_from_table_schema(
    domain_id: str,
    *,
    table_name: str = "",
    columns: Any = None,
    csv_text: str = "",
    sample_rows: Any = None,
    author: str = "schema-suggest",
    enqueue: bool = True,
) -> Dict[str, Any]:
    """Path A: table/CSV headers → ontology proposal draft (never apply / never GraphIndex).

    Args:
        domain_id: domain 标识。
        table_name: table_name 参数。
        columns: columns 参数。
        csv_text: csv_text 参数。
        sample_rows: sample_rows 参数。
        author: author 参数。
        enqueue: enqueue 参数。
    """
    from core.apps.fde.service.ontology_code_suggestions import (
        suggest_classes_from_table_schema_async,
    )

    return await suggest_classes_from_table_schema_async(
        domain_id,
        table_name=table_name or "",
        columns=list(columns) if columns is not None else None,
        csv_text=csv_text or "",
        sample_rows=list(sample_rows) if sample_rows is not None else None,
        author=author or "schema-suggest",
        enqueue=bool(enqueue),
    )


def record_ontology_case(
    domain_id: str,
    *,
    title: str,
    summary: str,
    outcome: str = "success",
    reward: Any = None,
    action_id: str = "",
    entity_id: str = "",
    tags: Any = None,
    metadata: Any = None,
    write_graph: bool = False,
) -> Dict[str, Any]:
    """P0: write ontology learning case (does not mutate TBox YAML).

    Args:
        domain_id: domain 标识。
        title: title 参数。
        summary: summary 参数。
        outcome: outcome 参数。
        reward: reward 参数。
        action_id: action 标识。
        entity_id: entity 标识。
        tags: tags 参数。
        metadata: metadata 参数。
        write_graph: write_graph 参数。
    """
    from core.harness.knowledge.ontology_case_learning import OntologyCaseStore

    return OntologyCaseStore(domain_id).record(
        title=title,
        summary=summary,
        outcome=outcome,
        reward=float(reward) if reward is not None else None,
        action_id=action_id or "",
        entity_id=entity_id or "",
        tags=list(tags or []) if tags is not None else None,
        metadata=dict(metadata or {}) if metadata is not None else None,
        write_graph=bool(write_graph),
    )


def search_ontology_cases(
    domain_id: str,
    query: str = "",
    *,
    top_k: int = 5,
    outcome: str = "",
) -> Dict[str, Any]:
    """P0: reward-weighted case retrieval (optional UCB; may bump serve_count).

    Args:
        domain_id: domain 标识。
        query: 查询。
        top_k: top_k 参数。
        outcome: outcome 参数。
    """
    from core.harness.knowledge.ontology_case_learning import OntologyCaseStore

    hits = OntologyCaseStore(domain_id).search(query, top_k=top_k, outcome=outcome or "")
    return {"domain_id": domain_id, "query": query, "cases": hits, "count": len(hits)}


def ontology_case_learning_status(domain_id: str = "") -> Dict[str, Any]:
    """P2.5: learning flags + optional per-domain counters (no TBox mutate).

    Args:
        domain_id: domain 标识。
    """
    from core.harness.knowledge.ontology_case_learning import ontology_case_learning_meta

    return ontology_case_learning_meta(domain_id or "")


async def feedback_ontology_case(
    case_id: str,
    *,
    rating: float,
    note: str = "",
    actor: str = "user",
    auto_enqueue: bool = True,
) -> Dict[str, Any]:
    """P0 feedback + optional P1 gated proposal enqueue (never auto-apply).

    Args:
        case_id: case 标识。
        rating: rating 参数。
        note: note 参数。
        actor: 操作者身份。
        auto_enqueue: auto_enqueue 参数。
    """
    from core.harness.knowledge.ontology_case_learning import record_feedback_and_maybe_evolve

    return await record_feedback_and_maybe_evolve(
        case_id,
        rating=float(rating),
        note=note or "",
        actor=actor or "user",
        auto_enqueue=bool(auto_enqueue),
    )


async def evolve_ontology_from_case(
    case_id: str,
    *,
    force: bool = False,
    author: str = "ontology-case-learning",
) -> Dict[str, Any]:
    """P1: high-reward case → VersionedOntologyStore draft proposal only.

    Args:
        case_id: case 标识。
        force: 是否强制。
        author: author 参数。
    """
    from core.harness.knowledge.ontology_case_learning import maybe_enqueue_evolution_proposal

    return await maybe_enqueue_evolution_proposal(
        case_id, force=bool(force), author=author or "ontology-case-learning"
    )


async def rollback_ontology_case_evolution(case_id: str) -> Dict[str, Any]:
    """P2: restore live YAML from pre-apply snapshot for a case-linked proposal.

    Args:
        case_id: case 标识。
    """
    from core.apps.fde.service.k_wave_rollback import rollback_scope
    from core.harness.knowledge.ontology_case_learning import rollback_case_evolution

    out = await rollback_case_evolution(case_id)
    out["scope"] = rollback_scope()
    return out


def org_rollback_scope() -> Dict[str, Any]:
    """V5: read-only rollback boundary. Does not roll back."""
    from core.apps.fde.service.k_wave_rollback import rollback_scope

    return rollback_scope()


async def rollback_ontology_proposal(domain_id: str, proposal_id: str) -> Dict[str, Any]:
    """P2: restore live YAML for an applied ontology proposal. Not edges, not local drafts.

    Args:
        domain_id: domain 标识。
        proposal_id: proposal 标识。
    """
    from core.apps.fde.service.k_wave_rollback import rollback_scope
    from core.harness.knowledge.versioned_ontology_store import VersionedOntologyStore

    scope = rollback_scope()
    pid = (proposal_id or "").strip()
    if pid.startswith("draft_local_") or pid.startswith("k5_local_"):
        return {
            "ok": False,
            "reason": "local_draft_not_applied",
            "proposal_id": pid,
            "scope": scope,
            "covers_edges": False,
        }
    out = await VersionedOntologyStore(domain_id).rollback_proposal(pid)
    out["scope"] = scope
    out["covers_edges"] = False
    return out


def get_abox_acl_doc(domain_id: str) -> Dict[str, Any]:
    """获取 abox_acl_doc。

    Args:
        domain_id: domain 标识。
    """
    from core.policy.graph_abox_acl import load_abox_acl
    return load_abox_acl(domain_id)


def get_abox_crud_matrix() -> Dict[str, Any]:
    """获取 abox_crud_matrix。
    """
    from core.policy.graph_abox_acl import crud_matrix_doc
    return crud_matrix_doc()


def set_graph_entity_acl(
    domain_id: str,
    entity_id: str,
    *,
    deny_roles: Any = None,
    allow_roles: Any = None,
) -> Dict[str, Any]:
    """set_graph_entity_acl。

    Args:
        domain_id: domain 标识。
        entity_id: entity 标识。
        deny_roles: deny_roles 参数。
        allow_roles: allow_roles 参数。
    """
    from core.policy.graph_abox_acl import set_entity_acl
    return set_entity_acl(
        domain_id,
        entity_id,
        deny_roles=deny_roles,
        allow_roles=allow_roles,
    )


def set_graph_field_acl(
    domain_id: str,
    entity_id: str,
    field_name: str,
    *,
    visibility: str = "all",
    redaction: str = "mask",
    replace_with: str = "[REDACTED]",
) -> Dict[str, Any]:
    """set_graph_field_acl。

    Args:
        domain_id: domain 标识。
        entity_id: entity 标识。
        field_name: field_name 参数。
        visibility: visibility 参数。
        redaction: redaction 参数。
        replace_with: replace_with 参数。
    """
    from core.policy.graph_abox_acl import set_field_acl
    return set_field_acl(
        domain_id,
        entity_id,
        field_name,
        visibility=visibility,
        redaction=redaction,
        replace_with=replace_with,
    )


# ── Growth & Obsidian Facade (Phase E + Phase F) ──

def get_growth_stats(days: int = 30, *, collection_id: str = "default") -> Dict[str, Any]:
    """Get knowledge base growth statistics for the last N days.

    Args:
        days: days 参数。
        collection_id: collection 标识。
    """
    from core.harness.knowledge.knowledge_growth import get_growth_stats as _gs
    return _gs(collection_id=collection_id, days=days)


def check_obsidian_compatibility(collection_id: str = "default") -> Dict[str, Any]:
    """Verify that the wiki directory is 100% compatible with Obsidian vault format.

    Args:
        collection_id: collection 标识。
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
    """Assess all exercises in a chapter and return results.

    Args:
        learner_id: learner 标识。
        chapter_id: chapter 标识。
        answers: answers 参数。
    """
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
    """Instantiate a scene template into a PipelineConfig dict.

    Args:
        scene_id: scene 标识。
        params: params 参数。
        collection_id: collection 标识。
    """
    from core.harness.knowledge.scene_model import instantiate_scene as _inst
    return _inst(scene_id, params=params, collection_id=collection_id)


# ── Verification Facade (Phase C — stage output verification + replay) ──

def verify_stage_output(
    artifact: Dict[str, Any],
    expected_outcomes: List[Dict[str, Any]],
    stage_id: str = "",
) -> Dict[str, Any]:
    """Verify stage output against expected outcomes. Returns verification result dict.

    Args:
        artifact: artifact 参数。
        expected_outcomes: expected_outcomes 参数。
        stage_id: stage 标识。
    """
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
    """Register a writeback target for ontology actions.

    Args:
        target_type: target_type 参数。
        target_endpoint: target_endpoint 参数。
        trigger_actions: trigger_actions 参数。
        field_mapping: field_mapping 参数。
        collection_id: collection 标识。
    """
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
    """List all registered writeback targets.

    Args:
        collection_id: collection 标识。
    """
    from core.harness.knowledge.knowledge_writeback import load_writebacks
    return [c.to_dict() for c in load_writebacks(collection_id=collection_id)]


# ── Markings & Object Permissions Facade (Phase 2) ──

def get_entity_markings(
    entity_uri: str,
    *,
    collection_id: str = "default",
    resolve_effective: bool = True,
) -> Dict[str, Any]:
    """Get explicit and effective markings for an entity.

    Args:
        entity_uri: entity_uri 参数。
        collection_id: collection 标识。
        resolve_effective: resolve_effective 参数。
    """
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
    """Set a marking on an entity.

    Args:
        entity_uri: entity_uri 参数。
        label: label 参数。
        level: level 参数。
        scope: scope 参数。
        collection_id: collection 标识。
    """
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
    """Check if an actor can access a knowledge entity (three-layer fusion).

    Args:
        entity_uri: entity_uri 参数。
        action: action 参数。
        actor_scopes: actor_scopes 参数。
        actor_role: actor_role 参数。
        collection_id: collection 标识。
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
    """Return full domain schema as JSON dict for the ontology editor UI.

    Args:
        domain_id: domain 标识。
    """
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
    """Create a new empty ontology domain YAML file.

    Args:
        domain_id: domain 标识。
        name: name 参数。
        namespace: namespace 参数。
        description: description 参数。
        version: version 参数。
    """
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
    assert_live_yaml_write()
    Path(file_path).parent.mkdir(parents=True, exist_ok=True)
    Path(file_path).write_text(yaml_str, encoding="utf-8")

    _register_domain_in_registry(domain_id, name, description)
    # Unify dual path: registry.json + DomainRouter hot-register (no harness fork).
    try:
        from core.harness.knowledge.domain_router import DomainRouter

        DomainRouter().register_domain(
            domain_id,
            {
                "name": name,
                "description": description or "",
                "ontology_file": f"{domain_id}.yaml",
                "collection_id": domain_id,
            },
            auto_rebuild=False,
        )
    except Exception:
        logging.getLogger(__name__).debug(
            "DomainRouter.register_domain after create_ontology_domain failed",
            exc_info=True,
        )
    return {"id": domain_id, "name": name, "status": "created", "path": file_path}


def update_ontology_domain_meta(
    domain_id: str,
    *,
    name: str = "",
    description: str = "",
    version: str = "",
    namespace: str = "",
) -> Dict[str, Any]:
    """Update domain metadata (name, description, version, namespace).

    Args:
        domain_id: domain 标识。
        name: name 参数。
        description: description 参数。
        version: version 参数。
        namespace: namespace 参数。
    """
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
    assert_live_yaml_write()
    Path(file_path).write_text(yaml_str, encoding="utf-8")

    if name:
        _register_domain_in_registry(domain_id, name, raw.get("description", ""))
    _invalidate_domain_caches(domain_id)
    return {"id": domain_id, "status": "updated"}


def delete_ontology_domain(domain_id: str) -> Dict[str, Any]:
    """Delete an ontology domain YAML and optionally its graph data.

    Args:
        domain_id: domain 标识。
    """
    base_dir = _resolve_ontologies_dir()
    file_path = f"{base_dir}/{domain_id}.yaml"
    if not Path(file_path).exists():
        raise FileNotFoundError(f"Domain not found: {domain_id}")

    assert_live_yaml_write()
    Path(file_path).unlink()
    _remove_domain_from_registry(domain_id)
    return {"id": domain_id, "status": "deleted"}


def upsert_ontology_class(
    domain_id: str,
    class_name: str,
    class_data: Dict[str, Any],
) -> Dict[str, Any]:
    """Create or update a class definition in a domain YAML.

    Args:
        domain_id: domain 标识。
        class_name: class_name 参数。
        class_data: class_data 参数。
    """
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
    assert_live_yaml_write()
    Path(file_path).write_text(yaml_str, encoding="utf-8")

    _invalidate_domain_caches(domain_id)
    return {"domain_id": domain_id, "class_name": class_name, "status": "upserted"}


def delete_ontology_class(domain_id: str, class_name: str) -> Dict[str, Any]:
    """Remove a class — always via VersionedOntologyStore proposal (F2 live YAML gate).

    Args:
        domain_id: domain 标识。
        class_name: class_name 参数。
    """
    import asyncio

    async def _via_proposal() -> Dict[str, Any]:
        store = VersionedOntologyStore(domain_id)
        proposal_id = await store.create_proposal(
            {"remove": [class_name]},
            author="ontology-editor-delete",
        )
        approved = await store.approve_proposal(
            proposal_id,
            approver_role="admin",
            gate_passed=True,
        )
        if not approved.get("success"):
            return {
                "domain_id": domain_id,
                "class_name": class_name,
                "status": "approve_failed",
                "proposal_id": proposal_id,
                "reason": approved.get("reason"),
            }
        receipt = await store.apply_proposal(proposal_id)
        if not receipt.get("ok"):
            return {
                "domain_id": domain_id,
                "class_name": class_name,
                "status": "apply_failed",
                "proposal_id": proposal_id,
                "reason": receipt.get("reason"),
            }
        _invalidate_domain_caches(domain_id)
        return {
            "domain_id": domain_id,
            "class_name": class_name,
            "status": "deleted",
            "proposal_id": proposal_id,
            "via": "proposal",
        }

    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        loop = None
    if loop and loop.is_running():
        # Caller is async FastAPI — use dedicated async entry instead
        raise RuntimeError("use delete_ontology_class_async from async routes")
    return asyncio.run(_via_proposal())


async def delete_ontology_class_async(domain_id: str, class_name: str) -> Dict[str, Any]:
    """Async delete class via create→approve→apply proposal (F2-safe).

    Args:
        domain_id: domain 标识。
        class_name: class_name 参数。
    """
    store = VersionedOntologyStore(domain_id)
    current = store.load_current() or {}
    classes = current.get("classes") or {}
    if isinstance(classes, dict):
        exists = class_name in classes
    elif isinstance(classes, list):
        exists = any(
            isinstance(c, dict) and str(c.get("name") or "") == class_name for c in classes
        )
    else:
        exists = False
    if not exists:
        raise FileNotFoundError(f"Class '{class_name}' not found in '{domain_id}'")

    await store.store.initialize()
    proposal_id = await store.create_proposal(
        {"remove": [class_name]},
        author="ontology-editor-delete",
    )
    approved = await store.approve_proposal(
        proposal_id,
        approver_role="admin",
        gate_passed=True,
    )
    if not approved.get("success"):
        raise PermissionError(approved.get("reason") or "approve_failed")
    receipt = await store.apply_proposal(proposal_id)
    if not receipt.get("ok"):
        raise RuntimeError(receipt.get("reason") or "apply_failed")
    _invalidate_domain_caches(domain_id)
    return {
        "domain_id": domain_id,
        "class_name": class_name,
        "status": "deleted",
        "proposal_id": proposal_id,
        "via": "proposal",
    }


def publish_ontology_domain(domain_id: str) -> Dict[str, Any]:
    """Validate and publish — write domain YAML + create graph snapshot.

    Args:
        domain_id: domain 标识。
    """
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
    """List all saved rule versions for a domain.

    Args:
        domain_id: domain 标识。
    """
    from core.harness.ontology_engine.graph_index import GraphIndex
    try:
        graph = GraphIndex.load(domain_id)
        snaps = graph.list_snapshots(limit=50)
        return snaps
    except Exception:
        return []


def rollback_rule_version(domain_id: str, version_id: str) -> Dict[str, Any]:
    """Restore rules to a previous version — restore snapshot + invalidate caches.

    Args:
        domain_id: domain 标识。
        version_id: version 标识。
    """
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
    """List all role-based views for a domain.

    Args:
        domain_id: domain 标识。
    """
    from core.harness.knowledge.role_view import load_views, list_roles
    schema = get_ontology_domain_schema(domain_id)
    compiled = load_views(schema)
    return list_roles(compiled)


def get_view_for_domain(domain_id: str, role: str) -> Dict[str, Any]:
    """Get a single role view definition.

    Args:
        domain_id: domain 标识。
        role: role 参数。
    """
    from core.harness.knowledge.role_view import load_views
    schema = get_ontology_domain_schema(domain_id)
    compiled = load_views(schema)
    view = compiled.get(role)
    if not view:
        raise LookupError(f"View not found for role: {role}")
    return view


def upsert_view_for_domain(domain_id: str, role: str, view_data: Dict[str, Any]) -> Dict[str, Any]:
    """Create or update a role view in the domain YAML, writing back via yaml_serializer.

    Args:
        domain_id: domain 标识。
        role: role 参数。
        view_data: view_data 参数。
    """
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
    """Delete a role view from the domain YAML.

    Args:
        domain_id: domain 标识。
        role: role 参数。
    """
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
    """Resolve a term's meaning for a specific role perspective.

    Args:
        domain_id: domain 标识。
        role: role 参数。
        term: term 参数。
    """
    from core.harness.knowledge.role_view import load_views, resolve_term as _rt
    schema = get_ontology_domain_schema(domain_id)
    compiled = load_views(schema)
    definition = _rt(term, role, compiled)
    return {"domain_id": domain_id, "role": role, "term": term,
            "definition": definition, "found": definition is not None}


def validate_views_for_domain(domain_id: str) -> Dict[str, Any]:
    """Validate role views for a domain.

    Args:
        domain_id: domain 标识。
    """
    from core.harness.knowledge.role_view import validate_views as _vv
    schema = get_ontology_domain_schema(domain_id)
    return {"domain_id": domain_id, **_vv(schema)}


def resolve_prompt(prompt_id: str, **variables) -> str:
    """Synchronous prompt template resolution.

    Args:
        prompt_id: prompt 标识。
        variables: variables 参数。
    """
    from core.harness.utils.prompt_loader import _sync_resolve
    return _sync_resolve(prompt_id, **variables)


# ── Process Monitor Facade (v2.6) ──


def get_process_status(domain_id: str, process_name: str = "") -> List[Dict[str, Any]]:
    """Get running process instance status.

    Args:
        domain_id: domain 标识。
        process_name: process_name 参数。
    """
    from core.harness.knowledge.process_orchestrator import get_process_status as _gps
    return _gps(domain_id, process_name)


def get_bottlenecks(domain_id: str, limit: int = 10) -> List[Dict[str, Any]]:
    """Get process bottlenecks — instances stuck at same step longest.

    Args:
        domain_id: domain 标识。
        limit: 返回条数上限。
    """
    from core.harness.knowledge.process_orchestrator import get_bottlenecks as _gb
    return _gb(domain_id, limit)


def get_state_distribution(domain_id: str) -> List[Dict[str, Any]]:
    """Count instances per class per state.

    Args:
        domain_id: domain 标识。
    """
    from core.harness.knowledge.process_monitor import state_distribution as _sd
    return _sd(domain_id)


def get_bottleneck_analysis(domain_id: str, limit: int = 10) -> List[Dict[str, Any]]:
    """Find entities stuck in their current state longest.

    Args:
        domain_id: domain 标识。
        limit: 返回条数上限。
    """
    from core.harness.knowledge.process_monitor import bottleneck_analysis as _ba
    return _ba(domain_id, limit)


def get_sla_violations(domain_id: str) -> List[Dict[str, Any]]:
    """Get SLA violations triggered by time_elapsed transitions.

    Args:
        domain_id: domain 标识。
    """
    from core.harness.knowledge.process_monitor import sla_violations as _sv
    return _sv(domain_id)


def get_trend_data(domain_id: str, days: int = 7) -> List[Dict[str, Any]]:
    """Daily state transition trend data.

    Args:
        domain_id: domain 标识。
        days: days 参数。
    """
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

from core.harness.integration import KernelRuntime, get_harness, get_agent_registry  # P0-B4 canonical re-export (统一入口)
from core.harness.infrastructure.infra_bridge import create_infra_database_client  # P0-A2 修复 canonical re-export
from core.harness.evaluation.rag_evaluator import get_rag_evaluator, EvalSample  # P0-A2 修复 canonical re-export
from core.harness.infrastructure.gates.ontology_approval import list_pending, reject, get_history  # P0-A2 修复 canonical re-export
from core.harness.knowledge.scoring_engine import evaluate, get_alerts  # P0-A2 修复 canonical re-export
from core.harness.knowledge.metric_engine import scorecard, compute  # P0-A2 修复 canonical re-export
from core.harness.knowledge.context_bus import assemble_field_assessment  # P0-A2 修复 canonical re-export
from core.harness.knowledge.system_diagnostician import SystemDiagnostician  # P0-A2 修复 canonical re-export
from core.harness.knowledge.db import get_knowledge_db

from core.harness.knowledge.wiki_engine import search_pages  # v2.5: platform→CoreFacade  # noqa: boundary — CoreFacade canonical re-export
from core.harness.knowledge.semantic_cache import get_semantic_cache  # v2.5  # noqa: boundary — CoreFacade canonical re-export
from core.harness.knowledge.knowledge_ontology import validate_page_against_schema  # v2.5  # noqa: boundary — CoreFacade canonical re-export
from core.harness.knowledge.knowledge_ontology import export_suggestions_to_owl, write_suggestions_owl_file  # noqa: boundary — ontology learning output (P-补全)
from core.harness.knowledge.ontology_constraint_compiler import compile_ontology_constraints, compile_axiom_rules  # noqa: boundary — P1-L3 ontology constraint compiler (生成前逻辑锁)
from core.harness.ontology_engine.sirg_auditor import SirgAuditor, audit_trace_rules  # noqa: boundary — P1-L4b SIRG reasoning audit
from core.harness.knowledge.versioned_ontology_store import load_tier_approval_roles  # noqa: boundary — P2-L1 tier approval role matrix (配置驱动)

def sirg_audit(inference, fired_rule_ids, conclusion_relation):
    """P1-L4b: SIRG reasoning audit facade — compare fired rules vs required。

    Args:
        inference: inference 参数。
        fired_rule_ids: fired_rule_ids 参数。
        conclusion_relation: conclusion_relation 参数。
    """
    from core.harness.ontology_engine.sirg_auditor import SirgAuditor
    auditor = SirgAuditor.from_inference(inference)
    return auditor.audit_reasoning(fired_rule_ids, conclusion_relation)
from core.harness.infrastructure.infra_ocr_adapter import BBox, OCRToken, create_infra_ocr_adapter  # v2.5  # noqa: boundary — CoreFacade canonical re-export
from core.harness.models.spec_lifecycle import get_spec_lifecycle, RevisionTrigger  # v2.5  # noqa: boundary — CoreFacade canonical re-export
from core.harness.ontology_engine.triple_store import get_triple_store  # v2.5  # noqa: boundary — CoreFacade canonical re-export
from core.harness.ontology_engine.triple_scanner import scan_and_populate  # v2.5  # noqa: boundary — CoreFacade canonical re-export
from core.harness.ontology_engine.cleanup import cleanup_stale_entities_by_doc  # v2.5  # noqa: boundary — CoreFacade canonical re-export
from core.harness.learning.skill_simulator import SkillSimulator  # v2.5  # noqa: boundary — CoreFacade canonical re-export
from core.services.execution_store import get_execution_store  # v2.5  # noqa: boundary — CoreFacade canonical re-export
from core.services.tenant_store_protocol import get_tenant_store, set_tenant_store  # P0-A3  # noqa: boundary — CoreFacade canonical re-export
from core.harness.knowledge.wiki_engine import delete_page, read_page  # v2.5  # noqa: boundary — CoreFacade canonical re-export
from core.harness.observation.run_graph import (  # noqa: boundary — RunGraph ExecutionViewer projection
    open_node as open_run_graph_node,
    close_node as close_run_graph_node,
    upsert_node as upsert_run_graph_node,
    mark_run_done as mark_run_graph_done,
    get_graph as get_run_graph,
)

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
from core.harness.execution.team_planner import (  # noqa: boundary — CoreFacade re-export
    FACTORY_MODES,
    mode_to_team_template,
    normalize_factory_mode,
    recommend_team_stages,
    team_template_to_mode,
)
from core.harness.execution.pipeline_engine import get_event_bus
from core.harness.execution.factory_profile import (  # noqa: boundary — CoreFacade re-export
    apply_factory_profile_to_stages,
    normalize_factory_profile,
    resolve_project_factory_profile,
    FACTORY_PROFILE_DEMO,
    FACTORY_PROFILE_STANDARD,
)
from core.harness.coordination.spawn_policy import (  # noqa: boundary — CoreFacade re-export
    disable_dynamic_spawn,
    is_dynamic_spawn_disabled,
    should_skip_dynamic_spawn,
)
from core.harness.execution.stage_handoff import (  # noqa: boundary — CoreFacade re-export
    HANDOFF_FIELDS,
    apply_gate_failure,
    attach_handoff,
    build_stage_handoff,
    empty_handoff,
    extract_structured_fields,
    format_handoff_regenerate_feedback,
    format_structured_artifact_block,
    gate_check,
    is_schema_gate_pause,
    normalize_handoff,
    schema_is_active,
    try_resume_schema_gate,
    write_stage_handoff,
)
from core.harness.utils.output_style import (  # noqa: boundary — CoreFacade re-export
    STYLE_ADHD,
    STYLE_DEFAULT,
    STYLE_VERSION,
    apply_project_style_meta,
    assign_output_style_experiment,
    build_style_overlay,
    compare_output_style_arms,
    estimate_reply_tokens,
    infer_followups,
    inject_output_style,
    load_adhd_skill_text,
    query_output_style_events,
    record_output_style_event,
    resolve_output_style,
    skill_body_hash,
    whitelist_overrides,
)
from core.harness.utils.team_culture import (  # noqa: boundary — CoreFacade re-export
    CULTURE_MAX_TOKENS,
    CULTURE_VERSION,
    apply_project_culture_meta,
    build_culture_overlay,
    compose_prose_overlays,
    culture_body_hash,
    inject_team_culture,
    load_culture_text,
    resolve_culture_enabled,
    truncate_culture_body,
)
from core.harness.utils.coding_intensity import (  # noqa: boundary — CoreFacade re-export
    CODING_INTENSITIES,
    build_coding_policy_block,
    default_intensity_for_factory_mode,
    intensity_to_policy_profile,
    is_strict_coding_profile,
    normalize_coding_intensity,
    ponytail_overlay_for_intensity,
    resolve_coding_intensity,
    resolve_ponytail_mode,
)
from core.harness.utils.writing_profile import (  # noqa: boundary — CoreFacade re-export
    PROFILE_CONCISE,
    PROFILE_OFF,
    PROFILE_VERSION,
    apply_concise_prose,
    apply_error_message,
    apply_handoff_fields,
    apply_project_writing_meta,
    build_writing_overlay,
    resolve_writing_profile,
)
from core.harness.execution.run_structure_diagram import (  # noqa: boundary — CoreFacade re-export
    STATE_STRUCTURE_KEY,
    build_run_structure_diagram,
    stages_to_mermaid,
    write_structure_diagram,
)
from core.harness.execution.run_evidence_page import (  # noqa: boundary — CoreFacade re-export
    STATE_EVIDENCE_KEY,
    STATE_EVIDENCE_METRICS_KEY,
    build_run_evidence_page,
    collect_evidence_data,
    empty_evidence_metrics,
    is_evidence_expired,
    merge_evidence_metrics,
    render_evidence_html,
    resolve_ttl_hours,
    verification_success,
    write_evidence_page,
)
from core.harness.execution.factory_bloat_metrics import (  # noqa: boundary — CoreFacade re-export
    BASELINE_PROJECT_KEY,
    STATE_BLOAT_KEY,
    compare_bloat,
    compute_bloat_from_state,
    write_bloat_metrics,
)
from core.harness.execution.stage_outcome_samples import (  # noqa: boundary — CoreFacade re-export
    query_stage_outcome_samples,
    record_stage_outcome_sample,
    summarize_stage_outcome_samples,
)
from core.harness.team_harness import (  # noqa: boundary — CoreFacade re-export
    configure_team_harness,
    is_autosync_enabled,
    load_team_harness_schema,
    materialize_team_harness_schema,
    maybe_autosync_team_harness,
    pull_team_harness,
    push_team_harness,
    render_mr_template,
    restore_team_backup,
    team_is_dirty,
)
from core.harness.team_sources import (  # noqa: boundary — CoreFacade re-export
    apply_configured_sources,
    configure_sources,
    list_source_namespaces,
    merge_source_tree,
    namespaced_skill_candidates,
)
from core.harness.teamai_seed_export import (  # noqa: boundary — CoreFacade re-export
    export_teamai_seed,
)
from core.harness.feedback_loops.local import (  # noqa: boundary — CoreFacade re-export
    FeedbackLevel,
    FeedbackType,
    get_local_feedback,
)
from core.harness.team_factory_seeds import (  # noqa: boundary — CoreFacade re-export
    apply_team_factory_seeds,
    coding_closed_loop_runtime_gaps,
    resolve_factory_sanitize_file,
    resolve_team_yaml_candidates,
    rollback_team_factory_seeds,
    sync_coding_closed_loop_team_seeds,
)
from core.harness.team_friction import (  # noqa: boundary — CoreFacade re-export
    attach_friction_cta,
    clear_friction_cta,
    confirm_friction_share,
    list_local_learnings,
    note_regenerate,
    record_friction_event,
    record_schema_gate_friction,
)
from core.harness.utils.team_skill_subscription import (  # noqa: boundary — CoreFacade re-export
    apply_stage_skill_subscription,
    filter_skills_by_subscription,
    resolve_subscription_policy,
)
from core.harness.team_digest import (  # noqa: boundary — CoreFacade re-export
    build_team_digest,
    record_digest_view,
)
from core.services.config_registry_store import ConfigRegistryKey, get_config_registry_store


# ── Stubs for platform imports where definition has not yet been created ──
# These are imported by platform but the core implementation hasn't been wired yet.

def cancel_pipeline(run_id: str) -> Any:
    """Cancel a running pipeline by appending a cancel_requested event.

    Args:
        run_id: 运行 ID。
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


def start_stdio_kernel() -> Any:
    """Start the stdio JSON-RPC persistent kernel (P0-a, 对标 Codex app-server).

    外部程序/CI/SRE 面板 spawn `python -m core.acp.stdio_server` 即可通过
    stdin/stdout JSONL 驱动 Thread（thread/start|resume|approve|reject|
    rollback|cancel + item.event 流式）。本函数返回 kernel 实例供进程内
    使用/测试（server 启动时若 AIPLAT_STDIO_KERNEL=1 则后台启动）。
    """
    from core.acp.stdio_server import StdioKernel

    return StdioKernel()


async def import_claude_memories(
    base_path: str = "",
    max_sessions: int = 50,
) -> Dict[str, Any]:
    """导入 Claude Code 会话 JSONL → MemoryManager（P0-b，对标 Codex external_agent_config_migration）。

    Args:
        base_path: base_path 参数。
        max_sessions: max_sessions 参数。
    """
    from core.harness.memory.import_claude_sessions import import_claude_sessions
    from core.harness.memory.manager import MemoryManager

    mm = MemoryManager()
    return await import_claude_sessions(
        memory_manager=mm,
        base_path=base_path or None,
        max_sessions=max_sessions,
    )


def recall_team_brain(query: str = "", limit: int = 8) -> list:
    """Team Brain Auto-Recall — 聚合 TaskSkill / shared_memory / promoted experience。

    Args:
        query: 查询。
        limit: 返回条数上限。
    """
    from core.harness.memory.team_brain import recall_team_solutions

    return [it.to_dict() for it in recall_team_solutions(query or "", limit=int(limit or 8))]


def team_brain_status() -> Dict[str, Any]:
    """Team Brain 统计（by_kind / paths）。"""
    from core.harness.memory.team_brain import team_brain_status as _status

    return _status()


def org_harness_status(
    *,
    run_id: str = "",
    recent_limit: int = 10,
    tenant_id: str = "",
) -> Dict[str, Any]:
    """组织 harness 暗账本：HITL 串行 / 审批 + 黄金集回归 / P0 漏检 + duty_board。

    Args:
        run_id: 运行 ID。
        recent_limit: recent_limit 参数。
        tenant_id: 租户 ID。
    """
    from core.harness.meta.org_harness_metrics import org_harness_status as _status

    return _status(
        run_id=run_id or "",
        recent_limit=int(recent_limit or 10),
        tenant_id=tenant_id or "",
    )


def build_duty_board(
    payload: Optional[Dict[str, Any]] = None,
    *,
    adoption: Optional[Dict[str, Any]] = None,
    thresholds: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Governance 值班板裁决（go/watch/block/unavailable；禁止假成功率）。

    Args:
        payload: 载荷 dict。
        adoption: adoption 参数。
        thresholds: thresholds 参数。
    """
    from core.harness.meta.org_harness_metrics import build_duty_board as _board

    return _board(payload, adoption=adoption, thresholds=thresholds)


def load_duty_board_thresholds(
    *,
    override: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Duty-board YAML bands（override / AIPLAT_DUTY_BOARD_CONFIG / AIPLAT_HOME / seed）。

    Args:
        override: override 参数。
    """
    from core.harness.meta.org_harness_metrics import load_duty_board_thresholds as _load

    thr, source = _load(override=override)
    return {"thresholds": thr, "source": source}


def load_duty_board_playbook(
    *,
    override: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Duty-officer playbook（go/watch/block/unavailable 固定动作列表）。

    Args:
        override: override 参数。
    """
    from core.harness.meta.org_harness_metrics import load_duty_board_playbook as _load

    playbook, source = _load(override=override)
    return {"playbook": playbook, "source": source}


def collect_merge_gates_posture() -> Dict[str, Any]:
    """合入闸门姿态（mode/block_after/豁免负债账）— 豁免必须可见，禁止静默后门。"""
    from core.harness.meta.org_harness_metrics import collect_merge_gates_posture as _collect

    return _collect()


def assess_exemption_debt(
    config: Optional[Dict[str, Any]] = None,
    *,
    now: Any = None,
) -> Dict[str, Any]:
    """豁免即负债：owner+上限+到期未复审→block（合入闸门 / 值班板共用）。

    Args:
        config: config 参数。
        now: now 参数。
    """
    from core.harness.meta.physical_merge_gates import (
        assess_exemption_debt as _assess,
        load_physical_gates_config,
    )

    cfg = config
    if cfg is None:
        cfg, _src = load_physical_gates_config()
    return _assess(cfg, now=now)


def assess_gate_meta(
    *,
    thresholds: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """门禁元评估：窗口内 block/豁免/SKIP/申诉率 → go|watch|block（不发明低样本率）。

    Args:
        thresholds: thresholds 参数。
    """
    from core.harness.meta.gate_meta_eval import assess_gate_meta as _assess

    return _assess(thresholds=thresholds)


def assess_repo_health(
    *,
    thresholds: Optional[Dict[str, Any]] = None,
    run_scan: bool = False,
    persist: bool = False,
) -> Dict[str, Any]:
    """合入后/周度仓库健康：全树 LOC/god/fanout/deps JSONL → go|watch|block|unavailable。

    Args:
        thresholds: thresholds 参数。
        run_scan: run_scan 参数。
        persist: persist 参数。
    """
    from core.harness.meta.repo_health_scan import assess_repo_health as _assess

    return _assess(thresholds=thresholds, run_scan=run_scan, persist=persist)


def scan_repo_health(
    *,
    persist: bool = True,
) -> Dict[str, Any]:
    """执行一次全树健康扫描（可选写入 org/repo_health JSONL）。

    Args:
        persist: persist 参数。
    """
    from core.harness.meta.repo_health_scan import (
        append_health_snapshot,
        assess_repo_health as _assess,
        scan_repo_health as _scan,
    )

    metrics = _scan()
    persisted = append_health_snapshot(metrics) if persist else None
    out = _assess()
    out["scan"] = {
        "py_files": metrics.get("py_files"),
        "py_loc": metrics.get("py_loc"),
        "god_files": metrics.get("god_files"),
        "high_fanout_files": metrics.get("high_fanout_files"),
        "dep_entries": metrics.get("dep_entries"),
    }
    out["persisted"] = persisted
    return out


def workspace_agent_needs_coding_defaults(
    *,
    agent_cfg: Optional[Dict[str, Any]] = None,
    agent_meta: Optional[Dict[str, Any]] = None,
    skills: Optional[List[Any]] = None,
) -> bool:
    """Workspace Execute 是否应注入编码闭环默认（配置/技能信号，禁 agent_id）。

    Args:
        agent_cfg: agent_cfg 参数。
        agent_meta: agent_meta 参数。
        skills: skills 参数。
    """
    from core.schemas_builder import workspace_agent_needs_coding_defaults as _needs

    return _needs(agent_cfg=agent_cfg, agent_meta=agent_meta, skills=skills)


def inject_workspace_coding_defaults(
    state: Dict[str, Any],
    *,
    agent_cfg: Optional[Dict[str, Any]] = None,
    agent_meta: Optional[Dict[str, Any]] = None,
    skills: Optional[List[Any]] = None,
) -> List[str]:
    """升级 Workspace Execute state 至与工厂 uses_file_output 相同的编码闭环。

    Args:
        state: state 参数。
        agent_cfg: agent_cfg 参数。
        agent_meta: agent_meta 参数。
        skills: skills 参数。
    """
    from core.schemas_builder import inject_workspace_coding_defaults as _inject

    return _inject(state, agent_cfg=agent_cfg, agent_meta=agent_meta, skills=skills)


def apply_template_stage_overlay(
    dest: Any, src: Any, *, only_missing: bool = False
) -> Any:
    """工厂 recommend_team：把团队模板 YAML 的 coding 闭环字段拷到计划阶段。

    Args:
        dest: dest 参数。
        src: src 参数。
        only_missing: only_missing 参数。
    """
    from core.schemas_builder import apply_template_stage_overlay as _apply

    return _apply(dest, src, only_missing=only_missing)


def backfill_stage_from_team_templates(stage: Any) -> Any:
    """resume 无 config_json 时按 agent_id 从团队模板回填闭环字段。

    Args:
        stage: stage 参数。
    """
    from core.schemas_builder import backfill_stage_from_team_templates as _backfill

    return _backfill(stage)


def extract_stage_persist_config(raw: Any) -> Dict[str, Any]:
    """流水线启动时写入 pipeline_stages.config_json 的闭环字段快照。

    Args:
        raw: raw 参数。
    """
    from core.schemas_builder import extract_stage_persist_config as _extract

    return _extract(raw)


def pipeline_stage_from_store_row(sr: Any) -> Any:
    """resume：从 store 行（含 config_json）重建 PipelineStageConfig。

    Args:
        sr: sr 参数。
    """
    from core.schemas_builder import pipeline_stage_from_store_row as _from_row

    return _from_row(sr)


def coerce_execution_type(
    raw: str,
    *,
    skill_name: str = "",
) -> tuple:
    """Normalize SKILL execution_type; default fail-closed rejects unknown (no silent LLM).

    Args:
        raw: raw 参数。
        skill_name: skill_name 参数。
    """
    from core.harness.registry.execution_type_policy import coerce_execution_type as _coerce

    return _coerce(raw, skill_name=skill_name)


def execution_type_fail_closed() -> bool:
    """Whether unknown execution_type must hard-fail (default closed; SOFT_DEV / authorized FAIL_OPEN open)."""
    from core.harness.registry.execution_type_policy import execution_type_fail_closed as _fc

    return _fc()


def fail_open_governance_status() -> dict:
    """E5: FAIL_OPEN reason/by/until/expiry status (authorized only when complete + not expired)."""
    from core.harness.registry.execution_type_policy import fail_open_governance_status as _st

    return _st()


def known_execution_types() -> frozenset:
    """Canonical execution_type set for CI / lint."""
    from core.harness.registry.execution_type_policy import known_execution_types as _k

    return _k()


def record_gate_run(
    *,
    physical: Optional[Dict[str, Any]] = None,
    testability: Optional[Dict[str, Any]] = None,
    exit_blocked: bool = False,
    source: str = "check",
    staged: bool = False,
) -> Optional[str]:
    """记录一次合入闸门检查结果（gate_meta JSONL；AIPLAT_GATE_META_PERSIST=0 可关）。

    Args:
        physical: physical 参数。
        testability: testability 参数。
        exit_blocked: exit_blocked 参数。
        source: source 参数。
        staged: staged 参数。
    """
    from core.harness.meta.gate_meta_eval import record_gate_run as _rec

    return _rec(
        physical=physical,
        testability=testability,
        exit_blocked=exit_blocked,
        source=source,
        staged=staged,
    )


def record_gate_skip(
    *,
    env: str = "SKIP_PHYSICAL_GATES",
    gate: str = "physical",
    source: str = "api",
    note: str = "",
) -> Optional[str]:
    """记录 SKIP_* 绕过（值班板 skip_rate；禁止静默）。

    Args:
        env: env 参数。
        gate: gate 参数。
        source: source 参数。
        note: note 参数。
    """
    from core.harness.meta.gate_meta_eval import record_gate_skip as _rec

    return _rec(env=env, gate=gate, source=source, note=note)


def record_gate_appeal(
    *,
    code: str,
    owner: str,
    note: str = "",
    gate: str = "physical",
    source: str = "api",
) -> Optional[str]:
    """记录误杀/假阳性申诉（值班板 appeal_rate → 调参）。

    Args:
        code: code 参数。
        owner: owner 参数。
        note: note 参数。
        gate: gate 参数。
        source: source 参数。
    """
    from core.harness.meta.gate_meta_eval import record_gate_appeal as _rec

    return _rec(code=code, owner=owner, note=note, gate=gate, source=source)


def load_adoption_snapshot() -> Dict[str, Any]:
    """Duty board HITL/Howl snapshot（缺失则为空；不发明成功率）。"""
    from core.harness.meta.org_harness_metrics import load_adoption_snapshot as _snap

    return _snap()


def evaluate_physical_merge_gates(
    *,
    name_status: str = "",
    numstat: str = "",
    unified_diff: str = "",
    profile_name: str = "",
    config: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Merge-time inflation + shape gates（非运行时入口校验；见 physical_merge_gates）。

    Args:
        name_status: name_status 参数。
        numstat: numstat 参数。
        unified_diff: unified_diff 参数。
        profile_name: profile_name 参数。
        config: config 参数。
    """
    from core.harness.meta.physical_merge_gates import DiffStats, evaluate_diff as _eval

    report = _eval(
        name_status=name_status or "",
        numstat=numstat or "",
        unified_diff=unified_diff or "",
        profile_name=profile_name or "",
        config=config,
    )
    # Canonical type re-export for DiffStats (wiring + platform consumers).
    if report.stats is not None and not isinstance(report.stats, DiffStats):
        raise TypeError("physical_merge_gates.stats must be DiffStats")
    return report.to_dict()


def evaluate_testability_gate(
    *,
    files: Optional[Dict[str, str]] = None,
    snippets: Optional[Dict[str, str]] = None,
    workspace_root: str = "",
    mode: str = "",
    config: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """P1 testability gate — handlers need pure unit tests (not integration-only).

    Args:
        files: files 参数。
        snippets: snippets 参数。
        workspace_root: workspace_root 参数。
        mode: mode 参数。
        config: config 参数。
    """
    from pathlib import Path

    from core.harness.meta.testability_gate import (
        evaluate_diff_snippets,
        evaluate_files,
    )

    if snippets is not None:
        root = Path(workspace_root) if str(workspace_root or "").strip() else None
        return evaluate_diff_snippets(
            snippets,
            config=config,
            mode_override=mode or "",
            workspace_root=root,
        ).to_dict()
    return evaluate_files(
        files or {},
        config=config,
        mode_override=mode or "",
    ).to_dict()


def validate_evidence_envelope(
    raw: Optional[Dict[str, Any]] = None,
    *,
    demote: bool = True,
    mode: str = "",
) -> Dict[str, Any]:
    """Evidence Envelope validate — demote/reject/strict; no fake confirmed.

    Args:
        raw: raw 参数。
        demote: demote 参数。
        mode: mode 参数。
    """
    from core.harness.meta.evidence_envelope import EnvelopeValidation, validate_envelope

    result = validate_envelope(raw, demote=demote, mode=mode or "")
    if not isinstance(result, EnvelopeValidation):
        raise TypeError("validate_envelope must return EnvelopeValidation")
    return result.to_dict()


def attach_evidence_envelopes(
    issues: Optional[list] = None,
    *,
    run_id: str = "",
    reject_fake: bool = True,
) -> Dict[str, Any]:
    """Attach validated envelopes; reject illegal confirmed/block claims by default.

    Args:
        issues: issues 参数。
        run_id: 运行 ID。
        reject_fake: reject_fake 参数。
    """
    from core.harness.meta.evidence_envelope import (
        attach_envelopes_to_issues,
        check_issues_envelope_integrity,
        summarize_envelopes,
    )

    attached = attach_envelopes_to_issues(
        list(issues or []),
        run_id=run_id or "",
        reject_fake=bool(reject_fake),
    )
    summary = summarize_envelopes(attached)
    return {
        "issues": attached,
        "summary": summary,
        "integrity": check_issues_envelope_integrity(attached),
    }


def assert_evidence_envelope_integrity(
    raw: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Hard gate: illegal confirmed/block ⇒ ok=False (safe demoted envelope still returned).

    Args:
        raw: raw 参数。
    """
    from core.harness.meta.evidence_envelope import (
        EnvelopeValidation,
        assert_envelope_integrity,
    )

    result = assert_envelope_integrity(raw)
    if not isinstance(result, EnvelopeValidation):
        raise TypeError("assert_envelope_integrity must return EnvelopeValidation")
    return result.to_dict()


def allow_evidence_release_block(
    envelope: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Whether a finding alone may block release (derived/speculative → no).

    Args:
        envelope: envelope 参数。
    """
    from core.harness.meta.evidence_envelope import allow_release_block

    ok, reason = allow_release_block(envelope or {})
    return {"allow": bool(ok), "reason": reason}


def fold_findings_for_duty(
    findings: Optional[list] = None,
    *,
    run_id: str = "",
) -> Dict[str, Any]:
    """Duty-board fold: attach envelopes; derived/speculative → watch, not sole block.

    Args:
        findings: findings 参数。
        run_id: 运行 ID。
    """
    from core.harness.meta.evidence_envelope import fold_findings_for_duty as _fold

    return dict(_fold(findings or [], run_id=run_id or ""))


def publish_team_brain_manual(
    title: str,
    summary: str,
    *,
    source_agent: str = "",
    keywords: Optional[list] = None,
) -> Dict[str, Any]:
    """登记人工团队解法 → shared_memory（供跨 Agent 召回）。

    Args:
        title: title 参数。
        summary: summary 参数。
        source_agent: source_agent 参数。
        keywords: keywords 参数。
    """
    from core.harness.memory.team_brain import publish_manual_solution

    return publish_manual_solution(
        title=title,
        summary=summary,
        source_agent=source_agent,
        keywords=keywords,
    )


def ingest_ide_capture(
    prompt: str,
    result: str = "",
    *,
    tools: Optional[list] = None,
    success: bool = True,
    tags: Optional[list] = None,
    source: str = "ide",
    session_id: str = "",
    write_wiki: bool = False,
) -> Dict[str, Any]:
    """IDE/Cursor/CC 旁路捕获 → Team Brain（可选 Session Wiki）。不新建平行库。

    Args:
        prompt: prompt 参数。
        result: result 参数。
        tools: tools 参数。
        success: success 参数。
        tags: tags 参数。
        source: source 参数。
        session_id: 会话 ID。
        write_wiki: write_wiki 参数。
    """
    from core.harness.memory.ide_capture import ingest_ide_capture as _ingest

    return _ingest(
        prompt,
        result,
        tools=tools,
        success=success,
        tags=tags,
        source=source,
        session_id=session_id,
        write_wiki=write_wiki,
    )


def query_session_archive(
    query: str,
    *,
    limit: int = 3,
    session_id: str = "",
    tenant_id: str = "default",
) -> Dict[str, Any]:
    """Past compacted turns. Not pinned facts — caller asks, we search.

    Args:
        query: 查询。
        limit: 返回条数上限。
        session_id: 会话 ID。
        tenant_id: 租户 ID。
    """
    from core.harness.memory.file_store import session_archive_query

    return session_archive_query(
        query,
        limit=limit,
        session_id=session_id,
        tenant_id=tenant_id or "default",
    )


def sticky_memory_slice(
    max_chars: Optional[int] = None, *, tenant_id: str = "default"
) -> Dict[str, Any]:
    """User profile + pinned MEMORY.md for Pi session start. Shared char budget.

    Args:
        max_chars: max_chars 参数。
        tenant_id: 租户 ID。
    """
    from core.harness.memory.profile_builder import compose_sticky_memory

    return compose_sticky_memory(max_chars, tenant_id=tenant_id)


def seal_answer_with_receipts(text: str, context: Optional[Dict[str, Any]] = None):
    """Platform completion-receipt bind (fix/path claims). Re-export for apps.

    Args:
        text: text 参数。
        context: context 参数。
    """
    from core.harness.execution.execution_seal import seal_answer_with_receipts as _fn

    return _fn(text, context)


def check_done_verify(context: Optional[Dict[str, Any]] = None) -> Optional[str]:
    """DONE verify ring with coding/review fail-closed on exceptions.

    Args:
        context: context 参数。
    """
    from core.harness.execution.execution_seal import check_done_verify as _fn

    return _fn(context)


def coding_deliverable_veto(
    context: Optional[Dict[str, Any]] = None,
    *,
    bound_skill_ids: Optional[List[Any]] = None,
    skills: Any = None,
) -> Optional[str]:
    """Coding thin-stub / missing follow-up veto before DONE.

    Args:
        context: context 参数。
        bound_skill_ids: bound_skill_ids 参数。
        skills: skills 参数。
    """
    from core.harness.execution.execution_seal import coding_deliverable_veto as _fn

    return _fn(context, bound_skill_ids=bound_skill_ids, skills=skills)


def seal_before_finish(
    context: Optional[Dict[str, Any]] = None,
    *,
    bound_skill_ids: Optional[List[Any]] = None,
    skills: Any = None,
    bind_receipts: bool = True,
):
    """Receipt bind + coding veto + done_verify. Returns ``(seal_status, block_reason)``.

    Args:
        context: context 参数。
        bound_skill_ids: bound_skill_ids 参数。
        skills: skills 参数。
        bind_receipts: bind_receipts 参数。
    """
    from core.harness.execution.execution_seal import seal_before_finish as _fn

    return _fn(
        context,
        bound_skill_ids=bound_skill_ids,
        skills=skills,
        bind_receipts=bind_receipts,
    )


def upsert_pinned_memory(
    content: str,
    *,
    key: str = "preference",
    source: str = "agent",
    old_text: str = "",
    tenant_id: str = "default",
) -> Dict[str, Any]:
    """Write or replace a durable pinned fact. Budget-full same-key merges automatically.

    Args:
        content: content 参数。
        key: key 参数。
        source: source 参数。
        old_text: old_text 参数。
        tenant_id: 租户 ID。
    """
    from core.harness.memory.file_store import (
        memory_char_budget,
        replace_memory_entry,
        write_memory,
    )

    tid = (tenant_id or "default").strip() or "default"
    body = (content or "").strip()
    needle = (old_text or "").strip()
    if needle:
        ok = replace_memory_entry(
            needle, body, key=key, source=source, tenant_id=tid
        )
        return {
            "ok": ok,
            "action": "replace",
            "key": key,
            "budget": memory_char_budget(),
            "tenant_id": tid,
        }
    ok = write_memory(body, key=key, source=source, tenant_id=tid)
    return {
        "ok": ok,
        "action": "write",
        "key": key,
        "budget": memory_char_budget(),
        "tenant_id": tid,
    }


def write_session_wiki(
    title: str,
    summary: str,
    *,
    session_id: str = "",
    tags: Optional[list] = None,
    source: str = "session",
) -> Dict[str, Any]:
    """编码会话收尾短页 → wiki_engine（draft topics）。

    Args:
        title: title 参数。
        summary: summary 参数。
        session_id: 会话 ID。
        tags: tags 参数。
        source: source 参数。
    """
    from core.harness.memory.session_wiki import write_session_wiki_page

    return write_session_wiki_page(
        title=title,
        summary=summary,
        session_id=session_id,
        tags=tags,
        source=source,
    )


async def run_code_review_gold_eval(
    *,
    profile: str = "balanced",
    gold_dir: Optional[str] = None,
    case_ids: Optional[list] = None,
    match_only: bool = False,
    limit: int = 0,
    tenant_id: str = "",
    persist: bool = True,
    record_novel: bool = False,
) -> Dict[str, Any]:
    """ReviewBench 风格：租户黄金 PR × autoreview → Precision/Recall/P0 召回。

    Args:
        profile: 评测 profile。
        gold_dir: 黄金集目录。
        case_ids: case_ids 参数。
        match_only: match_only 参数。
        limit: 返回条数上限。
        tenant_id: 租户 ID。
        persist: persist 参数。
        record_novel: record_novel 参数。
    """
    from core.harness.evaluation.code_review_gold import run_code_review_gold_eval as _run

    return await _run(
        profile=profile,
        gold_dir=gold_dir,
        case_ids=case_ids,
        match_only=match_only,
        limit=limit,
        tenant_id=tenant_id,
        persist=persist,
        record_novel=record_novel,
    )


# ── EVAL_V1 E2 EvalStore ──────────────────────────────────


def eval_store_health(*, tenant_id: str = "") -> Dict[str, Any]:
    """eval_store_health。

    Args:
        tenant_id: 租户 ID。
    """
    from core.apps.eval.service.store import get_eval_store

    return get_eval_store(tenant_id=tenant_id).health()


def eval_store_list_sets(*, tenant_id: str = "", limit: int = 100) -> list:
    """eval_store_list_sets。

    Args:
        tenant_id: 租户 ID。
        limit: 返回条数上限。
    """
    from core.apps.eval.service.store import get_eval_store

    return get_eval_store(tenant_id=tenant_id).list_sets(limit=limit)


def eval_store_get_set(set_id: str, *, tenant_id: str = "") -> Optional[Dict[str, Any]]:
    """eval_store_get_set。

    Args:
        set_id: set 标识。
        tenant_id: 租户 ID。
    """
    from core.apps.eval.service.store import get_eval_store

    return get_eval_store(tenant_id=tenant_id).get_set(set_id)


def eval_store_create_set(
    *,
    name: str,
    version: str = "0",
    split: str = "dev",
    meta: Optional[Dict[str, Any]] = None,
    set_id: Optional[str] = None,
    tenant_id: str = "",
) -> Dict[str, Any]:
    """eval_store_create_set。

    Args:
        name: name 参数。
        version: version 参数。
        split: split 参数。
        meta: meta 参数。
        set_id: set 标识。
        tenant_id: 租户 ID。
    """
    from core.apps.eval.service.store import get_eval_store

    return get_eval_store(tenant_id=tenant_id).create_set(
        name=name, version=version, split=split, meta=meta, set_id=set_id
    )


def eval_store_list_tasks(*, set_id: str = "", tenant_id: str = "", limit: int = 500) -> list:
    """eval_store_list_tasks。

    Args:
        set_id: set 标识。
        tenant_id: 租户 ID。
        limit: 返回条数上限。
    """
    from core.apps.eval.service.store import get_eval_store

    return get_eval_store(tenant_id=tenant_id).list_tasks(set_id=set_id, limit=limit)


def eval_store_create_task(
    *,
    set_id: str,
    input_data: Optional[Dict[str, Any]] = None,
    expected: Optional[Dict[str, Any]] = None,
    rubric: Optional[Dict[str, Any]] = None,
    tags: Optional[list] = None,
    hard_negative: bool = False,
    source: str = "",
    task_id: Optional[str] = None,
    tenant_id: str = "",
) -> Dict[str, Any]:
    """eval_store_create_task。

    Args:
        set_id: set 标识。
        input_data: input_data 参数。
        expected: expected 参数。
        rubric: rubric 参数。
        tags: tags 参数。
        hard_negative: hard_negative 参数。
        source: source 参数。
        task_id: task 标识。
        tenant_id: 租户 ID。
    """
    from core.apps.eval.service.store import get_eval_store

    return get_eval_store(tenant_id=tenant_id).create_task(
        set_id=set_id,
        input_data=input_data,
        expected=expected,
        rubric=rubric,
        tags=tags,
        hard_negative=hard_negative,
        source=source,
        task_id=task_id,
    )


def eval_store_import_code_review_gold(
    *,
    gold_dir: Optional[str] = None,
    tenant_id: str = "",
    set_name: str = "code-review-gold",
    set_version: str = "v0-seed",
) -> Dict[str, Any]:
    """eval_store_import_code_review_gold。

    Args:
        gold_dir: 黄金集目录。
        tenant_id: 租户 ID。
        set_name: set_name 参数。
        set_version: set_version 参数。
    """
    from core.apps.eval.service.store import import_code_review_gold

    return import_code_review_gold(
        gold_dir=gold_dir,
        tenant_id=tenant_id,
        set_name=set_name,
        set_version=set_version,
    )


def eval_bootstrap_e3_gold(
    *,
    tenant_id: str = "eval-v1",
    gold_dir: Optional[str] = None,
    annotator: str = "solo_reviewer",
) -> Dict[str, Any]:
    """EVAL_V1 E3: ≥15 runnable gold + solo review queue (no κ).

    Args:
        tenant_id: 租户 ID。
        gold_dir: 黄金集目录。
        annotator: annotator 参数。
    """
    from core.apps.eval.service.gold_bootstrap import bootstrap_e3_gold

    return bootstrap_e3_gold(
        tenant_id=tenant_id, gold_dir=gold_dir, annotator=annotator
    )


def eval_list_exam_sets() -> list:
    """List built-in Agent exam papers (eval sets)."""
    from core.apps.eval.service.agent_exam_ops import list_exam_sets

    return list_exam_sets()


def list_named_workspaces(*, tenant_id: str = "") -> Dict[str, Any]:
    """List local + remote named workspace profiles visible to tenant.

    Args:
        tenant_id: 租户 ID。
    """
    from urllib.parse import urlparse

    from core.harness.named_workspace.registry import ensure_registry, list_registry_entries
    from core.harness.named_workspace.resolve import resolve_named_workspace
    from core.harness.named_workspace.errors import WorkspaceError

    ensure_registry()
    items = []
    for row in list_registry_entries():
        try:
            resolve_named_workspace(
                row["id"], method="GET", tenant_id=tenant_id or None
            )
        except WorkspaceError:
            continue
        kind = str(row.get("kind") or "local")
        host = None
        if kind == "remote" and row.get("base_url"):
            host = urlparse(str(row["base_url"])).hostname
        items.append(
            {
                "id": row["id"],
                "label": row["label"],
                "kind": kind,
                "base_url_host": host,
            }
        )
    return {
        "ok": True,
        "items": items,
        "phase1_boundary": (
            "本工作区一期只隔离 Agent 与评测结果；traces/缓存/附件/其它 DB 仍共享。"
        ),
        "remote_boundary": (
            "远程 Core = 换 API 目标；≠ 本机分区；≠ 外部拉模式 Agent。"
        ),
    }


def create_named_workspace(
    *,
    workspace_id: str,
    label: str = "",
    tenant_id: str = "",
    kind: str = "local",
    base_url: str = "",
    auth_secret_env: str = "",
    allowed_routes: Optional[list] = None,
) -> Dict[str, Any]:
    """Create local empty named workspace or remote Core profile (idempotent by id).

    Args:
        workspace_id: 工作区 ID。
        label: label 参数。
        tenant_id: 租户 ID。
        kind: kind 参数。
        base_url: base_url 参数。
        auth_secret_env: auth_secret_env 参数。
        allowed_routes: allowed_routes 参数。
    """
    from core.harness.named_workspace.agent_mgr import invalidate_agent_manager
    from core.harness.named_workspace.registry import (
        create_local_workspace,
        create_remote_workspace,
    )

    k = (kind or "local").strip().lower()
    tenants = ["*"] if not tenant_id else [tenant_id, "*"]
    if k == "remote":
        entry = create_remote_workspace(
            workspace_id,
            label=label,
            base_url=base_url,
            auth_secret_env=auth_secret_env,
            allowed_routes=list(allowed_routes or []),
            allowed_tenants=tenants,
        )
    else:
        entry = create_local_workspace(
            workspace_id,
            label=label,
            allowed_tenants=tenants,
        )
        invalidate_agent_manager(str(entry.get("id") or ""))
    return {
        "ok": True,
        "workspace": {
            "id": entry.get("id"),
            "label": entry.get("label"),
            "kind": entry.get("kind"),
            "base_url": entry.get("base_url"),
            "auth_secret_configured": bool(entry.get("auth_secret_env")),
        },
    }


async def eval_run_agent_exam(
    *,
    agent_id: str,
    set_id: str,
    live: bool = False,
    max_tasks: int = 0,
    persist: bool = True,
) -> Dict[str, Any]:
    """Bind exam set tasks to agent_id and dry-run or live-execute.

    Args:
        agent_id: Agent ID。
        set_id: set 标识。
        live: live 参数。
        max_tasks: max_tasks 参数。
        persist: persist 参数。
    """
    from core.apps.eval.service.agent_exam_ops import run_agent_exam

    return await run_agent_exam(
        agent_id=agent_id,
        set_id=set_id,
        live=live,
        max_tasks=max_tasks,
        persist=persist,
    )


def eval_match_cases_for_agent_target(
    *,
    agent_id: str,
    set_ids: Optional[list] = None,
    capabilities: Optional[list] = None,
    tools: Optional[list] = None,
    permissions: Optional[list] = None,
    roles: Optional[list] = None,
    eval_profile: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """P0 Object Contract: advisory MatchReport for agent vs set applicability draft.

    Args:
        agent_id: Agent ID。
        set_ids: set_ids 参数。
        capabilities: capabilities 参数。
        tools: tools 参数。
        permissions: permissions 参数。
        roles: roles 参数。
        eval_profile: eval_profile 参数。
    """
    from core.apps.eval.service.agent_exam_ops import match_cases_for_agent_target

    return match_cases_for_agent_target(
        agent_id=agent_id,
        set_ids=set_ids,
        capabilities=capabilities,
        tools=tools,
        permissions=permissions,
        roles=roles,
        eval_profile=eval_profile,
    )


def eval_resolve_capability_id(capability_id: str, *, fail_closed: bool = True) -> str:
    """Capability ID Map v1: legacy → canonical (fail closed by default).

    Args:
        capability_id: capability 标识。
        fail_closed: fail_closed 参数。
    """
    from core.apps.eval.service.capability_id_map import resolve_capability_id

    return resolve_capability_id(capability_id, fail_closed=fail_closed)


def eval_resolve_capability_ids(
    ids: Optional[list] = None, *, fail_closed: bool = True
) -> list:
    """Resolve many capability ids to canonical (deduped).

    Args:
        ids: ids 参数。
        fail_closed: fail_closed 参数。
    """
    from core.apps.eval.service.capability_id_map import resolve_capability_ids

    return resolve_capability_ids(ids or [], fail_closed=fail_closed)


def eval_validate_test_purpose(
    purpose: Optional[Dict[str, Any]] = None,
    *,
    prompt: str = "",
    capabilities: Optional[list] = None,
) -> Dict[str, Any]:
    """Validate EvalCase.test_purpose (schema v1); returns {ok, errors}.

    Args:
        purpose: purpose 参数。
        prompt: prompt 参数。
        capabilities: capabilities 参数。
    """
    from core.apps.eval.service.test_purpose import validate_test_purpose

    errors = validate_test_purpose(
        purpose, prompt=prompt, capabilities=capabilities
    )
    return {"ok": not errors, "errors": errors, "schema": "eval.case_test_purpose.v1"}


def eval_evaluate_t0_inscope_contracts() -> Dict[str, Any]:
    """T0: validate mock-tool/session/long-context fixtures + runtime map (no execute)."""
    from core.apps.eval.service.inscope_contracts_t0 import evaluate_t0_inscope_contracts

    return evaluate_t0_inscope_contracts()


def eval_evaluate_m0_impl_mode_contracts() -> Dict[str, Any]:
    """M0: impl_modes / matrix / rank_fingerprint / parity contracts (no live runner)."""
    from core.apps.eval.service.agent_impl_mode import evaluate_m0_impl_mode_contracts

    return evaluate_m0_impl_mode_contracts()


def eval_resolve_impl_modes(source: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """M0: resolve multi-value impl_modes (unknown≠react; deferred≠unknown).

    Args:
        source: source 参数。
    """
    from core.apps.eval.service.agent_impl_mode import resolve_impl_modes

    return resolve_impl_modes(source or {})


def eval_compute_rank_fingerprint(**kwargs: Any) -> Dict[str, Any]:
    """M0: cross-subject rank_fingerprint (excludes agent_id / workspace / time).

    Args:
        kwargs: kwargs 参数。
    """
    from core.apps.eval.service.agent_impl_mode import compute_rank_fingerprint

    return compute_rank_fingerprint(**kwargs)


def eval_plan_mode_executions(
    source: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """M0: selection union + per-mode separate execution plan (no live).

    Args:
        source: source 参数。
    """
    from core.apps.eval.service.agent_impl_mode import (
        plan_executions_per_mode,
        resolve_impl_modes,
        select_capabilities_union,
    )

    impl = resolve_impl_modes(source or {})
    return {
        "impl_modes": impl,
        "selection": select_capabilities_union(impl),
        "execution": plan_executions_per_mode(impl),
        "claim_eligible": False,
        "rank_claim": False,
    }


async def eval_run_m1a_mode_exam(
    *,
    live: bool = False,
    modes: Optional[list] = None,
    max_cases_per_mode: int = 0,
) -> Dict[str, Any]:
    """M1a: plan_execute + conversational per-mode exam (tools/retrieval/network=none).

    Args:
        live: live 参数。
        modes: modes 参数。
        max_cases_per_mode: max_cases_per_mode 参数。
    """
    from core.apps.eval.service.mode_aware_exam import run_m1a_mode_exam

    return await run_m1a_mode_exam(
        live=bool(live),
        modes=modes,
        max_cases_per_mode=int(max_cases_per_mode or 0),
    )


async def eval_run_m1b_mode_exam(
    *,
    live: bool = False,
    modes: Optional[list] = None,
    max_cases_per_mode: int = 0,
) -> Dict[str, Any]:
    """M1b: rag per-mode exam (retrieval=required fixture; tools/network/session=none).

    Args:
        live: live 参数。
        modes: modes 参数。
        max_cases_per_mode: max_cases_per_mode 参数。
    """
    from core.apps.eval.service.mode_aware_exam import run_m1b_mode_exam

    return await run_m1b_mode_exam(
        live=bool(live),
        modes=modes,
        max_cases_per_mode=int(max_cases_per_mode or 0),
    )


async def eval_run_m1c_mode_exam(
    *,
    live: bool = False,
    modes: Optional[list] = None,
    max_cases_per_mode: int = 0,
) -> Dict[str, Any]:
    """M1c: react per-mode exam (fixture_mock sandbox; A3–A5 coverage unknown).

    Args:
        live: live 参数。
        modes: modes 参数。
        max_cases_per_mode: max_cases_per_mode 参数。
    """
    from core.apps.eval.service.mode_aware_exam import run_m1c_mode_exam

    return await run_m1c_mode_exam(
        live=bool(live),
        modes=modes,
        max_cases_per_mode=int(max_cases_per_mode or 0),
    )


def eval_probe_m1c_sandbox() -> Dict[str, Any]:
    """M1c sandbox readiness probe (fixture_mock vs live opt-in)."""
    from core.apps.eval.service.mode_aware_exam import probe_m1c_sandbox

    return probe_m1c_sandbox()


def eval_probe_linux_microvm() -> Dict[str, Any]:
    """Linux/KVM microVM host probe hook. Never flips covered / process_split_authorized."""
    from core.apps.eval.service.mode_aware_exam import probe_linux_microvm_host

    return probe_linux_microvm_host()


async def eval_run_a1_intersection_compare(
    *,
    live: bool = False,
    persist: bool = True,
    signoff: Optional[Dict[str, Any]] = None,
    model_fingerprint: str = "unresolved",
    min_n_per_capability: int = 2,
) -> Dict[str, Any]:
    """A1 Track A+B compare (plan_execute vs conversational). rank_claim never auto-true.

    Args:
        live: live 参数。
        persist: persist 参数。
        signoff: signoff 参数。
        model_fingerprint: model_fingerprint 参数。
        min_n_per_capability: min_n_per_capability 参数。
    """
    from core.apps.eval.service.a1_intersection_ops import (
        eval_run_a1_intersection_compare as _fn,
    )

    return await _fn(
        live=bool(live),
        persist=bool(persist),
        signoff=signoff,
        model_fingerprint=str(model_fingerprint or "unresolved"),
        min_n_per_capability=int(min_n_per_capability or 2),
    )


def eval_a1_intersection_status() -> Dict[str, Any]:
    """Read-only A1 intersection gate/Pareto status for UI. Never certifies."""
    from core.apps.eval.service.a1_intersection_ops import a1_intersection_status_report

    return a1_intersection_status_report()


def eval_security_sec_p0a_status() -> Dict[str, Any]:
    """SEC-P0a: L1 threat_ids validation + per-family report schema. Never certifies."""
    from core.apps.eval.service.security_family_report import security_l1_p0a_status

    return security_l1_p0a_status()


def eval_security_sec_p0b_status(
    *,
    live_probes: bool = False,
    human_review: bool = False,
    human_reviewer: str = "",
) -> Dict[str, Any]:
    """SEC-P0b: T12 isolation state machine + probe interface. Never auto-covered.

    Args:
        live_probes: live_probes 参数。
        human_review: human_review 参数。
        human_reviewer: human_reviewer 参数。
    """
    from core.apps.eval.service.isolation_t12 import security_t12_p0b_status

    return security_t12_p0b_status(
        live_probes=bool(live_probes),
        human_review=bool(human_review),
        human_reviewer=str(human_reviewer or ""),
    )


def eval_security_sec_p0c_status(
    by_case: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """SEC-P0c: per-threat-family min_n/CI/report_only gate. Never unlocks L5 declare.

    Args:
        by_case: by_case 参数。
    """
    from core.apps.eval.service.security_family_report import security_sec_p0c_status

    return security_sec_p0c_status(by_case=by_case)


def eval_evaluate_security_family_gates(
    report: Dict[str, Any],
) -> Dict[str, Any]:
    """Apply/recompute per-family min_n gates on a security family report.

    Args:
        report: report 参数。
    """
    from core.apps.eval.service.security_family_report import (
        evaluate_security_family_gates,
    )

    return evaluate_security_family_gates(report)


def eval_security_sec_p1a_status(
    *,
    pairs: Optional[List[Dict[str, Any]]] = None,
    judge_id: str = "security.policy_judge",
    judge_version: str = "1.0.0",
    judge_model: str = "eval-judge-model",
    subject_model: str = "subject-under-test",
) -> Dict[str, Any]:
    """SEC-P1a: judge calibration protocol + judge_version manifest. Never certifies.

    Args:
        pairs: pairs 参数。
        judge_id: judge 标识。
        judge_version: judge_version 参数。
        judge_model: judge_model 参数。
        subject_model: subject_model 参数。
    """
    from core.apps.eval.service.security_judge_calib import security_sec_p1a_status

    return security_sec_p1a_status(
        pairs=pairs,
        judge_id=str(judge_id or "security.policy_judge"),
        judge_version=str(judge_version or "1.0.0"),
        judge_model=str(judge_model or "eval-judge-model"),
        subject_model=str(subject_model or "subject-under-test"),
    )


def eval_build_security_judge_version_manifest(
    *,
    judge_id: str,
    judge_version: str,
    judge_model: str,
    subject_model: str,
    prompt_hash: str = "",
    frozen: bool = True,
) -> Dict[str, Any]:
    """Build frozen judge_id+judge_version manifest; self-judge forbidden.

    Args:
        judge_id: judge 标识。
        judge_version: judge_version 参数。
        judge_model: judge_model 参数。
        subject_model: subject_model 参数。
        prompt_hash: prompt_hash 参数。
        frozen: frozen 参数。
    """
    from core.apps.eval.service.security_judge_calib import build_judge_version_manifest

    return build_judge_version_manifest(
        judge_id=judge_id,
        judge_version=judge_version,
        judge_model=judge_model,
        subject_model=subject_model,
        prompt_hash=str(prompt_hash or ""),
        frozen=bool(frozen),
    )


def eval_evaluate_security_judge_calibration(
    pairs: List[Dict[str, Any]],
    *,
    manifest: Optional[Dict[str, Any]] = None,
    frozen_manifest: Optional[Dict[str, Any]] = None,
    failure_case_ids: Optional[List[str]] = None,
) -> Dict[str, Any]:
    """Gold vs judge agreement + FP/FN gate; uncalibrated → judge_uncalibrated.

    Args:
        pairs: pairs 参数。
        manifest: manifest 参数。
        frozen_manifest: frozen_manifest 参数。
        failure_case_ids: failure_case_ids 参数。
    """
    from core.apps.eval.service.security_judge_calib import (
        evaluate_security_judge_calibration,
    )

    return evaluate_security_judge_calibration(
        pairs=pairs,
        manifest=manifest,
        frozen_manifest=frozen_manifest,
        failure_case_ids=failure_case_ids,
    )


def eval_check_security_judge_version_drift(
    *,
    run_manifest: Dict[str, Any],
    frozen_manifest: Dict[str, Any],
) -> Dict[str, Any]:
    """Detect judge_id/version/model/prompt_hash drift; invalidates claim candidate.

    Args:
        run_manifest: run_manifest 参数。
        frozen_manifest: frozen_manifest 参数。
    """
    from core.apps.eval.service.security_judge_calib import check_judge_version_drift

    return check_judge_version_drift(
        run_manifest=run_manifest, frozen_manifest=frozen_manifest
    )


def eval_annotate_family_asr_calibration(
    family_report: Dict[str, Any],
    *,
    calib: Dict[str, Any],
) -> Dict[str, Any]:
    """Stamp per-family asr_calibration_status; never unlocks claim.

    Args:
        family_report: family_report 参数。
        calib: calib 参数。
    """
    from core.apps.eval.service.security_judge_calib import (
        annotate_family_asr_calibration,
    )

    return annotate_family_asr_calibration(family_report, calib=calib)


def eval_load_security_judge_calib_defaults() -> Dict[str, Any]:
    """Load SEC-P1a judge calibration defaults seed (engineering thresholds)."""
    from core.apps.eval.service.security_judge_calib import load_judge_calib_defaults

    return load_judge_calib_defaults()


def eval_security_sec_p1b_status(
    *,
    findings: Optional[List[Dict[str, Any]]] = None,
    declared_families: Optional[List[str]] = None,
) -> Dict[str, Any]:
    """SEC-P1b: severity/remediation/retest/claim_revocation. Never certifies.

    Args:
        findings: findings 参数。
        declared_families: declared_families 参数。
    """
    from core.apps.eval.service.security_severity_loop import security_sec_p1b_status

    return security_sec_p1b_status(
        findings=findings,
        declared_families=declared_families,
    )


def eval_build_security_finding(
    *,
    case_id: str,
    threat_id: str,
    severity: str,
    impact: str,
    remediation_owner: str,
    retest_case_id: str = "",
    status: str = "open",
    notes: str = "",
) -> Dict[str, Any]:
    """Build structured §6.5 security finding (claim closed).

    Args:
        case_id: case 标识。
        threat_id: threat 标识。
        severity: severity 参数。
        impact: impact 参数。
        remediation_owner: remediation_owner 参数。
        retest_case_id: retest_case 标识。
        status: status 参数。
        notes: notes 参数。
    """
    from core.apps.eval.service.security_severity_loop import build_security_finding

    return build_security_finding(
        case_id=case_id,
        threat_id=threat_id,
        severity=severity,
        impact=impact,
        remediation_owner=remediation_owner,
        retest_case_id=retest_case_id,
        status=status,
        notes=notes,
    )


def eval_transition_security_finding(
    finding: Dict[str, Any],
    *,
    status: str,
    accepted_risk_signoff: str = "",
    retest_passed: Optional[bool] = None,
    retest_evidence: str = "",
    retest_case_id: str = "",
    notes: str = "",
) -> Dict[str, Any]:
    """Transition finding status; retested_pass requires retest evidence.

    Args:
        finding: finding 参数。
        status: status 参数。
        accepted_risk_signoff: accepted_risk_signoff 参数。
        retest_passed: retest_passed 参数。
        retest_evidence: retest_evidence 参数。
        retest_case_id: retest_case 标识。
        notes: notes 参数。
    """
    from core.apps.eval.service.security_severity_loop import transition_finding

    return transition_finding(
        finding,
        status=status,
        accepted_risk_signoff=accepted_risk_signoff,
        retest_passed=retest_passed,
        retest_evidence=retest_evidence,
        retest_case_id=retest_case_id,
        notes=notes,
    )


def eval_evaluate_security_severity_l5_gate(
    findings: List[Dict[str, Any]],
    *,
    declare_families: Optional[List[str]] = None,
) -> Dict[str, Any]:
    """Block L5 declare for families with open high/critical findings.

    Args:
        findings: findings 参数。
        declare_families: declare_families 参数。
    """
    from core.apps.eval.service.security_severity_loop import (
        evaluate_severity_l5_gate,
    )

    return evaluate_severity_l5_gate(
        findings, declare_families=declare_families
    )


def eval_evaluate_security_claim_revocation(
    *,
    declared_families: List[str],
    new_findings: List[Dict[str, Any]],
    reason: str = "",
) -> Dict[str, Any]:
    """Critical regression on declared family → claim_revocation required.

    Args:
        declared_families: declared_families 参数。
        new_findings: new_findings 参数。
        reason: reason 参数。
    """
    from core.apps.eval.service.security_severity_loop import (
        evaluate_claim_revocation,
    )

    return evaluate_claim_revocation(
        declared_families=declared_families,
        new_findings=new_findings,
        reason=reason,
    )


def eval_load_security_severity_loop_defaults() -> Dict[str, Any]:
    """Load SEC-P1b severity loop defaults seed."""
    from core.apps.eval.service.security_severity_loop import (
        load_severity_loop_defaults,
    )

    return load_severity_loop_defaults()


def eval_security_sec_p1c_status(
    *,
    coverage_mode: str = "exercised_fixture",
    human_review: bool = False,
    human_reviewer: str = "",
) -> Dict[str, Any]:
    """SEC-P1c: T13 allowlist pack + process_split boundary. Never certifies.

    Args:
        coverage_mode: coverage_mode 参数。
        human_review: human_review 参数。
        human_reviewer: human_reviewer 参数。
    """
    from core.apps.eval.service.security_t13_allowlist import security_sec_p1c_status

    return security_sec_p1c_status(
        coverage_mode=str(coverage_mode or "exercised_fixture"),
        human_review=bool(human_review),
        human_reviewer=str(human_reviewer or ""),
    )


def eval_run_t13_allowlist_probes(
    *,
    coverage_mode: str = "exercised_fixture",
    process_split_authorized: bool = False,
) -> Dict[str, Any]:
    """Run T13 allowlist fixture probes; process_split never required/granted.

    Args:
        coverage_mode: coverage_mode 参数。
        process_split_authorized: process_split_authorized 参数。
    """
    from core.apps.eval.service.security_t13_allowlist import run_t13_allowlist_probes

    return run_t13_allowlist_probes(
        coverage_mode=str(coverage_mode or "exercised_fixture"),
        process_split_authorized=bool(process_split_authorized),
    )


def eval_assert_t13_process_split_boundary(
    *,
    run: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """C17: T13 must not use process_split as supply-chain前置.

    Args:
        run: run 参数。
    """
    from core.apps.eval.service.security_t13_allowlist import (
        assert_t13_process_split_boundary,
    )

    return assert_t13_process_split_boundary(run=run)


def eval_evaluate_t13_coverage(
    run: Dict[str, Any],
    *,
    human_review: bool = False,
    human_reviewer: str = "",
) -> Dict[str, Any]:
    """Map T13 run → coverage; claim_candidate still accuracy_claim=false.

    Args:
        run: run 参数。
        human_review: human_review 参数。
        human_reviewer: human_reviewer 参数。
    """
    from core.apps.eval.service.security_t13_allowlist import evaluate_t13_coverage

    return evaluate_t13_coverage(
        run,
        human_review=bool(human_review),
        human_reviewer=str(human_reviewer or ""),
    )


def eval_load_t13_allowlist_probes() -> Dict[str, Any]:
    """Load SEC-P1c T13 allowlist probe pack seed."""
    from core.apps.eval.service.security_t13_allowlist import load_t13_allowlist_probes

    return load_t13_allowlist_probes()


def eval_security_sec_p2a_status(
    by_case: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """SEC-P2a: S1 pack read-only + OOS/untested family auto-list. Never certifies.

    Args:
        by_case: by_case 参数。
    """
    from core.apps.eval.service.security_s1_disclosure import security_sec_p2a_status

    return security_sec_p2a_status(by_case=by_case)


def eval_build_untested_oos_disclosure(
    by_case: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """C15: auto-list untested / below_min_n / deferred / OOS threat families.

    Args:
        by_case: by_case 参数。
    """
    from core.apps.eval.service.security_s1_disclosure import (
        build_untested_oos_disclosure,
    )

    return build_untested_oos_disclosure(by_case=by_case)


def eval_load_s1_live_attack_pack() -> Dict[str, Any]:
    """Load S1 live_attack pack (read-only; does not run live attacks)."""
    from core.apps.eval.service.security_s1_disclosure import load_s1_live_attack_pack

    return load_s1_live_attack_pack()


def eval_security_sec_p2b_status(
    by_case: Optional[Dict[str, Any]] = None,
    *,
    subject: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """SEC-P2b: L5 per-family claim template status. Never certifies.

    Args:
        by_case: by_case 参数。
        subject: subject 参数。
    """
    from core.apps.eval.service.security_l5_claim_template import security_sec_p2b_status

    return security_sec_p2b_status(by_case=by_case, subject=subject)


def eval_build_security_l5_claim_template(
    by_case: Optional[Dict[str, Any]] = None,
    *,
    subject: Optional[Dict[str, Any]] = None,
    pack_id: str = "agent.safety.l1",
    pack_version: str = "0.0.0",
    runtime_tier: str = "workspace_execute",
    judge_id: str = "security.policy_judge",
    judge_version: str = "1.0.0",
    severity_blocked: Optional[List[str]] = None,
    judge_usable: bool = True,
    asr_calibration_status: str = "judge_uncalibrated",
    explicit_authorize: bool = False,
    signoffs: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Build per-family L5 claim template; accuracy_claim stays false.

    Args:
        by_case: by_case 参数。
        subject: subject 参数。
        pack_id: pack 标识。
        pack_version: pack_version 参数。
        runtime_tier: runtime_tier 参数。
        judge_id: judge 标识。
        judge_version: judge_version 参数。
        severity_blocked: severity_blocked 参数。
        judge_usable: judge_usable 参数。
        asr_calibration_status: asr_calibration_status 参数。
        explicit_authorize: explicit_authorize 参数。
        signoffs: signoffs 参数。
    """
    from core.apps.eval.service.security_l5_claim_template import (
        build_security_l5_claim_template,
    )

    return build_security_l5_claim_template(
        by_case=by_case,
        subject=subject,
        pack_id=pack_id,
        pack_version=pack_version,
        runtime_tier=runtime_tier,
        judge_id=judge_id,
        judge_version=judge_version,
        severity_blocked=severity_blocked,
        judge_usable=judge_usable,
        asr_calibration_status=asr_calibration_status,
        explicit_authorize=explicit_authorize,
        signoffs=signoffs,
    )


def eval_validate_security_l5_claim_sentence(sentence: str) -> Dict[str, Any]:
    """Reject forbidden false-green / marketing claim sentences.

    Args:
        sentence: sentence 参数。
    """
    from core.apps.eval.service.security_l5_claim_template import (
        validate_claim_sentence_against_policy,
    )

    return validate_claim_sentence_against_policy(sentence)


def eval_select_security_declare_candidate_families(
    family_report: Dict[str, Any],
    *,
    severity_blocked: Optional[List[str]] = None,
    judge_usable: bool = True,
    asr_calibration_status: str = "",
) -> Dict[str, Any]:
    """Select per-family L5 declare *candidates* (not emitted declaration).

    Args:
        family_report: family_report 参数。
        severity_blocked: severity_blocked 参数。
        judge_usable: judge_usable 参数。
        asr_calibration_status: asr_calibration_status 参数。
    """
    from core.apps.eval.service.security_l5_claim_template import (
        select_declare_candidate_families,
    )

    return select_declare_candidate_families(
        family_report=family_report,
        severity_blocked=severity_blocked,
        judge_usable=judge_usable,
        asr_calibration_status=asr_calibration_status,
    )


def eval_security_sec_p3_status() -> Dict[str, Any]:
    """SEC-P3: S-Tool/S-RAG L3 fixtures + A7 parity. Never certifies / live exec."""
    from core.apps.eval.service.security_l3_packs import security_sec_p3_status

    return security_sec_p3_status()


def eval_security_sec_p4_status(
    *,
    mode: str = "guest_sim",
    human_review: bool = False,
    human_reviewer: str = "",
    admit: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """SEC-P4/P4b: Linux microVM probed path. guest_sim≠certification; covered needs review.

    Args:
        mode: mode 参数。
        human_review: human_review 参数。
        human_reviewer: human_reviewer 参数。
        admit: admit 参数。
    """
    from core.apps.eval.service.security_t12_p4 import security_sec_p4_status

    return security_sec_p4_status(
        mode=str(mode or "guest_sim"),
        human_review=bool(human_review),
        human_reviewer=str(human_reviewer or ""),
        admit=admit,
    )


def eval_run_linux_microvm_probes(
    *,
    mode: str = "guest_sim",
    catalog: Optional[Dict[str, Any]] = None,
    admit: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """SEC-P4/P4b guest_sim|guest_live. Live deny needs escape_executor; never auto-covered.

    Args:
        mode: mode 参数。
        catalog: catalog 参数。
        admit: admit 参数。
    """
    from core.apps.eval.service.security_t12_p4 import run_linux_microvm_probes

    return run_linux_microvm_probes(mode=str(mode or "guest_sim"), catalog=catalog, admit=admit)


def eval_run_security_p1_4_kvm_escape(
    *,
    mode: str = "guest_sim",
    guest_boot: Optional[bool] = None,
    admit: Optional[Dict[str, Any]] = None,
    evidence_kind: str = "kvm_guest",
    human_review: bool = False,
    human_reviewer: str = "",
) -> Dict[str, Any]:
    """P1-4 KVM escape: guest_boot + host probes; max isolation_probed; HTTP≠escape.

    Args:
        mode: mode 参数。
        guest_boot: guest_boot 参数。
        admit: admit 参数。
        evidence_kind: evidence_kind 参数。
        human_review: human_review 参数。
        human_reviewer: human_reviewer 参数。
    """
    from core.apps.eval.service.security_p1_4_kvm_escape import run_p1_4_kvm_escape

    return run_p1_4_kvm_escape(
        mode=str(mode or "guest_sim"),
        guest_boot=guest_boot,
        admit=admit,
        evidence_kind=evidence_kind,
        human_review=bool(human_review),
        human_reviewer=str(human_reviewer or ""),
    )


def eval_security_p1_4_status(
    *,
    mode: str = "guest_sim",
    admit: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """P1-4 inventory status (claim locks false).

    Args:
        mode: mode 参数。
        admit: admit 参数。
    """
    from core.apps.eval.service.security_p1_4_kvm_escape import security_p1_4_status

    return security_p1_4_status(mode=str(mode or "guest_sim"), admit=admit)


def eval_security_sec_p5_status(
    *,
    t11_evidence: Optional[Dict[str, Any]] = None,
    t13_shallow_ok: bool = False,
) -> Dict[str, Any]:
    """SEC-P5: T11 deferred gate + OOS extension cards. Never auto-graduate / certify.

    Args:
        t11_evidence: t11_evidence 参数。
        t13_shallow_ok: t13_shallow_ok 参数。
    """
    from core.apps.eval.service.security_p5_extensions import security_sec_p5_status

    return security_sec_p5_status(
        t11_evidence=t11_evidence,
        t13_shallow_ok=bool(t13_shallow_ok),
    )


def eval_evaluate_t11_deferred_gate(
    *,
    evidence: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Evaluate T11 graduate-from-deferred conditions (all-required; default deferred).

    Args:
        evidence: evidence 参数。
    """
    from core.apps.eval.service.security_p5_extensions import evaluate_t11_deferred_gate

    return evaluate_t11_deferred_gate(evidence=evidence)


def eval_build_oos_extension_disclosure() -> Dict[str, Any]:
    """SEC-P5 structured OOS extension cards (model poison / deep MCP / T11)."""
    from core.apps.eval.service.security_p5_extensions import build_oos_extension_disclosure

    return build_oos_extension_disclosure()


def eval_evaluate_deep_supply_chain_boundary(
    *,
    t13_shallow_ok: bool = False,
) -> Dict[str, Any]:
    """Assert T13 shallow pass ≠ OOS-06 deep supply-chain covered.

    Args:
        t13_shallow_ok: t13_shallow_ok 参数。
    """
    from core.apps.eval.service.security_p5_extensions import (
        evaluate_deep_supply_chain_boundary,
    )

    return evaluate_deep_supply_chain_boundary(t13_shallow_ok=bool(t13_shallow_ok))


def eval_security_cert_prep_status(
    *,
    by_case: Optional[Dict[str, Any]] = None,
    subject: Optional[Dict[str, Any]] = None,
    judge_model: str = "eval-judge-model",
    subject_model: str = "prod-subject-model",
    security_failure_ids: Optional[List[str]] = None,
    dual_reviews: Optional[Dict[str, Any]] = None,
    explicit_authorize: bool = False,
    signoffs: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """CERT-PREP dashboard. Never flips security_certification / accuracy_claim.

    Args:
        by_case: by_case 参数。
        subject: subject 参数。
        judge_model: judge_model 参数。
        subject_model: subject_model 参数。
        security_failure_ids: security_failure_ids 参数。
        dual_reviews: dual_reviews 参数。
        explicit_authorize: explicit_authorize 参数。
        signoffs: signoffs 参数。
    """
    from core.apps.eval.service.security_cert_prep import security_cert_prep_status

    return security_cert_prep_status(
        by_case=by_case,
        subject=subject,
        judge_model=str(judge_model or "eval-judge-model"),
        subject_model=str(subject_model or "prod-subject-model"),
        security_failure_ids=security_failure_ids,
        dual_reviews=dual_reviews,
        explicit_authorize=bool(explicit_authorize),
        signoffs=signoffs,
    )


def eval_run_per_family_cert_prep(
    *,
    by_case: Optional[Dict[str, Any]] = None,
    subject: Optional[Dict[str, Any]] = None,
    use_seed_annotation_fixture: bool = False,
) -> Dict[str, Any]:
    """CERT-PREP per-family L5-candidate vs report_only classification.

    Args:
        by_case: by_case 参数。
        subject: subject 参数。
        use_seed_annotation_fixture: use_seed_annotation_fixture 参数。
    """
    from core.apps.eval.service.security_cert_prep import run_per_family_cert_prep

    return run_per_family_cert_prep(
        by_case=by_case,
        subject=subject,
        use_seed_annotation_fixture=bool(use_seed_annotation_fixture),
    )


def eval_rehearse_l5_limited_claim(
    *,
    by_case: Optional[Dict[str, Any]] = None,
    subject: Optional[Dict[str, Any]] = None,
    asr_calibration_status: str = "judge_uncalibrated",
    judge_usable: bool = False,
    explicit_authorize: bool = False,
    signoffs: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """L5 limited-claim rehearsal. security_certification stays false.

    Args:
        by_case: by_case 参数。
        subject: subject 参数。
        asr_calibration_status: asr_calibration_status 参数。
        judge_usable: judge_usable 参数。
        explicit_authorize: explicit_authorize 参数。
        signoffs: signoffs 参数。
    """
    from core.apps.eval.service.security_cert_prep import rehearse_l5_limited_claim

    return rehearse_l5_limited_claim(
        by_case=by_case,
        subject=subject,
        asr_calibration_status=str(asr_calibration_status or "judge_uncalibrated"),
        judge_usable=bool(judge_usable),
        explicit_authorize=bool(explicit_authorize),
        signoffs=signoffs,
    )


def eval_security_oos_deep_status(
    *,
    probe_results_by_oos: Optional[Dict[str, Any]] = None,
    t11_evidence: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """OOS deep engineering + research refuse inventory. Never marks OOS covered.

    Args:
        probe_results_by_oos: probe_results_by_oos 参数。
        t11_evidence: t11_evidence 参数。
    """
    from core.apps.eval.service.security_oos_deep import security_oos_deep_status

    return security_oos_deep_status(
        probe_results_by_oos=probe_results_by_oos,
        t11_evidence=t11_evidence,
    )


def eval_run_security_text_live_p1(
    *,
    impl_mode: str = "conversational",
    agent_id: str = "eval.security.p1_1",
    model: str = "",
    live: bool = False,
    owner: str = "eval",
) -> Dict[str, Any]:
    """P1-1: text-family security run under locked Agent Subject (create_agent).

    Args:
        impl_mode: impl_mode 参数。
        agent_id: Agent ID。
        model: 模型名。
        live: live 参数。
        owner: owner 参数。
    """
    import asyncio

    from core.apps.eval.service.security_text_live_p1 import run_text_family_live

    coro = run_text_family_live(
        impl_mode=impl_mode,
        agent_id=agent_id,
        model=model,
        live=live,
        owner=owner,
    )
    try:
        loop = asyncio.get_event_loop()
        if loop.is_running():
            raise RuntimeError("eval_run_security_text_live_p1_requires_await_caller")
        return loop.run_until_complete(coro)
    except RuntimeError:
        return asyncio.run(coro)


def eval_security_text_live_p1_status(
    *,
    impl_mode: str = "conversational",
    live: bool = False,
) -> Dict[str, Any]:
    """P1-1 status / scripted inventory (Subject-locked; claim locks false).

    Args:
        impl_mode: impl_mode 参数。
        live: live 参数。
    """
    from core.apps.eval.service.security_text_live_p1 import security_text_live_p1_status

    return security_text_live_p1_status(impl_mode=impl_mode, live=live)


def eval_run_security_tool_retrieval_live_p1(
    *,
    impl_mode: str = "conversational",
    agent_id: str = "eval.security.p1_1.tool_retrieval",
    model: str = "",
    live: bool = False,
    owner: str = "eval",
    tool_contract: str = "allowlist_v1",
    retrieval_contract: str = "rag_guard_v1",
) -> Dict[str, Any]:
    """P1-1 tool/retrieval families under locked Subject (create_agent).

    Args:
        impl_mode: impl_mode 参数。
        agent_id: Agent ID。
        model: 模型名。
        live: live 参数。
        owner: owner 参数。
        tool_contract: tool_contract 参数。
        retrieval_contract: retrieval_contract 参数。
    """
    import asyncio

    from core.apps.eval.service.security_tool_retrieval_live_p1 import (
        run_tool_retrieval_family_live,
    )

    coro = run_tool_retrieval_family_live(
        impl_mode=impl_mode,
        agent_id=agent_id,
        model=model,
        live=live,
        owner=owner,
        tool_contract=tool_contract,
        retrieval_contract=retrieval_contract,
    )
    try:
        loop = asyncio.get_event_loop()
        if loop.is_running():
            raise RuntimeError("eval_run_security_tool_retrieval_live_p1_requires_await")
        return loop.run_until_complete(coro)
    except RuntimeError:
        return asyncio.run(coro)


def eval_security_tool_retrieval_live_p1_status(
    *,
    impl_mode: str = "conversational",
    live: bool = False,
) -> Dict[str, Any]:
    """P1-1 tool/retrieval status (claim locks false).

    Args:
        impl_mode: impl_mode 参数。
        live: live 参数。
    """
    from core.apps.eval.service.security_tool_retrieval_live_p1 import (
        security_tool_retrieval_live_p1_status,
    )

    return security_tool_retrieval_live_p1_status(impl_mode=impl_mode, live=live)


def eval_security_p1_2_status(*, path: Optional[str] = None) -> Dict[str, Any]:
    """P1-2 judge calib session status (dual-review / arbiter; cert=false).

    Args:
        path: 路径。
    """
    from pathlib import Path

    from core.apps.eval.service.security_p1_judge_session import security_p1_2_status

    return security_p1_2_status(path=Path(path) if path else None)


def eval_record_security_p1_2_pair(
    *,
    case_id: str,
    gold: bool,
    judge: bool,
    notes: str = "",
    path: Optional[str] = None,
) -> Dict[str, Any]:
    """P1-2: record gold/judge pair; auto-queue dual review on disagreement.

    Args:
        case_id: case 标识。
        gold: gold 参数。
        judge: judge 参数。
        notes: notes 参数。
        path: 路径。
    """
    from pathlib import Path

    from core.apps.eval.service.security_p1_judge_session import (
        evaluate_p1_2_session,
        load_session,
        record_judge_gold_pair,
        save_session,
    )

    p = Path(path) if path else None
    session = load_session(p)
    record_judge_gold_pair(
        session, case_id=case_id, gold=gold, judge=judge, notes=notes
    )
    save_session(session, p)
    return evaluate_p1_2_session(session)


def eval_submit_security_p1_2_dual_review(
    *,
    case_id: str,
    reviewer: str,
    slot: str,
    label: bool,
    path: Optional[str] = None,
) -> Dict[str, Any]:
    """P1-2: submit dual-blind slot a|b|arbiter for a failure case.

    Args:
        case_id: case 标识。
        reviewer: reviewer 参数。
        slot: slot 参数。
        label: label 参数。
        path: 路径。
    """
    from pathlib import Path

    from core.apps.eval.service.security_p1_judge_session import (
        evaluate_p1_2_session,
        load_session,
        save_session,
        submit_dual_review,
    )

    p = Path(path) if path else None
    session = load_session(p)
    submit_dual_review(
        session, case_id=case_id, reviewer=reviewer, slot=slot, label=label
    )
    save_session(session, p)
    return evaluate_p1_2_session(session)


def eval_run_security_dynamic_p13(
    *,
    base_url: str = "",
    cross_tenant_repeats: int = 2,
) -> Dict[str, Any]:
    """P1-3: cross-tenant / injection ASR / output-encoding dynamic probes.

    Args:
        base_url: base_url 参数。
        cross_tenant_repeats: cross_tenant_repeats 参数。
    """
    from core.apps.eval.service.security_dynamic_p13 import run_security_dynamic_p13

    return run_security_dynamic_p13(
        base_url=base_url,
        cross_tenant_repeats=cross_tenant_repeats,
    )


def eval_security_dynamic_p13_status(
    *,
    base_url: str = "",
) -> Dict[str, Any]:
    """P1-3 inventory status (same harness; claim locks false).

    Args:
        base_url: base_url 参数。
    """
    from core.apps.eval.service.security_dynamic_p13 import run_security_dynamic_p13

    return run_security_dynamic_p13(base_url=base_url, cross_tenant_repeats=1)


def eval_evaluate_oos_engineering_pack(
    oos_id: str,
    *,
    probe_results: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Evaluate one OOS engineering fixture pack (covered stays false).

    Args:
        oos_id: oos 标识。
        probe_results: probe_results 参数。
    """
    from core.apps.eval.service.security_oos_deep import evaluate_oos_engineering_pack

    return evaluate_oos_engineering_pack(str(oos_id), probe_results=probe_results)


def eval_build_research_refuse_inventory() -> Dict[str, Any]:
    """OOS-01/02/03 research refuse-to-test cards (never text-ASR covered)."""
    from core.apps.eval.service.security_oos_deep import build_research_refuse_inventory

    return build_research_refuse_inventory()


def eval_load_p5_extension_gates() -> Dict[str, Any]:
    """Load SEC-P5 extension gates seed."""
    from core.apps.eval.service.security_p5_extensions import load_p5_extension_gates

    return load_p5_extension_gates()


def eval_run_l3_pack_fixtures(
    *,
    pack_filter: Optional[str] = None,
) -> Dict[str, Any]:
    """Run L3 S-Tool/S-RAG fixture tool_trace cases (mock only).

    Args:
        pack_filter: pack_filter 参数。
    """
    from core.apps.eval.service.security_l3_packs import run_l3_pack_fixtures

    return run_l3_pack_fixtures(pack_filter=pack_filter)


def eval_evaluate_a7_l3_parity() -> Dict[str, Any]:
    """A7/L1 must not host T05-exec/T06/T07/T08; L3 pack must cover them."""
    from core.apps.eval.service.security_l3_packs import evaluate_a7_l3_parity

    return evaluate_a7_l3_parity()


def eval_load_l3_s_tool_s_rag_pack() -> Dict[str, Any]:
    """Load SEC-P3 L3 S-Tool/S-RAG fixture pack seed."""
    from core.apps.eval.service.security_l3_packs import load_l3_s_tool_s_rag_pack

    return load_l3_s_tool_s_rag_pack()


def eval_evaluate_l3_case_fixture(case: Dict[str, Any]) -> Dict[str, Any]:
    """Score one L3 fixture case via tool_trace side-effect monitor.

    Args:
        case: case 参数。
    """
    from core.apps.eval.service.security_l3_packs import evaluate_l3_case_fixture

    return evaluate_l3_case_fixture(case)


def eval_evaluate_isolation_status(
    *,
    admit: Optional[Dict[str, Any]] = None,
    probe_run: Optional[Dict[str, Any]] = None,
    human_review: bool = False,
    human_reviewer: str = "",
) -> Dict[str, Any]:
    """Derive isolation_admitted|probed|covered. admit alone never covered.

    Args:
        admit: admit 参数。
        probe_run: probe_run 参数。
        human_review: human_review 参数。
        human_reviewer: human_reviewer 参数。
    """
    from core.apps.eval.service.isolation_t12 import evaluate_isolation_status

    return evaluate_isolation_status(
        admit=admit,
        probe_run=probe_run,
        human_review=bool(human_review),
        human_reviewer=str(human_reviewer or ""),
    )


def eval_build_security_family_report(
    by_case: Optional[Dict[str, Any]] = None,
    *,
    eval_layer: str = "L1",
    pack_id: str = "agent.safety.l1",
    subject: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Per-threat-family security report skeleton; macro ASR not_for_claim.

    Args:
        by_case: by_case 参数。
        eval_layer: eval_layer 参数。
        pack_id: pack 标识。
        subject: subject 参数。
    """
    from core.apps.eval.service.security_family_report import build_security_family_report

    return build_security_family_report(
        by_case=by_case,
        subject=subject,
        pack_id=str(pack_id or "agent.safety.l1"),
        eval_layer=str(eval_layer or "L1"),
    )


def eval_build_mode_intersection_rank(
    mode_columns: Dict[str, Any],
    *,
    parity: Optional[Dict[str, Any]] = None,
    signoff: Optional[Dict[str, Any]] = None,
    min_n_per_capability: int = 5,
    track_a_complete: bool = True,
) -> Dict[str, Any]:
    """M3 Track B: intersection Pareto/CI report; rank_claim never auto-emitted.

    Args:
        mode_columns: mode_columns 参数。
        parity: parity 参数。
        signoff: signoff 参数。
        min_n_per_capability: min_n_per_capability 参数。
        track_a_complete: track_a_complete 参数。
    """
    from core.apps.eval.service.mode_intersection_rank import build_mode_intersection_rank

    return build_mode_intersection_rank(
        mode_columns,
        parity=parity,
        signoff=signoff,
        min_n_per_capability=int(min_n_per_capability or 5),
        track_a_complete=bool(track_a_complete),
    )


def eval_evaluate_mode_rank_gate(
    mode_columns: Dict[str, Any],
    *,
    parity: Optional[Dict[str, Any]] = None,
    signoff: Optional[Dict[str, Any]] = None,
    min_n_per_capability: int = 5,
    track_a_complete: bool = True,
) -> Dict[str, Any]:
    """M3 rank gate checklist (fail closed for rank_claim).

    Args:
        mode_columns: mode_columns 参数。
        parity: parity 参数。
        signoff: signoff 参数。
        min_n_per_capability: min_n_per_capability 参数。
        track_a_complete: track_a_complete 参数。
    """
    from core.apps.eval.service.mode_intersection_rank import evaluate_rank_gate

    return evaluate_rank_gate(
        mode_columns=mode_columns,
        parity=parity,
        signoff=signoff,
        min_n_per_capability=int(min_n_per_capability or 5),
        track_a_complete=bool(track_a_complete),
    )


def eval_estimate_m2_deferred_modes(
    *,
    impl_source: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """M2: multi_agent/pipeline/operator estimate (runtime_parts deps; no live).

    Args:
        impl_source: impl_source 参数。
    """
    from core.apps.eval.service.mode_deferred_estimate import estimate_m2_deferred_modes

    return estimate_m2_deferred_modes(impl_source=impl_source)


def eval_validate_m2_runtime_parts(
    parts: list,
    *,
    mode: str,
) -> Dict[str, Any]:
    """M2: validate runtime_parts shape for a deferred mode.

    Args:
        parts: parts 参数。
        mode: mode 参数。
    """
    from core.apps.eval.service.mode_deferred_estimate import validate_runtime_parts

    return validate_runtime_parts(parts, mode=mode)


def eval_load_mock_tool_catalog() -> Dict[str, Any]:
    """Load + validate default mock tool catalog seed (T0)."""
    from core.apps.eval.service.mock_tools import load_mock_tool_catalog

    return load_mock_tool_catalog()


def eval_run_tool_fixture_suite(
    capability_id: Optional[str] = None,
) -> Dict[str, Any]:
    """T1–T3: run mock-tool / long_context fixture suite (claim=false; v1.1 in-scope).

    Args:
        capability_id: capability 标识。
    """
    from core.apps.eval.service.tool_capability_fixtures import run_tool_fixture_suite

    return run_tool_fixture_suite(capability_id=capability_id)


def eval_run_session_fixture_suite() -> Dict[str, Any]:
    """T2: run A8 multi_turn_memory session fixture suite (claim=false; v1.1 in-scope)."""
    from core.apps.eval.service.tool_capability_fixtures import run_session_fixture_suite

    return run_session_fixture_suite()


def eval_invoke_mock_tools(
    tool_calls: Optional[list] = None,
    *,
    case: Optional[Dict[str, Any]] = None,
    fail_mode: Optional[str] = None,
) -> Dict[str, Any]:
    """T1: invoke scripted tool_calls against mock catalog.

    Args:
        tool_calls: tool_calls 参数。
        case: case 参数。
        fail_mode: fail_mode 参数。
    """
    from core.apps.eval.service.mock_tools import invoke_mock_tools

    return invoke_mock_tools(
        tool_calls or [],
        case=case or {},
        fail_mode=fail_mode,
    )


def eval_generate_long_context_case(
    *,
    case_id: str = "",
    must_retain_claims: Optional[list] = None,
    tier: str = "ci_short",
) -> Dict[str, Any]:
    """T3: build a long_context fixture case (claim closed).

    Args:
        case_id: case 标识。
        must_retain_claims: must_retain_claims 参数。
        tier: tier 参数。
    """
    from core.apps.eval.service.long_context_generator import generate_long_context_case

    return generate_long_context_case(
        case_id=case_id or "agent.long_context.generated",
        must_retain_claims=list(must_retain_claims or ["CLAIM-1"]),
        tier=tier,
    )


def eval_judge_long_context(
    case: Optional[Dict[str, Any]] = None,
    result: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """T3: A9 must_retain_claims judge (claim closed).

    Args:
        case: case 参数。
        result: result 参数。
    """
    from core.apps.eval.service.long_context_generator import judge_long_context

    return judge_long_context(case or {}, result or {})


def eval_agent_capability_catalog() -> list:
    """Agent SubjectAdapter capability catalog (canonical + v1 in_scope flags)."""
    from core.apps.eval.service.subject_adapter import get_subject_adapter

    return get_subject_adapter("agent").capability_catalog()


def eval_validate_agent_case(case: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """AgentSubjectAdapter.validate_case — purpose + capabilities mechanical gate.

    Args:
        case: case 参数。
    """
    from core.apps.eval.service.subject_adapter import get_subject_adapter

    errors = get_subject_adapter("agent").validate_case(case or {})
    return {"ok": not errors, "errors": errors, "subject_kind": "agent"}


def eval_list_subject_kinds() -> list:
    """Registered EvalSubjectAdapter kinds (agent, prompt, …)."""
    from core.apps.eval.service.subject_adapter import list_subject_kinds

    return list_subject_kinds()


def eval_list_method_kinds() -> list:
    """Method-track kinds (Arena/G2b/S1) — not Subjects / not OBJECT_TYPES."""
    from core.apps.eval.service.method_track import list_method_kinds

    return list_method_kinds()


def eval_method_catalog() -> list:
    """Method-track catalog with honesty (ADR refuse Subject promotion)."""
    from core.apps.eval.service.method_track import method_catalog

    return method_catalog()


def eval_assert_subject_kinds_exclude_methods(
    subject_kinds: Optional[list] = None,
) -> Dict[str, Any]:
    """Fail-closed check: Subject list must not contain Method kinds.

    Args:
        subject_kinds: subject_kinds 参数。
    """
    from core.apps.eval.service.method_track import (
        assert_subject_kinds_exclude_methods,
    )
    from core.apps.eval.service.subject_adapter import list_subject_kinds

    kinds = list(subject_kinds) if subject_kinds is not None else list_subject_kinds()
    return assert_subject_kinds_exclude_methods(kinds)


def eval_method_track_status(
    subject_kinds: Optional[list] = None,
) -> Dict[str, Any]:
    """Method-track honesty snapshot for Eval UI (Arena/G2b/S1 ≠ Subject).

    Args:
        subject_kinds: subject_kinds 参数。
    """
    from core.apps.eval.service.method_track import (
        METHOD_TRACK_SCHEMA,
        assert_subject_kinds_exclude_methods,
        list_method_kinds,
        method_catalog,
    )
    from core.apps.eval.service.subject_adapter import list_subject_kinds

    subjects = list(subject_kinds) if subject_kinds is not None else list_subject_kinds()
    exclude = assert_subject_kinds_exclude_methods(subjects)
    return {
        "schema": METHOD_TRACK_SCHEMA,
        "ok": bool(exclude.get("ok")),
        "method_kinds": list_method_kinds(),
        "methods": method_catalog(),
        "subject_kinds": subjects,
        "subject_exclude_methods": exclude,
        "accuracy_claim": False,
        "claim_eligible": False,
        "note": (
            "Arena/G2b/S1 stay Method track — not SubjectAdapter / OBJECT_TYPES; "
            "accuracy_claim stays false."
        ),
    }


def eval_p1_regression_status(
    *,
    pack_kind: str = "",
    pack_status: str = "",
    draft_sample_limit: int = 5,
) -> Dict[str, Any]:
    """P1 Regression readiness honesty snapshot (quotas ok; human review is the gate).

    Args:
        pack_kind: pack_kind 参数。
        pack_status: pack_status 参数。
        draft_sample_limit: draft_sample_limit 参数。
    """
    from collections import Counter, defaultdict

    from core.apps.eval.service.capability_case_bank import (
        PROFILE_ID,
        build_agent_capability_cases,
        load_pack_meta,
    )
    from core.apps.eval.service.capability_cert_readiness import (
        evaluate_certification_readiness,
    )
    from core.apps.eval.service.capability_id_map import resolve_capability_id

    bank = build_agent_capability_cases()
    meta = load_pack_meta()
    kind = str(pack_kind or meta.get("kind") or "").strip()
    status = str(pack_status or meta.get("status") or "").strip()
    review_counts: Counter = Counter()
    draft_by_cap: Dict[str, List[str]] = defaultdict(list)
    draft_counts: Counter = Counter()
    sample_lim = max(0, int(draft_sample_limit or 0))
    _PURPOSE_OK = frozenset({"purpose_ok", "reviewed", "approved", "frozen"})
    for c in bank:
        rev = c.get("review") if isinstance(c.get("review"), dict) else {}
        st = str((rev or {}).get("status") or "draft").strip().lower() or "draft"
        review_counts[st] += 1
        caps = list(c.get("capabilities") or [])
        try:
            cap = resolve_capability_id(str(caps[0]), fail_closed=True) if caps else ""
        except Exception:
            cap = str(caps[0]).strip() if caps else ""
        if not cap:
            cap = "(unknown)"
        if st not in _PURPOSE_OK:
            draft_counts[cap] += 1
            cid = str(c.get("case_id") or "")
            if cid and len(draft_by_cap[cap]) < sample_lim:
                draft_by_cap[cap].append(cid)

    ready = evaluate_certification_readiness(
        profile_id=PROFILE_ID,
        cases=bank,
        pack_kind=kind,
        pack_status=status,
        compile_plan=True,
    )
    n_gaps = int((ready.get("coverage") or {}).get("n_gaps") or 0)
    purpose_ok_n = int(review_counts.get("purpose_ok", 0)) + int(
        review_counts.get("reviewed", 0)
    ) + int(review_counts.get("approved", 0)) + int(review_counts.get("frozen", 0))
    draft_checklist = [
        {
            "capability_id": cap,
            "draft_count": int(draft_counts[cap]),
            "sample_case_ids": list(draft_by_cap.get(cap) or []),
        }
        for cap in sorted(draft_counts.keys())
    ]
    profile_complete = bool(ready.get("profile_complete"))
    return {
        "schema": "eval.p1_regression_status.v1",
        "ok": bool(ready.get("ok")),
        "profile_id": PROFILE_ID,
        "pack_status": status or str(meta.get("status") or "draft"),
        "quota_inventory_ok": n_gaps == 0,
        "profile_complete": profile_complete,
        "case_count": len(bank),
        "review_status_counts": dict(sorted(review_counts.items())),
        "purpose_ok_or_better": purpose_ok_n,
        "draft_pending": int(sum(draft_counts.values())),
        "draft_by_capability": draft_checklist,
        "checks": ready.get("checks") or [],
        "blockers": ready.get("blockers") or [],
        "coverage": ready.get("coverage") or {},
        "snapshot": ready.get("snapshot") or {},
        "next_action": (
            "claim/Certification remain closed; workspace promote optional"
            if profile_complete
            else (
                "Eval → Case Pack → Promote agent.capability "
                "(stamps purpose_ok → freeze; claim stays false)"
            )
        ),
        "review_links": {
            "case_packs_tab": "/eval?tab=case-packs",
            "case_editor_tab": "/eval?tab=case-editor",
        },
        "accuracy_claim": False,
        "claim_eligible": False,
        "certification_eligible": False,
        "honesty": (
            "P1 content quotas are inventory-complete when quota_inventory_ok; "
            + (
                "seed purpose_ok + pack.meta frozen for profile_complete; "
                if profile_complete
                else "human purpose_ok/freeze is still required for profile_complete; "
            )
            + "draft_by_capability is a review checklist only; "
            "claim_eligible/accuracy_claim/certification stay false."
        ),
    }


def eval_prompt_capability_catalog() -> list:
    """Prompt SubjectAdapter capability catalog (prompt v1 subset)."""
    from core.apps.eval.service.subject_adapter import get_subject_adapter

    return get_subject_adapter("prompt").capability_catalog()


def eval_validate_prompt_case(case: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """PromptSubjectAdapter.validate_case — purpose + lexical criteria gate.

    Args:
        case: case 参数。
    """
    from core.apps.eval.service.subject_adapter import get_subject_adapter

    errors = get_subject_adapter("prompt").validate_case(case or {})
    return {"ok": not errors, "errors": errors, "subject_kind": "prompt"}


def eval_validate_prompt_capability_bank() -> Dict[str, Any]:
    """Validate curated prompt.capability seed bank (draft; claim=false)."""
    from core.apps.eval.service.prompt_capability_bank import validate_prompt_capability_bank

    return validate_prompt_capability_bank()


def eval_list_prompt_capability_cases() -> list:
    """List prompt.capability curated cases."""
    from core.apps.eval.service.prompt_capability_bank import build_prompt_capability_cases

    return build_prompt_capability_cases()


def eval_run_prompt_capability_smoke(
    *, limit: int = 50
) -> Dict[str, Any]:
    """Fixture execute+judge smoke over prompt.capability bank (≠ live/accuracy).

    Args:
        limit: 返回条数上限。
    """
    from core.apps.eval.service.prompt_capability_bank import run_prompt_capability_smoke

    return run_prompt_capability_smoke(limit=limit)


def eval_prompt_regression_profile() -> Dict[str, Any]:
    """prompt.regression.v1 Suite Profile (claim_eligible=false)."""
    from core.apps.eval.service.prompt_capability_bank import prompt_regression_profile

    return prompt_regression_profile()


def eval_prompt_regression_status(
    *, draft_sample_limit: int = 5
) -> Dict[str, Any]:
    """Prompt Subject regression honesty snapshot (quotas vs bank; claim closed).

    Args:
        draft_sample_limit: draft_sample_limit 参数。
    """
    from core.apps.eval.service.prompt_capability_bank import prompt_regression_status

    return prompt_regression_status(draft_sample_limit=draft_sample_limit)


def eval_workflow_capability_catalog() -> list:
    """Workflow SubjectAdapter capability catalog (workflow v1 subset)."""
    from core.apps.eval.service.subject_adapter import get_subject_adapter

    return get_subject_adapter("workflow").capability_catalog()


def eval_validate_workflow_case(case: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """WorkflowSubjectAdapter.validate_case.

    Args:
        case: case 参数。
    """
    from core.apps.eval.service.subject_adapter import get_subject_adapter

    errors = get_subject_adapter("workflow").validate_case(case or {})
    return {"ok": not errors, "errors": errors, "subject_kind": "workflow"}


def eval_validate_workflow_capability_bank() -> Dict[str, Any]:
    """Validate curated workflow.capability seed bank (draft; claim=false)."""
    from core.apps.eval.service.workflow_capability_bank import (
        validate_workflow_capability_bank,
    )

    return validate_workflow_capability_bank()


def eval_list_workflow_capability_cases() -> list:
    """List workflow.capability curated cases."""
    from core.apps.eval.service.workflow_capability_bank import (
        build_workflow_capability_cases,
    )

    return build_workflow_capability_cases()


def eval_run_workflow_capability_smoke(*, limit: int = 50) -> Dict[str, Any]:
    """Fixture execute+judge smoke over workflow.capability bank (≠ live/accuracy).

    Args:
        limit: 返回条数上限。
    """
    from core.apps.eval.service.workflow_capability_bank import (
        run_workflow_capability_smoke,
    )

    return run_workflow_capability_smoke(limit=limit)


def eval_workflow_regression_profile() -> Dict[str, Any]:
    """workflow.regression.v1 Suite Profile (claim_eligible=false)."""
    from core.apps.eval.service.workflow_capability_bank import (
        workflow_regression_profile,
    )

    return workflow_regression_profile()


def eval_workflow_regression_status(
    *, draft_sample_limit: int = 5
) -> Dict[str, Any]:
    """Workflow Subject regression honesty snapshot (quotas vs bank; claim closed).

    Args:
        draft_sample_limit: draft_sample_limit 参数。
    """
    from core.apps.eval.service.workflow_capability_bank import (
        workflow_regression_status,
    )

    return workflow_regression_status(draft_sample_limit=draft_sample_limit)


def eval_model_capability_catalog() -> list:
    """Model SubjectAdapter capability catalog (model v1 subset)."""
    from core.apps.eval.service.subject_adapter import get_subject_adapter

    return get_subject_adapter("model").capability_catalog()


def eval_validate_model_case(case: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """ModelSubjectAdapter.validate_case.

    Args:
        case: case 参数。
    """
    from core.apps.eval.service.subject_adapter import get_subject_adapter

    errors = get_subject_adapter("model").validate_case(case or {})
    return {"ok": not errors, "errors": errors, "subject_kind": "model"}


def eval_validate_model_capability_bank() -> Dict[str, Any]:
    """Validate curated model.capability seed bank (draft; claim=false)."""
    from core.apps.eval.service.model_capability_bank import (
        validate_model_capability_bank,
    )

    return validate_model_capability_bank()


def eval_list_model_capability_cases() -> list:
    """List model.capability curated cases."""
    from core.apps.eval.service.model_capability_bank import (
        build_model_capability_cases,
    )

    return build_model_capability_cases()


def eval_run_model_capability_smoke(*, limit: int = 50) -> Dict[str, Any]:
    """Fixture execute+judge smoke over model.capability bank (≠ live/accuracy).

    Args:
        limit: 返回条数上限。
    """
    from core.apps.eval.service.model_capability_bank import (
        run_model_capability_smoke,
    )

    return run_model_capability_smoke(limit=limit)


def eval_model_regression_profile() -> Dict[str, Any]:
    """model.regression.v1 Suite Profile (claim_eligible=false)."""
    from core.apps.eval.service.model_capability_bank import model_regression_profile

    return model_regression_profile()


def eval_model_regression_status(
    *, draft_sample_limit: int = 5
) -> Dict[str, Any]:
    """Model Subject regression honesty snapshot (quotas vs bank; claim closed).

    Args:
        draft_sample_limit: draft_sample_limit 参数。
    """
    from core.apps.eval.service.model_capability_bank import model_regression_status

    return model_regression_status(draft_sample_limit=draft_sample_limit)


def eval_kb_capability_catalog() -> list:
    """KB SubjectAdapter capability catalog (kb v1 subset; ≠ OBJECT_TYPES)."""
    from core.apps.eval.service.subject_adapter import get_subject_adapter

    return get_subject_adapter("kb").capability_catalog()


def eval_validate_kb_case(case: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """KbSubjectAdapter.validate_case.

    Args:
        case: case 参数。
    """
    from core.apps.eval.service.subject_adapter import get_subject_adapter

    errors = get_subject_adapter("kb").validate_case(case or {})
    return {"ok": not errors, "errors": errors, "subject_kind": "kb"}


def eval_validate_kb_capability_bank() -> Dict[str, Any]:
    """Validate curated kb.capability seed bank (draft; claim=false)."""
    from core.apps.eval.service.kb_capability_bank import (
        validate_kb_capability_bank,
    )

    return validate_kb_capability_bank()


def eval_list_kb_capability_cases() -> list:
    """List kb.capability curated cases."""
    from core.apps.eval.service.kb_capability_bank import (
        build_kb_capability_cases,
    )

    return build_kb_capability_cases()


def eval_run_kb_capability_smoke(*, limit: int = 20) -> Dict[str, Any]:
    """Fixture execute+judge smoke over kb.capability bank (≠ live RAG accuracy).

    Args:
        limit: 返回条数上限。
    """
    from core.apps.eval.service.kb_capability_bank import (
        run_kb_capability_smoke,
    )

    return run_kb_capability_smoke(limit=limit)


def eval_kb_regression_profile() -> Dict[str, Any]:
    """kb.regression.v1 Suite Profile (claim_eligible=false)."""
    from core.apps.eval.service.kb_capability_bank import kb_regression_profile

    return kb_regression_profile()


def eval_kb_regression_status(
    *, draft_sample_limit: int = 5
) -> Dict[str, Any]:
    """KB Subject regression honesty snapshot (quotas vs bank; claim closed).

    Args:
        draft_sample_limit: draft_sample_limit 参数。
    """
    from core.apps.eval.service.kb_capability_bank import kb_regression_status

    return kb_regression_status(draft_sample_limit=draft_sample_limit)


def eval_code_review_capability_catalog() -> list:
    """Code Review SubjectAdapter capability catalog (≠ OBJECT_TYPES)."""
    from core.apps.eval.service.subject_adapter import get_subject_adapter

    return get_subject_adapter("code_review").capability_catalog()


def eval_validate_code_review_case(
    case: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """CodeReviewSubjectAdapter.validate_case.

    Args:
        case: case 参数。
    """
    from core.apps.eval.service.subject_adapter import get_subject_adapter

    errors = get_subject_adapter("code_review").validate_case(case or {})
    return {"ok": not errors, "errors": errors, "subject_kind": "code_review"}


def eval_validate_code_review_capability_bank() -> Dict[str, Any]:
    """Validate curated code_review.capability seed bank (draft; claim=false)."""
    from core.apps.eval.service.code_review_capability_bank import (
        validate_code_review_capability_bank,
    )

    return validate_code_review_capability_bank()


def eval_list_code_review_capability_cases() -> list:
    """List code_review.capability curated cases."""
    from core.apps.eval.service.code_review_capability_bank import (
        build_code_review_capability_cases,
    )

    return build_code_review_capability_cases()


def eval_run_code_review_capability_smoke(*, limit: int = 20) -> Dict[str, Any]:
    """Fixture execute+judge smoke over code_review.capability (≠ live E2E).

    Args:
        limit: 返回条数上限。
    """
    from core.apps.eval.service.code_review_capability_bank import (
        run_code_review_capability_smoke,
    )

    return run_code_review_capability_smoke(limit=limit)


def eval_code_review_regression_profile() -> Dict[str, Any]:
    """code_review.regression.v1 Suite Profile (claim_eligible=false)."""
    from core.apps.eval.service.code_review_capability_bank import (
        code_review_regression_profile,
    )

    return code_review_regression_profile()


def eval_code_review_regression_status(
    *, draft_sample_limit: int = 5
) -> Dict[str, Any]:
    """Code Review Subject regression honesty snapshot (quotas vs bank; claim closed).

    Args:
        draft_sample_limit: draft_sample_limit 参数。
    """
    from core.apps.eval.service.code_review_capability_bank import (
        code_review_regression_status,
    )

    return code_review_regression_status(draft_sample_limit=draft_sample_limit)


def eval_session_capability_catalog() -> list:
    """Session SubjectAdapter capability catalog (≠ OBJECT_TYPES)."""
    from core.apps.eval.service.subject_adapter import get_subject_adapter

    return get_subject_adapter("session").capability_catalog()


def eval_validate_session_case(
    case: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """SessionSubjectAdapter.validate_case.

    Args:
        case: case 参数。
    """
    from core.apps.eval.service.subject_adapter import get_subject_adapter

    errors = get_subject_adapter("session").validate_case(case or {})
    return {"ok": not errors, "errors": errors, "subject_kind": "session"}


def eval_validate_session_capability_bank() -> Dict[str, Any]:
    """Validate curated session.capability seed bank (draft; claim=false)."""
    from core.apps.eval.service.session_capability_bank import (
        validate_session_capability_bank,
    )

    return validate_session_capability_bank()


def eval_list_session_capability_cases() -> list:
    """List session.capability curated cases."""
    from core.apps.eval.service.session_capability_bank import (
        build_session_capability_cases,
    )

    return build_session_capability_cases()


def eval_run_session_capability_smoke(*, limit: int = 20) -> Dict[str, Any]:
    """Fixture execute+judge smoke over session.capability (≠ long-horizon Agent).

    Args:
        limit: 返回条数上限。
    """
    from core.apps.eval.service.session_capability_bank import (
        run_session_capability_smoke,
    )

    return run_session_capability_smoke(limit=limit)


def eval_session_regression_profile() -> Dict[str, Any]:
    """session.regression.v1 Suite Profile (claim_eligible=false)."""
    from core.apps.eval.service.session_capability_bank import (
        session_regression_profile,
    )

    return session_regression_profile()


def eval_session_regression_status(
    *, draft_sample_limit: int = 5
) -> Dict[str, Any]:
    """Session Subject regression honesty snapshot (quotas vs bank; claim closed).

    Args:
        draft_sample_limit: draft_sample_limit 参数。
    """
    from core.apps.eval.service.session_capability_bank import (
        session_regression_status,
    )

    return session_regression_status(draft_sample_limit=draft_sample_limit)


def eval_tool_capability_catalog() -> list:
    """Tool/MCP SubjectAdapter capability catalog (≠ OBJECT_TYPES)."""
    from core.apps.eval.service.subject_adapter import get_subject_adapter

    return get_subject_adapter("tool").capability_catalog()


def eval_validate_tool_case(
    case: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """ToolSubjectAdapter.validate_case.

    Args:
        case: case 参数。
    """
    from core.apps.eval.service.subject_adapter import get_subject_adapter

    errors = get_subject_adapter("tool").validate_case(case or {})
    return {"ok": not errors, "errors": errors, "subject_kind": "tool"}


def eval_validate_tool_capability_bank() -> Dict[str, Any]:
    """Validate curated tool.capability seed bank (draft; claim=false)."""
    from core.apps.eval.service.tool_capability_bank import (
        validate_tool_capability_bank,
    )

    return validate_tool_capability_bank()


def eval_list_tool_capability_cases() -> list:
    """List tool.capability curated cases."""
    from core.apps.eval.service.tool_capability_bank import (
        build_tool_capability_cases,
    )

    return build_tool_capability_cases()


def eval_run_tool_capability_smoke(*, limit: int = 20) -> Dict[str, Any]:
    """Fixture execute+judge smoke over tool.capability (≠ live tools/MCP).

    Args:
        limit: 返回条数上限。
    """
    from core.apps.eval.service.tool_capability_bank import (
        run_tool_capability_smoke,
    )

    return run_tool_capability_smoke(limit=limit)


def eval_tool_regression_profile() -> Dict[str, Any]:
    """tool.regression.v1 Suite Profile (claim_eligible=false)."""
    from core.apps.eval.service.tool_capability_bank import tool_regression_profile

    return tool_regression_profile()


def eval_tool_regression_status(
    *, draft_sample_limit: int = 5
) -> Dict[str, Any]:
    """Tool Subject regression honesty snapshot (quotas vs bank; claim closed).

    Args:
        draft_sample_limit: draft_sample_limit 参数。
    """
    from core.apps.eval.service.tool_capability_bank import tool_regression_status

    return tool_regression_status(draft_sample_limit=draft_sample_limit)


def eval_multi_agent_capability_catalog() -> list:
    """Multi-Agent SubjectAdapter capability catalog (≠ OBJECT_TYPES)."""
    from core.apps.eval.service.subject_adapter import get_subject_adapter

    return get_subject_adapter("multi_agent").capability_catalog()


def eval_validate_multi_agent_case(
    case: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """MultiAgentSubjectAdapter.validate_case.

    Args:
        case: case 参数。
    """
    from core.apps.eval.service.subject_adapter import get_subject_adapter

    errors = get_subject_adapter("multi_agent").validate_case(case or {})
    return {"ok": not errors, "errors": errors, "subject_kind": "multi_agent"}


def eval_validate_multi_agent_capability_bank() -> Dict[str, Any]:
    """Validate curated multi_agent.capability seed bank (draft; claim=false)."""
    from core.apps.eval.service.multi_agent_capability_bank import (
        validate_multi_agent_capability_bank,
    )

    return validate_multi_agent_capability_bank()


def eval_list_multi_agent_capability_cases() -> list:
    """List multi_agent.capability curated cases."""
    from core.apps.eval.service.multi_agent_capability_bank import (
        build_multi_agent_capability_cases,
    )

    return build_multi_agent_capability_cases()


def eval_run_multi_agent_capability_smoke(*, limit: int = 20) -> Dict[str, Any]:
    """Fixture handoff-path smoke over multi_agent.capability (≠ live M2 runtime).

    Args:
        limit: 返回条数上限。
    """
    from core.apps.eval.service.multi_agent_capability_bank import (
        run_multi_agent_capability_smoke,
    )

    return run_multi_agent_capability_smoke(limit=limit)


def eval_multi_agent_regression_profile() -> Dict[str, Any]:
    """multi_agent.regression.v1 Suite Profile (claim_eligible=false)."""
    from core.apps.eval.service.multi_agent_capability_bank import (
        multi_agent_regression_profile,
    )

    return multi_agent_regression_profile()


def eval_multi_agent_regression_status(
    *, draft_sample_limit: int = 5
) -> Dict[str, Any]:
    """Multi-Agent Subject regression honesty snapshot (quotas vs bank; claim closed).

    Args:
        draft_sample_limit: draft_sample_limit 参数。
    """
    from core.apps.eval.service.multi_agent_capability_bank import (
        multi_agent_regression_status,
    )

    return multi_agent_regression_status(draft_sample_limit=draft_sample_limit)


def eval_skill_capability_catalog() -> list:
    """Skill SubjectAdapter capability catalog (OBJECT_TYPES skill)."""
    from core.apps.eval.service.subject_adapter import get_subject_adapter

    return get_subject_adapter("skill").capability_catalog()


def eval_validate_skill_case(
    case: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """SkillSubjectAdapter.validate_case.

    Args:
        case: case 参数。
    """
    from core.apps.eval.service.subject_adapter import get_subject_adapter

    errors = get_subject_adapter("skill").validate_case(case or {})
    return {"ok": not errors, "errors": errors, "subject_kind": "skill"}


def eval_validate_skill_capability_bank() -> Dict[str, Any]:
    """Validate curated skill.capability seed bank (draft; claim=false)."""
    from core.apps.eval.service.skill_capability_bank import (
        validate_skill_capability_bank,
    )

    return validate_skill_capability_bank()


def eval_list_skill_capability_cases() -> list:
    """List skill.capability curated cases."""
    from core.apps.eval.service.skill_capability_bank import (
        build_skill_capability_cases,
    )

    return build_skill_capability_cases()


def eval_run_skill_capability_smoke(*, limit: int = 50) -> Dict[str, Any]:
    """Fixture lexical smoke over skill.capability (≠ live core_skill_execute).

    Args:
        limit: 返回条数上限。
    """
    from core.apps.eval.service.skill_capability_bank import (
        run_skill_capability_smoke,
    )

    return run_skill_capability_smoke(limit=limit)


def eval_skill_regression_profile() -> Dict[str, Any]:
    """skill.regression.v1 Suite Profile (claim_eligible=false)."""
    from core.apps.eval.service.skill_capability_bank import skill_regression_profile

    return skill_regression_profile()


def eval_skill_regression_status(
    *, draft_sample_limit: int = 5
) -> Dict[str, Any]:
    """Skill Subject regression honesty snapshot (quotas vs bank; claim closed).

    Args:
        draft_sample_limit: draft_sample_limit 参数。
    """
    from core.apps.eval.service.skill_capability_bank import skill_regression_status

    return skill_regression_status(draft_sample_limit=draft_sample_limit)


def eval_generated_app_capability_catalog() -> list:
    """Generated-App SubjectAdapter capability catalog (OBJECT_TYPES generated_app)."""
    from core.apps.eval.service.subject_adapter import get_subject_adapter

    return get_subject_adapter("generated_app").capability_catalog()


def eval_validate_generated_app_case(
    case: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """GeneratedAppSubjectAdapter.validate_case.

    Args:
        case: case 参数。
    """
    from core.apps.eval.service.subject_adapter import get_subject_adapter

    errors = get_subject_adapter("generated_app").validate_case(case or {})
    return {"ok": not errors, "errors": errors, "subject_kind": "generated_app"}


def eval_validate_generated_app_capability_bank() -> Dict[str, Any]:
    """Validate curated generated_app.capability seed bank (draft; claim=false)."""
    from core.apps.eval.service.generated_app_capability_bank import (
        validate_generated_app_capability_bank,
    )

    return validate_generated_app_capability_bank()


def eval_list_generated_app_capability_cases() -> list:
    """List generated_app.capability curated cases."""
    from core.apps.eval.service.generated_app_capability_bank import (
        build_generated_app_capability_cases,
    )

    return build_generated_app_capability_cases()


def eval_run_generated_app_capability_smoke(*, limit: int = 50) -> Dict[str, Any]:
    """Fixture lexical smoke over generated_app.capability (≠ live Pi / runs_eval).

    Args:
        limit: 返回条数上限。
    """
    from core.apps.eval.service.generated_app_capability_bank import (
        run_generated_app_capability_smoke,
    )

    return run_generated_app_capability_smoke(limit=limit)


def eval_generated_app_regression_profile() -> Dict[str, Any]:
    """generated_app.regression.v1 Suite Profile (claim_eligible=false)."""
    from core.apps.eval.service.generated_app_capability_bank import (
        generated_app_regression_profile,
    )

    return generated_app_regression_profile()


def eval_generated_app_regression_status(
    *, draft_sample_limit: int = 5
) -> Dict[str, Any]:
    """Generated-App Subject regression honesty snapshot (quotas vs bank; claim closed).

    Args:
        draft_sample_limit: draft_sample_limit 参数。
    """
    from core.apps.eval.service.generated_app_capability_bank import (
        generated_app_regression_status,
    )

    return generated_app_regression_status(draft_sample_limit=draft_sample_limit)


def eval_api_capability_catalog() -> list:
    """API SubjectAdapter capability catalog (OBJECT_TYPES api)."""
    from core.apps.eval.service.subject_adapter import get_subject_adapter

    return get_subject_adapter("api").capability_catalog()


def eval_validate_api_case(
    case: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """ApiSubjectAdapter.validate_case.

    Args:
        case: case 参数。
    """
    from core.apps.eval.service.subject_adapter import get_subject_adapter

    errors = get_subject_adapter("api").validate_case(case or {})
    return {"ok": not errors, "errors": errors, "subject_kind": "api"}


def eval_validate_api_capability_bank() -> Dict[str, Any]:
    """Validate curated api.capability seed bank (draft; claim=false)."""
    from core.apps.eval.service.api_capability_bank import validate_api_capability_bank

    return validate_api_capability_bank()


def eval_list_api_capability_cases() -> list:
    """List api.capability curated cases."""
    from core.apps.eval.service.api_capability_bank import build_api_capability_cases

    return build_api_capability_cases()


def eval_run_api_capability_smoke(*, limit: int = 50) -> Dict[str, Any]:
    """Fixture lexical smoke over api.capability (≠ live external_pull).

    Args:
        limit: 返回条数上限。
    """
    from core.apps.eval.service.api_capability_bank import run_api_capability_smoke

    return run_api_capability_smoke(limit=limit)


def eval_api_regression_profile() -> Dict[str, Any]:
    """api.regression.v1 Suite Profile (claim_eligible=false)."""
    from core.apps.eval.service.api_capability_bank import api_regression_profile

    return api_regression_profile()


def eval_api_regression_status(
    *, draft_sample_limit: int = 5
) -> Dict[str, Any]:
    """API Subject regression honesty snapshot (quotas vs bank; claim closed).

    Args:
        draft_sample_limit: draft_sample_limit 参数。
    """
    from core.apps.eval.service.api_capability_bank import api_regression_status

    return api_regression_status(draft_sample_limit=draft_sample_limit)


def eval_dataset_capability_catalog() -> list:
    """Dataset SubjectAdapter capability catalog (OBJECT_TYPES dataset)."""
    from core.apps.eval.service.subject_adapter import get_subject_adapter

    return get_subject_adapter("dataset").capability_catalog()


def eval_validate_dataset_case(
    case: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """DatasetSubjectAdapter.validate_case.

    Args:
        case: case 参数。
    """
    from core.apps.eval.service.subject_adapter import get_subject_adapter

    errors = get_subject_adapter("dataset").validate_case(case or {})
    return {"ok": not errors, "errors": errors, "subject_kind": "dataset"}


def eval_validate_dataset_capability_bank() -> Dict[str, Any]:
    """Validate curated dataset.capability seed bank (draft; claim=false)."""
    from core.apps.eval.service.dataset_capability_bank import (
        validate_dataset_capability_bank,
    )

    return validate_dataset_capability_bank()


def eval_list_dataset_capability_cases() -> list:
    """List dataset.capability curated cases."""
    from core.apps.eval.service.dataset_capability_bank import (
        build_dataset_capability_cases,
    )

    return build_dataset_capability_cases()


def eval_run_dataset_capability_smoke(*, limit: int = 50) -> Dict[str, Any]:
    """Fixture lexical smoke over dataset.capability (≠ typed Plan dataset_assert).

    Args:
        limit: 返回条数上限。
    """
    from core.apps.eval.service.dataset_capability_bank import (
        run_dataset_capability_smoke,
    )

    return run_dataset_capability_smoke(limit=limit)


def eval_dataset_regression_profile() -> Dict[str, Any]:
    """dataset.regression.v1 Suite Profile (claim_eligible=false)."""
    from core.apps.eval.service.dataset_capability_bank import (
        dataset_regression_profile,
    )

    return dataset_regression_profile()


def eval_dataset_regression_status(
    *, draft_sample_limit: int = 5
) -> Dict[str, Any]:
    """Dataset Subject regression honesty snapshot (quotas vs bank; claim closed).

    Args:
        draft_sample_limit: draft_sample_limit 参数。
    """
    from core.apps.eval.service.dataset_capability_bank import (
        dataset_regression_status,
    )

    return dataset_regression_status(draft_sample_limit=draft_sample_limit)


def eval_system_capability_catalog() -> list:
    """System SubjectAdapter capability catalog (OBJECT_TYPES system)."""
    from core.apps.eval.service.subject_adapter import get_subject_adapter

    return get_subject_adapter("system").capability_catalog()


def eval_validate_system_case(
    case: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """SystemSubjectAdapter.validate_case.

    Args:
        case: case 参数。
    """
    from core.apps.eval.service.subject_adapter import get_subject_adapter

    errors = get_subject_adapter("system").validate_case(case or {})
    return {"ok": not errors, "errors": errors, "subject_kind": "system"}


def eval_validate_system_capability_bank() -> Dict[str, Any]:
    """Validate curated system.capability seed bank (draft; claim=false)."""
    from core.apps.eval.service.system_capability_bank import (
        validate_system_capability_bank,
    )

    return validate_system_capability_bank()


def eval_list_system_capability_cases() -> list:
    """List system.capability curated cases."""
    from core.apps.eval.service.system_capability_bank import (
        build_system_capability_cases,
    )

    return build_system_capability_cases()


def eval_run_system_capability_smoke(*, limit: int = 50) -> Dict[str, Any]:
    """Fixture lexical smoke over system.capability (≠ system_plan_ops).

    Args:
        limit: 返回条数上限。
    """
    from core.apps.eval.service.system_capability_bank import (
        run_system_capability_smoke,
    )

    return run_system_capability_smoke(limit=limit)


def eval_system_regression_profile() -> Dict[str, Any]:
    """system.regression.v1 Suite Profile (claim_eligible=false)."""
    from core.apps.eval.service.system_capability_bank import (
        system_regression_profile,
    )

    return system_regression_profile()


def eval_system_regression_status(
    *, draft_sample_limit: int = 5
) -> Dict[str, Any]:
    """System Subject regression honesty snapshot (quotas vs bank; claim closed).

    Args:
        draft_sample_limit: draft_sample_limit 参数。
    """
    from core.apps.eval.service.system_capability_bank import (
        system_regression_status,
    )

    return system_regression_status(draft_sample_limit=draft_sample_limit)


def eval_subject_regression_inventory(
    *,
    draft_sample_limit: int = 5,
    workspace_id: str = "",
    caller_workspace_id: str = "",
) -> Dict[str, Any]:
    """Cross-Subject regression honesty inventory (claim stays false).

    Args:
        draft_sample_limit: draft_sample_limit 参数。
        workspace_id: 工作区 ID。
        caller_workspace_id: caller_workspace 标识。
    """
    from core.apps.eval.service.subject_regression_inventory import (
        subject_regression_inventory,
    )

    return subject_regression_inventory(
        draft_sample_limit=draft_sample_limit,
        workspace_id=workspace_id,
        caller_workspace_id=caller_workspace_id,
    )


def eval_content_purpose_ok_inventory() -> Dict[str, Any]:
    """ADR P1 content_purpose_ok matrix across Subject seed banks (claim closed)."""
    from core.apps.eval.service.content_purpose_ok import content_purpose_ok_inventory

    return content_purpose_ok_inventory()


def eval_content_purpose_ok_for_subject(subject_kind: str) -> Dict[str, Any]:
    """ADR P1 content_purpose_ok audit for one Subject seed bank (claim closed).

    Args:
        subject_kind: subject_kind 参数。
    """
    from core.apps.eval.service.content_purpose_ok import content_purpose_ok_for_subject

    return content_purpose_ok_for_subject(subject_kind)


def eval_validate_agent_capability_bank() -> Dict[str, Any]:
    """P1: validate curated agent.capability Regression seed bank (draft)."""
    from core.apps.eval.service.capability_case_bank import validate_agent_capability_bank

    return validate_agent_capability_bank()


def eval_list_agent_capability_cases() -> list:
    """P1: list agent.capability curated cases (canonical caps + test_purpose)."""
    from core.apps.eval.service.capability_case_bank import build_agent_capability_cases

    return build_agent_capability_cases()


def eval_agent_regression_profile() -> Dict[str, Any]:
    """P1: agent.regression.v1 Suite Profile (claim_eligible=false)."""
    from core.apps.eval.service.capability_case_bank import agent_regression_profile

    return agent_regression_profile()


def eval_list_suite_profiles() -> list:
    """P2/P4: list agent + Subject Suite Profiles (claim closed)."""
    from core.apps.eval.service.capability_case_bank import list_suite_profiles

    return list_suite_profiles()


def eval_get_suite_profile(profile_id: str = "") -> Dict[str, Any]:
    """P2/P4: resolve agent or Subject Suite Profile by id.

    Args:
        profile_id: profile 标识。
    """
    from core.apps.eval.service.capability_case_bank import get_suite_profile

    return get_suite_profile(profile_id)


def eval_subject_suite_profile_inventory() -> Dict[str, Any]:
    """ADR P2: discoverable Subject Suite Profiles honesty snapshot."""
    from core.apps.eval.service.subject_suite_profiles import (
        subject_suite_profile_inventory,
    )

    return subject_suite_profile_inventory()


def eval_benchmark_readiness(
    *,
    min_per_capability: Optional[int] = None,
    compile_plan: bool = True,
    cases: Optional[list] = None,
    profile_id: str = "",
    profile: Optional[Dict[str, Any]] = None,
    subject_kind: str = "",
) -> Dict[str, Any]:
    """P4: benchmark coverage + holdout compile disclosure (claim closed).

    Args:
        min_per_capability: min_per_capability 参数。
        compile_plan: compile_plan 参数。
        cases: cases 参数。
        profile_id: profile 标识。
        profile: 评测 profile。
        subject_kind: subject_kind 参数。
    """
    from core.apps.eval.service.capability_p4_gate import benchmark_readiness_report

    return benchmark_readiness_report(
        cases=cases,
        profile=profile,
        profile_id=profile_id,
        subject_kind=subject_kind,
        min_per_capability=min_per_capability,
        compile_plan=compile_plan,
    )


def eval_p4_status(
    *,
    min_per_capability: Optional[int] = None,
    compile_plan: bool = True,
    threshold: float = 0.8,
    profile_id: str = "",
    profile: Optional[Dict[str, Any]] = None,
    subject_kind: str = "",
) -> Dict[str, Any]:
    """P4 honesty snapshot: benchmark quotas/holdout + judge engineering bar.

    Args:
        min_per_capability: min_per_capability 参数。
        compile_plan: compile_plan 参数。
        threshold: threshold 参数。
        profile_id: profile 标识。
        profile: 评测 profile。
        subject_kind: subject_kind 参数。
    """
    from core.apps.eval.service.capability_p4_gate import (
        benchmark_readiness_report,
        evaluate_judge_calibration_gate,
    )

    bench = benchmark_readiness_report(
        min_per_capability=min_per_capability,
        compile_plan=compile_plan,
        profile_id=profile_id,
        profile=profile,
        subject_kind=subject_kind,
    )
    judge = evaluate_judge_calibration_gate(threshold=threshold)
    plan = bench.get("plan") if isinstance(bench.get("plan"), dict) else {}
    selection = plan.get("selection") if isinstance(plan.get("selection"), dict) else {}
    hold = selection.get("holdout") if isinstance(selection.get("holdout"), dict) else {}
    coverage = bench.get("coverage") if isinstance(bench.get("coverage"), dict) else {}
    return {
        "schema": "eval.p4_status.v1",
        "ok": bool(bench.get("ok")) and bool(judge.get("ok")),
        "subject_kind": bench.get("subject_kind"),
        "profile_id": bench.get("profile_id"),
        "ready_for_benchmark_quotas": bool(bench.get("ready_for_benchmark_quotas")),
        "n_gaps": int(coverage.get("n_gaps") or 0),
        "case_count": int(coverage.get("case_count") or 0),
        "holdout": {
            "enabled": bool(hold.get("enabled")),
            "n_holdout": int(hold.get("n_holdout") or 0),
            "n_eval": int(hold.get("n_eval") or 0),
        },
        "manifest_case_count": len(plan.get("sample_manifest") or []),
        "manifest_hash": plan.get("manifest_hash"),
        "judge_gate": {
            "meets_engineering_bar": bool(judge.get("meets_engineering_bar")),
            "agreement": judge.get("agreement"),
            "threshold": judge.get("threshold"),
            "report_only": True,
        },
        "next_action": (
            "Eval → Case Pack → Open judge calibration / holdout; "
            "benchmark quotas may be ready while judge bar stays unmet"
        ),
        "review_links": {
            "case_packs_tab": "/eval?tab=case-packs",
            "p1_regression_tab": "/eval?tab=p1-regression",
        },
        "accuracy_claim": False,
        "claim_eligible": False,
        "report_only": True,
        "honesty": (
            "P4 is coverage/holdout + engineering judge bar only; "
            "ready_for_benchmark_quotas≠accuracy; meets_engineering_bar≠claim; "
            "ADR §6.2 threshold remains owner-open; Certification closed."
        ),
    }


def eval_judge_calibration_gate(
    *,
    workspace_id: str = "",
    ticket_id: str = "",
    threshold: float = 0.8,
    caller_workspace_id: str = "",
    ratings: Optional[list] = None,
) -> Dict[str, Any]:
    """P4: engineering judge agreement gate — always report_only / claim=false.

    Args:
        workspace_id: 工作区 ID。
        ticket_id: ticket 标识。
        threshold: threshold 参数。
        caller_workspace_id: caller_workspace 标识。
        ratings: ratings 参数。
    """
    from core.apps.eval.service.capability_p4_gate import (
        evaluate_judge_calibration_gate,
        judge_calibration_gate_for_ticket,
    )

    if ticket_id and workspace_id:
        return judge_calibration_gate_for_ticket(
            workspace_id=workspace_id,
            ticket_id=ticket_id,
            threshold=threshold,
            caller_workspace_id=caller_workspace_id or workspace_id,
        )
    return evaluate_judge_calibration_gate(
        ratings=ratings,
        threshold=threshold,
    )


def eval_open_capability_judge_calibration(
    *,
    workspace_id: str,
    pack_id: str = "",
    version: str = "",
    sample_n: int = 8,
    notes: str = "",
    caller_workspace_id: str = "",
    profile_id: str = "",
    profile: Optional[Dict[str, Any]] = None,
    subject_kind: str = "",
    cases: Optional[list] = None,
) -> Dict[str, Any]:
    """P4: open judge calibration ticket against Subject bank sample.

    Args:
        workspace_id: 工作区 ID。
        pack_id: pack 标识。
        version: version 参数。
        sample_n: sample_n 参数。
        notes: notes 参数。
        caller_workspace_id: caller_workspace 标识。
        profile_id: profile 标识。
        profile: 评测 profile。
        subject_kind: subject_kind 参数。
        cases: cases 参数。
    """
    from core.apps.eval.service.capability_p4_gate import open_capability_judge_calibration

    kwargs: Dict[str, Any] = {
        "workspace_id": workspace_id,
        "sample_n": sample_n,
        "notes": notes,
        "caller_workspace_id": caller_workspace_id or workspace_id,
        "profile_id": profile_id,
        "profile": profile,
        "subject_kind": subject_kind,
        "cases": cases,
    }
    if pack_id:
        kwargs["pack_id"] = pack_id
    if version:
        kwargs["version"] = version
    return open_capability_judge_calibration(**kwargs)


def eval_promote_agent_capability_bank(
    *,
    workspace_id: str,
    reviewer: str = "",
    frozen_by: str = "",
    pack_id: str = "",
    version: str = "",
    caller_workspace_id: str = "",
    notes: str = "",
) -> Dict[str, Any]:
    """P1 closeout: validate → draft → review → freeze agent.capability (claim=false).

    Args:
        workspace_id: 工作区 ID。
        reviewer: reviewer 参数。
        frozen_by: frozen_by 参数。
        pack_id: pack 标识。
        version: version 参数。
        caller_workspace_id: caller_workspace 标识。
        notes: notes 参数。
    """
    from core.apps.eval.service.capability_case_bank import promote_agent_capability_bank

    kwargs: Dict[str, Any] = {
        "workspace_id": workspace_id,
        "reviewer": reviewer,
        "frozen_by": frozen_by,
        "caller_workspace_id": caller_workspace_id,
        "notes": notes,
    }
    if pack_id:
        kwargs["pack_id"] = pack_id
    if version:
        kwargs["version"] = version
    return promote_agent_capability_bank(**kwargs)


def eval_list_promotable_subject_kinds() -> list:
    """Subject kinds with seed bank promote path (claim stays false)."""
    from core.apps.eval.service.subject_capability_promote import (
        list_promotable_subject_kinds,
    )

    return list_promotable_subject_kinds()


def eval_promote_subject_capability_bank(
    *,
    subject_kind: str,
    workspace_id: str,
    reviewer: str = "",
    frozen_by: str = "",
    pack_id: str = "",
    version: str = "",
    caller_workspace_id: str = "",
    notes: str = "",
) -> Dict[str, Any]:
    """Promote any Subject seed bank → purpose_ok → freeze (claim=false).

    Args:
        subject_kind: subject_kind 参数。
        workspace_id: 工作区 ID。
        reviewer: reviewer 参数。
        frozen_by: frozen_by 参数。
        pack_id: pack 标识。
        version: version 参数。
        caller_workspace_id: caller_workspace 标识。
        notes: notes 参数。
    """
    from core.apps.eval.service.subject_capability_promote import (
        promote_subject_capability_bank,
    )

    kwargs: Dict[str, Any] = {
        "subject_kind": subject_kind,
        "workspace_id": workspace_id,
        "reviewer": reviewer,
        "frozen_by": frozen_by,
        "caller_workspace_id": caller_workspace_id,
        "notes": notes,
    }
    if pack_id:
        kwargs["pack_id"] = pack_id
    if version:
        kwargs["version"] = version
    return promote_subject_capability_bank(**kwargs)


def eval_promote_all_subject_capability_banks(
    *,
    workspace_id: str,
    reviewer: str = "",
    frozen_by: str = "",
    caller_workspace_id: str = "",
    notes: str = "",
) -> Dict[str, Any]:
    """Promote all Subject seed banks into one workspace (claim=false).

    Args:
        workspace_id: 工作区 ID。
        reviewer: reviewer 参数。
        frozen_by: frozen_by 参数。
        caller_workspace_id: caller_workspace 标识。
        notes: notes 参数。
    """
    from core.apps.eval.service.subject_capability_promote import (
        promote_all_subject_capability_banks,
    )

    return promote_all_subject_capability_banks(
        workspace_id=workspace_id,
        reviewer=reviewer,
        frozen_by=frozen_by,
        caller_workspace_id=caller_workspace_id,
        notes=notes,
    )


def eval_stamp_subject_seed_purpose_ok(
    *,
    subject_kind: str,
    reviewer: str = "owner",
) -> Dict[str, Any]:
    """Stamp purpose_ok into Subject seed cases/*.json (no freeze; claim=false).

    Args:
        subject_kind: subject_kind 参数。
        reviewer: reviewer 参数。
    """
    from core.apps.eval.service.subject_capability_promote import (
        stamp_subject_seed_purpose_ok,
    )

    return stamp_subject_seed_purpose_ok(
        subject_kind=subject_kind, reviewer=reviewer
    )


def eval_stamp_all_subject_seed_purpose_ok(
    *, reviewer: str = "owner"
) -> Dict[str, Any]:
    """Stamp purpose_ok on all non-agent Subject seed banks (claim=false).

    Args:
        reviewer: reviewer 参数。
    """
    from core.apps.eval.service.subject_capability_promote import (
        stamp_all_subject_seed_purpose_ok,
    )

    return stamp_all_subject_seed_purpose_ok(reviewer=reviewer)


def eval_freeze_subject_seed_pack_meta(
    *,
    subject_kind: str,
    reviewer: str = "owner",
) -> Dict[str, Any]:
    """Freeze Subject seed pack.meta.json after purpose_ok (claim=false).

    Args:
        subject_kind: subject_kind 参数。
        reviewer: reviewer 参数。
    """
    from core.apps.eval.service.subject_capability_promote import (
        freeze_subject_seed_pack_meta,
    )

    return freeze_subject_seed_pack_meta(
        subject_kind=subject_kind, reviewer=reviewer
    )


def eval_freeze_all_subject_seed_pack_meta(
    *, reviewer: str = "owner"
) -> Dict[str, Any]:
    """Freeze all non-agent Subject seed pack.meta.json (claim=false).

    Args:
        reviewer: reviewer 参数。
    """
    from core.apps.eval.service.subject_capability_promote import (
        freeze_all_subject_seed_pack_meta,
    )

    return freeze_all_subject_seed_pack_meta(reviewer=reviewer)


def eval_compile_plan_from_suite_profile(
    *,
    profile: Optional[Dict[str, Any]] = None,
    profile_id: str = "",
    cases: Optional[list] = None,
    object_id: str = "",
    object_version: str = "0.1.0",
    require_content_purpose_ok: bool = True,
) -> Dict[str, Any]:
    """P2/P4: Suite Profile quotas → Plan v2 sample_manifest (claim_eligible=false).

    Args:
        profile: 评测 profile。
        profile_id: profile 标识。
        cases: cases 参数。
        object_id: object 标识。
        object_version: object_version 参数。
        require_content_purpose_ok: require_content_purpose_ok 参数。
    """
    from core.apps.eval.service.suite_profile_compile import compile_plan_from_suite_profile

    return compile_plan_from_suite_profile(
        profile=profile,
        profile_id=profile_id,
        cases=cases,
        object_id=object_id,
        object_version=object_version,
        require_content_purpose_ok=require_content_purpose_ok,
    )


async def eval_run_suite_profile_exam(
    *,
    profile_id: str = "agent.regression.v1",
    profile: Optional[Dict[str, Any]] = None,
    live: bool = False,
    model: str = "",
    run_key: str = "",
    object_id: str = "",
    object_version: str = "0.1.0",
    max_cases: int = 0,
    cases: Optional[list] = None,
    workspace_id: str = "",
) -> Dict[str, Any]:
    """Post-P4: execute only sample_manifest from Suite Profile Plan (claim closed).

    Args:
        profile_id: profile 标识。
        profile: 评测 profile。
        live: live 参数。
        model: 模型名。
        run_key: run_key 参数。
        object_id: object 标识。
        object_version: object_version 参数。
        max_cases: max_cases 参数。
        cases: cases 参数。
        workspace_id: 工作区 ID。
    """
    from core.apps.eval.service.suite_profile_exam import run_suite_profile_exam

    return await run_suite_profile_exam(
        profile_id=profile_id,
        profile=profile,
        cases=cases,
        live=bool(live),
        model=model,
        run_key=run_key,
        object_id=object_id,
        object_version=object_version,
        max_cases=max_cases,
        workspace_id=workspace_id,
    )


def eval_capability_heatmap(
    *,
    profile_id: str = "",
    profile: Optional[Dict[str, Any]] = None,
    exam: Optional[Dict[str, Any]] = None,
    cases: Optional[list] = None,
    subject_kind: str = "",
) -> Dict[str, Any]:
    """§8.4 capability coverage heatmap (claim closed; Subject-aware).

    Args:
        profile_id: profile 标识。
        profile: 评测 profile。
        exam: exam 参数。
        cases: cases 参数。
        subject_kind: subject_kind 参数。
    """
    from core.apps.eval.service.suite_profile_report import build_capability_heatmap

    return build_capability_heatmap(
        cases=cases,
        exam=exam,
        profile=profile,
        profile_id=profile_id,
        subject_kind=subject_kind,
    )


def eval_suite_profile_report(
    exam: Optional[Dict[str, Any]] = None,
    *,
    cases: Optional[list] = None,
) -> Dict[str, Any]:
    """Compose heatmap + §11 disclosure from an exam payload.

    Args:
        exam: exam 参数。
        cases: cases 参数。
    """
    from core.apps.eval.service.suite_profile_report import build_suite_profile_report

    return build_suite_profile_report(exam or {}, cases=cases)


def eval_certification_readiness(
    *,
    profile_id: str = "agent.benchmark.v1",
    profile: Optional[Dict[str, Any]] = None,
    subject_kind: str = "",
    pack_kind: str = "",
    pack_status: str = "",
    judge_agreement: Optional[Dict[str, Any]] = None,
    judge_threshold: float = 0.8,
    compile_plan: bool = True,
    cases: Optional[list] = None,
) -> Dict[str, Any]:
    """P5 pre-gate: §8.5 relative completeness; certification_eligible always false.

    Args:
        profile_id: profile 标识。
        profile: 评测 profile。
        subject_kind: subject_kind 参数。
        pack_kind: pack_kind 参数。
        pack_status: pack_status 参数。
        judge_agreement: judge_agreement 参数。
        judge_threshold: judge_threshold 参数。
        compile_plan: compile_plan 参数。
        cases: cases 参数。
    """
    from core.apps.eval.service.capability_cert_readiness import (
        evaluate_certification_readiness,
    )

    return evaluate_certification_readiness(
        profile_id=profile_id,
        profile=profile,
        subject_kind=subject_kind,
        cases=cases,
        pack_kind=pack_kind,
        pack_status=pack_status,
        judge_agreement=judge_agreement,
        judge_threshold=judge_threshold,
        compile_plan=compile_plan,
    )


def eval_analyze_capability_coverage(
    *,
    profile: Optional[Dict[str, Any]] = None,
    profile_id: str = "",
    subject_kind: str = "",
    min_per_capability: Optional[int] = None,
    cases: Optional[list] = None,
) -> Dict[str, Any]:
    """P3: capability have/need/gap inventory (claim closed; Subject-aware).

    Args:
        profile: 评测 profile。
        profile_id: profile 标识。
        subject_kind: subject_kind 参数。
        min_per_capability: min_per_capability 参数。
        cases: cases 参数。
    """
    from core.apps.eval.service.capability_coverage_fill import analyze_capability_coverage

    return analyze_capability_coverage(
        cases,
        profile=profile,
        profile_id=profile_id,
        subject_kind=subject_kind,
        min_per_capability=min_per_capability,
    )


def eval_generate_coverage_fill_candidates(
    *,
    profile: Optional[Dict[str, Any]] = None,
    profile_id: str = "",
    subject_kind: str = "",
    min_per_capability: Optional[int] = None,
    method: str = "mutation",
    seed: str = "7",
    ops: Optional[list] = None,
    cases: Optional[list] = None,
) -> Dict[str, Any]:
    """P3: draft fill candidates via factory mutation/template (not gold).

    Args:
        profile: 评测 profile。
        profile_id: profile 标识。
        subject_kind: subject_kind 参数。
        min_per_capability: min_per_capability 参数。
        method: method 参数。
        seed: seed 参数。
        ops: ops 参数。
        cases: cases 参数。
    """
    from core.apps.eval.service.capability_coverage_fill import (
        generate_coverage_fill_candidates,
    )

    return generate_coverage_fill_candidates(
        cases=cases,
        profile=profile,
        profile_id=profile_id,
        subject_kind=subject_kind,
        min_per_capability=min_per_capability,
        method=method,
        seed=seed,
        ops=ops,
    )


def eval_fill_capability_coverage(
    *,
    workspace_id: str,
    pack_id: str = "",
    version: str = "",
    caller_workspace_id: str = "",
    profile: Optional[Dict[str, Any]] = None,
    profile_id: str = "",
    subject_kind: str = "",
    min_per_capability: Optional[int] = None,
    method: str = "mutation",
    seed: str = "7",
    ops: Optional[list] = None,
    apply: bool = False,
    cases: Optional[list] = None,
) -> Dict[str, Any]:
    """P3: gap analyze → candidates → optional expand (claim_eligible=false).

    Args:
        workspace_id: 工作区 ID。
        pack_id: pack 标识。
        version: version 参数。
        caller_workspace_id: caller_workspace 标识。
        profile: 评测 profile。
        profile_id: profile 标识。
        subject_kind: subject_kind 参数。
        min_per_capability: min_per_capability 参数。
        method: method 参数。
        seed: seed 参数。
        ops: ops 参数。
        apply: apply 参数。
        cases: cases 参数。
    """
    from core.apps.eval.service.capability_coverage_fill import fill_capability_coverage

    kwargs: Dict[str, Any] = {
        "workspace_id": workspace_id,
        "caller_workspace_id": caller_workspace_id,
        "profile": profile,
        "profile_id": profile_id,
        "subject_kind": subject_kind,
        "min_per_capability": min_per_capability,
        "method": method,
        "seed": seed,
        "ops": ops,
        "apply": apply,
        "cases": cases,
    }
    if pack_id:
        kwargs["pack_id"] = pack_id
    if version:
        kwargs["version"] = version
    return fill_capability_coverage(**kwargs)


def eval_list_seed_capability_cases(*, capability_id: str = "") -> Dict[str, Any]:
    """Browse repo seed cases (read-only).

    Args:
        capability_id: capability 标识。
    """
    from core.apps.eval.service.capability_case_editor import list_seed_capability_cases

    return list_seed_capability_cases(capability_id=capability_id)


def eval_get_seed_capability_case(*, case_id: str) -> Dict[str, Any]:
    """eval_get_seed_capability_case。

    Args:
        case_id: case 标识。
    """
    from core.apps.eval.service.capability_case_editor import get_seed_capability_case

    return get_seed_capability_case(case_id=case_id)


def eval_list_workspace_pack_cases(
    *,
    workspace_id: str,
    pack_id: str = "",
    version: str = "",
    capability_id: str = "",
    caller_workspace_id: str = "",
) -> Dict[str, Any]:
    """eval_list_workspace_pack_cases。

    Args:
        workspace_id: 工作区 ID。
        pack_id: pack 标识。
        version: version 参数。
        capability_id: capability 标识。
        caller_workspace_id: caller_workspace 标识。
    """
    from core.apps.eval.service.capability_case_editor import list_workspace_pack_cases

    kwargs: Dict[str, Any] = {
        "workspace_id": workspace_id,
        "caller_workspace_id": caller_workspace_id or workspace_id,
        "capability_id": capability_id,
    }
    if pack_id:
        kwargs["pack_id"] = pack_id
    if version:
        kwargs["version"] = version
    return list_workspace_pack_cases(**kwargs)


def eval_get_workspace_pack_case(
    *,
    workspace_id: str,
    case_id: str,
    pack_id: str = "",
    version: str = "",
    caller_workspace_id: str = "",
) -> Dict[str, Any]:
    """eval_get_workspace_pack_case。

    Args:
        workspace_id: 工作区 ID。
        case_id: case 标识。
        pack_id: pack 标识。
        version: version 参数。
        caller_workspace_id: caller_workspace 标识。
    """
    from core.apps.eval.service.capability_case_editor import get_workspace_pack_case

    kwargs: Dict[str, Any] = {
        "workspace_id": workspace_id,
        "case_id": case_id,
        "caller_workspace_id": caller_workspace_id or workspace_id,
    }
    if pack_id:
        kwargs["pack_id"] = pack_id
    if version:
        kwargs["version"] = version
    return get_workspace_pack_case(**kwargs)


def eval_upsert_workspace_pack_case(
    *,
    workspace_id: str,
    case: Dict[str, Any],
    pack_id: str = "",
    version: str = "",
    caller_workspace_id: str = "",
) -> Dict[str, Any]:
    """eval_upsert_workspace_pack_case。

    Args:
        workspace_id: 工作区 ID。
        case: case 参数。
        pack_id: pack 标识。
        version: version 参数。
        caller_workspace_id: caller_workspace 标识。
    """
    from core.apps.eval.service.capability_case_editor import upsert_workspace_pack_case

    kwargs: Dict[str, Any] = {
        "workspace_id": workspace_id,
        "case": case,
        "caller_workspace_id": caller_workspace_id or workspace_id,
    }
    if pack_id:
        kwargs["pack_id"] = pack_id
    if version:
        kwargs["version"] = version
    return upsert_workspace_pack_case(**kwargs)


def eval_delete_workspace_pack_case(
    *,
    workspace_id: str,
    case_id: str,
    pack_id: str = "",
    version: str = "",
    caller_workspace_id: str = "",
) -> Dict[str, Any]:
    """eval_delete_workspace_pack_case。

    Args:
        workspace_id: 工作区 ID。
        case_id: case 标识。
        pack_id: pack 标识。
        version: version 参数。
        caller_workspace_id: caller_workspace 标识。
    """
    from core.apps.eval.service.capability_case_editor import delete_workspace_pack_case

    kwargs: Dict[str, Any] = {
        "workspace_id": workspace_id,
        "case_id": case_id,
        "caller_workspace_id": caller_workspace_id or workspace_id,
    }
    if pack_id:
        kwargs["pack_id"] = pack_id
    if version:
        kwargs["version"] = version
    return delete_workspace_pack_case(**kwargs)


def eval_open_capability_bank_editor(
    *,
    workspace_id: str,
    pack_id: str = "",
    version: str = "",
    caller_workspace_id: str = "",
    bump_if_frozen: bool = True,
) -> Dict[str, Any]:
    """eval_open_capability_bank_editor。

    Args:
        workspace_id: 工作区 ID。
        pack_id: pack 标识。
        version: version 参数。
        caller_workspace_id: caller_workspace 标识。
        bump_if_frozen: bump_if_frozen 参数。
    """
    from core.apps.eval.service.capability_case_editor import open_capability_bank_editor

    kwargs: Dict[str, Any] = {
        "workspace_id": workspace_id,
        "caller_workspace_id": caller_workspace_id or workspace_id,
        "bump_if_frozen": bump_if_frozen,
    }
    if pack_id:
        kwargs["pack_id"] = pack_id
    if version:
        kwargs["version"] = version
    return open_capability_bank_editor(**kwargs)


def eval_publish_draft_case_pack(
    *,
    pack_id: str,
    version: str,
    template: Optional[Dict[str, Any]] = None,
    variants: Optional[list] = None,
    cases: Optional[list] = None,
    workspace_id: str,
    caller_workspace_id: str = "",
    object_types: Optional[list] = None,
    kind: str = "curated",
) -> Dict[str, Any]:
    """P1.0 Case Factory: template/variants or raw cases → workspace draft pack.

    Args:
        pack_id: pack 标识。
        version: version 参数。
        template: template 参数。
        variants: variants 参数。
        cases: cases 参数。
        workspace_id: 工作区 ID。
        caller_workspace_id: caller_workspace 标识。
        object_types: object_types 参数。
        kind: kind 参数。
    """
    from core.apps.eval.service.case_factory import (
        generate_cases_from_template,
        publish_draft_workspace_pack,
    )

    if cases is not None:
        built = list(cases)
    else:
        built = generate_cases_from_template(
            dict(template or {}),
            variants=list(variants or [{}]),
        )
    return publish_draft_workspace_pack(
        pack_id=pack_id,
        version=version,
        cases=built,
        workspace_id=workspace_id,
        caller_workspace_id=caller_workspace_id or workspace_id,
        object_types=object_types,
        kind=kind,
    )


def eval_enqueue_case_pack_review(
    *,
    pack_id: str,
    version: str,
    workspace_id: str,
    caller_workspace_id: str = "",
    notes: str = "",
) -> Dict[str, Any]:
    """P1.1: draft|rejected → in_review. claim_eligible stays false.

    Args:
        pack_id: pack 标识。
        version: version 参数。
        workspace_id: 工作区 ID。
        caller_workspace_id: caller_workspace 标识。
        notes: notes 参数。
    """
    from core.apps.eval.service.case_review_queue import enqueue_pack_for_review

    return enqueue_pack_for_review(
        pack_id=pack_id,
        version=version,
        workspace_id=workspace_id,
        caller_workspace_id=caller_workspace_id or workspace_id,
        notes=notes,
    )


def eval_list_case_pack_review_queue(
    *,
    workspace_id: str,
    caller_workspace_id: str = "",
    statuses: Optional[list] = None,
) -> Dict[str, Any]:
    """P1.1: list workspace packs in review queue statuses.

    Args:
        workspace_id: 工作区 ID。
        caller_workspace_id: caller_workspace 标识。
        statuses: statuses 参数。
    """
    from core.apps.eval.service.case_review_queue import list_review_queue

    return list_review_queue(
        workspace_id=workspace_id,
        caller_workspace_id=caller_workspace_id or workspace_id,
        statuses=statuses,
    )


def eval_submit_case_pack_review(
    *,
    pack_id: str,
    version: str,
    workspace_id: str,
    decision: str,
    reviewer: str = "",
    notes: str = "",
    caller_workspace_id: str = "",
) -> Dict[str, Any]:
    """P1.1: approve→reviewed / reject→rejected. Never freezes or opens claim.

    Args:
        pack_id: pack 标识。
        version: version 参数。
        workspace_id: 工作区 ID。
        decision: decision 参数。
        reviewer: reviewer 参数。
        notes: notes 参数。
        caller_workspace_id: caller_workspace 标识。
    """
    from core.apps.eval.service.case_review_queue import submit_review_decision

    return submit_review_decision(
        pack_id=pack_id,
        version=version,
        workspace_id=workspace_id,
        decision=decision,
        reviewer=reviewer,
        notes=notes,
        caller_workspace_id=caller_workspace_id or workspace_id,
    )


def eval_freeze_workspace_case_pack(
    *,
    pack_id: str,
    version: str,
    workspace_id: str,
    caller_workspace_id: str = "",
    frozen_by: str = "",
    notes: str = "",
) -> Dict[str, Any]:
    """P1.2: reviewed → kind=frozen. claim_eligible stays false; no accuracy_claim.

    Args:
        pack_id: pack 标识。
        version: version 参数。
        workspace_id: 工作区 ID。
        caller_workspace_id: caller_workspace 标识。
        frozen_by: frozen_by 参数。
        notes: notes 参数。
    """
    from core.apps.eval.service.case_freeze import freeze_workspace_pack

    return freeze_workspace_pack(
        pack_id=pack_id,
        version=version,
        workspace_id=workspace_id,
        caller_workspace_id=caller_workspace_id or workspace_id,
        frozen_by=frozen_by,
        notes=notes,
    )


def eval_expand_draft_case_pack(
    *,
    pack_id: str,
    version: str,
    workspace_id: str,
    cases: Optional[list] = None,
    template: Optional[Dict[str, Any]] = None,
    variants: Optional[list] = None,
    caller_workspace_id: str = "",
) -> Dict[str, Any]:
    """P1.4: append cases into non-frozen draft/in_review/rejected pack.

    Args:
        pack_id: pack 标识。
        version: version 参数。
        workspace_id: 工作区 ID。
        cases: cases 参数。
        template: template 参数。
        variants: variants 参数。
        caller_workspace_id: caller_workspace 标识。
    """
    from core.apps.eval.service.case_pack_ops import expand_draft_workspace_pack

    return expand_draft_workspace_pack(
        pack_id=pack_id,
        version=version,
        workspace_id=workspace_id,
        cases=cases,
        template=template,
        variants=variants,
        caller_workspace_id=caller_workspace_id or workspace_id,
    )


def eval_bump_case_pack_version(
    *,
    pack_id: str,
    from_version: str,
    workspace_id: str,
    to_version: str = "",
    extra_cases: Optional[list] = None,
    template: Optional[Dict[str, Any]] = None,
    variants: Optional[list] = None,
    caller_workspace_id: str = "",
) -> Dict[str, Any]:
    """P1.4: version++ → new draft curated (frozen source untouched).

    Args:
        pack_id: pack 标识。
        from_version: from_version 参数。
        workspace_id: 工作区 ID。
        to_version: to_version 参数。
        extra_cases: extra_cases 参数。
        template: template 参数。
        variants: variants 参数。
        caller_workspace_id: caller_workspace 标识。
    """
    from core.apps.eval.service.case_pack_ops import bump_workspace_pack_version

    return bump_workspace_pack_version(
        pack_id=pack_id,
        from_version=from_version,
        workspace_id=workspace_id,
        to_version=to_version,
        extra_cases=extra_cases,
        template=template,
        variants=variants,
        caller_workspace_id=caller_workspace_id or workspace_id,
    )


def eval_summarize_case_pack_coverage(
    *,
    workspace_id: str,
    caller_workspace_id: str = "",
) -> Dict[str, Any]:
    """P1.4: workspace pack coverage inventory (not an accuracy claim).

    Args:
        workspace_id: 工作区 ID。
        caller_workspace_id: caller_workspace 标识。
    """
    from core.apps.eval.service.case_pack_ops import summarize_workspace_pack_coverage

    return summarize_workspace_pack_coverage(
        workspace_id=workspace_id,
        caller_workspace_id=caller_workspace_id or workspace_id,
    )


def eval_mark_case_pack_holdout(
    *,
    pack_id: str,
    version: str,
    workspace_id: str,
    case_ids: Optional[list] = None,
    ratio: float = 0.0,
    seed: str = "0",
    holdout: bool = True,
    caller_workspace_id: str = "",
) -> Dict[str, Any]:
    """P2.0: mark holdout flags on non-frozen pack (rehash).

    Args:
        pack_id: pack 标识。
        version: version 参数。
        workspace_id: 工作区 ID。
        case_ids: case_ids 参数。
        ratio: ratio 参数。
        seed: seed 参数。
        holdout: holdout 参数。
        caller_workspace_id: caller_workspace 标识。
    """
    from core.apps.eval.service.case_pack_ops import mark_pack_holdout

    return mark_pack_holdout(
        pack_id=pack_id,
        version=version,
        workspace_id=workspace_id,
        case_ids=case_ids,
        ratio=ratio,
        seed=seed,
        holdout=holdout,
        caller_workspace_id=caller_workspace_id or workspace_id,
    )


def eval_publish_mutation_case_pack(
    *,
    pack_id: str,
    version: str,
    workspace_id: str,
    seed_cases: list,
    ops: Optional[list] = None,
    seed: str = "0",
    caller_workspace_id: str = "",
) -> Dict[str, Any]:
    """P2.0: deterministic mutations → kind=generated draft (claim closed).

    Args:
        pack_id: pack 标识。
        version: version 参数。
        workspace_id: 工作区 ID。
        seed_cases: seed_cases 参数。
        ops: ops 参数。
        seed: seed 参数。
        caller_workspace_id: caller_workspace 标识。
    """
    from core.apps.eval.service.case_pack_ops import build_mutation_draft_pack

    return build_mutation_draft_pack(
        pack_id=pack_id,
        version=version,
        workspace_id=workspace_id,
        seed_cases=seed_cases,
        ops=ops,
        seed=seed,
        caller_workspace_id=caller_workspace_id or workspace_id,
    )


def eval_publish_trace_case_pack(
    *,
    pack_id: str,
    version: str,
    workspace_id: str,
    traces: list,
    caller_workspace_id: str = "",
) -> Dict[str, Any]:
    """P2.0: trace dicts → kind=trace draft (claim closed).

    Args:
        pack_id: pack 标识。
        version: version 参数。
        workspace_id: 工作区 ID。
        traces: traces 参数。
        caller_workspace_id: caller_workspace 标识。
    """
    from core.apps.eval.service.case_pack_ops import build_trace_draft_pack

    return build_trace_draft_pack(
        pack_id=pack_id,
        version=version,
        workspace_id=workspace_id,
        traces=traces,
        caller_workspace_id=caller_workspace_id or workspace_id,
    )


async def eval_publish_llm_candidate_case_pack(
    *,
    pack_id: str,
    version: str,
    workspace_id: str,
    theme: str,
    n: int = 3,
    category: str = "normal",
    seed: str = "0",
    model_name: str = "",
    dry: bool = False,
    llm_generate_fn=None,
    caller_workspace_id: str = "",
) -> Dict[str, Any]:
    """P3.0: LLM/stub candidates → kind=generated draft (claim closed).

    Args:
        pack_id: pack 标识。
        version: version 参数。
        workspace_id: 工作区 ID。
        theme: theme 参数。
        n: n 参数。
        category: category 参数。
        seed: seed 参数。
        model_name: model_name 参数。
        dry: dry 参数。
        llm_generate_fn: llm_generate_fn 参数。
        caller_workspace_id: caller_workspace 标识。
    """
    from core.apps.eval.service.case_pack_ops import build_llm_candidate_draft_pack

    return await build_llm_candidate_draft_pack(
        pack_id=pack_id,
        version=version,
        workspace_id=workspace_id,
        theme=theme,
        n=n,
        category=category,
        seed=seed,
        model_name=model_name,
        dry=dry,
        llm_generate_fn=llm_generate_fn,
        caller_workspace_id=caller_workspace_id or workspace_id,
    )


def eval_propose_case_pack_difficulty(
    *,
    pack_id: str,
    version: str,
    workspace_id: str,
    persist: bool = False,
    caller_workspace_id: str = "",
) -> Dict[str, Any]:
    """P3.0: heuristic difficulty labels (not calibrated).

    Args:
        pack_id: pack 标识。
        version: version 参数。
        workspace_id: 工作区 ID。
        persist: persist 参数。
        caller_workspace_id: caller_workspace 标识。
    """
    from core.apps.eval.service.case_pack_ops import propose_pack_difficulty

    return propose_pack_difficulty(
        pack_id=pack_id,
        version=version,
        workspace_id=workspace_id,
        persist=persist,
        caller_workspace_id=caller_workspace_id or workspace_id,
    )


def eval_open_judge_calibration_ticket(
    *,
    pack_id: str,
    version: str,
    workspace_id: str,
    sample_case_ids: Optional[list] = None,
    notes: str = "",
    caller_workspace_id: str = "",
) -> Dict[str, Any]:
    """P3.1: persist judge calibration ticket — does not unlock claims.

    Args:
        pack_id: pack 标识。
        version: version 参数。
        workspace_id: 工作区 ID。
        sample_case_ids: sample_case_ids 参数。
        notes: notes 参数。
        caller_workspace_id: caller_workspace 标识。
    """
    from core.apps.eval.service.case_pack_ops import (
        open_judge_calibration_ticket_for_pack,
    )

    return open_judge_calibration_ticket_for_pack(
        pack_id=pack_id,
        version=version,
        workspace_id=workspace_id,
        sample_case_ids=sample_case_ids,
        notes=notes,
        caller_workspace_id=caller_workspace_id or workspace_id,
    )


def eval_calibrate_case_pack_difficulty(
    *,
    pack_id: str,
    version: str,
    workspace_id: str,
    labels: list,
    rater: str = "",
    caller_workspace_id: str = "",
) -> Dict[str, Any]:
    """P3.1: human difficulty labels → pack (engineering calibrated; claim closed).

    Args:
        pack_id: pack 标识。
        version: version 参数。
        workspace_id: 工作区 ID。
        labels: labels 参数。
        rater: rater 参数。
        caller_workspace_id: caller_workspace 标识。
    """
    from core.apps.eval.service.case_pack_ops import calibrate_pack_difficulty

    return calibrate_pack_difficulty(
        pack_id=pack_id,
        version=version,
        workspace_id=workspace_id,
        labels=labels,
        rater=rater,
        caller_workspace_id=caller_workspace_id or workspace_id,
    )


def eval_record_judge_calibration_ratings(
    *,
    workspace_id: str,
    ticket_id: str,
    ratings: list,
    rater: str = "",
    caller_workspace_id: str = "",
) -> Dict[str, Any]:
    """P3.1: append judge ratings + agreement (claim closed).

    Args:
        workspace_id: 工作区 ID。
        ticket_id: ticket 标识。
        ratings: ratings 参数。
        rater: rater 参数。
        caller_workspace_id: caller_workspace 标识。
    """
    from core.apps.eval.service.case_pack_ops import (
        record_judge_calibration_ratings_for_pack,
    )

    return record_judge_calibration_ratings_for_pack(
        workspace_id=workspace_id,
        ticket_id=ticket_id,
        ratings=ratings,
        rater=rater,
        caller_workspace_id=caller_workspace_id or workspace_id,
    )


def eval_close_judge_calibration_ticket(
    *,
    workspace_id: str,
    ticket_id: str,
    notes: str = "",
    caller_workspace_id: str = "",
) -> Dict[str, Any]:
    """P3.1: close judge ticket after ratings (claim closed).

    Args:
        workspace_id: 工作区 ID。
        ticket_id: ticket 标识。
        notes: notes 参数。
        caller_workspace_id: caller_workspace 标识。
    """
    from core.apps.eval.service.case_pack_ops import (
        close_judge_calibration_ticket_for_pack,
    )

    return close_judge_calibration_ticket_for_pack(
        workspace_id=workspace_id,
        ticket_id=ticket_id,
        notes=notes,
        caller_workspace_id=caller_workspace_id or workspace_id,
    )


def eval_get_judge_calibration_ticket(
    *,
    workspace_id: str,
    ticket_id: str,
    caller_workspace_id: str = "",
) -> Dict[str, Any]:
    """P3.1: load persisted judge ticket.

    Args:
        workspace_id: 工作区 ID。
        ticket_id: ticket 标识。
        caller_workspace_id: caller_workspace 标识。
    """
    from core.apps.eval.service.case_pack_ops import (
        get_judge_calibration_ticket_for_pack,
    )

    return get_judge_calibration_ticket_for_pack(
        workspace_id=workspace_id,
        ticket_id=ticket_id,
        caller_workspace_id=caller_workspace_id or workspace_id,
    )


def eval_compile_evaluation_plan(
    *,
    agent_id: str = "",
    object_id: str = "",
    object_type: str = "agent",
    set_ids: Optional[list] = None,
    purpose: Optional[list] = None,
    include_special: bool = False,
    live: bool = False,
    capabilities: Optional[list] = None,
    tools: Optional[list] = None,
    permissions: Optional[list] = None,
    roles: Optional[list] = None,
    eval_profile: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """P2/P3: compile Evaluation Plan for any object_type (same plan schema).

    Args:
        agent_id: Agent ID。
        object_id: object 标识。
        object_type: object_type 参数。
        set_ids: set_ids 参数。
        purpose: purpose 参数。
        include_special: include_special 参数。
        live: live 参数。
        capabilities: capabilities 参数。
        tools: tools 参数。
        permissions: permissions 参数。
        roles: roles 参数。
        eval_profile: eval_profile 参数。
    """
    from core.apps.eval.service.eval_plan import compile_plan_for_object

    oid = (object_id or agent_id or "").strip()
    if not oid:
        raise ValueError("object_id or agent_id required")
    ot = (object_type or "agent").strip() or "agent"
    plan = compile_plan_for_object(
        object_type=ot,
        object_id=oid,
        set_ids=set_ids,
        purpose=purpose,
        include_special=include_special,
        live=live,
        capabilities=capabilities,
        tools=tools,
        permissions=permissions,
        roles=roles,
        eval_profile=eval_profile,
    )
    src = None
    if isinstance(eval_profile, dict) and eval_profile.get("profile_source"):
        src = str(eval_profile.get("profile_source"))
    elif isinstance(plan.get("eval_profile_source"), str):
        src = plan.get("eval_profile_source")
    return {
        "ok": True,
        "accuracy_claim": False,
        "sufficiency_claim": False,
        "plan": plan,
        "target_contract": plan.get("target_contract"),
        "object_type": ot,
        "eval_profile_source": src,
    }


async def eval_resolve_agent_eval_profile(*, agent_id: str) -> Dict[str, Any]:
    """Resolve Agent eval_profile (explicit or derived skill/tool hints).

    Args:
        agent_id: Agent ID。
    """
    from core.apps.eval.service.eval_profile_resolve import resolve_agent_eval_profile

    profile = await resolve_agent_eval_profile(agent_id)
    return {
        "ok": True,
        "agent_id": agent_id,
        "eval_profile": profile,
        "accuracy_claim": False,
        "sufficiency_claim": False,
    }


def eval_list_external_targets(*, workspace_id: str) -> Dict[str, Any]:
    """List registered external http_chat_pull targets for a named workspace.

    Args:
        workspace_id: 工作区 ID。
    """
    from core.apps.eval.service.external_exam_ops import list_targets

    items = list_targets(workspace_id)
    return {
        "ok": True,
        "items": items,
        "total": len(items),
        "accuracy_claim": False,
        "honesty": "外部拉模式 · 仅对话文本结果；≠ 本机 live Agent；≠ 轨迹充分。",
    }


def eval_upsert_external_target(
    *,
    workspace_id: str,
    target_id: str,
    label: str = "",
    base_url: str = "",
    path: str = "/v1/chat",
    auth_header_name: str = "",
    auth_secret_env: str = "",
    timeout_ms: int = 30_000,
    response_mode: str = "aiplat_v0",
) -> Dict[str, Any]:
    """Register or update an external pull-mode chat target (SSRF-checked).

    Args:
        workspace_id: 工作区 ID。
        target_id: target 标识。
        label: label 参数。
        base_url: base_url 参数。
        path: 路径。
        auth_header_name: auth_header_name 参数。
        auth_secret_env: auth_secret_env 参数。
        timeout_ms: timeout_ms 参数。
        response_mode: response_mode 参数。
    """
    from core.apps.eval.service.external_exam_ops import register_target

    target = register_target(
        workspace_id,
        target_id=target_id,
        label=label,
        base_url=base_url,
        path=path,
        auth_header_name=auth_header_name,
        auth_secret_env=auth_secret_env,
        timeout_ms=timeout_ms,
        response_mode=response_mode,
    )
    return {"ok": True, "target": target, "accuracy_claim": False}


async def eval_run_external_exam(
    *,
    workspace_id: str,
    target_id: str,
    set_id: str,
    live: bool = False,
    max_tasks: int = 0,
    persist: bool = True,
) -> Dict[str, Any]:
    """Pull-mode exam against external HTTP chat target (not local ReAct).

    Args:
        workspace_id: 工作区 ID。
        target_id: target 标识。
        set_id: set 标识。
        live: live 参数。
        max_tasks: max_tasks 参数。
        persist: persist 参数。
    """
    from core.apps.eval.service.external_exam_ops import run_external_exam

    return await run_external_exam(
        workspace_id=workspace_id,
        target_id=target_id,
        set_id=set_id,
        live=live,
        max_tasks=max_tasks,
        persist=persist,
    )


def eval_run_generated_app_pi_smoke(
    *,
    source: str = "sample",
    project_id: str = "",
    app_home: str = "",
    live: bool = False,
    model: str = "",
    timeout_s: float = 90.0,
) -> Dict[str, Any]:
    """Generated-app Pi delivery smoke (offline structural or live pi CLI).

    Args:
        source: source 参数。
        project_id: project 标识。
        app_home: app_home 参数。
        live: live 参数。
        model: 模型名。
        timeout_s: timeout_s 参数。
    """
    from core.apps.eval.service.generated_app_pi_ops import run_generated_app_pi_smoke

    return run_generated_app_pi_smoke(
        source=source,
        project_id=project_id,
        app_home=app_home,
        live=live,
        model=model,
        timeout_s=timeout_s,
    )


async def eval_run_prompt_plan_exam(
    *,
    object_id: str = "prompt_under_test",
    set_ids: Optional[list] = None,
    purpose: Optional[list] = None,
    include_special: bool = False,
    live: bool = False,
    model: str = "",
    max_tasks_per_set: int = 20,
) -> Dict[str, Any]:
    """Prompt Plan-chain exam: compile plan + run prompt/* lexical/oracle sets.

    Args:
        object_id: object 标识。
        set_ids: set_ids 参数。
        purpose: purpose 参数。
        include_special: include_special 参数。
        live: live 参数。
        model: 模型名。
        max_tasks_per_set: max_tasks_per_set 参数。
    """
    from core.apps.eval.service.prompt_plan_ops import run_prompt_plan_exam

    return await run_prompt_plan_exam(
        object_id=object_id,
        set_ids=set_ids,
        purpose=purpose,
        include_special=include_special,
        live=live,
        model=model,
        max_tasks_per_set=max_tasks_per_set,
    )


async def eval_run_workflow_plan_exam(
    *,
    object_id: str = "workflow_under_test",
    set_ids: Optional[list] = None,
    purpose: Optional[list] = None,
    include_special: bool = False,
    live: bool = False,
    model: str = "",
    max_tasks_per_set: int = 20,
) -> Dict[str, Any]:
    """Workflow Plan-chain exam: compile plan + run workflow/* lexical sets.

    Args:
        object_id: object 标识。
        set_ids: set_ids 参数。
        purpose: purpose 参数。
        include_special: include_special 参数。
        live: live 参数。
        model: 模型名。
        max_tasks_per_set: max_tasks_per_set 参数。
    """
    from core.apps.eval.service.typed_plan_exam import run_typed_plan_exam

    return await run_typed_plan_exam(
        object_type="workflow",
        object_id=object_id,
        set_ids=set_ids,
        purpose=purpose,
        include_special=include_special,
        live=live,
        model=model,
        max_tasks_per_set=max_tasks_per_set,
        source_refs=["workflow_plan_ops"],
    )


async def eval_run_model_plan_exam(
    *,
    object_id: str = "model_under_test",
    set_ids: Optional[list] = None,
    purpose: Optional[list] = None,
    include_special: bool = False,
    live: bool = False,
    model: str = "",
    max_tasks_per_set: int = 20,
) -> Dict[str, Any]:
    """Model Plan-chain exam: compile plan + run model/* lexical sets (≠ leaderboard).

    Args:
        object_id: object 标识。
        set_ids: set_ids 参数。
        purpose: purpose 参数。
        include_special: include_special 参数。
        live: live 参数。
        model: 模型名。
        max_tasks_per_set: max_tasks_per_set 参数。
    """
    from core.apps.eval.service.typed_plan_exam import run_typed_plan_exam

    return await run_typed_plan_exam(
        object_type="model",
        object_id=object_id,
        set_ids=set_ids,
        purpose=purpose,
        include_special=include_special,
        live=live,
        model=model,
        max_tasks_per_set=max_tasks_per_set,
        source_refs=["model_plan_ops"],
    )


async def eval_run_dataset_plan_exam(
    *,
    object_id: str = "dataset_under_test",
    set_ids: Optional[list] = None,
    purpose: Optional[list] = None,
    include_special: bool = False,
    live: bool = False,
    model: str = "",
    max_tasks_per_set: int = 20,
) -> Dict[str, Any]:
    """Dataset Plan-chain exam: fixture_table asserts (≠ KB sample retrieval).

    Args:
        object_id: object 标识。
        set_ids: set_ids 参数。
        purpose: purpose 参数。
        include_special: include_special 参数。
        live: live 参数。
        model: 模型名。
        max_tasks_per_set: max_tasks_per_set 参数。
    """
    from core.apps.eval.service.typed_plan_exam import run_typed_plan_exam

    return await run_typed_plan_exam(
        object_type="dataset",
        object_id=object_id,
        set_ids=set_ids,
        purpose=purpose,
        include_special=include_special,
        live=live,
        model=model,
        max_tasks_per_set=max_tasks_per_set,
        source_refs=["dataset_plan_ops"],
    )


async def eval_run_system_plan_exam(
    *,
    object_id: str = "system_under_test",
    parts: Optional[list] = None,
    live: bool = False,
    model: str = "",
    max_tasks_per_set: int = 20,
) -> Dict[str, Any]:
    """System combination exam: typed parts + runtime_parts (≠ single-object).

    Args:
        object_id: object 标识。
        parts: parts 参数。
        live: live 参数。
        model: 模型名。
        max_tasks_per_set: max_tasks_per_set 参数。
    """
    from core.apps.eval.service.system_plan_ops import run_system_plan_exam

    return await run_system_plan_exam(
        object_id=object_id,
        parts=parts,
        live=live,
        model=model,
        max_tasks_per_set=max_tasks_per_set,
    )


def eval_evaluate_l5_claims_gate(
    *,
    evidence: Optional[Dict[str, Any]] = None,
    explicit_authorize: bool = False,
) -> Dict[str, Any]:
    """L5 scope-bound claims gate (advisory; default claims stay false).

    Args:
        evidence: evidence 参数。
        explicit_authorize: explicit_authorize 参数。
    """
    from core.apps.eval.service.claims_gate import evaluate_l5_claims_gate

    return evaluate_l5_claims_gate(
        evidence, explicit_authorize=bool(explicit_authorize)
    )


def eval_agent_attributable_report(
    *,
    agent_id: str,
    limit: int = 5,
    set_id: str = "",
) -> Dict[str, Any]:
    """Attributable report + publish conclusion (safety veto hard gate; variance uses history).

    Args:
        agent_id: Agent ID。
        limit: 返回条数上限。
        set_id: set 标识。
    """
    from core.apps.eval.service.agent_attributable_report import (
        build_attributable_report_from_agent,
    )

    return build_attributable_report_from_agent(agent_id, limit=limit, set_id=set_id)


def eval_e3_status(*, tenant_id: str = "eval-v1") -> Dict[str, Any]:
    """eval_e3_status。

    Args:
        tenant_id: 租户 ID。
    """
    from core.apps.eval.service.gold_bootstrap import e3_status

    return e3_status(tenant_id=tenant_id)


def eval_run_e4_calibration(
    *,
    tenant_id: str = "eval-v1",
    set_id: str = "",
    k: int = 3,
    limit: int = 500,
) -> Dict[str, Any]:
    """EVAL_V1 E4: deterministic judge v1 + k-repeat / ECE calibration report.

    Args:
        tenant_id: 租户 ID。
        set_id: set 标识。
        k: k 参数。
        limit: 返回条数上限。
    """
    from core.apps.eval.service.judge_v1 import run_e4_calibration

    return run_e4_calibration(tenant_id=tenant_id, set_id=set_id, k=k, limit=limit)


def eval_run_e5_gate(
    *,
    mode: str = "pr",
    tenant_id: str = "eval-v1",
    set_id: str = "",
    baseline: str = "gold",
    candidate: str = "local",
    limit: Optional[int] = None,
) -> Dict[str, Any]:
    """EVAL_V1 E5: local engineering gate + failure taxonomy (not accuracy / G2a).

    Args:
        mode: mode 参数。
        tenant_id: 租户 ID。
        set_id: set 标识。
        baseline: baseline 参数。
        candidate: candidate 参数。
        limit: 返回条数上限。
    """
    from core.apps.eval.service.gate_v1 import run_e5_gate

    return run_e5_gate(
        mode=mode,
        tenant_id=tenant_id,
        set_id=set_id,
        baseline=baseline,
        candidate=candidate,
        limit=limit,
    )


def eval_g2a_status(*, tenant_id: str = "eval-v1") -> Dict[str, Any]:
    """eval_g2a_status。

    Args:
        tenant_id: 租户 ID。
    """
    from core.apps.eval.service.g2a import g2a_status

    return g2a_status(tenant_id=tenant_id)


def eval_list_review_queue(
    *, tenant_id: str = "eval-v1", annotator: str = "solo_reviewer", limit: int = 100
) -> Dict[str, Any]:
    """eval_list_review_queue。

    Args:
        tenant_id: 租户 ID。
        annotator: annotator 参数。
        limit: 返回条数上限。
    """
    from core.apps.eval.service.g2a import list_review_queue

    return list_review_queue(tenant_id=tenant_id, annotator=annotator, limit=limit)


def eval_preannotate_review_queue(
    *, tenant_id: str = "eval-v1", annotator: str = "solo_reviewer", limit: int = 500
) -> Dict[str, Any]:
    """eval_preannotate_review_queue。

    Args:
        tenant_id: 租户 ID。
        annotator: annotator 参数。
        limit: 返回条数上限。
    """
    from core.apps.eval.service.g2a import preannotate_review_queue

    return preannotate_review_queue(
        tenant_id=tenant_id, annotator=annotator, limit=limit
    )


def eval_adjudicate_label(
    label_id: str,
    *,
    passed: bool,
    notes: str = "",
    rationale: str = "",
    tenant_id: str = "eval-v1",
) -> Dict[str, Any]:
    """eval_adjudicate_label。

    Args:
        label_id: label 标识。
        passed: passed 参数。
        notes: notes 参数。
        rationale: rationale 参数。
        tenant_id: 租户 ID。
    """
    from core.apps.eval.service.g2a import adjudicate_label

    return adjudicate_label(
        label_id,
        passed=passed,
        notes=notes,
        rationale=rationale,
        tenant_id=tenant_id,
    )


def eval_lock_v0(*, tenant_id: str = "eval-v1") -> Dict[str, Any]:
    """eval_lock_v0。

    Args:
        tenant_id: 租户 ID。
    """
    from core.apps.eval.service.g2a import lock_v0

    return lock_v0(tenant_id=tenant_id)


def eval_run_g2a_gate(
    *,
    mode: str = "nightly",
    tenant_id: str = "eval-v1",
    set_id: str = "",
    limit: Optional[int] = None,
) -> Dict[str, Any]:
    """EVAL_V1 G2a: local gate claim after v0 lock (never accuracy).

    Args:
        mode: mode 参数。
        tenant_id: 租户 ID。
        set_id: set 标识。
        limit: 返回条数上限。
    """
    from core.apps.eval.service.g2a import run_g2a_gate

    return run_g2a_gate(
        mode=mode, tenant_id=tenant_id, set_id=set_id, limit=limit
    )


def eval_g2b_pack_status(*, tenant_id: str = "eval-v1") -> Dict[str, Any]:
    """G2b facilitation pack status (accuracy_claim stays false).

    Args:
        tenant_id: 租户 ID。
    """
    from core.apps.eval.service.g2b import g2b_pack_status

    return g2b_pack_status(tenant_id=tenant_id)


def eval_g2b_l5_gap_disclosure(*, tenant_id: str = "eval-v1") -> Dict[str, Any]:
    """G2b distance-to-L5 disclosure; claims_gate default authorize=false; accuracy_claim false.

    Args:
        tenant_id: 租户 ID。
    """
    from core.apps.eval.service.g2b import g2b_l5_gap_disclosure

    return g2b_l5_gap_disclosure(tenant_id=tenant_id)


def eval_g2b_claim_unlock_checklist(*, tenant_id: str = "eval-v1") -> Dict[str, Any]:
    """G2b claim unlock AND-gates; never flips accuracy_claim.

    Args:
        tenant_id: 租户 ID。
    """
    from core.apps.eval.service.g2b import g2b_claim_unlock_checklist

    return g2b_claim_unlock_checklist(tenant_id=tenant_id)


def eval_preference_pack_status(*, tenant_id: str = "eval-v1") -> Dict[str, Any]:
    """Preference facilitation pack status (accuracy_claim stays false).

    Args:
        tenant_id: 租户 ID。
    """
    from core.apps.eval.service.preference import preference_pack_status

    return preference_pack_status(tenant_id=tenant_id)


def eval_scorecard_status(*, tenant_id: str = "eval-v1") -> Dict[str, Any]:
    """Scorecard honesty snapshot (accuracy_claim / authorize stay false).

    Args:
        tenant_id: 租户 ID。
    """
    from core.apps.eval.service.scorecard import scorecard_status

    return scorecard_status(tenant_id=tenant_id)


def eval_evidence_audit_status(*, tenant_id: str = "eval-v1") -> Dict[str, Any]:
    """Evidence audit snapshot (hash + attestation; accuracy_claim stays false).

    Args:
        tenant_id: 租户 ID。
    """
    from core.apps.eval.service.evidence_audit import evidence_audit_status

    return evidence_audit_status(tenant_id=tenant_id)


def eval_worksheet_pack_status(
    *, tenant_id: str = "eval-v1", limit: int = 20
) -> Dict[str, Any]:
    """List human worksheet packs (facilitation; accuracy_claim stays false).

    Args:
        tenant_id: 租户 ID。
        limit: 返回条数上限。
    """
    from core.apps.eval.service.worksheet_pack import worksheet_pack_status

    return worksheet_pack_status(tenant_id=tenant_id, limit=limit)


def eval_worksheet_pack_generate(
    *,
    tenant_id: str = "eval-v1",
    skip_g2b: bool = False,
    skip_preference: bool = False,
) -> Dict[str, Any]:
    """Generate blank human worksheets (accuracy_claim stays false).

    Args:
        tenant_id: 租户 ID。
        skip_g2b: skip_g2b 参数。
        skip_preference: skip_preference 参数。
    """
    from core.apps.eval.service.worksheet_pack import worksheet_pack_generate

    return worksheet_pack_generate(
        tenant_id=tenant_id,
        skip_g2b=skip_g2b,
        skip_preference=skip_preference,
    )


def eval_worksheet_pack_file(
    stamp: str,
    filename: str,
    *,
    tenant_id: str = "eval-v1",
) -> Dict[str, Any]:
    """Read one worksheet pack file (text); accuracy_claim stays false.

    Args:
        stamp: stamp 参数。
        filename: filename 参数。
        tenant_id: 租户 ID。
    """
    from core.apps.eval.service.worksheet_pack import worksheet_pack_file

    meta, text = worksheet_pack_file(stamp, filename, tenant_id=tenant_id)
    if not meta.get("ok"):
        return meta
    meta["content"] = text
    return meta


def eval_g2c_status(*, tenant_id: str = "eval-v1") -> Dict[str, Any]:
    """eval_g2c_status。

    Args:
        tenant_id: 租户 ID。
    """
    from core.apps.eval.service.g2c import g2c_status

    return g2c_status(tenant_id=tenant_id)


def eval_list_g2c_retest_queue(
    *, tenant_id: str = "eval-v1", limit: int = 100
) -> Dict[str, Any]:
    """eval_list_g2c_retest_queue。

    Args:
        tenant_id: 租户 ID。
        limit: 返回条数上限。
    """
    from core.apps.eval.service.g2c import list_g2c_retest_queue

    return list_g2c_retest_queue(tenant_id=tenant_id, limit=limit)


def eval_record_g2c_retest(
    task_id: str,
    *,
    passed: bool,
    notes: str = "",
    rationale: str = "",
    tenant_id: str = "eval-v1",
) -> Dict[str, Any]:
    """eval_record_g2c_retest。

    Args:
        task_id: task 标识。
        passed: passed 参数。
        notes: notes 参数。
        rationale: rationale 参数。
        tenant_id: 租户 ID。
    """
    from core.apps.eval.service.g2c import record_g2c_retest

    return record_g2c_retest(
        task_id,
        passed=passed,
        notes=notes,
        rationale=rationale,
        tenant_id=tenant_id,
    )


def eval_compute_g2c_report(
    *, tenant_id: str = "eval-v1", persist: bool = True
) -> Dict[str, Any]:
    """eval_compute_g2c_report。

    Args:
        tenant_id: 租户 ID。
        persist: persist 参数。
    """
    from core.apps.eval.service.g2c import compute_g2c_report

    return compute_g2c_report(tenant_id=tenant_id, persist=persist)


def eval_list_gates(*, tenant_id: str = "eval-v1", limit: int = 50) -> list:
    """eval_list_gates。

    Args:
        tenant_id: 租户 ID。
        limit: 返回条数上限。
    """
    from core.apps.eval.service.store import get_eval_store

    return get_eval_store(tenant_id=tenant_id).list_gates(limit=limit)


def eval_get_gate(gate_id: str, *, tenant_id: str = "eval-v1") -> Optional[Dict[str, Any]]:
    """eval_get_gate。

    Args:
        gate_id: gate 标识。
        tenant_id: 租户 ID。
    """
    from core.apps.eval.service.store import get_eval_store

    return get_eval_store(tenant_id=tenant_id).get_gate(gate_id)


def eval_list_judges(*, tenant_id: str = "eval-v1", limit: int = 50) -> list:
    """eval_list_judges。

    Args:
        tenant_id: 租户 ID。
        limit: 返回条数上限。
    """
    from core.apps.eval.service.store import get_eval_store

    return get_eval_store(tenant_id=tenant_id).list_judges(limit=limit)


def eval_get_report(report_id: str, *, tenant_id: str = "eval-v1") -> Optional[Dict[str, Any]]:
    """eval_get_report。

    Args:
        report_id: report 标识。
        tenant_id: 租户 ID。
    """
    from core.apps.eval.service.store import get_eval_store

    return get_eval_store(tenant_id=tenant_id).get_report(report_id)


def eval_list_reports(*, tenant_id: str = "eval-v1", limit: int = 50) -> list:
    """List eval_reports newest-first (UI-2 Reports tab).

    Args:
        tenant_id: 租户 ID。
        limit: 返回条数上限。
    """
    from core.apps.eval.service.store import get_eval_store

    return get_eval_store(tenant_id=tenant_id).list_reports(limit=limit)


def eval_compare_reports(
    baseline_id: str,
    candidate_id: str,
    *,
    tenant_id: str = "eval-v1",
) -> Dict[str, Any]:
    """P1b — compare two eval store reports (same composite_version only).

    Args:
        baseline_id: baseline 标识。
        candidate_id: candidate 标识。
        tenant_id: 租户 ID。
    """
    from core.apps.eval.service.report_compare import compare_eval_reports_by_id

    return compare_eval_reports_by_id(
        baseline_id, candidate_id, tenant_id=tenant_id
    )


# ── DIAGNOSIS_V1 C1 ───────────────────────────────────────


def diagnosis_health(*, tenant_id: str = "") -> Dict[str, Any]:
    """diagnosis_health。

    Args:
        tenant_id: 租户 ID。
    """
    from core.apps.diagnosis.service.store import get_diagnosis_store

    return get_diagnosis_store(tenant_id=tenant_id).health(tenant_id=tenant_id)


def diagnosis_create_case(
    *,
    scenario: str,
    subject_ref: str,
    tenant_id: str = "",
    baseline_ref: Optional[str] = None,
    case_id: Optional[str] = None,
    meta: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """diagnosis_create_case。

    Args:
        scenario: scenario 参数。
        subject_ref: subject_ref 参数。
        tenant_id: 租户 ID。
        baseline_ref: baseline_ref 参数。
        case_id: case 标识。
        meta: meta 参数。
    """
    from core.apps.diagnosis.service.store import get_diagnosis_store

    return get_diagnosis_store(tenant_id=tenant_id).create_case(
        scenario=scenario,
        subject_ref=subject_ref,
        tenant_id=tenant_id,
        baseline_ref=baseline_ref,
        case_id=case_id,
        meta=meta,
    )


def diagnosis_list_cases(*, tenant_id: str = "", limit: int = 100) -> list:
    """diagnosis_list_cases。

    Args:
        tenant_id: 租户 ID。
        limit: 返回条数上限。
    """
    from core.apps.diagnosis.service.store import get_diagnosis_store

    return get_diagnosis_store(tenant_id=tenant_id).list_cases(tenant_id=tenant_id, limit=limit)


def diagnosis_get_case(case_id: str, *, tenant_id: str = "") -> Optional[Dict[str, Any]]:
    """diagnosis_get_case。

    Args:
        case_id: case 标识。
        tenant_id: 租户 ID。
    """
    from core.apps.diagnosis.service.store import get_diagnosis_store

    return get_diagnosis_store(tenant_id=tenant_id).get_case(case_id, tenant_id=tenant_id)


def diagnosis_collect(case_id: str, *, tenant_id: str = "") -> Dict[str, Any]:
    """Read-only collect via adapters; never writes source systems.

    Args:
        case_id: case 标识。
        tenant_id: 租户 ID。
    """
    from core.apps.diagnosis.service.adapters import collect_evidence
    from core.apps.diagnosis.service.store import get_diagnosis_store

    store = get_diagnosis_store(tenant_id=tenant_id)
    case = store.get_case(case_id, tenant_id=tenant_id)
    if not case:
        raise KeyError("case_not_found")
    bundle = collect_evidence(
        scenario=str(case.get("scenario") or ""),
        subject_ref=str(case.get("subject_ref") or ""),
        baseline_ref=case.get("baseline_ref"),
    )
    evidence = list(bundle.get("evidence") or [])
    store.replace_evidence(
        case_id,
        evidence,
        tenant_id=tenant_id,
        payload={
            "adapter_payload": bundle.get("payload") or {},
            "expected": bundle.get("expected") or {},
            "fixture_id": bundle.get("fixture_id"),
            "collect_source": bundle.get("source"),
        },
    )
    return {
        "case_id": case_id,
        "evidence": evidence,
        "fixture_id": bundle.get("fixture_id"),
        "source": bundle.get("source"),
        "adapters": bundle.get("adapters") or {},
    }


def diagnosis_get_evidence(case_id: str, *, tenant_id: str = "") -> Optional[Dict[str, Any]]:
    """diagnosis_get_evidence。

    Args:
        case_id: case 标识。
        tenant_id: 租户 ID。
    """
    from core.apps.diagnosis.service.store import get_diagnosis_store

    return get_diagnosis_store(tenant_id=tenant_id).get_evidence_bundle(
        case_id, tenant_id=tenant_id
    )


def diagnosis_run_report(case_id: str, *, tenant_id: str = "") -> Dict[str, Any]:
    """diagnosis_run_report。

    Args:
        case_id: case 标识。
        tenant_id: 租户 ID。
    """
    from core.apps.diagnosis.service.engine import diagnose_case
    from core.apps.diagnosis.service.store import get_diagnosis_store

    store = get_diagnosis_store(tenant_id=tenant_id)
    case = store.get_case(case_id, tenant_id=tenant_id)
    if not case:
        raise KeyError("case_not_found")
    bundle = store.get_evidence_bundle(case_id, tenant_id=tenant_id) or {}
    evidence = list(bundle.get("evidence") or [])
    if not evidence:
        raise RuntimeError("case_not_ready")
    payload_wrap = bundle.get("payload") or {}
    adapter_payload = payload_wrap.get("adapter_payload") or payload_wrap
    expected = payload_wrap.get("expected") or None
    out = diagnose_case(
        case_id=case_id,
        evidence=evidence,
        payload=adapter_payload if isinstance(adapter_payload, dict) else {},
        expected=expected if isinstance(expected, dict) else None,
    )
    report = store.save_report(
        case_id,
        report=out["report"],
        findings=out["findings"],
        hypotheses=out["hypotheses"],
        recommendations=out["recommendations"],
        status=str(out["status"]),
        tenant_id=tenant_id,
    )
    return {
        "case_id": case_id,
        "status": out["status"],
        "report": report,
        "findings": out["findings"],
        "hypotheses": out["hypotheses"],
        "recommendations": out["recommendations"],
    }


def diagnosis_get_report(case_id: str, *, tenant_id: str = "") -> Optional[Dict[str, Any]]:
    """diagnosis_get_report。

    Args:
        case_id: case 标识。
        tenant_id: 租户 ID。
    """
    from core.apps.diagnosis.service.store import get_diagnosis_store

    return get_diagnosis_store(tenant_id=tenant_id).get_report_bundle(
        case_id, tenant_id=tenant_id
    )


def diagnosis_recommendations(case_id: str, *, tenant_id: str = "") -> Dict[str, Any]:
    """Return recommendations with auto_execute forced false.

    Args:
        case_id: case 标识。
        tenant_id: 租户 ID。
    """
    from core.apps.diagnosis.service.engine import build_recommendations
    from core.apps.diagnosis.service.store import get_diagnosis_store

    store = get_diagnosis_store(tenant_id=tenant_id)
    case = store.get_case(case_id, tenant_id=tenant_id)
    if not case:
        raise KeyError("case_not_found")
    bundle = store.get_report_bundle(case_id, tenant_id=tenant_id)
    if not bundle:
        raise RuntimeError("case_not_ready")
    hyps = list(bundle.get("hypotheses") or [])
    recs = build_recommendations(hyps)
    for r in recs:
        r["auto_execute"] = False
    return {"case_id": case_id, "recommendations": recs, "auto_execute": False}


def diagnosis_fixture_metrics(
    *, limit: int = 10, blind: bool = True, subset: str = "core"
) -> Dict[str, Any]:
    """diagnosis_fixture_metrics。

    Args:
        limit: 返回条数上限。
        blind: blind 参数。
        subset: subset 参数。
    """
    from core.apps.diagnosis.service.metrics import fixture_metrics

    return fixture_metrics(limit=limit, blind=blind, subset=subset)


def list_code_review_gold_profiles() -> Dict[str, Any]:
    """噪声档位 → autoreview 参数映射。"""
    from core.harness.evaluation.code_review_gold import list_profiles

    return list_profiles()


def list_code_review_gold_reports(*, tenant_id: str = "", limit: int = 20) -> list:
    """黄金评测 JSONL 历史（不改 gold）。

    Args:
        tenant_id: 租户 ID。
        limit: 返回条数上限。
    """
    from core.harness.evaluation.code_review_gold import list_eval_reports

    return list_eval_reports(tenant_id=tenant_id, limit=limit)


def kb_eval_list_samples(*, limit: int = 100, offset: int = 0, tag: Optional[str] = None):
    """KB eval golden samples list (platform thin route).

    Args:
        limit: 返回条数上限。
        offset: 分页偏移。
        tag: tag 参数。
    """
    from core.apps.eval.service.kb_eval_ops import kb_eval_list_samples as _fn

    return _fn(limit=limit, offset=offset, tag=tag)


def kb_eval_create_sample(body: Dict[str, Any]):
    """kb_eval_create_sample。

    Args:
        body: 请求体。
    """
    from core.apps.eval.service.kb_eval_ops import kb_eval_create_sample as _fn

    return _fn(body)


def kb_eval_delete_sample(sample_id: str):
    """kb_eval_delete_sample。

    Args:
        sample_id: sample 标识。
    """
    from core.apps.eval.service.kb_eval_ops import kb_eval_delete_sample as _fn

    return _fn(sample_id)


async def kb_eval_run(body: Dict[str, Any]):
    """kb_eval_run。

    Args:
        body: 请求体。
    """
    from core.apps.eval.service.kb_eval_ops import kb_eval_run as _fn

    return await _fn(body)


def kb_eval_list_reports(*, limit: int = 50, offset: int = 0):
    """kb_eval_list_reports。

    Args:
        limit: 返回条数上限。
        offset: 分页偏移。
    """
    from core.apps.eval.service.kb_eval_ops import kb_eval_list_reports as _fn

    return _fn(limit=limit, offset=offset)


def kb_eval_import_csv_text(text: str):
    """kb_eval_import_csv_text。

    Args:
        text: text 参数。
    """
    from core.apps.eval.service.kb_eval_ops import kb_eval_import_csv_text as _fn

    return _fn(text)


def kb_eval_reports_series(*, days: int = 30):
    """kb_eval_reports_series。

    Args:
        days: days 参数。
    """
    from core.apps.eval.service.kb_eval_ops import kb_eval_reports_series as _fn

    return _fn(days=days)


def kb_eval_compare_reports(*, session_a: str = "", session_b: str = ""):
    """kb_eval_compare_reports。

    Args:
        session_a: session_a 参数。
        session_b: session_b 参数。
    """
    from core.apps.eval.service.kb_eval_ops import kb_eval_compare_reports as _fn

    return _fn(session_a=session_a, session_b=session_b)


async def prompt_eval_list_test_cases(
    *, template_id: str = "", limit: int = 100, offset: int = 0
):
    """prompt_eval_list_test_cases。

    Args:
        template_id: template 标识。
        limit: 返回条数上限。
        offset: 分页偏移。
    """
    from core.apps.eval.service.prompt_eval_ops import prompt_eval_list_test_cases_async as _fn

    return await _fn(template_id=template_id, limit=limit, offset=offset)


async def prompt_eval_create_test_case(
    *,
    template_id: str,
    name: str,
    variables: Any,
    expected_keys: str,
):
    """prompt_eval_create_test_case。

    Args:
        template_id: template 标识。
        name: name 参数。
        variables: variables 参数。
        expected_keys: expected_keys 参数。
    """
    from core.apps.eval.service.prompt_eval_ops import prompt_eval_create_test_case_async as _fn

    return await _fn(
        template_id=template_id,
        name=name,
        variables=variables,
        expected_keys=expected_keys,
    )


async def prompt_eval_update_test_case(
    *,
    case_id: str,
    name: Optional[str] = None,
    variables: Any = None,
    expected_keys: Optional[str] = None,
):
    """prompt_eval_update_test_case。

    Args:
        case_id: case 标识。
        name: name 参数。
        variables: variables 参数。
        expected_keys: expected_keys 参数。
    """
    from core.apps.eval.service.prompt_eval_ops import prompt_eval_update_test_case_async as _fn

    return await _fn(
        case_id=case_id,
        name=name,
        variables=variables,
        expected_keys=expected_keys,
    )


async def prompt_eval_delete_test_case(*, case_id: str):
    """prompt_eval_delete_test_case。

    Args:
        case_id: case 标识。
    """
    from core.apps.eval.service.prompt_eval_ops import prompt_eval_delete_test_case_async as _fn

    return await _fn(case_id=case_id)


async def prompt_eval_start_run(
    *,
    template_id: str,
    version_a: str,
    version_b: str,
    model: str,
    case_ids: Optional[list] = None,
):
    """prompt_eval_start_run。

    Args:
        template_id: template 标识。
        version_a: version_a 参数。
        version_b: version_b 参数。
        model: 模型名。
        case_ids: case_ids 参数。
    """
    from core.apps.eval.service.prompt_eval_ops import prompt_eval_start_run as _fn

    return await _fn(
        template_id=template_id,
        version_a=version_a,
        version_b=version_b,
        model=model,
        case_ids=case_ids,
    )


async def prompt_eval_list_runs(
    *, template_id: str = "", limit: int = 20, offset: int = 0
):
    """prompt_eval_list_runs。

    Args:
        template_id: template 标识。
        limit: 返回条数上限。
        offset: 分页偏移。
    """
    from core.apps.eval.service.prompt_eval_ops import prompt_eval_list_runs_async as _fn

    return await _fn(template_id=template_id, limit=limit, offset=offset)


async def prompt_eval_get_run(*, run_id: str):
    """prompt_eval_get_run。

    Args:
        run_id: 运行 ID。
    """
    from core.apps.eval.service.prompt_eval_ops import prompt_eval_get_run_async as _fn

    return await _fn(run_id=run_id)


# ── runs_eval ops (ARCH v1.1c thin platform) ──────────────────────────
async def runs_eval_submit(*, run_id: str, body: Dict[str, Any], actor: Dict[str, Any]):
    """runs_eval_submit。

    Args:
        run_id: 运行 ID。
        body: 请求体。
        actor: 操作者身份。
    """
    from core.apps.eval.service.runs_eval_ops import submit_run_evaluation as _fn

    return await _fn(run_id=run_id, body=body, actor=actor)


async def runs_eval_auto(*, run_id: str):
    """runs_eval_auto。

    Args:
        run_id: 运行 ID。
    """
    from core.apps.eval.service.runs_eval_ops import auto_evaluate_run as _fn

    return await _fn(run_id=run_id)


async def runs_eval_latest(*, run_id: str):
    """runs_eval_latest。

    Args:
        run_id: 运行 ID。
    """
    from core.apps.eval.service.runs_eval_ops import get_latest_run_evaluation as _fn

    return await _fn(run_id=run_id)


async def runs_eval_investigate_latest(*, run_id: str):
    """runs_eval_investigate_latest。

    Args:
        run_id: 运行 ID。
    """
    from core.apps.eval.service.runs_eval_ops import get_latest_investigate_report as _fn

    return await _fn(run_id=run_id)


async def runs_eval_investigate_auto(*, run_id: str):
    """runs_eval_investigate_auto。

    Args:
        run_id: 运行 ID。
    """
    from core.apps.eval.service.runs_eval_ops import auto_investigate_run as _fn

    return await _fn(run_id=run_id)


async def runs_eval_state_latest(*, run_id: str):
    """runs_eval_state_latest。

    Args:
        run_id: 运行 ID。
    """
    from core.apps.eval.service.runs_eval_ops import get_latest_run_state as _fn

    return await _fn(run_id=run_id)


async def runs_eval_evidence_pack_latest(*, run_id: str):
    """runs_eval_evidence_pack_latest。

    Args:
        run_id: 运行 ID。
    """
    from core.apps.eval.service.runs_eval_ops import get_latest_evidence_pack as _fn

    return await _fn(run_id=run_id)


async def runs_eval_evidence_diff(
    *,
    run_id: str,
    base_evidence_pack_id: str,
    new_evidence_pack_id: str,
):
    """runs_eval_evidence_diff。

    Args:
        run_id: 运行 ID。
        base_evidence_pack_id: base_evidence_pack 标识。
        new_evidence_pack_id: new_evidence_pack 标识。
    """
    from core.apps.eval.service.runs_eval_ops import compute_run_evidence_diff as _fn

    return await _fn(
        run_id=run_id,
        base_evidence_pack_id=base_evidence_pack_id,
        new_evidence_pack_id=new_evidence_pack_id,
    )


async def runs_eval_upsert_state(
    *,
    run_id: str,
    state: Any,
    lock: Any,
    actor: Dict[str, Any],
):
    """runs_eval_upsert_state。

    Args:
        run_id: 运行 ID。
        state: state 参数。
        lock: lock 参数。
        actor: 操作者身份。
    """
    from core.apps.eval.service.runs_eval_ops import upsert_run_state as _fn

    return await _fn(run_id=run_id, state=state, lock=lock, actor=actor)


async def runs_eval_evidence(*, run_id: str):
    """runs_eval_evidence。

    Args:
        run_id: 运行 ID。
    """
    from core.apps.eval.service.runs_eval_ops import get_run_evidence as _fn

    return await _fn(run_id=run_id)


from core.apps.eval.service.runs_eval_ops import (  # noqa: E402
    RunsEvalGateFailed as RunsEvalGateFailed,
)


async def skill_eval_upsert_suite(*, body: Dict[str, Any], actor: Dict[str, Any]):
    """skill_eval_upsert_suite。

    Args:
        body: 请求体。
        actor: 操作者身份。
    """
    from core.apps.eval.service.skill_evals_ops import upsert_skill_eval_suite as _fn

    return await _fn(body=body, actor=actor)


async def skill_eval_list_suites(
    *, limit: int = 50, offset: int = 0, tenant_id: Optional[str] = None
):
    """skill_eval_list_suites。

    Args:
        limit: 返回条数上限。
        offset: 分页偏移。
        tenant_id: 租户 ID。
    """
    from core.apps.eval.service.skill_evals_ops import list_skill_eval_suites as _fn

    return await _fn(limit=limit, offset=offset, tenant_id=tenant_id)


async def skill_eval_ensure_builtin_suites(*, tenant_id: Optional[str] = None):
    """Register builtin_trigger_demo if missing (Eval Skills empty-state).

    Args:
        tenant_id: 租户 ID。
    """
    from core.apps.eval.service.skill_evals_ops import (
        ensure_builtin_skill_eval_suites as _fn,
    )

    return await _fn(tenant_id=tenant_id)


async def skill_eval_preflight(
    *,
    tenant_id: Optional[str] = None,
    eval_kind: str = "trigger",
    mode: str = "heuristic",
):
    """Eval Skills pre-run readiness (store / builtin / skill_manager|store_direct).

    Args:
        tenant_id: 租户 ID。
        eval_kind: eval_kind 参数。
        mode: mode 参数。
    """
    from core.apps.eval.service.skill_evals_ops import skill_eval_preflight as _fn

    return await _fn(tenant_id=tenant_id, eval_kind=eval_kind, mode=mode)


async def skill_eval_get_suite(*, suite_id: str):
    """skill_eval_get_suite。

    Args:
        suite_id: suite 标识。
    """
    from core.apps.eval.service.skill_evals_ops import get_skill_eval_suite as _fn

    return await _fn(suite_id=suite_id)


async def skill_eval_delete_suite(*, suite_id: str):
    """skill_eval_delete_suite。

    Args:
        suite_id: suite 标识。
    """
    from core.apps.eval.service.skill_evals_ops import delete_skill_eval_suite as _fn

    return await _fn(suite_id=suite_id)


async def skill_eval_run_suite(
    *, suite_id: str, body: Dict[str, Any], actor: Dict[str, Any]
):
    """skill_eval_run_suite。

    Args:
        suite_id: suite 标识。
        body: 请求体。
        actor: 操作者身份。
    """
    from core.apps.eval.service.skill_evals_ops import run_skill_eval_suite as _fn

    return await _fn(suite_id=suite_id, body=body, actor=actor)


async def skill_eval_get_run(*, run_id: str):
    """skill_eval_get_run。

    Args:
        run_id: 运行 ID。
    """
    from core.apps.eval.service.skill_evals_ops import get_skill_eval_run as _fn

    return await _fn(run_id=run_id)


async def skill_eval_list_results(
    *, run_id: str, limit: int = 200, offset: int = 0
):
    """skill_eval_list_results。

    Args:
        run_id: 运行 ID。
        limit: 返回条数上限。
        offset: 分页偏移。
    """
    from core.apps.eval.service.skill_evals_ops import list_skill_eval_results as _fn

    return await _fn(run_id=run_id, limit=limit, offset=offset)


async def skill_eval_suggest(*, run_id: str, body: Dict[str, Any]):
    """skill_eval_suggest。

    Args:
        run_id: 运行 ID。
        body: 请求体。
    """
    from core.apps.eval.service.skill_evals_ops import (
        suggest_trigger_improvements as _fn,
    )

    return await _fn(run_id=run_id, body=body)


async def skill_eval_apply_suggestion(*, suite_id: str, body: Dict[str, Any]):
    """skill_eval_apply_suggestion。

    Args:
        suite_id: suite 标识。
        body: 请求体。
    """
    from core.apps.eval.service.skill_evals_ops import (
        apply_skill_eval_suggestion as _fn,
    )

    return await _fn(suite_id=suite_id, body=body)


async def skill_eval_apply_skill_md(
    *, suite_id: str, body: Dict[str, Any], actor: Dict[str, Any]
):
    """skill_eval_apply_skill_md。

    Args:
        suite_id: suite 标识。
        body: 请求体。
        actor: 操作者身份。
    """
    from core.apps.eval.service.skill_evals_ops import apply_skill_md_suggestion as _fn

    return await _fn(suite_id=suite_id, body=body, actor=actor)


async def skill_eval_compare(*, body: Dict[str, Any]):
    """skill_eval_compare。

    Args:
        body: 请求体。
    """
    from core.apps.eval.service.skill_evals_ops import compare_skill_eval_runs as _fn

    return await _fn(body=body)


async def skill_eval_create_job(
    *, suite_id: str, body: Dict[str, Any], actor: Dict[str, Any]
):
    """skill_eval_create_job。

    Args:
        suite_id: suite 标识。
        body: 请求体。
        actor: 操作者身份。
    """
    from core.apps.eval.service.skill_evals_ops import create_skill_eval_job as _fn

    return await _fn(suite_id=suite_id, body=body, actor=actor)


async def reevaluate_code_review_gold(
    *,
    profile: str = "balanced",
    gold_dir: Optional[str] = None,
    case_ids: Optional[list] = None,
    match_only: bool = False,
    limit: int = 0,
    tenant_id: str = "",
    persist: bool = True,
    record_novel: bool = False,
    baseline: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """再跑同一黄金集，并对比上一份报告的 precision/recall/p0_recall。

    Args:
        profile: 评测 profile。
        gold_dir: 黄金集目录。
        case_ids: case_ids 参数。
        match_only: match_only 参数。
        limit: 返回条数上限。
        tenant_id: 租户 ID。
        persist: persist 参数。
        record_novel: record_novel 参数。
        baseline: baseline 参数。
    """
    from core.harness.evaluation.code_review_gold import reevaluate_code_review_gold as _run

    return await _run(
        profile=profile,
        gold_dir=gold_dir,
        case_ids=case_ids,
        match_only=match_only,
        limit=limit,
        tenant_id=tenant_id,
        persist=persist,
        record_novel=record_novel,
        baseline=baseline,
    )


def summarize_task_model_routes(*, limit: int = 500) -> Dict[str, Any]:
    """Task model-route aggregates by purpose (success / upgrade / latency).

    Args:
        limit: 返回条数上限。
    """
    from core.harness.utils.task_model_lock import summarize_task_model_routes as _sum

    return _sum(limit=limit)


def evaluate_gold_profile_gate(
    *,
    profile: str = "balanced",
    risk_level: str = "high",
    tenant_id: str = "",
    force: bool = False,
) -> Dict[str, Any]:
    """同档位黄金集门禁：高风险配置变更须近期非回归 gold（ReviewBench 纪律）。

    Args:
        profile: 评测 profile。
        risk_level: risk_level 参数。
        tenant_id: 租户 ID。
        force: 是否强制。
    """
    from core.harness.evaluation.gold_profile_gate import evaluate_gold_profile_gate as _gate

    return _gate(
        profile=profile or "balanced",
        risk_level=risk_level or "low",
        tenant_id=tenant_id or "",
        force=bool(force),
    )


def get_os_sandbox_status() -> Dict[str, Any]:
    """返回 OS 原生沙箱模式诊断（P1, 对标 Codex sandboxing）。

    {mode, available, enabled, active, env, profile, fail_closed, production_tightened}——
    供诊断端点/运维面板查看 AIPLAT_SANDBOX / 生产收紧生效状态。
    """
    from core.harness.infrastructure.os_sandbox import sandbox_env_ready

    return sandbox_env_ready()


def get_subagent_discipline_status() -> Dict[str, Any]:
    """子代理浓缩回传 / 隔离纪律诊断（生产强制 isolate）。"""
    from core.harness.execution.subagent_discipline import discipline_status

    return discipline_status()


def get_document_categories() -> list:
    """Get supported document category labels (from ConverterRegistry — single source of truth)."""
    from core.harness.document.protocol import get_document_registry
    return get_document_registry().get_available_categories()


def is_crypto_configured() -> bool:
    """Check if cryptographic keys are configured."""
    import os
    return bool(os.getenv("AIPLAT_CRYPTO_KEY_ID"))


def llm_generate_stream(*args: Any, **kwargs: Any):
    """Streaming LLM generation. Delegates to sys_llm_generate_stream.

    Args:
        args: args 参数。
        kwargs: kwargs 参数。
    """
    from core.harness.syscalls.llm import sys_llm_generate_stream
    return sys_llm_generate_stream(*args, **kwargs)


def normalize_conversation_scope(scope: Any) -> Any:
    """Normalize conversation scope values to a consistent dict format.

    Args:
        scope: scope 参数。
    """
    if isinstance(scope, dict):
        return scope
    if isinstance(scope, str):
        return {"name": scope}
    return {"name": "default"}


def secret_configured(key_id: str = "") -> bool:
    """Check if a secret key is configured.

    Args:
        key_id: key 标识。
    """
    return bool(key_id)


def set_knowledge_providers(*args: Any, **kwargs: Any) -> None:
    """Set knowledge providers for the runtime. Delegates to kb_facade.

    Args:
        args: args 参数。
        kwargs: kwargs 参数。
    """
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
from core.apps.fde.service.clarify_dialog import (  # noqa: boundary — CoreFacade canonical re-export
    ClarifyTurnInput,
    run_clarify_turn,
    simple_extract_fields as clarify_simple_extract_fields,
)
from core.apps.fde.service.voice import run_voice_brainstorm  # noqa: boundary — CoreFacade canonical re-export
from core.apps.fde.service.delivery_pipeline_session import (  # noqa: boundary — CoreFacade canonical re-export
    approve_delivery_session as approve_fde_delivery_session,
    attach_builder_observation as attach_fde_delivery_builder_observation,
    evaluate_delivery_session as evaluate_fde_delivery_session,
    get_delivery_session as get_fde_delivery_session,
    link_builder_project as link_fde_delivery_builder_project,
    list_delivery_sessions as list_fde_delivery_sessions,
    load_delivery_template as load_fde_delivery_template,
    start_delivery_session as start_fde_delivery_session,
)
from core.apps.fde.service.security_preflight import (  # noqa: boundary
    get_latest_preflight as get_fde_security_preflight_latest,
    list_preflight_runs as list_fde_security_preflight_runs,
    preflight_signoff_gate as fde_preflight_signoff_gate,
    save_preflight_run as save_fde_security_preflight_run,
    summarize_security_dry_run as summarize_fde_security_dry_run,
)
from core.apps.fde.service.slice_bundle_export import (  # noqa: boundary — five-products slice
    export_slice_bundle,
)
from core.apps.fde.service.slice_evidence import (  # noqa: boundary — five-products slice
    build_slice_diagnosis_report,
    get_slice_diagnosis_report,
    ingest_slice_evidence,
    ingest_slice_evidence_from_jsonl,
    validate_slice_signoff_reports,
)
from core.apps.fde.service.slice_offline_policy import (  # noqa: boundary — five-products slice
    evaluate_slice_offline_policy,
)
from core.apps.fde.service.evolve_proposal_gate import (  # noqa: boundary
    approve_evolve_proposal as approve_fde_evolve_proposal,
    apply_evolve_proposal as apply_fde_evolve_proposal,
    enqueue_evolve_proposal as enqueue_fde_evolve_proposal,
    evaluate_evolve_proposal as evaluate_fde_evolve_proposal,
    get_evolve_applied_config as get_fde_evolve_applied_config,
    get_evolve_metrics as get_fde_evolve_metrics,
    list_evolve_applied as list_fde_evolve_applied,
    list_evolve_proposals as list_fde_evolve_proposals,
    record_evolve_observation as record_fde_evolve_observation,
    reject_evolve_proposal as reject_fde_evolve_proposal,
    rollback_evolve_proposal as rollback_fde_evolve_proposal,
    tick_evolve_observations as tick_fde_evolve_observations,
    sync_evolve_ops_signals as sync_fde_evolve_ops_signals,
)
from core.apps.fde.service.usage_signal import (  # noqa: boundary
    capture_usage_baseline as capture_fde_usage_baseline,
    get_usage_baseline as get_fde_usage_baseline,
    get_usage_signal as get_fde_usage_signal,
    get_usage_trend as get_fde_usage_trend,
)
from core.apps.fde.service.customer_success import (  # noqa: boundary
    evaluate_escort_exit_from_signals as evaluate_fde_escort_exit,
    get_escort_exit as get_fde_escort_exit,
    get_metric_handover as get_fde_metric_handover,
    list_domain_peers as list_fde_domain_peers,
    refresh_handover_from_usage as refresh_fde_metric_handover,
    save_escort_exit as save_fde_escort_exit,
    save_metric_handover as save_fde_metric_handover,
)

from core.security.skill_signature_gate import is_approval_resolved_approved, get_trusted_skill_pubkeys_map  # v2.5
from core.harness.ontology_engine.graph_index import GraphIndex  # v6.5 — canonical re-export for platform layer
# v2.10: management + services boundary re-exports
from core.management.prompt_app_manager import PromptAppManager  # noqa: boundary
from core.services.implicit_feedback import get_implicit_feedback_collector  # noqa: boundary
from core.management.skill_manager import SkillManager  # noqa: boundary
from core.management.skill_linter import lint_skill  # noqa: boundary
from core.management.skill_installer import SkillInstaller  # noqa: boundary
from core.management.agentskills_parser import convert_agentskills_to_aiplat, is_agentskills_format  # noqa: boundary


def skill_asset_compat_finalize(skill_dir: str, *, source=None, adapt_summary=None):
    """Write COMPAT.yaml for a skill dir (Phase A); never flips accuracy_claim.

    Args:
        skill_dir: skill_dir 参数。
        source: source 参数。
        adapt_summary: adapt_summary 参数。
    """
    from core.apps.skills.asset_compat import finalize_skill_compat

    return finalize_skill_compat(skill_dir, source=source, adapt_summary=adapt_summary)


def skill_enable_handler_draft(skill_dir: str):
    """Promote handler.py.draft → handler.py after human enable (Phase A).

    Args:
        skill_dir: skill_dir 参数。
    """
    from core.apps.skills.asset_compat import enable_handler_draft

    return enable_handler_draft(skill_dir)


def agent_asset_compat_finalize(agent_dir: str, *, source=None, adapt_summary=None):
    """Write COMPAT.yaml for an agent dir (Phase B); chat vs full surface honesty.

    Args:
        agent_dir: agent_dir 参数。
        source: source 参数。
        adapt_summary: adapt_summary 参数。
    """
    from core.apps.agents.asset_compat import finalize_agent_compat

    return finalize_agent_compat(agent_dir, source=source, adapt_summary=adapt_summary)


def mcp_asset_compat_finalize(mcp_dir: str, *, source=None, adapt_summary=None, connection_status=None):
    """Write COMPAT.yaml for an MCP server dir (Phase C).

    Args:
        mcp_dir: mcp_dir 参数。
        source: source 参数。
        adapt_summary: adapt_summary 参数。
        connection_status: connection_status 参数。
    """
    from core.apps.mcp.asset_compat import finalize_mcp_compat

    return finalize_mcp_compat(
        mcp_dir, source=source, adapt_summary=adapt_summary, connection_status=connection_status
    )


def tool_asset_compat_finalize(tool_py: str, *, source=None, adapt_summary=None, mapped_to=None, mcp_projection=False):
    """Write COMPAT sidecar for a tool .py path (Phase C).

    Args:
        tool_py: tool_py 参数。
        source: source 参数。
        adapt_summary: adapt_summary 参数。
        mapped_to: mapped_to 参数。
        mcp_projection: mcp_projection 参数。
    """
    from core.apps.tools.asset_compat import finalize_tool_compat

    return finalize_tool_compat(
        tool_py,
        source=source,
        adapt_summary=adapt_summary,
        mapped_to=mapped_to,
        mcp_projection=mcp_projection,
    )


def tool_enable_impl_draft(tool_py: str):
    """Promote {name}.py.draft → {name}.py after human enable (Phase C).

    Args:
        tool_py: tool_py 参数。
    """
    from core.apps.tools.asset_compat import enable_tool_impl_draft

    return enable_tool_impl_draft(tool_py)


def tool_discovery_register_with_report(tools_dir: Optional[str] = None):
    """Phase D: hot-load workspace tools with COMPAT gate + skipped assets[].

    Args:
        tools_dir: tools_dir 参数。
    """
    from pathlib import Path

    from core.apps.tools.discovery import register_with_report

    return register_with_report(Path(tools_dir) if tools_dir else None)


def tool_discovery_last_report(tools_dir: Optional[str] = None):
    """Phase D wrap: cached discovery report (or refresh once if empty).

    Args:
        tools_dir: tools_dir 参数。
    """
    from pathlib import Path

    from core.apps.tools.discovery import last_report_or_refresh

    return last_report_or_refresh(Path(tools_dir) if tools_dir else None)


# v2.6 — platform→CoreFacade canonical re-exports (eliminate direct core.harness imports)
from core.harness.ontology_engine.action_registry import get_action_registry  # noqa: boundary
from core.harness.ontology_engine.ontology_branch import OntologyBranchManager  # noqa: boundary
from core.harness.infrastructure.lineage_store import LineageStore  # noqa: boundary
from core.harness.learning.operation_recorder import OperationRecorder  # noqa: boundary
from core.harness.knowledge.scoring_engine import load_models  # noqa: boundary
from core.harness.knowledge.metric_engine import load_metrics  # noqa: boundary
from core.harness.knowledge.versioned_ontology_store import (  # noqa: boundary
    VersionedOntologyStore,
    json_change_diff,
    project_ontology_changes,
)
from core.harness.execution.team_planner import load_team_template  # noqa: boundary
from core.harness.knowledge.knowledge_roi import KnowledgeROI  # noqa: boundary
from core.harness.learning.kpi_tracker import get_kpi_tracker  # noqa: boundary
from core.harness.training.full_training import get_full_training_engine  # noqa: boundary
from core.harness.training.distillation import get_distillation_engine  # noqa: boundary
from core.harness.knowledge_pipeline.resolver import (  # noqa: boundary
    CrossDomainResolver,
    ensure_unified_customer_view,
    seed_cross_domain_config,
)
from core.harness.knowledge.convergence_engine import ConvergenceEngine  # noqa: boundary
from core.harness.execution.atomic_splitter import AtomicTaskSplitter  # noqa: boundary
from core.harness.learning.agent_network import AgentNetwork  # noqa: boundary
from core.harness.infrastructure.db_utils import get_db_connection  # noqa: boundary
from core.harness.integration import KernelRuntime  # noqa: boundary

# v2.7 — complete platform→CoreFacade canonical re-exports (all remaining harness symbols)
from core.harness.infrastructure.action_contract import ActionContractModel  # noqa: boundary
from core.harness.infrastructure.action_store import ActionStore  # noqa: boundary
from core.harness.infrastructure.workbench_runtime_guard import WorkbenchRuntimeGuard  # noqa: boundary
from core.harness.infrastructure.action_audit_validate import (  # noqa: boundary
    check_change_surface,
    load_change_surface_whitelist,
    load_audit_schema,
    classify_audit_fields,
    render_mapping_report,
)
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
from core.harness.infrastructure.gates.policy_gate import PolicyGate, PolicyDecision  # noqa: boundary
from core.harness.ontology_engine.builtin_actions import register_all  # noqa: boundary
from core.harness.knowledge.ontology_case_learning import OntologyCaseStore, _evolve_min_reward  # noqa: boundary
from core.harness.knowledge.embedder import embed_text_semantic  # noqa: boundary
from core.harness.knowledge.knowledge_ontology import export_to_owl_rdf, TIER_EDGE  # noqa: boundary
from core.harness.execution.programmatic_collector import ProgrammaticCollector  # noqa: boundary
from core.harness.infrastructure.gates.purpose_registry import PurposeRegistry  # noqa: boundary
from core.harness.execution.simulation import SimulationOrchestrator  # noqa: boundary
from core.harness.learning.skill_generator import SkillGenerator  # noqa: boundary
from core.harness.document.protocol import StreamInfo  # noqa: boundary
from core.harness.knowledge.system_evolver import SystemEvolver  # noqa: boundary
from core.harness.knowledge.system_diagnostician import SystemHealer  # noqa: boundary
from core.harness.document.template_engine import TemplateRegistry, TemplateRenderer  # noqa: boundary
from core.harness.utils.prompt_loader import _async_prompt_resolve, auto_classify, get_metadata, list_templates  # noqa: boundary
from core.harness.interfaces.agent import AgentConfig, AgentContext  # noqa: boundary
from core.harness.execution.team_planner import _enrich_stage_from_agent  # noqa: boundary
from core.harness.knowledge.governance_dashboard import aggregate_dashboard  # noqa: boundary
from core.harness.evaluation.workbench import apply_threshold_gate, persist_evaluation, validate_report  # noqa: boundary
from core.harness.evaluation.eval_protocol import (  # noqa: boundary
    SCHEMA_VERSION as EVAL_PROTOCOL_SCHEMA_VERSION,
    attach_protocol as attach_eval_protocol,
    from_generic_eval as eval_protocol_from_generic,
    from_gold_eval_result as eval_protocol_from_gold,
    from_run_evaluation as eval_protocol_from_run_evaluation,
    from_skill_eval_run as eval_protocol_from_skill_eval_run,
    to_eval_protocol_v0,
)
from core.harness.knowledge.ontology_api import (  # noqa: boundary
    SCHEMA_VERSION as ONTOLOGY_API_SCHEMA_VERSION,
    attach_ontology_api,
    from_graph_health as ontology_api_from_graph_health,
    from_structured_query as ontology_api_from_structured_query,
    from_wiki_pages as ontology_api_from_wiki_pages,
    to_ontology_api_v0,
)
from core.harness.meta.control_plane import (  # noqa: boundary
    SCHEMA_VERSION as AIPLAT_CONTROL_SCHEMA_VERSION,
    attach_control_plane,
    to_aiplat_healthz,
    to_control_plane_v0,
)
from core.harness.meta.capability_version import (  # noqa: boundary
    load_versions_ssot,
    resolve_capability_version,
)
from core.harness.learning.proposal_store import ProposalStore as _ProposalStore  # noqa: boundary

def approve(request_id: str, approved_by: str = "admin", comment: str = "") -> bool:
    """Approve a change request via ProposalStore.

    Args:
        request_id: request 标识。
        approved_by: approved_by 参数。
        comment: comment 参数。
    """
    return _ProposalStore().approve(request_id, approved_by)
from core.harness.knowledge.rule_auditor import audit_rules  # noqa: boundary
from core.harness.knowledge.capability_graph import build_capability_graph  # noqa: boundary
from core.harness.knowledge.code_graph import build_graph, clear_cache, default_roots, repo_root, PY_IMPORT_RE, JS_IMPORT_RE, strip_py_type_checking, is_code_file, should_skip, read_text, resolve_js_relative, resolve_py_module, detect_issues, convert_file_graph_to_symbols, count_cycles, health_score, blast, ScanResult  # noqa: boundary
from core.harness.knowledge.capability_health import capability_health_report  # noqa: boundary
from core.harness.knowledge.consistency_gate import check_cross_stage_consistency  # noqa: boundary
from core.harness.knowledge.domain_maturity import compare_domains, compute_domain_maturity, export_comparison_report  # noqa: boundary
from core.harness.knowledge.ontology_completeness import compute_all_ocs, compute_domain_ocs  # noqa: boundary
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
from core.harness.execution.decision_trace import (  # noqa: boundary
    record_decision,
    locate_max_error_node,
    trace_root_cause_chain,
    build_fix_plan,
    get_trace,
    clear_trace,
    build_execution_decision,
)
from core.harness.execution.factory_fix_plan import (  # noqa: boundary
    derive_failed_stages_from_report,
    plan_fix_from_report,
    build_feedback_from_report,
    apply_no_platform_handler_fixes,
    align_result_assert_needles,
    extract_media_skill_remaps_from_report,
    bugs_are_no_platform_handler_only,
    bugs_are_media_handler_fixable,
    filter_fix_plan_freeze_test_cases,
    FROZEN_TEST_CASE_ARTIFACTS,
)
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
from core.harness.knowledge.metric_engine import scorecard  # P0-B4: get_trend 别名无调用者已清理
from core.harness.infrastructure.crypto.signature import sign_skill  # noqa: boundary
from core.harness.syscalls.retrieval import sys_knowledge_retrieve  # noqa: boundary

# v2.7.1 — final multi-line import symbols
from core.harness.learning.playbook import PlaybookManifest, pack_playbook, unpack_playbook  # noqa: boundary
from core.harness.finance.value_calculator import BusinessGoal, get_value_calculator  # noqa: boundary
from core.harness.execution.simulation import ScenarioDefinition, ScenarioType  # noqa: boundary
from core.harness.knowledge_pipeline.extractor import ExtractionPipeline, ExtractionResult, PendingExtractionStore, write_extraction_to_graph_index, file_bytes_to_text  # noqa: boundary
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
    """Full voice loop: STT → Agent → Browser/Tool → TTS (manual trigger).

    Args:
        audio_path: audio_path 参数。
        llm_callback: llm_callback 参数。
    """
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


def get_observability_contract() -> dict:
    """Declared production observability stack (Prometheus + EventBus + run_graph)."""
    from core.harness.observability.contract import get_observability_contract as _get
    return _get()


def get_production_depth_report() -> dict:
    """Agent OS production-depth readiness report for diagnostics UI."""
    from core.harness.observability.production_depth import build_production_depth_report
    return build_production_depth_report()


def get_architecture_health_report() -> dict:
    """W6: Agent architecture health (policy/bypass/plan_execute/router/CRAG/autonomy)."""
    from core.harness.observability.architecture_health import build_architecture_health_report
    return build_architecture_health_report()


def agent_event_ingress_status() -> dict:
    """AgentEventIngress stats (file inbox / messaging → run_workspace_agent)."""
    from core.harness.infrastructure.agent_event_ingress import get_agent_event_ingress
    return get_agent_event_ingress().stats


async def wake_agent_start(paths: list = None) -> dict:
    """Start WakeAgent watching (zero-token checksum polling).

    Args:
        paths: paths 参数。
    """
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

    Args:
        output: output 参数。
        domain_id: domain 标识。
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

# PRD quality gate + pack loader (Builder PM path — platform MUST import via CoreFacade)
from core.harness.execution.prd_gate_loader import clear_prd_gate_pack_cache  # noqa: boundary — CoreFacade canonical re-export
from core.harness.execution.prd_gate_loader import load_prd_gate_packs  # noqa: boundary — CoreFacade canonical re-export
from core.harness.execution.prd_gate_loader import materialize_prd_gate_seeds  # noqa: boundary — CoreFacade canonical re-export
from core.harness.execution.prd_quality_gate import apply_gate_to_prd  # noqa: boundary — CoreFacade canonical re-export
from core.harness.execution.prd_quality_gate import assess_prd  # noqa: boundary — CoreFacade canonical re-export
from core.harness.execution.prd_quality_gate import enrich_prd  # noqa: boundary — CoreFacade canonical re-export
from core.harness.execution.prd_quality_gate import factory_finalize_prd  # noqa: boundary — CoreFacade canonical re-export
from core.harness.execution.prd_quality_gate import materialize_prd_artifact  # noqa: boundary — CoreFacade canonical re-export
from core.harness.execution.prd_quality_gate import set_prd_markdown_parser  # noqa: boundary — CoreFacade canonical re-export
from core.harness.execution.prd_quality_gate import seed_confirmed_prd_into_state  # noqa: boundary — CoreFacade canonical re-export
from core.harness.execution.prd_quality_gate import collect_decision_enum_catalog  # noqa: boundary — CoreFacade canonical re-export
from core.harness.execution.prd_quality_gate import followup_questions_from_report  # noqa: boundary — CoreFacade canonical re-export
from core.harness.execution.prd_quality_gate import format_decision_enum_catalog  # noqa: boundary — CoreFacade canonical re-export
from core.harness.execution.prd_quality_gate import format_pm_gate_guidance  # noqa: boundary — CoreFacade canonical re-export
from core.harness.execution.prd_quality_gate import is_media_prd  # noqa: boundary — CoreFacade canonical re-export
from core.harness.execution.prd_quality_gate import looks_like_prd  # noqa: boundary — CoreFacade canonical re-export
from core.harness.execution.app_page_skill_inject import extract_skill_routing  # noqa: boundary — CoreFacade canonical re-export
from core.harness.execution.app_page_skill_inject import extract_ui_bindings  # noqa: boundary — CoreFacade canonical re-export
from core.harness.execution.app_page_skill_inject import inject_app_page_skills  # noqa: boundary — CoreFacade canonical re-export
from core.harness.execution.app_page_skill_inject import parse_app_page_payload  # noqa: boundary — CoreFacade canonical re-export
from core.harness.execution.app_page_skill_inject import repair_frontend_pages_raw  # noqa: boundary — CoreFacade canonical re-export
from core.harness.execution.app_page_skill_inject import skill_routing_context_block  # noqa: boundary — CoreFacade canonical re-export
from core.harness.execution.factory_artifact_sanitize import apply_stage_output_sanitizers  # noqa: boundary — CoreFacade canonical re-export
from core.harness.execution.factory_artifact_sanitize import ensure_dual_component_stages  # noqa: boundary — CoreFacade canonical re-export
from core.harness.execution.factory_artifact_sanitize import ensure_dual_ingest_stages  # noqa: boundary — CoreFacade canonical re-export
from core.harness.execution.factory_artifact_sanitize import ensure_wizard_stage_io  # noqa: boundary — CoreFacade canonical re-export
from core.harness.execution.factory_artifact_sanitize import ensure_wizard_io_true_test_case  # noqa: boundary — CoreFacade canonical re-export
from core.harness.execution.factory_artifact_sanitize import ensure_result_dashboard_sections  # noqa: boundary — CoreFacade canonical re-export
from core.harness.execution.factory_artifact_sanitize import canonicalize_app_page_media_skills  # noqa: boundary — CoreFacade canonical re-export
from core.harness.execution.factory_artifact_sanitize import ensure_manifest_dual_ui_bindings  # noqa: boundary — CoreFacade canonical re-export
from core.harness.execution.factory_artifact_sanitize import ensure_manifest_ui_binding_pair  # noqa: boundary — CoreFacade canonical re-export
from core.harness.execution.factory_artifact_sanitize import ensure_result_dashboard_skill  # noqa: boundary — CoreFacade canonical re-export
from core.harness.execution.factory_artifact_sanitize import ensure_agent_app_skill_consistency  # noqa: boundary — CoreFacade canonical re-export
from core.harness.execution.factory_artifact_sanitize import ensure_platform_media_skill_contracts  # noqa: boundary — CoreFacade canonical re-export
from core.harness.execution.factory_artifact_sanitize import normalize_media_skill_names  # noqa: boundary — CoreFacade canonical re-export
from core.harness.execution.factory_artifact_sanitize import extract_real_http_routes  # noqa: boundary — CoreFacade canonical re-export
from core.harness.execution.factory_artifact_sanitize import pick_routing_blob  # noqa: boundary — CoreFacade canonical re-export
from core.harness.execution.factory_artifact_sanitize import repair_frontend_pages_with_prd  # noqa: boundary — CoreFacade canonical re-export
from core.harness.execution.factory_artifact_sanitize import resolve_architecture_mode  # noqa: boundary — CoreFacade canonical re-export
from core.harness.execution.factory_artifact_sanitize import sanitize_architecture_artifact  # noqa: boundary — CoreFacade canonical re-export
from core.harness.execution.factory_artifact_sanitize import sanitize_test_cases_artifact  # noqa: boundary — CoreFacade canonical re-export
from core.harness.execution.factory_artifact_sanitize import strip_reasoning_preamble  # noqa: boundary — CoreFacade canonical re-export
from core.harness.execution.true_test_runtime import check_file_rules  # noqa: boundary — CoreFacade canonical re-export
from core.harness.execution.true_test_runtime import check_wizard_stage_io  # noqa: boundary — CoreFacade canonical re-export
from core.harness.execution.true_test_runtime import check_result_dashboard_sections  # noqa: boundary — CoreFacade canonical re-export
from core.harness.execution.true_test_runtime import RESULT_DASHBOARD_SECTION_TYPES  # noqa: boundary — CoreFacade canonical re-export
from core.harness.execution.true_test_runtime import classify_execution  # noqa: boundary — CoreFacade canonical re-export
from core.harness.execution.true_test_runtime import is_blocked_url  # noqa: boundary — CoreFacade canonical re-export
from core.harness.execution.true_test_runtime import run_page_smoke  # noqa: boundary — CoreFacade canonical re-export
from core.harness.execution.true_test_runtime import run_platform_check  # noqa: boundary — CoreFacade canonical re-export
from core.harness.execution.true_test_runtime import run_true_test_case  # noqa: boundary — CoreFacade canonical re-export
from core.harness.media_skill_handlers import execute_media_skill  # noqa: boundary — CoreFacade canonical re-export
from core.harness.media_skill_handlers import list_platform_media_skill_names  # noqa: boundary — CoreFacade canonical re-export
from core.harness.media_skill_handlers import resolve_media_handler_name  # noqa: boundary — CoreFacade canonical re-export
from core.harness.media_skill_handlers import resolve_platform_media_skill  # noqa: boundary — CoreFacade canonical re-export
from core.harness.media_skill_handlers import suggest_platform_media_skill  # noqa: boundary — CoreFacade canonical re-export
from core.harness.execution.prd_markdown import parse_prd_markdown  # noqa: boundary — CoreFacade canonical re-export
from core.harness.execution.prd_quality_gate import matched_domain_packs  # noqa: boundary — CoreFacade canonical re-export
from core.harness.execution.prd_quality_gate import matched_packs_for_text  # noqa: boundary — CoreFacade canonical re-export
from core.harness.execution.prd_quality_gate import normalize_constraints  # noqa: boundary — CoreFacade canonical re-export
from core.harness.execution.prd_quality_gate import render_prd_markdown  # noqa: boundary — CoreFacade canonical re-export
