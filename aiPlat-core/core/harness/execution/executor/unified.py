"""
Unified Executor Module

Provides unified execution interface for different executor types.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional
import asyncio


@dataclass
class ExecutionRequest:
    """Execution request"""
    executor_type: str  # "loop", "langgraph", "sandbox", "background"
    target: Any         # The thing to execute
    initial_state: Dict[str, Any] = field(default_factory=dict)
    config: Dict[str, Any] = field(default_factory=dict)


@dataclass
class ExecutionResponse:
    """Execution response"""
    success: bool
    result: Any = None
    error: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)


class IExecutor(ABC):
    """
    Executor interface
    """

    @abstractmethod
    async def execute(self, request: ExecutionRequest) -> ExecutionResponse:
        """Execute request"""
        pass

    @abstractmethod
    async def submit(self, request: ExecutionRequest) -> str:
        """Submit request and return execution ID"""
        pass

    @abstractmethod
    async def get_result(self, execution_id: str) -> Optional[ExecutionResponse]:
        """Get result by execution ID"""
        pass


class UnifiedExecutor(IExecutor):
    """
    Unified executor that dispatches to different executor types
    """

    def __init__(self):
        self._executors: Dict[str, IExecutor] = {}
        self._results: Dict[str, ExecutionResponse] = {}
        self._register_default_executors()

    def _register_default_executors(self) -> None:
        """Register default executors"""
        from .loop import BaseLoop
        from .langgraph import ReActGraph
        from .langgraph.executor import LangGraphExecutor
        
        # These would be proper implementations
        pass

    def register_executor(self, executor_type: str, executor: IExecutor) -> None:
        """Register an executor for a type"""
        self._executors[executor_type] = executor

    async def execute(self, request: ExecutionRequest) -> ExecutionResponse:
        """Execute request using appropriate executor"""
        executor = self._executors.get(request.executor_type)
        
        if not executor:
            return ExecutionResponse(
                success=False,
                error=f"No executor registered for type: {request.executor_type}"
            )
        
        return await executor.execute(request)

    async def submit(self, request: ExecutionRequest) -> str:
        """Submit request for async execution"""
        execution_id = f"exec_{len(self._results)}"
        
        # Create task
        task = asyncio.create_task(self.execute(request))
        
        # Store task reference
        self._results[execution_id] = None
        
        # Add callback to store result
        task.add_done_callback(
            lambda t: self._store_result(execution_id, t)
        )
        
        return execution_id

    def _store_result(self, execution_id: str, task: asyncio.Task) -> None:
        """Store result from completed task"""
        try:
            result = task.result()
            self._results[execution_id] = result
        except Exception as e:
            self._results[execution_id] = ExecutionResponse(
                success=False,
                error=str(e)
            )

    async def get_result(self, execution_id: str) -> Optional[ExecutionResponse]:
        """Get result by execution ID"""
        return self._results.get(execution_id)


class LoopExecutor(IExecutor):
    """Executor for loop-based execution"""

    async def execute(self, request: ExecutionRequest) -> ExecutionResponse:
        """Execute loop"""
        from .loop import create_loop
        
        try:
            loop = create_loop(
                loop_type=request.config.get("loop_type", "react"),
                config=request.config.get("loop_config")
            )
            
            from ..interfaces.loop import LoopState
            state = LoopState(
                context=request.initial_state.get("context", {}),
                step_count=0
            )
            
            result = await loop.run(state, request.config.get("loop_config", None))
            
            return ExecutionResponse(
                success=result.success,
                result=result.output,
                metadata={"steps": result.final_state.step_count if result.final_state else 0}
            )
            
        except Exception as e:
            return ExecutionResponse(
                success=False,
                error=str(e)
            )

    async def submit(self, request: ExecutionRequest) -> str:
        """Submit loop execution"""
        return await self.execute(request)

    async def get_result(self, execution_id: str) -> Optional[ExecutionResponse]:
        """Get result (not applicable for sync executor)"""
        return None


class LangGraphExecutorWrapper(IExecutor):
    """Executor for LangGraph-based execution"""

    async def execute(self, request: ExecutionRequest) -> ExecutionResponse:
        """Execute LangGraph"""
        from .langgraph import create_react_graph
        
        try:
            graph = create_react_graph(
                model=request.config.get("model"),
                tools=request.config.get("tools", []),
                max_steps=request.config.get("max_steps", 10)
            )
            
            result = await graph.run(request.initial_state)
            
            return ExecutionResponse(
                success=True,
                result=result.observation if hasattr(result, 'observation') else str(result),
                metadata={"steps": result.step_count if hasattr(result, 'step_count') else 0}
            )
            
        except Exception as e:
            return ExecutionResponse(
                success=False,
                error=str(e)
            )

    async def submit(self, request: ExecutionRequest) -> str:
        """Submit LangGraph execution"""
        return await self.execute(request)

    async def get_result(self, execution_id: str) -> Optional[ExecutionResponse]:
        """Get result (not applicable for sync executor)"""
        return None


def create_unified_executor() -> UnifiedExecutor:
    """Create unified executor with default executors"""
    executor = UnifiedExecutor()
    
    executor.register_executor("loop", LoopExecutor())
    executor.register_executor("langgraph", LangGraphExecutorWrapper())
    
    return executor