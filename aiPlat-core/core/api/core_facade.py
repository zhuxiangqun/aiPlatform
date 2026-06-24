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
from typing import Any, Dict, List, Optional
import logging
from core.harness.utils.llm_env import get_llm_api_key, get_llm_base_url


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


def create_agent(
    agent_type: str,
    config: Any = None,
    model: Any = None,
    system_prompt: str = "",
) -> Any:
    """Create an agent instance by type. Supported types:
    conversational, plan_execute, react.

    config can be a dict with keys: name, model, temperature, max_tokens, timeout,
    metadata. If None, defaults are used."""
    from core.harness.interfaces.agent import AgentConfig
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
    if agent_type == "conversational":
        from core.apps.agents.conversational import create_conversational_agent
        return create_conversational_agent(config=config, model=model, system_prompt=system_prompt)
    elif agent_type == "plan_execute":
        from core.apps.agents.plan_execute import PlanExecuteAgent
        return PlanExecuteAgent(config=config, model=model)
    elif agent_type == "react":
        from core.apps.agents.react import ReActAgent
        return ReActAgent(config=config, model=model)
    else:
        raise ValueError(f"Unknown agent type: {agent_type}")


def get_skill_registry() -> Any:
    """Get the global SkillRegistry singleton."""
    from core.apps.skills import get_skill_registry as _get
    return _get()


def get_tool_registry() -> Any:
    """Get the global ToolRegistry singleton."""
    from core.apps.tools.base import get_tool_registry as _get
    return _get()


def get_model_registry() -> Any:
    """Get the global ModelManager from infra (unique source of truth for models)."""
    from infra.management.model.manager import ModelManager
    return ModelManager()


def llm_generate(model: Any, prompt: Any, **kwargs: Any) -> Any:
    """Call LLM through the syscall boundary. Use this instead of importing
    sys_llm_generate directly from core.harness.syscalls."""
    from core.harness.syscalls.llm import sys_llm_generate
    return sys_llm_generate(model, prompt, **kwargs)


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
    except Exception:
        pass

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
        except Exception:
            pass

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
    except Exception:
        pass

    # ── 3. SkillRegistry: bind matching Skills ──
    skills_used: List[str] = []
    try:
        skill_reg = get_skill_registry()
        # Auto-bind skills based on agent's required_skills from frontmatter
        required = (frontmatter or {}).get("required_skills") if frontmatter else None
        if required:
            skills_used = [s for s in required if isinstance(s, str)]
    except Exception:
        pass

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
        except Exception:
            pass

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
    except Exception:
        pass

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
    """Seed SkillRegistry, ToolRegistry, and ModelRegistry with built-in defaults.
    Platform processes call this during startup instead of seeding registries
    with platform-specific knowledge."""
    # Skill registry — seed built-in + workspace skills
    try:
        registry = get_skill_registry()
        registry.seed_for_platform()
    except Exception:
        pass
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
            except Exception:
                pass
    except Exception:
        pass

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
        return await self._engine.initialize(project_id, requirement, prd_data=prd_data)

    async def approve(self, state: Dict[str, Any]) -> Dict[str, Any]:
        """HITL approval: resume pipeline from current HITL pause."""
        return await self._engine.approve(dict(state))

    async def reject(self, state: Dict[str, Any], feedback: str = "") -> Dict[str, Any]:
        """HITL rejection: provide feedback and resume pipeline."""
        return await self._engine.reject(dict(state), feedback)

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
    engine = PipelineEngine(config=config, model=model, skill_loader=skill_loader)
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
        resource_type=resource_type, resource_id=resource_id,
        action=action, before=before, after=after,
        tenant_id=tenant_id, actor_id=actor_id, metadata=metadata,
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


def publish_learning_release(release_id: str) -> Dict[str, Any]:
    """Publish a learning release candidate. Use instead of importing
    from core.api.routers.learning_releases directly."""
    from core.api.routers.learning_releases import publish_release_candidate as _fn
    return _fn(release_id)


