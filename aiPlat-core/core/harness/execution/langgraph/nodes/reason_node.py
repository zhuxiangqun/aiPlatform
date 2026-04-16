"""
LangGraph Base Nodes

Provides base node classes and common node implementations.
"""

from abc import ABC, abstractmethod
from typing import Any, Callable, Dict, List, Optional, TypedDict
import asyncio
import os
from ...tool_calling import parse_action_call
from ....syscalls import sys_llm_generate, sys_tool_call
from ....assembly import PromptAssembler


class AgentState(TypedDict, total=False):
    """
    Agent state for LangGraph.
    
    Uses TypedDict for LangGraph StateGraph compatibility.
    LangGraph requires state types to be TypedDict subclasses, not dataclasses.
    """
    messages: List[Dict[str, str]]
    reasoning: str
    action: str
    observation: str
    step_count: int
    used_tokens: int
    context: Dict[str, Any]
    metadata: Dict[str, Any]


class BaseNode(ABC):
    """
    Base node class for LangGraph
    
    All nodes should inherit from this class.
    """

    def __init__(
        self,
        name: str,
        description: str = "",
        model: Optional[Any] = None,
        tools: Optional[List[Any]] = None
    ):
        self.name = name
        self.description = description
        self._model = model
        self._tools = tools or []

    @abstractmethod
    async def execute(self, state: AgentState) -> Dict[str, Any]:
        """
        Execute node logic
        
        Args:
            state: Current agent state
            
        Returns:
            Dict: State updates to apply
        """
        pass

    def validate_tools(self) -> bool:
        """Validate that required tools are available"""
        return True


class ReasonNode(BaseNode):
    """
    Reasoning node
    
    Uses LLM to reason about the current state and decide next action.
    """

    def __init__(
        self,
        name: str = "reason",
        description: str = "Reasoning node",
        model: Optional[Any] = None,
        tools: Optional[List[Any]] = None
    ):
        super().__init__(name, description, model, tools)

    async def execute(self, state: AgentState) -> Dict[str, Any]:
        """Execute reasoning"""
        # Build prompt from state
        prompt = self._build_prompt(state)
        
        # Get response from model
        if self._model:
            response = await sys_llm_generate(self._model, prompt)
            reasoning = response.content
        else:
            reasoning = "No model available"
        
        step_count = int(state.get("step_count", 0) or 0) + 1
        return {"reasoning": reasoning, "step_count": step_count}

    def _build_prompt(self, state: AgentState):
        """Build reasoning prompt from state"""
        messages = state.get("messages") or []
        history = "\n".join([f"{msg.get('role', 'user')}: {msg.get('content', '')}" for msg in messages[-5:]])
        if os.getenv("AIPLAT_ENABLE_PROMPT_ASSEMBLER", "false").lower() in ("1", "true", "yes", "y"):
            return PromptAssembler().build_langgraph_reason_messages(
                history=history,
                reasoning=str(state.get("reasoning", "") or ""),
                action=str(state.get("action", "") or ""),
                observation=str(state.get("observation", "") or ""),
            )

        return f"""Current state:
- History: {history}
- Reasoning: {state.get('reasoning','')}
- Action: {state.get('action','')}
- Observation: {state.get('observation','')}

What should I do next?

优先使用结构化工具调用（推荐）：
```json
{{"tool":"tool_name","args":{{...}}}}
```

兼容旧格式：
ACTION: tool_name: {{json_or_text}}

If finished, respond with: DONE
"""


