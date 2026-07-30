"""
aiPlat Intents — the UNIFIED intent-level API for all AI interactions.

Design principle:
  Application declares intent. Core automatically activates all
  relevant subsystems (Memory, Trace, Skills, Evaluation, ...).
  Application NEVER needs to know which subsystems exist.

Three intents cover all AI application needs:
  core_chat(...)    — agent conversation (PM, support, QA, ...)
  core_execute(...) — pipeline execution (build, test, deploy, ...)
  core_query(...)   — knowledge retrieval (search, RAG, ...)

All three are application-agnostic: they know HOW to run AI,
not WHAT the business context is. Applications interpret results
at their layer (PRD ready detection, approval logic, etc.).
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from core.harness.utils.model_injection import get_default_model


# ═══════════════════════════════════════════════════════════════
# Data types
# ═══════════════════════════════════════════════════════════════

class ChatContext:
    """Intent-level chat input. Application declares WHO to chat with
    and WHAT to say. Core activates Memory/Trace/Skills automatically."""

    def __init__(
        self,
        *,
        agent_name: str,
        session_id: str,
        user_input: str,
        user_id: str = "system",
        model: Any = None,
        metadata: Optional[Dict[str, Any]] = None,
    ):
        self.agent_name = agent_name
        self.session_id = session_id
        self.user_input = user_input
        self.user_id = user_id
        self.model = model
        self.metadata = metadata or {}


class ChatResult:
    """Structured chat output. Application interprets the reply
    at its layer (PRD ready, approval needed, etc.)."""

    def __init__(
        self,
        *,
        reply: str,
        trace_id: str = "",
        skills_used: Optional[List[str]] = None,
        memory_saved: bool = False,
        metadata: Optional[Dict[str, Any]] = None,
    ):
        self.reply = reply
        self.trace_id = trace_id
        self.skills_used = skills_used or []
        self.memory_saved = memory_saved
        self.metadata = metadata or {}


class ExecuteContext:
    """Intent-level pipeline execution input. Application declares
    WHAT to run. Core activates Evaluation/Trace/Feedback automatically."""

    def __init__(
        self,
        *,
        stages: List[Any],
        input_data: Dict[str, Any] = None,
        model: Any = None,
        metadata: Optional[Dict[str, Any]] = None,
    ):
        self.stages = stages
        self.input_data = input_data or {}
        self.model = model
        self.metadata = metadata or {}


class ExecuteResult:
    """Structured pipeline execution output."""

    def __init__(
        self,
        *,
        success: bool,
        output: Dict[str, Any] = None,
        trace_id: str = "",
        metadata: Optional[Dict[str, Any]] = None,
    ):
        self.success = success
        self.output = output or {}
        self.trace_id = trace_id
        self.metadata = metadata or {}


class QueryContext:
    """Intent-level knowledge query input."""

    def __init__(
        self,
        *,
        query_text: str,
        session_id: str = "",
        scope: Optional[Dict[str, Any]] = None,
        model: Any = None,
        metadata: Optional[Dict[str, Any]] = None,
    ):
        self.query_text = query_text
        self.session_id = session_id
        self.scope = scope or {}
        self.model = model
        self.metadata = metadata or {}


class QueryResult:
    """Structured knowledge query output."""

    def __init__(
        self,
        *,
        answer: str,
        citations: Optional[List[Dict[str, Any]]] = None,
        trace_id: str = "",
        metadata: Optional[Dict[str, Any]] = None,
    ):
        self.answer = answer
        self.citations = citations or []
        self.trace_id = trace_id
        self.metadata = metadata or {}


# ═══════════════════════════════════════════════════════════════
# Intent implementations — application-agnostic, auto-activate subsystems
# ═══════════════════════════════════════════════════════════════

async def core_chat(ctx: ChatContext) -> ChatResult:
    """Execute a conversational agent turn.

    Application declares intent (agent_name + session_id + user_input).
    Core automatically activates:

    1. AgentRegistry → discovers agent config and system prompt
    2. MemoryManager → persists conversation (survives restart)
    3. SkillRegistry → binds matching Skills from AGENT.md
    4. Trace → generates trace_id for end-to-end observability

    Application interprets the reply at its layer (PRD ready? approval?).
    Core does NOT know what PRD, approval, or requirements mean.
    """
    import time
    import uuid as _uuid

    from core.api.core_facade import (
        create_agent, get_agent_frontmatter, get_default_model,
    )
    from core.api.facades.skill_tool_facade import get_skill_registry

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
        import logging
        logging.getLogger("core.intents").warning(
            "AGENT.md not found or empty for agent '%s'. Using bare-minimum fallback prompt. "
            "Agent behavior will be unpredictable. "
            "Create AGENT.md at ~/.aiplat/agents/%s/AGENT.md with SOP instructions.",
            ctx.agent_name, ctx.agent_name,
        )
        from core.harness.utils.prompt_loader import _async_prompt_resolve
        system_prompt = await _async_prompt_resolve("agent-fallback", agent_name=str(ctx.agent_name))

    # ── 2. MemoryManager: load conversation history ──
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
        required = frontmatter.get("required_skills") if frontmatter else None
        if required:
            skills_used = [s for s in required if isinstance(s, str)]
        elif not system_prompt.strip():
            pass
    except Exception as e:
        logging.debug(str(e), exc_info=True)

    # Auto-select skill subset via intent classification (v2.4)
    if skills_used and frontmatter.get("auto_select_skills", True):
        try:
            from core.harness.routing.classifier import classify
            from core.schemas_routing import RoutingContext as _Rctx
            _rctx = _Rctx(
                user_message=ctx.user_input or "",
                agent_id=ctx.agent_name,
                agent_name=ctx.agent_name,
                available_skills=list(skills_used),
            )
            _routing = classify(_rctx)
            if _routing.confidence >= 0.80 and _routing.auto_filter_skill_ids:
                auto_skills = _routing.auto_filter_skill_ids
                if auto_skills and len(auto_skills) < len(skills_used):
                    skills_used = auto_skills
                    logging.info("auto_skill_select", extra={
                        "agent": ctx.agent_name, "intent": _routing.intent.value,
                        "confidence": round(_routing.confidence, 2),
                        "selected_skills": skills_used,
                    })
        except Exception:
            logging.getLogger(__name__).debug('Auto-select failure, not breaking execution', exc_info=True)

    # ── 4. Create and execute agent ──
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
    # Skills passed via context.skills — BaseAgent.execute() resolves from registry
    agent_ctx = AgentContext(
        session_id=ctx.session_id,
        user_id=ctx.user_id,
        messages=message_history,
        skills=list(skills_used),
    )
    result = await agent.execute(agent_ctx)

    reply = ""
    if result.success:
        if isinstance(result.output, dict):
            reply = result.output.get("content", "") or str(result.output)
        else:
            reply = str(result.output) if result.output else ""
    else:
        error_detail = result.error or "Unknown error (agent execution failed)"
        if hasattr(result, 'metadata') and isinstance(result.metadata, dict):
            extra = result.metadata.get("error_detail") or result.metadata
        else:
            extra = ""
        reply = f"Agent error: {error_detail}{' — ' + str(extra) if extra else ''}"

    # ── 5. MemoryManager: save interaction ──
    try:
        from core.harness.memory.manager import get_memory_manager as _get_mem2
        mgr = _get_mem2()
        await mgr.save_interaction(
            user_input=ctx.user_input, agent_output=reply,
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
        metadata=ctx.metadata,
    )


async def core_execute(ctx: ExecuteContext) -> ExecuteResult:
    """Execute a pipeline with automatic subsystem activation.

    Application declares intent (stages + input). Core automatically activates:
    1. PipelineEngine → runs stages through ReAct loop
    2. Evaluation → auto-evaluates each stage output
    3. Trace → full pipeline trace_id
    4. Feedback → records execution feedback for future optimization
    5. Governance → creates changeset audit trail

    Application interprets the output (artifacts, pass rates, etc.).
    """
    import uuid as _uuid

    from core.api.core_facade import create_pipeline_session, validate_pipeline_stages
    from core.schemas_builder import BuilderSessionPhase, PipelineConfig

    trace_id = f"exec_{_uuid.uuid4().hex[:12]}"

    max_tokens = 100000
    max_retry = 3
    config = PipelineConfig(
        stages=ctx.stages,
        max_tokens_per_run=max_tokens,
        max_retry_attempts=max_retry,
    )
    diagnostics = validate_pipeline_stages(config.stages)

    session = create_pipeline_session(config=config, model=ctx.model)
    state = await session.start(
        project_id=ctx.metadata.get("project_id", trace_id),
        requirement=ctx.input_data.get("requirement", ""),
        prd_data=ctx.input_data.get("prd"),
    )

    return ExecuteResult(
        success=bool(state.get("phase") != BuilderSessionPhase.failed.value),
        output=state,
        trace_id=trace_id,
        metadata={
            "diagnostics": diagnostics,
            "stages": len(ctx.stages),
        },
    )


async def core_query(ctx: QueryContext) -> QueryResult:
    """Execute a knowledge retrieval query.

    Application declares intent (query_text + scope). Core automatically activates:
    1. RAG Agent → retrieves relevant documents
    2. MemoryManager → includes conversation context
    3. SkillRegistry → binds kb_query/doc_query skills
    4. Trace → generates trace_id

    Application interprets the results (citations, relevance, etc.).
    """
    import uuid as _uuid
    from core.api.core_facade import create_agent
    from core.api.facades.skill_tool_facade import get_skill_registry

    trace_id = f"query_{_uuid.uuid4().hex[:12]}"
    model = ctx.model or get_default_model()

    from core.harness.utils.prompt_loader import _async_prompt_resolve
    agent = create_agent(
        agent_type="conversational",
        config={"name": "kb_query", "temperature": 0.3, "timeout": 300},
        model=model,
        system_prompt=await _async_prompt_resolve("kb-retrieval-assistant"),
    )

    skill_reg = get_skill_registry()
    for skill_name in ("kb_query", "doc_query"):
        try:
            if skill_reg.get(skill_name) and hasattr(agent, "add_skill"):
                agent.add_skill(skill_name)
        except Exception as e:
            logging.debug(str(e), exc_info=True)

    from core.harness.interfaces.agent import AgentContext
    messages: List[Dict[str, str]] = [{"role": "user", "content": ctx.query_text}]
    result = await agent.execute(AgentContext(
        session_id=ctx.session_id or trace_id,
        user_id="system",
        messages=messages,
    ))

    answer = ""
    if result.success:
        answer = str(result.output) if result.output else ""
    else:
        answer = f"Query error: {result.error}"

    return QueryResult(
        answer=answer,
        trace_id=trace_id,
        metadata=ctx.metadata,
    )