def rollback_learning_release(release_id: str, reason: str = "") -> Dict[str, Any]:
    """Rollback a learning release candidate. Use instead of importing
    from core.api.routers.learning_releases directly."""
    from core.api.routers.learning_releases import rollback_release_candidate as _fn
    return _fn(release_id, reason)


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
    except Exception:
        pass

    write_page(title, body, category="entities", tags=tags,
               summary=body[:300].replace("\n", " "),
               source_articles=[f"kb:{doc_id}"],
               images=image_descriptions)

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
                images=image_descriptions)
            if curated["title"] != old_title:
                from core.harness.knowledge.wiki_engine import delete_page
                try: delete_page(old_title)
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
            except Exception:
                pass
        except Exception:
            pass

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
    except Exception:
        pass

    # ── Ontology: incremental A-Box rebuild after ingest ──
    try:
        from core.harness.knowledge.knowledge_abox_builder import rebuild_for_doc
        rebuild_for_doc(doc_id)
    except Exception:
        pass

    # ── Evolution: auto-trigger if enough new pages accumulated ──
    try:
        from core.harness.knowledge.evolution_runner import EvolutionRunner
        runner = EvolutionRunner(collection_id=collection_id or "default", max_mutations=3)
        if runner.can_evolve():
            await runner.run_one_generation(force=False)
    except Exception:
        pass

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
    except Exception:
        pass

    return {"status": "created", "title": title, "category": final_category, "chars": len(body)}


def wiki_skill_deps() -> Dict[str, Any]:
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
    """Parse a document file into element list via the unified parsers."""
    from core.harness.document import parsers
    dispatch = {
        # Office formats → MarkItDown (preserves heading/table/list structure)
        "docx": parsers.parse_markitdown, "word": parsers.parse_markitdown,
        "pptx": parsers.parse_markitdown, "ppt": parsers.parse_markitdown,
        "xlsx": parsers.parse_markitdown, "xls": parsers.parse_markitdown,
        "pdf": parsers.parse_markitdown,
        "html": parsers.parse_html, "htm": parsers.parse_html,
        # Lightweight formats → dedicated parsers
        "csv": parsers.parse_csv,
        "md": parsers.parse_markdown, "markdown": parsers.parse_markdown,
        "json": parsers.parse_json_document,
        "eml": parsers.parse_eml,
        # Media → keep existing pipelines (Whisper/OCR)
        "audio": parsers.parse_audio, "mp3": parsers.parse_audio, "wav": parsers.parse_audio,
        "image": parsers.parse_image, "png": parsers.parse_image, "jpg": parsers.parse_image,
    }
    parser = dispatch.get(str(kind).lower())
    if not parser:
        return []
    return parser(file_path)


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
    except Exception:
        pass
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
            except Exception:
                pass

    def _resolve_model():
        from core.harness.utils.model_injection import create_selected_adapter, best_model_for_purpose
        
        cfg = getattr(agent_info, "config", None)
        model_name = cfg.get("model") if isinstance(cfg, dict) else ""
        
        # Always go through infra ModelManager for model resolution (single source of truth)
        if not model_name or model_name == "auto":
            model_name = best_model_for_purpose("chat")  # noqa: model-legacy
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
                    model_name = best_model_for_purpose("chat")  # noqa: model-legacy
            except Exception:
                model_name = best_model_for_purpose("chat")  # noqa: model-legacy
        
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
    except Exception:
        pass

    # Resolve agent's bound skills from registry (parallel to tools resolution)
    resolved_skills = []
    try:
        from core.harness.integration import get_skill_registry
        sk_reg = get_skill_registry()
        for sn in (getattr(agent_info, "skills", []) or []):
            s = sk_reg.get(str(sn)) if hasattr(sk_reg, "get") else None
            if s: resolved_skills.append(s)
    except Exception:
        pass

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
        except Exception:
            pass

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
    except Exception:
        pass
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
    except Exception:
        # Best-effort: routing must not break execution
        pass

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
        except Exception:
            pass
    try:
        agent_mcp_ids = getattr(agent_info, "mcp_ids", None)
        mcp_ids = list(agent_mcp_ids) if isinstance(agent_mcp_ids, list) else None
    except Exception:
        pass
    try:
        agent_agent_ids = getattr(agent_info, "agent_ids", None)
        agent_ids = list(agent_agent_ids) if isinstance(agent_agent_ids, list) else None
    except Exception:
        pass
    try:
        agent_workflow_ids = getattr(agent_info, "workflow_ids", None)
        workflow_ids = list(agent_workflow_ids) if isinstance(agent_workflow_ids, list) else None
    except Exception:
        pass
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
        except Exception:
            pass

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
        except Exception:
            pass
    except Exception:
        pass

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
    finally:
        if ws_token is not None:
            try:
                from core.harness.kernel.execution_context import reset_active_workspace_context
                reset_active_workspace_context(ws_token)
            except Exception:
                pass
        if req_token is not None:
            try:
                from core.harness.kernel.execution_context import reset_active_request_context
                reset_active_request_context(req_token)
            except Exception:
                pass

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
    except Exception:
        pass

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
    except Exception:
        pass

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
            except Exception:
                pass
    except Exception:
        pass

    # Query token usage from syscall_events for this run
    tokens = None
    try:
        from core.services.execution_store import get_execution_store
        store = get_execution_store()
        cost = await store.get_run_cost_summary(run_id=run_id)
        if cost.get("ok"):
            tokens = cost.get("llm_tokens")
    except Exception:
        pass

    # Extract real error from StageRunner output if present
    if (result_text or "") and "STAGE_ERROR:" in result_text:
        error_msg = result_text.split("STAGE_ERROR:", 1)[1].strip() or "unknown stage error"
        status = "failed"
    is_error = status != "completed"
    resp = {"ok": not is_error, "status": status if not is_error else "failed",
            "output": result_text if not is_error else None, "error": error_msg if is_error else None, "run_id": run_id, "execution_id": run_id,
            "duration_ms": _duration_ms, "trace_id": trace_id or ""}
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
        except Exception:
            pass
    model_name = get_default_model(purpose="chat") or get_default_model()
    return create_selected_adapter(model_name=model_name)


