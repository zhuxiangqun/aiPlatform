"""
LangGraph Executor

Provides execution capabilities for LangGraph graphs.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional
import asyncio

from .graphs import ReActGraph, MultiAgentGraph, TriAgentGraph
from ...interfaces.loop import LoopState, LoopConfig, LoopResult


@dataclass
class ExecutorConfig:
    """Executor configuration"""
    timeout: int = 60
    max_retries: int = 3
    enable_checkpoint: bool = False
    metadata: Dict[str, Any] = field(default_factory=dict)


class IGraphExecutor(ABC):
    """
    Graph executor interface
    """

    @abstractmethod
    async def execute(self, graph: Any, initial_state: Dict[str, Any]) -> Any:
        """Execute graph"""
        pass

    @abstractmethod
    async def execute_with_config(
        self,
        graph: Any,
        initial_state: Dict[str, Any],
        config: ExecutorConfig
    ) -> Any:
        """Execute graph with config"""
        pass


class LangGraphExecutor(IGraphExecutor):
    """
    LangGraph executor implementation
    """

    def __init__(self, config: Optional[ExecutorConfig] = None):
        self._config = config or ExecutorConfig()

    async def execute(self, graph: Any, initial_state: Dict[str, Any]) -> Any:
        """Execute graph"""
        return await self.execute_with_config(graph, initial_state, self._config)

    async def execute_with_config(
        self,
        graph: Any,
        initial_state: Dict[str, Any],
        config: ExecutorConfig
    ) -> Any:
        """Execute graph with config"""
        try:
            # Check if graph has run method
            if hasattr(graph, 'run'):
                result = await asyncio.wait_for(
                    graph.run(initial_state),
                    timeout=config.timeout
                )
                return result
            else:
                raise ValueError("Graph does not have run method")
                
        except asyncio.TimeoutError:
            raise ExecutionTimeoutError(f"Execution timed out after {config.timeout}s")
        except Exception as e:
            if config.max_retries > 1:
                # Retry logic could be added here
                pass
            raise ExecutionError(str(e))


class ExecutionTimeoutError(Exception):
    """Execution timeout error"""
    pass


class ExecutionError(Exception):
    """Execution error"""
    pass


async def execute_react(
    model: Optional[Any] = None,
    tools: Optional[List[Any]] = None,
    messages: Optional[List[Dict[str, str]]] = None,
    max_steps: int = 10,
    timeout: int = 60
) -> Any:
    """
    Quick execute ReAct graph
    
    Args:
        model: Language model
        tools: List of tools
        messages: Chat messages
        max_steps: Max steps
        timeout: Timeout in seconds
        
    Returns:
        Execution result
    """
    from .graphs import create_react_graph
    
    graph = create_react_graph(model=model, tools=tools, max_steps=max_steps)
    
    config = ExecutorConfig(timeout=timeout)
    executor = LangGraphExecutor(config)
    
    initial_state = {
        "messages": messages or [],
        "context": {}
    }
    
    return await executor.execute(graph, initial_state)


async def execute_multi_agent(
    num_agents: int = 3,
    model: Optional[Any] = None,
    tools: Optional[List[Any]] = None,
    task: str = "",
    max_rounds: int = 5,
    timeout: int = 60
) -> Any:
    """
    Quick execute multi-agent graph
    
    Args:
        num_agents: Number of agents
        model: Language model
        tools: List of tools
        task: Task string
        max_rounds: Max rounds
        timeout: Timeout in seconds
        
    Returns:
        Execution result
    """
    from .graphs import create_multi_agent_graph
    
    graph = create_multi_agent_graph(
        num_agents=num_agents,
        model=model,
        tools=tools,
        max_rounds=max_rounds
    )
    
    config = ExecutorConfig(timeout=timeout)
    executor = LangGraphExecutor(config)
    
    return await asyncio.wait_for(
        graph.run(task),
        timeout=timeout
    )