class ActNode(BaseNode):
    """
    Action node
    
    Executes the action decided in the reasoning phase.
    """

    def __init__(
        self,
        name: str = "act",
        description: str = "Action node",
        model: Optional[Any] = None,
        tools: Optional[List[Any]] = None
    ):
        super().__init__(name, description, model, tools)

    async def execute(self, state: AgentState) -> Dict[str, Any]:
        """Execute action"""
        action_result = ""
        
        reasoning = state.get("reasoning", "") or ""
        parsed = parse_action_call(reasoning)
        if parsed and parsed.kind == "skill":
            action = None
            tool_args = {}
        else:
            action = parsed.name if parsed else self._parse_action(reasoning)
            tool_args = parsed.args if parsed else {}
        
        if action and self._tools:
            # Find and execute tool
            tool = self._get_tool(action)
            if tool:
                try:
                    ctx = state.get("context") or {}
                    result = await sys_tool_call(
                        tool,
                        tool_args,
                        user_id=str(ctx.get("user_id", "system")),
                        session_id=str(ctx.get("session_id", "default")),
                    )
                    action_result = str(result.output or result.error or "Success")
                except Exception as e:
                    action_result = f"Error: {str(e)}"
            else:
                action_result = f"Tool not found: {action}"
        elif action:
            action_result = f"Action: {action}"
        else:
            action_result = "No action to execute"
        
        return {
            "action": action,
            "observation": action_result,
        }

    def _parse_action(self, reasoning: str) -> Optional[str]:
        """Parse action from reasoning"""
        if "ACTION:" in reasoning.upper():
            parts = reasoning.upper().split("ACTION:")
            if len(parts) > 1:
                return parts[1].strip().split()[0]
        return None

    def _get_tool(self, name: str) -> Optional[Any]:
        """Get tool by name"""
        for tool in self._tools:
            if hasattr(tool, 'name') and tool.name == name:
                return tool
        return None


class ObserveNode(BaseNode):
    """
    Observation node
    
    Processes the result of the action and prepares for next iteration.
    """

    def __init__(
        self,
        name: str = "observe",
        description: str = "Observation node",
        model: Optional[Any] = None,
        tools: Optional[List[Any]] = None
    ):
        super().__init__(name, description, model, tools)

    async def execute(self, state: AgentState) -> Dict[str, Any]:
        """Execute observation"""
        observation = state.get("observation", "")
        
        # If model available, use it to process observation
        if self._model and observation:
            if os.getenv("AIPLAT_ENABLE_PROMPT_ASSEMBLER", "false").lower() in ("1", "true", "yes", "y"):
                prompt = PromptAssembler().build_langgraph_observe_messages(observation=str(observation))
            else:
                prompt = f"Observation: {observation}\nWhat does this mean for the next step?"
            try:
                response = await sys_llm_generate(self._model, prompt)
                # Could add processed observation to state
            except Exception:
                pass
        
        return {
            "observation": observation,
        }


class ToolNode(BaseNode):
    """
    Generic tool execution node
    """

    def __init__(
        self,
        name: str,
        tool: Any,
        description: str = ""
    ):
        super().__init__(name, description, tools=[tool])
        self._tool = tool

    async def execute(self, state: AgentState) -> Dict[str, Any]:
        """Execute tool"""
        # Extract parameters from state context
        context = state.get("context") or {}
        params = context.get("tool_params", {}) if isinstance(context, dict) else {}
        
        try:
            result = await sys_tool_call(
                self._tool,
                params if isinstance(params, dict) else {},
                user_id=str(context.get("user_id", "system")) if isinstance(context, dict) else "system",
                session_id=str(context.get("session_id", "default")) if isinstance(context, dict) else "default",
                trace_context={
                    "trace_id": (state.get("metadata") or {}).get("trace_id") if isinstance(state.get("metadata"), dict) else None,
                    "run_id": (state.get("metadata") or {}).get("graph_run_id") if isinstance(state.get("metadata"), dict) else None,
                },
            )
            return {
                "tool_result": getattr(result, "output", None),
                "tool_error": getattr(result, "error", None),
            }
        except Exception as e:
            return {
                "tool_result": None,
                "tool_error": str(e),
            }


class ConditionalNode(BaseNode):
    """
    Conditional routing node
    
    Routes to different nodes based on condition.
    """

    def __init__(
        self,
        name: str,
        condition: Callable[[AgentState], str],
        branches: Dict[str, str]
    ):
        super().__init__(name, "Conditional routing node")
        self._condition = condition
        self._branches = branches

    async def execute(self, state: AgentState) -> Dict[str, Any]:
        """Execute conditional routing"""
        result = self._condition(state)
        next_node = self._branches.get(result, "end")
        
        return {
            "next_node": next_node,
            "condition_result": result,
        }


def create_reason_node(model: Optional[Any] = None, tools: Optional[List[Any]] = None) -> ReasonNode:
    """Create reason node"""
    return ReasonNode(model=model, tools=tools)


def create_act_node(model: Optional[Any] = None, tools: Optional[List[Any]] = None) -> ActNode:
    """Create act node"""
    return ActNode(model=model, tools=tools)


def create_observe_node(model: Optional[Any] = None, tools: Optional[List[Any]] = None) -> ObserveNode:
    """Create observe node"""
    return ObserveNode(model=model, tools=tools)
