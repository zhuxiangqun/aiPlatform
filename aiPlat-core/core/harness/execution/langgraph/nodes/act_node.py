"""
LangGraph Action Node

Implements the action node for executing tools/actions.
"""

from typing import Any, Dict, List, Optional
from dataclasses import dataclass, field

from .reason_node import BaseNode, AgentState
from ...tool_calling import parse_action_call


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
        tools: Optional[List[Any]] = None,
        max_retries: int = 2
    ):
        super().__init__(name, description, model, tools)
        self._max_retries = max_retries

    async def execute(self, state: AgentState) -> Dict[str, Any]:
        """Execute action"""
        action_result = ""
        
        # Parse action call (tool/skill). LangGraph ActNode 仅执行 tool。
        parsed = parse_action_call(state.reasoning or "")
        if parsed and parsed.kind == "skill":
            action = None
            tool_args = {}
        else:
            action = parsed.name if parsed else self._parse_action(state.reasoning or "")
            tool_args = parsed.args if parsed else state.context.get("tool_params", {})
        
        if action and self._tools:
            # Find and execute tool with retry
            tool = self._get_tool(action)
            if tool:
                # Put parsed tool args into context for downstream nodes (best effort)
                try:
                    state.context["tool_params"] = tool_args
                except Exception:
                    pass
                action_result = await self._execute_with_retry(tool, state.context)
            else:
                action_result = f"Tool not found: {action}"
        elif action:
            # No tools, treat as simple action
            action_result = f"Action: {action}"
        else:
            action_result = "No action to execute"
        
        return {
            "action": action,
            "observation": action_result,
        }

    async def _execute_with_retry(self, tool: Any, context: Dict[str, Any]) -> str:
        """Execute tool with retry logic"""
        params = context.get("tool_params", {})
        
        for attempt in range(self._max_retries):
            try:
                result = await tool.execute(params)
                if result.success:
                    return str(result.output or "Success")
                else:
                    if attempt < self._max_retries - 1:
                        continue
                    return f"Error: {result.error}"
            except Exception as e:
                if attempt < self._max_retries - 1:
                    continue
                return f"Error: {str(e)}"
        
        return "Max retries exceeded"

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


def create_act_node(
    model: Optional[Any] = None,
    tools: Optional[List[Any]] = None,
    max_retries: int = 2
) -> ActNode:
    """Create action node with retry support"""
    return ActNode(model=model, tools=tools, max_retries=max_retries)
