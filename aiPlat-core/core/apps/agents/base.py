import logging
"""
Agent Base Module

Provides base Agent class implementing IAgent interface.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from ...harness.interfaces import (
    IAgent,
    AgentConfig,
    AgentContext,
    AgentResult,
    AgentStatus,
    LoopConfig,
)
from ...harness.execution import create_loop
# Avoid importing adapters.llm package (it is a large public surface area).
# Import the minimal symbols directly to reduce coupling and avoid cycles.
from ...adapters.llm.base import ILLMAdapter, LLMConfig


@dataclass
class AgentMetadata:
    """Agent metadata"""
    name: str
    description: str = ""
    version: str = "1.0.0"
    capabilities: List[str] = field(default_factory=list)
    supported_loop_types: List[str] = field(default_factory=list)


class BaseAgent(IAgent):
    """
    Base Agent Implementation
    
    Provides common functionality for all agent implementations.
    """

    def __init__(
        self,
        config: AgentConfig,
        model: Optional[ILLMAdapter] = None,
        loop_type: str = "react",
        loop_config: Optional[LoopConfig] = None
    ):
        self._config = config
        self._model = model
        self._status = AgentStatus.IDLE
        self._loop = None
        self._current_context: Optional[AgentContext] = None
        
        # Initialize execution loop
        self._loop = create_loop(
            loop_type=loop_type,
            config=loop_config or LoopConfig()
        )
        self._skills: List[Any] = []
        self._tools: List[Any] = []

    async def initialize(self, config: AgentConfig) -> None:
        """Initialize agent with configuration"""
        self._config = config
        self._status = AgentStatus.INITIALIZING
        
        # Initialize model via infra ModelManager (central resolution)
        if not self._model and config.model:
            try:
                from core.harness.utils.model_injection import create_selected_adapter
                self._model = create_selected_adapter(model_name=config.model)
            except Exception as e:
                logging.debug(str(e), exc_info=True)
        self._status = AgentStatus.READY


    async def execute(self, context: AgentContext) -> AgentResult:
        """Execute agent with given context"""
        self._status = AgentStatus.RUNNING
        self._current_context = context

        # ── Semantic Gateway pre-intercept: unified validation for all agent interactions ──
        try:
            from core.harness.infrastructure.semantic_gateway import route, GatewayRequest
            agent_task = str(getattr(context, 'task', '') or
                           (getattr(context, 'messages', [{}]) or [{}])[-1].get('content', '') or
                           getattr(context, 'user_input', ''))
            if agent_task:
                req = GatewayRequest(
                    action="agent_execute",
                    payload={"task": agent_task[:500]},
                    context={"session_id": getattr(context, 'session_id', ''),
                             "agent_type": type(self).__name__},
                )
                routing = await route(req)
                if not routing.allowed:
                    return AgentResult(
                        success=False,
                        output=f"Agent execution blocked by Semantic Gateway: {routing.reason}",
                        metadata={"blocked": True, "gateway": "semantic_gateway"},
                    )
        except ImportError:
            pass  # noqa: optional-dependency

        try:
            # Prepare initial state
            from ...harness.interfaces import LoopState, LoopStateEnum

            resume_snapshot = None
            try:
                if isinstance(context.variables, dict):
                    resume_snapshot = context.variables.get("_resume_loop_state")
            except Exception:
                resume_snapshot = None

            if isinstance(resume_snapshot, dict):
                # Resume from a paused loop state snapshot (Phase 3.5).
                try:
                    cur = str(resume_snapshot.get("current", "paused"))
                    current_enum = LoopStateEnum(cur) if cur in [e.value for e in LoopStateEnum] else LoopStateEnum.PAUSED
                except Exception:
                    current_enum = LoopStateEnum.PAUSED

                state = LoopState(
                    current=current_enum,
                    step_count=int(resume_snapshot.get("step_count", 0) or 0),
                    used_tokens=int(resume_snapshot.get("used_tokens", 0) or 0),
                    max_tokens=int(resume_snapshot.get("max_tokens", 8192) or 8192),
                    budget_remaining=float(resume_snapshot.get("budget_remaining", 1.0) or 1.0),
                    context=resume_snapshot.get("context") or {},
                    history=resume_snapshot.get("history") or [],
                    metadata=resume_snapshot.get("metadata") or {},
                )
                # Switch to "resume" mode: skip reasoning once and re-run act.
                state.current = LoopStateEnum.ACTING
                state.metadata = dict(state.metadata or {})
                state.metadata.pop("pause_requested", None)
                state.metadata["resume_skip_reason"] = True
            else:
                state = LoopState(
                    context={
                        "task": context.messages[-1].get("content", "") if context.messages else "",
                        "session_id": context.session_id,
                        "user_id": context.user_id,
                        "_agent_namespace": context.session_id or "default",
                        **context.variables
                    },
                    step_count=0
                )
            
            # Inject model, skills, and tools into the loop before running
            resolved_tools = []
            resolved_skills = []
            if self._loop:
                if hasattr(self._loop, 'set_model') and self._model:
                    self._loop.set_model(self._model)
                if hasattr(self._loop, 'set_tools') and hasattr(self, '_tools'):
                    from ...apps.tools.base import get_tool_registry
                    tool_registry = get_tool_registry()
                    for tool_name in context.tools if context.tools else []:
                        tool = tool_registry.get(tool_name)
                        if tool:
                            resolved_tools.append(tool)
                    if hasattr(self, '_tools') and self._tools:
                        resolved_tools.extend(self._tools)
                    self._loop.set_tools(resolved_tools)
                if hasattr(self._loop, 'set_skills') and hasattr(self, '_skills'):
                    from ...apps.skills import get_skill_registry
                    skill_registry = get_skill_registry()
                    for skill_name in context.skills if context.skills else []:
                        skill = skill_registry.get(skill_name)
                        if skill:
                            resolved_skills.append(skill)
                    if hasattr(self, '_skills') and self._skills:
                        resolved_skills.extend(self._skills)
                    self._loop.set_skills(resolved_skills)

                # Fast path: agents with no tools AND no skills use direct syscall
                # (avoids ReAct loop iterating max_steps with nothing to act on)
                # Must still go through sys_llm_generate for injection guard + trace gate.
                if not resolved_tools and not resolved_skills and hasattr(self, '_model') and self._model:
                    from ...harness.syscalls.llm import sys_llm_generate
                    messages = []
                    conv_cfg = getattr(self, '_conv_config', None)
                    if conv_cfg and getattr(conv_cfg, 'system_prompt', ''):
                        messages.append({"role": "system", "content": conv_cfg.system_prompt})
                    elif context.variables.get("system_prompt"):
                        messages.append({"role": "system", "content": str(context.variables["system_prompt"])})
                    
                    # ── Memory injection: load working/episodic/semantic context ──
                    sid = getattr(context, 'session_id', None) or None
                    try:
                        from ...harness.memory.manager import get_memory_manager
                        mgr = get_memory_manager()
                        mem_ctx = await mgr.build_context(
                            current_query=context.messages[-1].get("content", "") if context.messages else "",
                            system_prompt=messages[0]["content"] if messages else "",
                            session_id=sid,
                        )
                        if mem_ctx:
                            existing = getattr(mem_ctx, 'messages', None) or []
                            if isinstance(existing, list):
                                messages = list(existing) + messages
                    except Exception:
                        logging.getLogger(__name__).debug("swallowing non-critical exception", exc_info=True)
                    
                    messages.extend(list(context.messages) if context.messages else [])
                    if not messages:
                        messages = [{"role": "user", "content": str(context.variables.get("task", ""))}]
                    try:
                        response = await sys_llm_generate(
                            self._model, messages,
                            session_id=getattr(context, 'session_id', None) or None)
                        output = getattr(response, 'content', str(response))
                        self._status = AgentStatus.COMPLETED
                        return AgentResult(success=True, output=output, metadata={
                            "loop_type": "direct_syscall", "steps": 0, "loop_state": "completed",
                        })
                    except Exception as e:
                        self._status = AgentStatus.ERROR
                        return AgentResult(success=False, output=None, error=str(e), metadata={
                            "loop_type": "direct_syscall", "steps": 0, "loop_state": "error",
                            "exception": type(e).__name__,
                        })

                result = await self._loop.run(state, self._loop._config if hasattr(self._loop, '_config') else LoopConfig())

                # Include a minimal loop checkpoint snapshot when paused (for resume).
                loop_snapshot = None
                if result.final_state and getattr(result.final_state, "current", None) and result.final_state.current.value == "paused":
                    try:
                        from dataclasses import asdict
                        loop_snapshot = asdict(result.final_state)
                        # normalize enum
                        try:
                            loop_snapshot["current"] = result.final_state.current.value
                        except Exception as e:
                            logging.debug(str(e), exc_info=True)
                    except Exception:
                        loop_snapshot = None
                
                return AgentResult(
                    success=result.success,
                    output=result.output,
                    error=result.error,
                    metadata={
                        "steps": result.final_state.step_count if result.final_state else 0,
                        "loop_type": type(self._loop).__name__,
                        "loop_state": result.final_state.current.value if result.final_state else None,
                        "stop_reason": (result.metadata or {}).get("stop_reason"),
                        # Approval / policy info (if paused by sys_tool)
                        "approval": (result.final_state.context or {}).get("approval") if result.final_state else None,
                        "policy": (result.final_state.context or {}).get("policy") if result.final_state else None,
                        "loop_state_snapshot": loop_snapshot,
                    },
                    token_usage={"total": result.final_state.used_tokens if result.final_state else 0}
                )
            else:
                return AgentResult(
                    success=False,
                    error="No execution loop initialized"
                )
                
        except Exception as e:
            self._status = AgentStatus.ERROR
            return AgentResult(
                success=False,
                error=str(e),
                metadata={"exception": type(e).__name__}
            )
        finally:
            if self._status != AgentStatus.ERROR:
                self._status = AgentStatus.COMPLETED

    async def cleanup(self) -> None:
        """Cleanup resources"""
        self._status = AgentStatus.IDLE
        self._current_context = None
        
        if self._loop:
            await self._loop.reset()

    def get_status(self) -> AgentStatus:
        """Get current agent status"""
        return self._status

    async def pause(self) -> None:
        """Pause agent execution"""
        if self._status == AgentStatus.RUNNING:
            self._status = AgentStatus.PAUSED

    async def resume(self) -> AgentContext:
        """Resume agent execution"""
        self._status = AgentStatus.RUNNING
        return self._current_context

    def get_config(self) -> AgentConfig:
        """Get agent configuration"""
        return self._config

    def get_model(self) -> Optional[ILLMAdapter]:  # noqa: agent-model — per-agent model, distinct from model_injection
        """Get model adapter"""
        return self._model

    def add_skill(self, skill: Any) -> None:
        """Add skill to agent. Every agent subclass gets this for free."""
        self._skills.append(skill)

    def add_tool(self, tool: Any) -> None:
        """Add tool to agent. Every agent subclass gets this for free."""
        self._tools.append(tool)


class ConfigurableAgent(BaseAgent):
    """
    Configurable Agent
    
    Agent that can be configured at runtime.
    """

    def __init__(
        self,
        config: AgentConfig,
        model: Optional[ILLMAdapter] = None,
        tools: Optional[List[Any]] = None,
        skills: Optional[List[Any]] = None,
        **kwargs
    ):
        super().__init__(config, model, **kwargs)
        self._tools = tools or []
        self._skills = skills or []

    def add_tool(self, tool: Any) -> None:
        """Add tool to agent"""
        self._tools.append(tool)

    def remove_tool(self, tool_name: str) -> None:
        """Remove tool from agent"""
        self._tools = [t for t in self._tools if getattr(t, 'name', '') != tool_name]

    def add_skill(self, skill: Any) -> None:
        """Add skill to agent"""
        self._skills.append(skill)

    def get_tools(self) -> List[Any]:
        """Get agent tools"""
        return self._tools

    def get_skills(self) -> List[Any]:
        """Get agent skills"""
        return self._skills


def create_agent(
    agent_type: str = "base",
    config: Optional[AgentConfig] = None,
    **kwargs
) -> IAgent:
    """
    Factory function to create agent.
    
    Agent types are defined in ~/.aiplat/registry/agent_types.yaml (single source of truth).
    """
    from core.harness.registry.registry_loader import load_agent_types

    types = load_agent_types()
    resolved_type = types.resolve(agent_type)

    # Lazy import to avoid circular dependencies between agent modules.
    import importlib
    ReActAgent = importlib.import_module(f"{__package__}.react").ReActAgent
    PlanExecuteAgent = importlib.import_module(f"{__package__}.plan_execute").PlanExecuteAgent
    ConversationalAgent = importlib.import_module(f"{__package__}.conversational").ConversationalAgent
    MultiAgent = importlib.import_module(f"{__package__}.multi_agent").MultiAgent
    MaterialsChatAgent = importlib.import_module(f"{__package__}.materials_chat").MaterialsChatAgent
    OperatorAgent = importlib.import_module(f"{__package__}.operator_agent").OperatorAgent
    
    if config is None:
        config = AgentConfig(name="default")

    # ── 编排策略自动升级 ──
    # 如果 AGENT.md frontmatter 中声明了 orchestration.mode，
    # 自动将 agent_type 升级为 multi_agent，无需手动改类型。
    frontmatter = kwargs.pop("frontmatter", None) or config.frontmatter if hasattr(config, 'frontmatter') else None
    orchestration = (frontmatter or {}).get("orchestration", {})
    if isinstance(orchestration, dict) and orchestration.get("mode"):
        mode = orchestration["mode"]
        if mode in ("supervisor", "fan_out_fan_in", "expert_pool", "pipeline",
                     "hierarchical_delegation", "producer_reviewer",
                     "parallel", "sequential"):
            resolved_type = "multi_agent"
            kwargs["coordination_pattern"] = mode
            kwargs["sub_agents"] = orchestration.get("workers", [])

    if resolved_type == "react":
        agent = ReActAgent(config=config, **kwargs)
        if agent_type == "tool":
            agent._loop_type = "tool"
        return agent
    elif resolved_type == "plan_execute":
        agent = PlanExecuteAgent(config=config, **kwargs)
        if agent_type == "reflection":
            agent._loop_type = "reflection"
        return agent
    elif resolved_type == "conversational":
        return ConversationalAgent(config=config, **kwargs)
    elif resolved_type == "multi_agent":
        return MultiAgent(config=config, **kwargs)
    elif resolved_type == "rag":
        RAGAgent = importlib.import_module(f"{__package__}.rag").RAGAgent
        return RAGAgent(config=config, **kwargs)
    elif resolved_type == "materials_chat":
        # v4.0: AGENT.md stages-aware routing
        # If stages[] are defined (in registry metadata), run via PipelineCompiler
        # Otherwise fall back to hand-crafted Python class (backward compat)
        try:
            from .discovery import get_agent_registry
            reg = get_agent_registry()
            meta = reg.get_metadata("materials_chat")
            if meta and meta.stages:
                from .pipeline_compiler import PipelineCompiler
                from .pipeline_agent import PipelineAgent
                compiled = PipelineCompiler.compile(meta.stages)
                return PipelineAgent(config=config, stages=compiled, **kwargs)
        except Exception as e:
            logging.debug(str(e), exc_info=True)
        return MaterialsChatAgent(config=config, **kwargs)
    elif resolved_type == "operator":
        return OperatorAgent(config=config, **kwargs)
    else:
        return BaseAgent(config=config, **kwargs)

