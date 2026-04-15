"""
Plan-Execute Agent Module

Provides Plan-Execute agent implementation.
"""

from typing import Any, Dict, List, Optional
from dataclasses import dataclass, field

from .base import BaseAgent, AgentMetadata
from ...harness.interfaces import (
    AgentConfig,
    AgentContext,
    AgentResult,
    AgentStatus,
    LoopState,
)
from ...adapters.llm import ILLMAdapter


@dataclass
class PlanStep:
    """Plan step"""
    id: int
    description: str
    status: str = "pending"  # pending, executing, completed, failed
    result: Any = None


@dataclass
class PlanExecuteAgentConfig:
    """Plan-Execute agent configuration"""
    max_planning_steps: int = 5
    max_execution_steps: int = 10
    enable_replanning: bool = True
    replan_on_error: bool = True


class PlanExecuteAgent(BaseAgent):
    """
    Plan-Execute Agent
    
    Implements two-phase execution:
    - Planning: Analyze task and create execution plan
    - Execution: Execute plan step by step
    """

    def __init__(
        self,
        config: AgentConfig,
        model: Optional[ILLMAdapter] = None,
        tools: Optional[List[Any]] = None,
        agent_config: Optional[PlanExecuteAgentConfig] = None,
        **kwargs
    ):
        self._pe_config = agent_config or PlanExecuteAgentConfig()
        self._tools = tools or []
        self._plan: List[PlanStep] = []
        
        super().__init__(
            config=config,
            model=model,
            loop_type="plan_execute",
            **kwargs
        )
        
        self._metadata = AgentMetadata(
            name="PlanExecuteAgent",
            description="Plan then execute agent",
            version="1.0.0",
            capabilities=["planning", "execution", "replanning"],
            supported_loop_types=["plan_execute"]
        )

    async def execute(self, context: AgentContext) -> AgentResult:
        """Execute Plan-Execute agent via Harness loop delegation.
        
        Delegates to BaseAgent.execute() which runs the PlanExecuteLoop,
        with model injected before execution.
        """
        if self._loop and hasattr(self._loop, 'set_model') and self._model:
            self._loop.set_model(self._model)
        
        return await super().execute(context)

    async def _plan_task(self, context: AgentContext) -> List[PlanStep]:
        """Create execution plan"""
        if not self._model:
            return []
        
        # Build planning prompt
        task = context.messages[-1].get("content", "") if context.messages else ""
        
        tools_desc = "\n".join([
            f"- {getattr(t, 'name', str(t))}"
            for t in self._tools
        ]) if self._tools else "No tools available"
        
        prompt = f"""Task: {task}

Available tools:
{tools_desc}

Create a step-by-step plan to complete this task.
Respond with a numbered list, one step per line.
Example:
1. First step
2. Second step
3. Final step
"""
        
        response = await self._model.generate([
            {"role": "user", "content": prompt}
        ])
        
        # Parse plan
        plan = []
        lines = response.content.strip().split("\n")
        
        for i, line in enumerate(lines):
            line = line.strip()
            # Remove numbering like "1." or "1)"
            if line and (line[0].isdigit() or (len(line) > 1 and line[1].isdigit())):
                # Find the actual description
                parts = line.split(".", 1)
                if len(parts) > 1:
                    description = parts[1].strip()
                else:
                    description = line
                
                if description:
                    plan.append(PlanStep(
                        id=i + 1,
                        description=description
                    ))
        
        return plan

    async def _execute_plan(self, context: AgentContext) -> List[Any]:
        """Execute the plan"""
        results = []
        
        for step in self._plan:
            if step.status == "completed":
                continue
            
            step.status = "executing"
            
            try:
                # Execute step
                result = await self._execute_step(step, context)
                step.result = result
                step.status = "completed"
                results.append(result)
                
                # Check if should continue
                if self._should_stop(step):
                    break
                    
            except Exception as e:
                step.status = "failed"
                results.append({"error": str(e)})
                
                # Replan if enabled
                if self._pe_config.replan_on_error and self._pe_config.enable_replanning:
                    await self._replan(step, context)
        
        return results

    async def _execute_step(self, step: PlanStep, context: AgentContext) -> Any:
        """Execute a single plan step"""
        # Find relevant tool
        tool = self._find_tool(step.description)
        
        if tool:
            result = await tool.execute({})
            return result.output if hasattr(result, 'output') else result
        
        # No tool, use model
        if self._model:
            prompt = f"Execute this step: {step.description}\nContext: {context.variables}"
            response = await self._model.generate([
                {"role": "user", "content": prompt}
            ])
            return response.content
        
        return f"Step: {step.description}"

    def _find_tool(self, step_description: str) -> Optional[Any]:
        """Find appropriate tool for step"""
        step_lower = step_description.lower()
        
        for tool in self._tools:
            tool_name = getattr(tool, 'name', '').lower()
            if tool_name in step_lower:
                return tool
        
        return None

    def _should_stop(self, step: PlanStep) -> bool:
        """Check if should stop execution"""
        # Check if step indicates completion
        done_indicators = ["final", "complete", "done", "finish", "result", "answer"]
        step_lower = step.description.lower()
        
        return any(indicator in step_lower for indicator in done_indicators)

    async def _replan(self, failed_step: PlanStep, context: AgentContext) -> None:
        """Replan after error"""
        if not self._model:
            return
        
        # Create new plan from current state
        remaining = [s for s in self._plan if s.status != "completed"]
        
        prompt = f"""Previous step failed: {failed_step.description}
Error: {failed_step.result}

Remaining steps: {[s.description for s in remaining]}

Create a revised plan to complete the task.
"""
        
        response = await self._model.generate([
            {"role": "user", "content": prompt}
        ])
        
        # Update plan (simplified)
        # In production, would properly merge plans

    def _combine_results(self, results: List[Any]) -> str:
        """Combine execution results"""
        combined = []
        
        for i, result in enumerate(results):
            if isinstance(result, dict) and "error" in result:
                combined.append(f"Step {i+1}: Error - {result['error']}")
            else:
                combined.append(f"Step {i+1}: {result}")
        
        return "\n".join(combined)

    def get_plan(self) -> List[PlanStep]:
        """Get current plan"""
        return self._plan


def create_plan_execute_agent(
    config: AgentConfig,
    model: Optional[ILLMAdapter] = None,
    tools: Optional[List[Any]] = None,
    **kwargs
) -> PlanExecuteAgent:
    """Create Plan-Execute agent"""
    return PlanExecuteAgent(config=config, model=model, tools=tools, **kwargs)