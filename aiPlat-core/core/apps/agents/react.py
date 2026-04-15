"""
ReAct Agent Module

Provides ReAct (Reasoning + Acting) agent implementation.
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
    LoopConfig,
)
from ...harness.execution import create_loop
from ...harness.infrastructure.hooks import HookManager, HookPhase, HookContext
from ...adapters.llm import ILLMAdapter


@dataclass
class ReActAgentConfig:
    """ReAct agent configuration"""
    max_steps: int = 10
    max_tokens: int = 4096
    temperature: float = 0.7
    enable_reflection: bool = True
    tool_choice: str = "auto"  # auto, force, none


class ReActAgent(BaseAgent):
    """
    ReAct Agent
    
    Implements Reasoning + Acting pattern:
    - Think about what action to take
    - Execute the action
    - Observe the result
    - Repeat until done
    """

    def __init__(
        self,
        config: AgentConfig,
        model: Optional[ILLMAdapter] = None,
        tools: Optional[List[Any]] = None,
        loop_config: Optional[ReActAgentConfig] = None,
        hook_manager: Optional[HookManager] = None
    ):
        self._react_config = loop_config or ReActAgentConfig()
        self._tools = tools or []
        self._hook_manager = hook_manager or HookManager()
        
        # Create ReAct loop
        loop_cfg = LoopConfig(
            max_steps=self._react_config.max_steps,
            max_tokens=self._react_config.max_tokens,
        )
        
        super().__init__(
            config=config,
            model=model,
            loop_type="react",
            loop_config=loop_cfg
        )
        
        self._metadata = AgentMetadata(
            name="ReActAgent",
            description="Reasoning + Acting agent",
            version="1.0.0",
            capabilities=["reasoning", "tool_use", "reflection"],
            supported_loop_types=["react"]
        )

    async def execute(self, context: AgentContext) -> AgentResult:
        """Execute ReAct agent via Harness loop delegation.
        
        Delegates to BaseAgent.execute() which runs the ReActLoop,
        with model/skills/tools injected before execution.
        """
        # Inject tools into loop before running
        if self._loop and hasattr(self._loop, 'set_tools') and self._tools:
            from ...apps.tools.base import get_tool_registry
            tool_registry = get_tool_registry()
            resolved_tools = []
            for tool_name in context.tools if context.tools else []:
                tool = tool_registry.get(tool_name)
                if tool:
                    resolved_tools.append(tool)
            resolved_tools.extend(self._tools)
            self._loop.set_tools(resolved_tools)
        
        # Delegate to BaseAgent.execute() which runs the loop
        return await super().execute(context)

    def _build_initial_state(self, context: AgentContext) -> LoopState:
        """Build initial loop state from context"""
        return LoopState(
            context={
                "task": self._extract_task(context),
                "messages": context.messages,
                "tools": [getattr(t, 'name', str(t)) for t in self._tools],
                "session_id": context.session_id,
                "user_id": context.user_id,
                **context.variables
            },
            step_count=0
        )

    def _extract_task(self, context: AgentContext) -> str:
        """Extract task from messages"""
        if context.messages:
            return context.messages[-1].get("content", "")
        return ""

    async def _execute_reasoning_loop(
        self,
        state: LoopState,
        context: AgentContext
    ) -> AgentResult:
        """Execute the reasoning loop"""
        step = 0
        max_steps = self._react_config.max_steps
        final_output = None
        
        while step < max_steps:
            step += 1
            state.step_count = step
            
            # Phase 1: Reasoning
            reasoning = await self._reason(state, context)
            state.context["reasoning"] = reasoning
            
            # Phase 2: Acting
            if self._tools:
                action_result = await self._act(state, context)
                state.context["action_result"] = action_result
                
                # Phase 3: Observing
                observation = await self._observe(state, action_result)
                state.context["observation"] = observation
                
                # Check for completion
                if self._check_completion(observation):
                    final_output = observation
                    break
            else:
                # No tools, just use model response
                final_output = reasoning
                break
        
        return AgentResult(
            success=final_output is not None,
            output=final_output,
            metadata={"steps": step, "loop_type": "ReAct"}
        )

    async def _reason(self, state: LoopState, context: AgentContext) -> str:
        """Reasoning phase - decide what action to take"""
        await self._trigger_hook(HookPhase.PRE_REASONING, state.context)
        
        if not self._model:
            return "No model available"
        
        # Build prompt
        prompt = self._build_reasoning_prompt(state, context)
        
        # Get model response
        response = await self._model.generate([
            {"role": "user", "content": prompt}
        ])
        
        await self._trigger_hook(HookPhase.POST_REASONING, state.context)
        
        return response.content

    def _build_reasoning_prompt(self, state: LoopState, context: AgentContext) -> str:
        """Build reasoning prompt"""
        task = state.context.get("task", "")
        history = "\n".join([
            f"{msg.get('role', 'user')}: {msg.get('content', '')}"
            for msg in context.messages[-5:]
        ])
        
        tools_desc = "\n".join([
            f"- {getattr(t, 'name', str(t))}: {getattr(t, 'description', '')}"
            for t in self._tools
        ]) if self._tools else "No tools available"
        
        prompt = f"""Task: {task}

