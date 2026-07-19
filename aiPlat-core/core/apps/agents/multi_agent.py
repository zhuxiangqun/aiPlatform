"""
Multi-Agent Module

Provides multi-agent coordination implementation.
Delegates to Harness coordination patterns for execution.
"""

from typing import Any, Dict, List, Optional
from dataclasses import dataclass, field

from .base import BaseAgent, AgentMetadata, ConfigurableAgent
from ...harness.interfaces import (
    AgentConfig,
    AgentContext,
    AgentResult,
    AgentStatus,
    CoordinationConfig,
    CoordinationResult,
)
from ...harness.execution.langgraph import create_multi_agent_graph
from ...harness.coordination.patterns import (
    PipelinePattern,
    FanOutFanInPattern,
    ExpertPoolPattern,
    ProducerReviewerPattern,
    SupervisorPattern,
    HierarchicalDelegationPattern,
    CoordinationContext,
    CoordinationResult as PatternResult,
)
from ...adapters.llm import ILLMAdapter


@dataclass
class MultiAgentConfig:
    """Multi-agent configuration"""
    num_agents: int = 3
    coordination_pattern: str = "parallel"  # parallel, sequential, pipeline, fan_out_fan_in, expert_pool, producer_reviewer, supervisor, hierarchical_delegation
    convergence_threshold: float = 0.8
    max_rounds: int = 5
    allow_specialization: bool = True


@dataclass
class AgentSpec:
    """Agent specification"""
    name: str
    role: str
    system_prompt: str = ""
    tools: List[Any] = field(default_factory=list)