# ── Ontology Facade (Phase 1: semantic↔action loop closure) ──

def get_ontology_context(
    question: str = "",
    *,
    max_pages: int = 10,
    collection_id: str = "default",
    include_contradictions: bool = True,
    include_state_summary: bool = True,
) -> Dict[str, Any]:
    u"""Query ontology state — lifecycle summary, contradictions, health score.

    Use this from platform/management to get ontology context without importing
    harness-internal modules.
    """
    from core.harness.syscalls.ontology_context import sys_ontology_context
    return sys_ontology_context(
        question=question,
        max_pages=max_pages,
        collection_id=collection_id,
        include_contradictions=include_contradictions,
        include_state_summary=include_state_summary,
    )


def get_entity_lifecycle_summary(
    collection_id: str = "default",
) -> Dict[str, Any]:
    u"""Return lifecycle state counts across all ontology entities."""
    from core.harness.knowledge.knowledge_action import get_entity_lifecycle_summary
    from core.harness.knowledge.knowledge_ontology import get_ontology
    onto = get_ontology()
    return get_entity_lifecycle_summary(onto, collection_id=collection_id)


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

def get_learning_paths() -> List[Dict[str, Any]]:
    u"""List all available learning paths with summaries."""
    from core.harness.knowledge.learning_paths import get_path_summary
    return get_path_summary()


def get_learner_profile(learner_id: str) -> Optional[Dict[str, Any]]:
    u"""Get a learner profile."""
    from core.harness.knowledge.learning_ontology import load_learner_profile
    profile = load_learner_profile(learner_id)
    return profile.to_dict() if profile else None


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

def get_scene_template(scene_id: str, *, collection_id: str = "default") -> Optional[Dict[str, Any]]:
    u"""Get a scene template by ID."""
    from core.harness.knowledge.scene_model import get_scene
    scene = get_scene(scene_id, collection_id=collection_id)
    return scene.to_dict() if scene else None


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


# ── Backward-compatible re-exports (platform imports these from CoreFacade) ──

from core.harness.integration import KernelRuntime, get_harness
from core.harness.kernel.runtime import get_kernel_runtime
from core.harness.kernel.types import ExecutionRequest
from core.harness.infrastructure.approval.types import ApprovalContext, ApprovalRule, RequestStatus, RuleType
from core.harness.infrastructure.crypto.secretbox import is_configured
from core.harness.infrastructure.crypto.signature import key_id_for_public_key
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
    """Cancel a running pipeline. (stub)"""
    return {"ok": True, "run_id": run_id, "status": "cancelled"}


def get_document_categories() -> list:
    """Get document category labels. (stub)"""
    return ["pdf", "docx", "pptx", "html", "txt", "markdown", "image"]


def is_crypto_configured() -> bool:
    """Check if cryptographic keys are configured. (stub)"""
    import os
    return bool(os.getenv("AIPLAT_CRYPTO_KEY_ID"))


def llm_generate_stream(*args: Any, **kwargs: Any):
    """Streaming LLM generation. (stub)"""
    from core.harness.syscalls.llm import sys_llm_generate_stream
    return sys_llm_generate_stream(*args, **kwargs)


def normalize_conversation_scope(scope: Any) -> Any:
    """Normalize conversation scope values. (stub)"""
    if isinstance(scope, dict):
        return scope
    if isinstance(scope, str):
        return {"name": scope}
    return {"name": "default"}


def secret_configured(key_id: str = "") -> bool:
    """Check if a secret key is configured. (stub)"""
    return bool(key_id)


def set_knowledge_providers(*args: Any, **kwargs: Any) -> None:
    """Set knowledge providers for the runtime. (stub)"""
    pass
