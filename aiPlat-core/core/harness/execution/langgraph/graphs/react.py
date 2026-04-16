"""
ReAct Graph（LangGraph 目录下的统一实现）

说明：
- 过去此模块尝试直接使用第三方 `langgraph`（StateGraph），但 state 类型/实例化与本仓 TypedDict
  定义不一致，且无法与 aiPlat 的 callbacks/checkpoints/ExecutionStore 形成闭环。
- 自 Round12 起：ReActGraph.run 默认使用本仓内部的 CompiledGraph 引擎（core.py），从而支持：
  1) callbacks（落库到 ExecutionStore）
  2) checkpoints（支持 restore/resume）
  3) 与 Harness 主执行路径统一口径
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