class MultiAgent(ConfigurableAgent):
    """
    Multi-Agent Coordinator
    
    Coordinates multiple agents to collaborate on tasks.
    Uses Harness coordination patterns for execution.
    """

    def __init__(
        self,
        config: AgentConfig,
        model: Optional[ILLMAdapter] = None,
        agent_specs: Optional[List[AgentSpec]] = None,
        multi_config: Optional[MultiAgentConfig] = None,
        **kwargs
    ):
        self._multi_config = multi_config or MultiAgentConfig()
        self._agent_specs = agent_specs or []
        self._sub_agents: List[BaseAgent] = []
        self._pattern = None
        
        super().__init__(config=config, model=model, **kwargs)
        
        self._metadata = AgentMetadata(
            name="MultiAgent",
            description="Multi-agent coordination system",
            version="1.0.0",
            capabilities=["coordination", "collaboration", "parallel_execution"],
            supported_loop_types=[]
        )
        
        # Create sub-agents
        self._create_sub_agents()

    def _create_sub_agents(self) -> None:
        """Create sub-agents based on specs"""
        for spec in self._agent_specs:
            agent_config = AgentConfig(
                name=spec.name,
                model=self._config.model,
                temperature=self._config.temperature,
                metadata={"role": spec.role, "system_prompt": spec.system_prompt}
            )
            
            from .conversational import create_conversational_agent
            
            agent = create_conversational_agent(
                config=agent_config,
                model=self._model,
                system_prompt=spec.system_prompt
            )
            
            for tool in spec.tools:
                agent.add_tool(tool)
            
            self._sub_agents.append(agent)
        
        # Create coordination pattern
        self._pattern = self._create_pattern()

    def _create_pattern(self):
        """Create coordination pattern based on config"""
        pattern_type = self._multi_config.coordination_pattern
        pattern_map = {
            "parallel": FanOutFanInPattern,
            "sequential": PipelinePattern,
            "pipeline": PipelinePattern,
            "hierarchical": SupervisorPattern,
            "fan_out_fan_in": FanOutFanInPattern,
            "expert_pool": ExpertPoolPattern,
            "producer_reviewer": ProducerReviewerPattern,
            "supervisor": SupervisorPattern,
            "hierarchical_delegation": HierarchicalDelegationPattern,
        }
        
        pattern_cls = pattern_map.get(pattern_type, FanOutFanInPattern)
        pattern = pattern_cls()
        
        if pattern_type == "supervisor" and self._sub_agents:
            pattern.set_supervisor(self._sub_agents[0])
            for worker in self._sub_agents[1:]:
                pattern.add_worker(worker)
        
        return pattern

    def _build_task_context(self, parent_state, task: str, required_tools: list = None, required_skills: list = None):
        u"""Build lightweight task-only context — strips parent memory/compression/system-injections."""
        return {
            "task": task,
            "messages": [{"role": "user", "content": task}],
            "tools": [t for t in (parent_state.get("tools") or []) if not required_tools or t in required_tools],
            "skills": [s for s in (parent_state.get("skills") or []) if not required_skills or s in required_skills],
            "variables": {},
            # Deliberately EXCLUDED: working_memory, episodic_memory, semantic_memory, compressed_context, claude_md, system_prompt
        }

    async def execute(self, context: AgentContext) -> AgentResult:
        """Execute multi-agent coordination using Harness patterns.

        Uses coordination patterns (Pipeline/FanOut/ExpertPool) with
        AgentMessageBus for inter-agent communication (TASK_ASSIGN/RESULT/ERROR).
        """
        self._status = AgentStatus.RUNNING
        
        try:
            # Build coordination context
            task = context.messages[-1].get("content", "") if context.messages else ""
            if not task:
                task = context.variables.get("task", "")
            
            # If we have sub-agents and a pattern, use it
            if self._sub_agents and self._pattern:
                # Build wrapper agents that work with the pattern interface
                class _PatternAgentAdapter:
                    def __init__(self, agent, ctx, msg_bus=None, outer=None):
                        self._agent = agent
                        self._ctx = ctx
                        self._bus = msg_bus
                        self._outer = outer
                    
                    async def execute(self, task_input):
                        task_ctx = self._outer._build_task_context(
                            {"tools": self._ctx.tools, "skills": self._ctx.skills},
                            str(task_input)
                        ) if self._outer else {
                            "messages": [{"role": "user", "content": str(task_input)}],
                            "variables": self._ctx.variables.copy(),
                            "tools": self._ctx.tools,
                            "skills": self._ctx.skills,
                        }
                        agent_ctx = AgentContext(
                            session_id=self._ctx.session_id,
                            user_id=self._ctx.user_id,
                            messages=task_ctx["messages"],
                            variables=task_ctx.get("variables", {}),
                            tools=task_ctx.get("tools", self._ctx.tools),
                            skills=task_ctx.get("skills", self._ctx.skills),
                        )
                        # AgentMessage protocol: send TASK_ASSIGN before execution
                        agent_id = getattr(self._agent, '_agent_id', 'unknown')
                        if self._bus:
                            import uuid
                            from core.harness.interfaces.messaging import AgentMessage, AgentMessageType
                            msg = AgentMessage(
                                msg_id=str(uuid.uuid4())[:8],
                                type=AgentMessageType.TASK_ASSIGN,
                                sender_id="coordinator",
                                receiver_id=agent_id,
                                payload={"task": str(task_input)[:500]},
                            )
                            self._bus.send(msg)
                        result = await self._agent.execute(agent_ctx)
                        if self._bus:
                            msg_type = AgentMessageType.RESULT if getattr(result, 'success', False) else AgentMessageType.ERROR
                            self._bus.send(AgentMessage(
                                msg_id=str(uuid.uuid4())[:8],
                                type=msg_type,
                                sender_id=agent_id,
                                receiver_id="coordinator",
                                payload={"output": str(getattr(result, 'output', ''))[:1000], "success": getattr(result, 'success', False)},
                            ))
                        return result
                
                from core.harness.interfaces.messaging import get_message_bus
                msg_bus = get_message_bus()
                adapters = [_PatternAgentAdapter(a, context, msg_bus, self) for a in self._sub_agents]
                
                coord_ctx = CoordinationContext(
                    task=task,
                    agents=adapters,
                    state=context.variables.copy(),
                    metadata={"pattern": self._multi_config.coordination_pattern}
                )
                
                result = await self._pattern.coordinate(coord_ctx)
                
                # Convert CoordinationResult to AgentResult
                output = "\n\n".join([
                    str(o) for o in result.outputs
                ]) if result.outputs else "No output"
                
                if result.errors and not result.outputs:
                    output = f"Errors: {'; '.join(result.errors)}"
                
                return AgentResult(
                    success=result.success,
                    output=output,
                    metadata={
                        "pattern": self._multi_config.coordination_pattern,
                        "total_agents": len(self._sub_agents),
                        "errors": result.errors,
                        "messages": [m.to_dict() for m in msg_bus._sent],
                        **result.metadata
                    }
                )
            
            # Always use Coordination Patterns for execution.
            # If no pattern was created, create one now from the coordination config.
            if not self._pattern:
                from core.harness.coordination.patterns import create_pattern
                pattern_map = {
                    "parallel": "fanout",
                    "sequential": "pipeline",
                    "pipeline": "pipeline",
                    "hierarchical": "supervisor",
                    "supervisor": "supervisor",
                    "coordinated": "fanout",
                }
                pattern_type = pattern_map.get(
                    self._multi_config.coordination_pattern, "fanout"
                )
                self._pattern = create_pattern(pattern_type)

            if self._multi_config.coordination_pattern == "coordinated":
                result = await self._execute_coordinated(context)
            else:
                from core.harness.coordination.patterns import CoordinationContext as PatContext, CoordinationResult as PatResult
                pat_context = PatContext(
                    task=context.messages[-1].get("content", "") if context.messages else "",
                    agents=[self._create_adapter(a, context)[0] for a in self._sub_agents],
                    state=context.variables,
                    metadata={"coordination_pattern": self._multi_config.coordination_pattern},
                )
                result = await self._pattern.coordinate(pat_context)
                if isinstance(result, PatResult):
                    result = AgentResult(
                        success=result.success,
                        output="\n".join(str(o) for o in (result.outputs or [])),
                        error="\n".join(result.errors) if result.errors else None,
                        metadata=result.metadata,
                    )
                else:
                    result = AgentResult(success=True, output=str(result))
            
            return result
            
        except Exception as e:
            self._status = AgentStatus.ERROR
            return AgentResult(
                success=False,
                error=str(e),
                metadata={"exception": type(e).__name__}
            )

    def _create_adapter(self, agent: BaseAgent, context: AgentContext, msg_bus: Any = None):
        """Create a PatternAgentAdapter with optional message bus for observability."""
        from core.harness.interfaces.messaging import get_message_bus
        bus = msg_bus or get_message_bus()

        class _Adapter:
            def __init__(self, a, ctx, b, outer=None):
                self._agent = a
                self._ctx = ctx
                self._bus = b
                self._outer = outer

            async def execute(self, task_input):
                task_ctx = self._outer._build_task_context(
                    {"tools": self._ctx.tools, "skills": self._ctx.skills},
                    str(task_input)
                ) if self._outer else {
                    "messages": [{"role": "user", "content": str(task_input)}],
                    "variables": self._ctx.variables.copy(),
                    "tools": self._ctx.tools,
                    "skills": self._ctx.skills,
                }
                agent_ctx = AgentContext(
                    session_id=self._ctx.session_id,
                    user_id=self._ctx.user_id,
                    messages=task_ctx["messages"],
                    variables=task_ctx.get("variables", {}),
                    tools=task_ctx.get("tools", self._ctx.tools),
                    skills=task_ctx.get("skills", self._ctx.skills),
                )
                import uuid
                from core.harness.interfaces.messaging import AgentMessage, AgentMessageType
                aid = getattr(self._agent, '_agent_id', 'unknown')
                self._bus.send(AgentMessage(
                    msg_id=str(uuid.uuid4())[:8],
                    type=AgentMessageType.TASK_ASSIGN,
                    sender_id="coordinator",
                    receiver_id=aid,
                    payload={"task": str(task_input)[:500]},
                ))
                result = await self._agent.execute(agent_ctx)
                msg_type = AgentMessageType.RESULT if getattr(result, 'success', False) else AgentMessageType.ERROR
                self._bus.send(AgentMessage(
                    msg_id=str(uuid.uuid4())[:8],
                    type=msg_type,
                    sender_id=aid,
                    receiver_id="coordinator",
                    payload={"output": str(getattr(result, 'output', ''))[:1000], "success": getattr(result, 'success', False)},
                ))
                return result

        return _Adapter(agent, context, bus, self), bus

    async def _execute_coordinated(self, context: AgentContext) -> AgentResult:
        """Delegate to SubagentCoordinator (P1-3 wiring)."""
        try:
            from core.apps.agents.subagent.coordinator import get_subagent_coordinator
            coordinator = get_subagent_coordinator()
            task = context.messages[-1].get("content", "") if context.messages else ""
            if not task:
                task = context.variables.get("task", "")
            subagent_names = [getattr(a, '_name', '') or getattr(getattr(a, '_config', None), 'name', '') or '' for a in self._sub_agents if a]
            result = await coordinator.execute_coordinated(
                task=task,
                subagent_names=subagent_names,
                context=context.variables.get("previous_results", []) if hasattr(context, 'variables') else None,
            )
            return AgentResult(
                success=True, output=result,
                metadata={"pattern": "coordinated", "coordinator": "SubagentCoordinator"})
        except Exception:
            return AgentResult(success=False, output="", error="SubagentCoordinator unavailable",
                metadata={"pattern": "coordinated", "error": "SubagentCoordinator not reachable"})

    def add_sub_agent(self, agent: BaseAgent) -> None:
        """Add a sub-agent"""
        self._sub_agents.append(agent)
        self._pattern = self._create_pattern()

    def remove_sub_agent(self, agent_name: str) -> None:
        """Remove a sub-agent"""
        self._sub_agents = [
            a for a in self._sub_agents
            if a.get_config().name != agent_name
        ]
        self._pattern = self._create_pattern()

    def get_sub_agents(self) -> List[BaseAgent]:
        """Get all sub-agents"""
        return self._sub_agents

    @staticmethod
    def summarize_subagent_result(result: AgentResult) -> str:
        """Condense subagent output to a ~1-2K token summary (avoids context bloat)."""
        if not result.success:
            return f"Subagent failed: {str(result.error or 'unknown')[:200]}"
        output = result.output
        if isinstance(output, str):
            return output[:1000]
        if isinstance(output, dict):
            parts = []
            if "answer" in output:
                parts.append(str(output["answer"])[:800])
            if output.get("sources"):
                parts.append(f"Sources: {len(output['sources'])} files")
            if output.get("errors"):
                parts.append(f"Errors: {len(output['errors'])}")
            return "\n".join(parts) if parts else "Subagent completed successfully"
        return "Subagent completed"


class SwarmAgent(MultiAgent):
    """
    Swarm Agent
    
    Specializes in dynamic, emergent coordination.
    """

    def __init__(self, config: AgentConfig, **kwargs):
        super().__init__(config=config, **kwargs)
        
        self._metadata = AgentMetadata(
            name="SwarmAgent",
            description="Swarm coordination system",
            version="1.0.0",
            capabilities=["emergent_behavior", "self_organization", "dynamic_coordination"],
            supported_loop_types=[]
        )


def create_multi_agent(
    config: AgentConfig,
    agent_specs: Optional[List[AgentSpec]] = None,
    num_agents: int = 3,
    **kwargs
) -> MultiAgent:
    """Create multi-agent system"""
    if not agent_specs:
        agent_specs = [
            AgentSpec(name=f"agent_{i}", role="worker", system_prompt=f"You are agent {i}.")
            for i in range(num_agents)
        ]
    
    multi_config = MultiAgentConfig(num_agents=num_agents)
    return MultiAgent(config=config, agent_specs=agent_specs, multi_config=multi_config, **kwargs)
