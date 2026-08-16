"""
ReAct Graph (unified implementation under the LangGraph directory)

Notes:
- Previously this module tried to use the third-party `langgraph` (StateGraph) directly, but its state
  typing/instantiation was inconsistent with this repo's TypedDict definitions, and it could not form a
  closed loop with aiPlat's callbacks/checkpoints/ExecutionStore.
- Since Round12: ReActGraph.run defaults to this repo's internal CompiledGraph engine (core.py), enabling:
  1) callbacks (persisted to ExecutionStore)
  2) checkpoints (supporting restore/resume)
  3) unified behavior with the Harness main execution path
"""

from typing import Any, Dict, List, Optional
from dataclasses import dataclass, field

try:
    from langgraph.graph import StateGraph, END
    LANGGRAPH_AVAILABLE = True
except ImportError:
    LANGGRAPH_AVAILABLE = False
    StateGraph = None
    END = None

from ..compiled_graphs import create_compiled_react_graph
from ..core import GraphConfig


@dataclass
class ReActGraphConfig:
    """ReAct graph configuration"""
    max_steps: int = 10
    max_tokens: int = 8192
    model: Optional[Any] = None
    tools: List[Any] = field(default_factory=list)
    enable_observation_processing: bool = True
    enable_checkpoints: bool = True
    checkpoint_interval: int = 1
    enable_callbacks: bool = True
    graph_name: str = "react"


class ReActGraph:
    """
    ReAct Graph Implementation
    
    Implements the ReAct pattern using LangGraph:
    - Reason node: LLM decides action
    - Act node: Execute action
    - Observe node: Process result
    """

    def __init__(self, config: Optional[ReActGraphConfig] = None):
        self._config = config or ReActGraphConfig()
        # Keep compatibility: external StateGraph may exist, but run() uses internal compiled graph by default.
        self._graph = None

    async def run(self, initial_state: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """
        Run the ReAct graph
        
        Args:
            initial_state: Initial state dictionary
            
        Returns:
            Dict[str, Any]: Final state
        """
        compiled = create_compiled_react_graph(
            model=self._config.model,
            tools=self._config.tools,
            max_steps=self._config.max_steps,
            graph_name=self._config.graph_name,
        )

        init = dict(initial_state or {})
        init.setdefault("messages", [])
        init.setdefault("context", {})
        init.setdefault("metadata", {})
        init.setdefault("step_count", 0)
        init["max_steps"] = self._config.max_steps

        return await compiled.execute(
            init,
            config=GraphConfig(
                max_steps=self._config.max_steps,
                enable_checkpoints=self._config.enable_checkpoints,
                checkpoint_interval=self._config.checkpoint_interval,
                enable_callbacks=self._config.enable_callbacks,
            ),
        )


def create_react_graph(
    model: Optional[Any] = None,
    tools: Optional[List[Any]] = None,
    max_steps: int = 10
) -> ReActGraph:
    """
    Create ReAct graph
    
    Args:
        model: Language model
        tools: List of tools
        max_steps: Maximum steps
        
    Returns:
        ReActGraph: Configured ReAct graph
    """
    config = ReActGraphConfig(
        max_steps=max_steps,
        model=model,
        tools=tools or []
    )
    return ReActGraph(config)
