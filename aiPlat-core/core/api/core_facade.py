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
            model=config.get("model", "gpt-4"),
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
    """Get the global ModelRegistry singleton."""
    from core.harness.infrastructure.model_registry import get_model_registry as _get
    return _get()


def llm_generate(model: Any, prompt: Any, **kwargs: Any) -> Any:
    """Call LLM through the syscall boundary. Use this instead of importing
    sys_llm_generate directly from core.harness.syscalls."""
    from core.harness.syscalls.llm import sys_llm_generate
    return sys_llm_generate(model, prompt, **kwargs)


async def chat_conversation(
    model: Any,
    system_prompt: str,
    messages: List[Dict[str, str]],
    user_instruction: str = "",
    name: str = "chat_agent",
) -> str:
    """DEPRECATED: Use intents.core_chat() instead.
    Redirects to the intent-level API for backward compatibility."""
    from core.api.intents import core_chat, ChatContext as ICtx

    ctx = ICtx(
        agent_name=name,
        session_id="legacy_chat",
        user_input=user_instruction or (messages[-1].get("content", "") if messages else ""),
        model=model,
        metadata={"system_prompt": system_prompt, "legacy_caller": True},
    )
    result = await core_chat(ctx)
    return result.reply


# ═══════════════════════════════════════════════════════════════
# core_chat() — intent-level agent conversation entry.
# Automatically activates Memory, Trace, AgentRegistry, Skills.
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


def extract_json(text: str) -> str:
    """Extract JSON substring from text (handles markdown code blocks and
    raw curly-brace regions). Use instead of duplicating extraction logic
    in platform."""
    from core.harness.execution.pipeline_engine import PipelineEngine
    return PipelineEngine._extract_json(text)


def extract_json_safe(text: str) -> Optional[str]:
    """Extract JSON substring with bracket-balanced truncation handling.
    Unlike extract_json, this finds the first balanced {…} or […] block,
    making it safe for LLM outputs where JSON may be followed by commentary.
    """
    import re
    if not text:
        return None
    # 1. Try ```json fence
    m = re.search(r'```(?:json)?\s*([\s\S]*?)\s*```', text, re.IGNORECASE)
    candidate = m.group(1).strip() if m else text
    # 2. Find first { or [ at outermost level
    def _balanced(src: str, open_ch: str, close_ch: str) -> Optional[str]:
        i = src.find(open_ch)
        if i < 0:
            return None
        depth, in_str, esc = 0, False, False
        for j in range(i, len(src)):
            ch = src[j]
            if in_str:
                if esc: esc = False
                elif ch == '\\': esc = True
                elif ch == '"': in_str = False
            else:
                if ch == '"': in_str = True
                elif ch == open_ch: depth += 1
                elif ch == close_ch:
                    depth -= 1
                    if depth == 0:
                        return src[i:j + 1]
        return None
    return _balanced(candidate, '{', '}') or _balanced(candidate, '[', ']')


def parse_json(raw: str) -> Optional[Dict[str, Any]]:
    """Extract and parse JSON from LLM output. Returns parsed dict or None."""
    import json
    json_str = extract_json_safe(raw or "")
    if json_str:
        try:
            return json.loads(json_str)
        except json.JSONDecodeError:
            pass
    return None


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
    # Model registry — seed default models
    try:
        import os
        from core.harness.infrastructure.model_registry import ModelEntry
        reg = get_model_registry()
        if not reg.list_models():
            reg.register(ModelEntry(
                name="deepseek-chat", provider="deepseek",
                api_key_env="DEEPSEEK_API_KEY",
                description="DeepSeek Chat model (default)",
            ))
            if get_llm_api_key("openai"):
                reg.register(ModelEntry(
                    name="gpt-4o", provider="openai",
                    api_key_env="OPENAI_API_KEY",
                    description="GPT-4o model (code generation)",
                ))
    except Exception:
        pass


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
    return _fn(plugin_id, action, params or {})