History:
{history}

Available tools:
{tools_desc}

Observation: {state.context.get('observation', 'None')}

Think about what to do next. If using a tool, respond with:
ACTION: tool_name: argument

If finished, respond with:
DONE: final_answer
"""
        return prompt

    async def _act(self, state: LoopState, context: AgentContext) -> str:
        """Acting phase - execute action"""
        await self._trigger_hook(HookPhase.PRE_ACT, state.context)
        
        reasoning = state.context.get("reasoning", "")
        
        # Parse action
        action = self._parse_action(reasoning)
        
        if not action:
            return "No action to execute"
        
        tool_name, tool_args = action
        
        # Find and execute tool
        for tool in self._tools:
            if getattr(tool, 'name', '') == tool_name:
                await self._trigger_hook(HookPhase.PRE_TOOL_USE, {"tool": tool_name})
                
                result = await tool.execute(tool_args)
                
                await self._trigger_hook(HookPhase.POST_TOOL_USE, {
                    "tool": tool_name,
                    "result": result.output if hasattr(result, 'output') else str(result)
                })
                
                return str(result.output if hasattr(result, 'output') else result)
        
        return f"Tool not found: {tool_name}"

    def _parse_action(self, reasoning: str) -> Optional[tuple]:
        """Parse action from reasoning"""
        if "ACTION:" in reasoning.upper():
            try:
                parts = reasoning.upper().split("ACTION:")[1].strip()
                if ":" in parts:
                    tool_name, args = parts.split(":", 1)
                    return tool_name.strip(), args.strip()
                return parts.strip(), {}
            except Exception:
                return None
        return None

    async def _observe(self, state: LoopState, action_result: str) -> str:
        """Observing phase - process result"""
        await self._trigger_hook(HookPhase.PRE_OBSERVE, state.context)
        
        observation = action_result
        
        # If reflection enabled, process observation
        if self._react_config.enable_reflection and self._model:
            prompt = f"Action result: {observation}\nWhat does this mean for the task?"
            try:
                response = await self._model.generate([
                    {"role": "user", "content": prompt}
                ])
                observation = f"{observation}\n{response.content}"
            except Exception:
                pass
        
        await self._trigger_hook(HookPhase.POST_OBSERVE, state.context)
        
        return observation

    def _check_completion(self, observation: str) -> bool:
        """Check if execution should complete"""
        obs_upper = observation.upper()
        return "DONE" in obs_upper

    async def _trigger_hook(self, phase: HookPhase, data: Any) -> None:
        """Trigger hooks"""
        context = HookContext(phase=phase, metadata=data)
        await self._hook_manager.trigger(phase, context)

    def add_tool(self, tool: Any) -> None:
        """Add tool to agent"""
        self._tools.append(tool)


def create_react_agent(
    config: AgentConfig,
    model: Optional[ILLMAdapter] = None,
    tools: Optional[List[Any]] = None,
    **kwargs
) -> ReActAgent:
    """Create ReAct agent"""
    return ReActAgent(config=config, model=model, tools=tools, **kwargs)