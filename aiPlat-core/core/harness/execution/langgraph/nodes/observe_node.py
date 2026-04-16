"""
LangGraph Observation Node

Implements the observation node for processing action results.
"""

from typing import Any, Dict, List, Optional
from dataclasses import dataclass, field

from .reason_node import BaseNode, AgentState
from ....syscalls import sys_llm_generate
import os
from ....assembly import PromptAssembler


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
        tools: Optional[List[Any]] = None,
        process_observation: bool = True
    ):
        super().__init__(name, description, model, tools)
        self._process_observation = process_observation

    async def execute(self, state: AgentState) -> Dict[str, Any]:
        """Execute observation"""
        observation = state.observation
        updates = {
            "observation": observation,
        }
        
        # Use model to process observation if enabled
        if self._process_observation and self._model and observation:
            try:
                processed = await self._process_with_model(observation, state)
                updates["processed_observation"] = processed
            except Exception:
                pass
        
        return updates

    async def _process_with_model(
        self,
        observation: str,
        state: AgentState
    ) -> str:
        """Process observation using model"""
        if os.getenv("AIPLAT_ENABLE_PROMPT_ASSEMBLER", "false").lower() in ("1", "true", "yes", "y"):
            prompt = PromptAssembler().build_langgraph_observe_messages(observation=str(observation))
        else:
            prompt = f"""Observation from tool execution: {observation}

Based on this observation, what should I do next?
- If more work needed, respond with what to do
- If task complete, respond with DONE
- If error occurred, respond with ERROR: description
"""
        response = await sys_llm_generate(self._model, prompt)
        return response.content

    def should_continue(self, observation: str) -> bool:
        """Determine if execution should continue"""
        obs_upper = observation.upper()
        
        if "DONE" in obs_upper:
            return False
        
        if "ERROR" in obs_upper:
            return False
        
        return True


def create_observe_node(
    model: Optional[Any] = None,
    tools: Optional[List[Any]] = None,
    process_observation: bool = True
) -> ObserveNode:
    """Create observation node"""
    return ObserveNode(
        model=model,
        tools=tools,
        process_observation=process_observation
    )
