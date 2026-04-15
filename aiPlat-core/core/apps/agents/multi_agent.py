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
    ICoordinator,
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
    CoordinationContext,
    CoordinationResult as PatternResult,
)
from ...adapters.llm import ILLMAdapter


@dataclass
class MultiAgentConfig:
    """Multi-agent configuration"""
    num_agents: int = 3
    coordination_pattern: str = "parallel"  # parallel, sequential, hierarchical, pipeline, expert_pool, producer_reviewer, supervisor
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
        }
        
        pattern_cls = pattern_map.get(pattern_type, FanOutFanInPattern)
        pattern = pattern_cls()
        
        if pattern_type == "supervisor" and self._sub_agents:
            pattern.set_supervisor(self._sub_agents[0])
            for worker in self._sub_agents[1:]:
                pattern.add_worker(worker)
        
        return pattern

    async def execute(self, context: AgentContext) -> AgentResult:
        """Execute multi-agent coordination using Harness patterns"""
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
                    def __init__(self, agent, ctx):
                        self._agent = agent
                        self._ctx = ctx
                    
                    async def execute(self, task_input):
                        agent_ctx = AgentContext(
                            session_id=self._ctx.session_id,
                            user_id=self._ctx.user_id,
                            messages=[{"role": "user", "content": str(task_input)}],
                            variables=self._ctx.variables.copy(),
                            tools=self._ctx.tools,
                            skills=self._ctx.skills,
                        )
                        result = await self._agent.execute(agent_ctx)
                        return result
                
                adapters = [_PatternAgentAdapter(a, context) for a in self._sub_agents]
                
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
                        **result.metadata
                    }
                )
            
            # Fallback: use built-in execution if no pattern
            if self._multi_config.coordination_pattern == "parallel":
                result = await self._execute_parallel(context)
            elif self._multi_config.coordination_pattern in ("sequential", "pipeline"):
                result = await self._execute_sequential(context)
            elif self._multi_config.coordination_pattern in ("hierarchical", "supervisor"):
                result = await self._execute_hierarchical(context)
            else:
                result = await self._execute_parallel(context)
            
            return result
            
        except Exception as e:
            self._status = AgentStatus.ERROR
            return AgentResult(
                success=False,
                error=str(e),
                metadata={"exception": type(e).__name__}
            )

    async def _execute_parallel(self, context: AgentContext) -> AgentResult:
        """Fallback parallel execution"""
        import asyncio
        tasks = []
        for agent in self._sub_agents:
            agent_context = AgentContext(
                session_id=context.session_id,
                user_id=context.user_id,
                messages=context.messages.copy(),
                variables=context.variables.copy(),
                tools=[t.name for t in self._tools if hasattr(t, 'name')],
            )
            tasks.append(agent.execute(agent_context))
        
        results = await asyncio.gather(*tasks, return_exceptions=True)
        successful = [r for r in results if isinstance(r, AgentResult) and r.success]
        
        combined_output = "\n\n".join([
            f"Agent {i+1}: {r.output if hasattr(r, 'output') else str(r)}"
            for i, r in enumerate(results)
        ])
        
        return AgentResult(
            success=len(successful) > 0,
            output=combined_output,
            metadata={"total_agents": len(self._sub_agents), "successful": len(successful), "pattern": "parallel"}
        )

    async def _execute_sequential(self, context: AgentContext) -> AgentResult:
        """Fallback sequential execution"""
        results = []
        for i, agent in enumerate(self._sub_agents):
            if i > 0:
                context.variables["previous_results"] = results[-1]
            result = await agent.execute(context)
            results.append(result)
            if not result.success:
                break
        
        combined_output = "\n".join([
            f"Step {i+1}: {r.output if hasattr(r, 'output') else str(r)}"
            for i, r in enumerate(results)
        ])
        
        return AgentResult(
            success=all(r.success for r in results),
            output=combined_output,
            metadata={"total_steps": len(results), "pattern": "sequential"}
        )

    async def _execute_hierarchical(self, context: AgentContext) -> AgentResult:
        """Fallback hierarchical execution"""
        import asyncio
        
        if not self._sub_agents:
            return AgentResult(success=False, error="No sub-agents")
        
        coordinator = self._sub_agents[0]
        workers = self._sub_agents[1:]
        
        coord_result = await coordinator.execute(context)
        if not coord_result.success:
            return coord_result
        
        worker_context = AgentContext(
            session_id=context.session_id,
            user_id=context.user_id,
            messages=[{"role": "user", "content": coord_result.output}],
            variables=context.variables.copy(),
        )
        
        tasks = [agent.execute(worker_context) for agent in workers]
        worker_results = await asyncio.gather(*tasks, return_exceptions=True)
        
        final_result = "\n".join([
            f"Worker {i+1}: {r.output if hasattr(r, 'output') else str(r)}"
            for i, r in enumerate(worker_results)
        ])
        
        return AgentResult(
            success=True,
            output=final_result,
            metadata={"coordinator": coordinator.get_config().name, "workers": len(workers), "pattern": "hierarchical"}
        )

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