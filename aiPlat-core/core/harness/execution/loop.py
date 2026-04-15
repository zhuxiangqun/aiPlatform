"""
Execution Loop - Base Implementation

Implements ILoop interface with ReAct (Reasoning + Acting) execution pattern.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Callable
import asyncio

from ..interfaces.loop import (
    ILoop,
    LoopState,
    LoopStateEnum,
    LoopConfig,
    LoopResult,
)
from ..infrastructure.hooks import HookManager, HookPhase, HookContext


class BaseLoop(ILoop):
    """
    Base execution loop implementation
    
    Provides common functionality for execution loops.
    """

    def __init__(
        self,
        config: Optional[LoopConfig] = None,
        hook_manager: Optional[HookManager] = None
    ):
        self._config = config or LoopConfig()
        self._hook_manager = hook_manager or HookManager()
        self._current_state = LoopState()
        self._current_node = "init"
        self._step_handlers: Dict[LoopStateEnum, Callable] = {}

    async def run(self, state: LoopState, config: LoopConfig) -> LoopResult:
        """Run execution loop"""
        self._current_state = state
        self._config = config
        
        # Pre-loop hook
        await self._trigger_hook(HookPhase.PRE_LOOP, {"state": state})
        
        try:
            while self.should_continue(self._current_state):
                # Execute step
                self._current_state = await self.step(self._current_state)
                
                # Check for errors
                if self._current_state.current == LoopStateEnum.ERROR:
                    if config.stop_on_error:
                        break
            
            # Post-loop hook
            await self._trigger_hook(HookPhase.POST_LOOP, {"state": self._current_state})
            
            return LoopResult(
                success=self._current_state.current == LoopStateEnum.FINISHED,
                final_state=self._current_state,
                output=self._current_state.context.get("output"),
                metadata={"steps": self._current_state.step_count}
            )
            
        except Exception as e:
            self._current_state.current = LoopStateEnum.ERROR
            return LoopResult(
                success=False,
                final_state=self._current_state,
                error=str(e),
                metadata={"exception": type(e).__name__}
            )

    def should_continue(self, state: LoopState) -> bool:
        """Determine if loop should continue"""
        # Check max steps
        if state.step_count >= self._config.max_steps:
            return False
        
        # Check token budget
        if state.budget_remaining <= 0:
            return False
        
        # Check state
        if state.current in [LoopStateEnum.FINISHED, LoopStateEnum.ERROR]:
            return False
        
        return True

    async def step(self, state: LoopState) -> LoopState:
        """Execute single step - to be implemented by subclass"""
        state.step_count += 1
        state.history.append({
            "step": state.step_count,
            "node": self._current_node,
            "state": state.current.value
        })
        
        return state

    def get_current_node(self) -> str:
        """Get current execution node"""
        return self._current_node

    async def reset(self) -> None:
        """Reset loop to initial state"""
        self._current_state = LoopState()
        self._current_node = "init"

    async def _trigger_hook(self, phase: HookPhase, data: Dict[str, Any]) -> None:
        """Trigger hooks for a phase"""
        context = HookContext(phase=phase, state=data)
        await self._hook_manager.trigger(phase, context)


class ReActLoop(BaseLoop):
    """
    ReAct (Reasoning + Acting) Execution Loop
    
    Implements the ReAct pattern:
    - Reasoning: LLM decides what action to take
    - Acting: Execute the action (Skill or Tool)
    - Observing: Process the result
    
    Skill vs Tool distinction:
    - Skill: Internal capability, executed within Agent (e.g., text generation, code analysis)
    - Tool: External interface, called outside Agent (e.g., API, database, web search)
    """

    def __init__(
        self,
        config: Optional[LoopConfig] = None,
        hook_manager: Optional[HookManager] = None,
        model: Optional[Any] = None,
        skills: Optional[List[Any]] = None,
        tools: Optional[List[Any]] = None,
        approval_manager: Optional[Any] = None
    ):
        super().__init__(config, hook_manager)
        self._model = model
        self._skills = skills or []
        self._tools = tools or []
        self._approval_manager = approval_manager
        self._current_node = "reason"

    def set_model(self, model: Any) -> None:
        self._model = model

    def set_skills(self, skills: List[Any]) -> None:
        self._skills = skills

    def set_tools(self, tools: List[Any]) -> None:
        self._tools = tools
    
    def set_approval_manager(self, manager: Any) -> None:
        self._approval_manager = manager
    
    def _approval_check(self, tool_name: str, context: Dict[str, Any]) -> None:
        """Check tool approval via ApprovalManager. Raises if denied."""
        if not self._approval_manager:
            return
        try:
            from ...infrastructure.approval import ApprovalContext, RequestStatus
            user_id = context.get("user_id", "system")
            session_id = context.get("session_id", "default")
            approval_ctx = ApprovalContext(
                session_id=session_id,
                user_id=user_id,
                operation=f"tool:{tool_name}",
                operation_context={"tool": tool_name, "context": context}
            )
            request = self._approval_manager.check_and_request(approval_ctx)
            if request.status in (RequestStatus.PENDING, RequestStatus.REJECTED):
                raise RuntimeError(f"Tool '{tool_name}' not approved: {request.result.comments if request.result else 'pending'}")
        except RuntimeError:
            raise
        except Exception:
            pass
    
    def _get_skill(self, name: str) -> Optional[Any]:
        """Get skill by name"""
        for skill in self._skills:
            if hasattr(skill, 'name') and skill.name == name:
                return skill
            if hasattr(skill, '_config') and skill._config.name == name:
                return skill
        return None
    
    def _get_tool(self, name: str) -> Optional[Any]:
        """Get tool by name"""
        for tool in self._tools:
            if hasattr(tool, 'name') and tool.name == name:
                return tool
        return None

    async def step(self, state: LoopState) -> LoopState:
        """Execute single ReAct step: reason -> act -> observe."""
        state.step_count += 1
        state.history.append({
            "step": state.step_count,
            "node": self._current_node,
            "state": state.current.value
        })

        await self._trigger_hook(HookPhase.PRE_REASONING, state.context)
        state.current = LoopStateEnum.REASONING
        reasoning = await self._reason(state)
        state.context["reasoning"] = reasoning
        await self._trigger_hook(HookPhase.POST_REASONING, state.context)

        state.current = LoopStateEnum.ACTING
        await self._trigger_hook(HookPhase.PRE_ACT, state.context)
        action_result = await self._act(state)
        state.context["action_result"] = action_result
        await self._trigger_hook(HookPhase.POST_ACT, state.context)

        state.current = LoopStateEnum.OBSERVING
        await self._trigger_hook(HookPhase.PRE_OBSERVE, state.context)
        observation = await self._observe(state)
        state.context["observation"] = observation
        await self._trigger_hook(HookPhase.POST_OBSERVE, state.context)

        if "DONE" in observation.upper() or "FINISHED" in observation.upper():
            state.current = LoopStateEnum.FINISHED

        return state

    async def _reason(self, state: LoopState) -> str:
        """Reasoning phase"""
        if not self._model:
            return "No model available"

        task = state.context.get("task", "")
        history = "\n".join([
            f"{msg.get('role', 'user')}: {msg.get('content', '')}"
            for msg in state.context.get("messages", [])[-5:]
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
        try:
            response = await self._model.generate([{"role": "user", "content": prompt}])
            return response.content
        except Exception as e:
            return f"Model error: {e}"

    async def _act(self, state: LoopState) -> str:
        """Acting phase - execute tool or skill."""
        reasoning = state.context.get("reasoning", "")
        if "ACTION:" not in reasoning.upper():
            return "No action to execute"

        try:
            parts = reasoning.upper().split("ACTION:")[1].strip()
            if ":" in parts:
                tool_name = parts.split(":", 1)[0].strip()
                tool_args_str = parts.split(":", 1)[1].strip()
                try:
                    import json
                    tool_args = json.loads(tool_args_str)
                except Exception:
                    tool_args = {"input": tool_args_str}
            else:
                tool_name = parts.strip()
                tool_args = {}
        except Exception:
            return "Failed to parse action"

        for tool in self._tools:
            if getattr(tool, 'name', '') == tool_name:
                self._approval_check(tool_name, state.context)
                await self._trigger_hook(HookPhase.PRE_TOOL_USE, {"tool": tool_name})
                try:
                    result = await tool.execute(tool_args)
                    result_output = result.output if hasattr(result, 'output') else str(result)
                except Exception as e:
                    result_output = f"Tool error: {e}"
                await self._trigger_hook(HookPhase.POST_TOOL_USE, {"tool": tool_name, "result": result_output})
                return str(result_output)

        if self._skills:
            for skill in self._skills:
                skill_name = getattr(skill, 'name', '') or getattr(skill, '_config', {}).name if hasattr(getattr(skill, '_config', None), 'name') else ''
                if skill_name and skill_name in reasoning.lower():
                    from ..interfaces import SkillContext
                    await self._trigger_hook(HookPhase.PRE_SKILL_USE, {"skill": skill_name})
                    try:
                        skill_context = SkillContext(
                            session_id=state.context.get("session_id", "default"),
                            user_id=state.context.get("user_id", "system"),
                            variables=tool_args,
                        )
                        result = await skill.execute(skill_context, tool_args)
                        result_output = result.output if hasattr(result, 'output') else str(result)
                    except Exception as e:
                        result_output = f"Skill error: {e}"
                    await self._trigger_hook(HookPhase.POST_SKILL_USE, {"skill": skill_name, "result": result_output})
                    return str(result_output)

        return f"Tool not found: {tool_name}"

    async def _observe(self, state: LoopState) -> str:
        """Observing phase"""
        return state.context.get("action_result", "")


class PlanExecuteLoop(BaseLoop):
    """
    Plan-Execute Loop
    
    Implements two-phase execution:
    - Plan: Analyze task and create execution plan
    - Execute: Execute plan steps using available tools/skills
    """

    def __init__(
        self,
        config: Optional[LoopConfig] = None,
        hook_manager: Optional[HookManager] = None,
        model: Optional[Any] = None,
        skills: Optional[List[Any]] = None,
        tools: Optional[List[Any]] = None
    ):
        super().__init__(config, hook_manager)
        self._model = model
        self._skills = skills or []
        self._tools = tools or []
        self._plan: List[Dict[str, Any]] = []
        self._current_node = "plan"

    def set_model(self, model: Any) -> None:
        self._model = model

    def set_skills(self, skills: List[Any]) -> None:
        self._skills = skills

    def set_tools(self, tools: List[Any]) -> None:
        self._tools = tools

    async def step(self, state: LoopState) -> LoopState:
        """Execute Plan-Execute step"""
        state.step_count += 1
        
        if self._current_node == "plan":
            state = await self._plan(state)
        elif self._current_node == "execute":
            state = await self._execute(state)
        
        state.history.append({
            "step": state.step_count,
            "node": self._current_node,
            "state": state.current.value
        })
        
        return state

    async def _plan(self, state: LoopState) -> LoopState:
        """Planning phase - create execution plan"""
        state.current = LoopStateEnum.REASONING
        
        if self._model:
            prompt = f"Task: {state.context.get('task', '')}\nCreate a step-by-step plan."
            response = await self._model.generate(
                [{"role": "user", "content": prompt}]
            )
            
            # Parse plan (simplified)
            self._plan = [
                {"step": i + 1, "action": line.strip().lstrip("0123456789. ").strip()}
                for i, line in enumerate(response.content.split("\n"))
                if line.strip() and not line.strip().startswith("#")
            ]
        
        state.context["plan"] = self._plan
        self._current_node = "execute"
        state.current = LoopStateEnum.ACTING
        
        return state

    async def _execute(self, state: LoopState) -> LoopState:
        """Execution phase - execute plan steps with tool/skill support"""
        state.current = LoopStateEnum.ACTING
        
        current_step = state.context.get("current_step", 0)
        
        if current_step < len(self._plan):
            step = self._plan[current_step]
            action = step.get("action", "")
            state.context["current_step"] = current_step + 1
            
            # Pre-acting hook
            await self._trigger_hook(HookPhase.PRE_ACT, {"state": state, "step": step})
            
            step_result = None
            
            # Try to execute with a tool
            tool_executed = False
            if self._tools:
                for tool in self._tools:
                    tool_name = getattr(tool, 'name', '')
                    if tool_name and tool_name.lower() in action.lower():
                        try:
                            await self._trigger_hook(HookPhase.PRE_TOOL_USE, {"tool": tool_name})
                            result = await tool.execute(state.context)
                            step_result = result.output if hasattr(result, 'output') else str(result)
                            await self._trigger_hook(HookPhase.POST_TOOL_USE, {"tool": tool_name, "result": result})
                            tool_executed = True
                            break
                        except Exception as e:
                            step_result = f"Tool error ({tool_name}): {e}"
            
            # Try to execute with a skill
            if not tool_executed and self._skills:
                for skill in self._skills:
                    skill_name = getattr(skill, '_config', None)
                    skill_name = skill_name.name if skill_name else getattr(skill, 'name', '')
                    if skill_name and skill_name.lower() in action.lower():
                        try:
                            from ...harness.interfaces import SkillContext
                            skill_context = SkillContext(
                                session_id=state.context.get("session_id", "loop"),
                                user_id=state.context.get("user_id", "system"),
                                variables={"prompt": action},
                                tools=[t.name for t in self._tools if hasattr(t, 'name')],
                            )
                            await self._trigger_hook(HookPhase.PRE_SKILL_USE, {"skill": skill_name})
                            result = await skill.execute(skill_context, {"prompt": action})
                            step_result = result.output if hasattr(result, 'output') else str(result)
                            await self._trigger_hook(HookPhase.POST_SKILL_USE, {"skill": skill_name, "result": result})
                            break
                        except Exception as e:
                            step_result = f"Skill error ({skill_name}): {e}"
            
            # Fall back to model for this step
            if step_result is None and self._model:
                try:
                    prompt = f"Execute this step: {action}\nContext: {state.context.get('task', '')}"
                    response = await self._model.generate(
                        [{"role": "user", "content": prompt}]
                    )
                    step_result = response.content
                except Exception as e:
                    step_result = f"Model error: {e}"
            
            if step_result is None:
                step_result = f"No handler for step: {action}"
            
            state.context[f"step_{current_step}_result"] = step_result
            state.context["action_result"] = step_result
            
            # Post-acting hook
            await self._trigger_hook(HookPhase.POST_ACT, {"state": state, "result": step_result})
            
            if current_step + 1 >= len(self._plan):
                state.context["output"] = state.context.get("step_0_result", step_result)
                state.current = LoopStateEnum.FINISHED
                self._current_node = "finish"
        else:
            state.current = LoopStateEnum.FINISHED
            self._current_node = "finish"
        
        return state


def create_loop(
    loop_type: str = "react",
    config: Optional[LoopConfig] = None,
    **kwargs
) -> ILoop:
    """
    Factory function to create execution loop
    
    Args:
        loop_type: Type of loop ("react", "plan_execute")
        config: Loop configuration
        **kwargs: Additional arguments
        
    Returns:
        ILoop: Execution loop instance
    """
    if loop_type == "react":
        return ReActLoop(config=config, **kwargs)
    elif loop_type == "plan_execute":
        return PlanExecuteLoop(config=config, **kwargs)
    else:
        return BaseLoop(config=config)