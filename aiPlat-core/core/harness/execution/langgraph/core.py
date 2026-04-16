"""
LangGraph Core Module

Provides core functionality for LangGraph-based execution.
"""

from typing import Any, Dict, List, Optional, Callable, TypedDict
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
import asyncio
import uuid


class GraphState(TypedDict, total=False):
    """State passed through the graph"""
    messages: List[Dict[str, Any]]
    context: Dict[str, Any]
    current_step: str
    step_count: int
    max_steps: int
    metadata: Dict[str, Any]
    errors: List[Dict[str, Any]]
    results: Dict[str, Any]


class NodeType(Enum):
    """Node types in the graph"""
    REASON = "reason"
    ACT = "act"
    OBSERVE = "observe"
    DECIDE = "decide"
    ROUTE = "route"
    AGGREGATE = "aggregate"
    TRANSFORM = "transform"


@dataclass
class NodeResult:
    """Result from executing a node"""
    success: bool
    output: Any
    next_node: Optional[str] = None
    should_continue: bool = True
    metadata: Dict[str, Any] = field(default_factory=dict)
    error: Optional[str] = None


@dataclass
class GraphConfig:
    """Graph configuration"""
    max_steps: int = 10
    timeout: float = 300.0
    enable_checkpoints: bool = True
    checkpoint_interval: int = 5
    enable_callbacks: bool = True
    metadata: Dict[str, Any] = field(default_factory=dict)


class ExecutionTrace:
    """Tracks execution through the graph"""
    
    def __init__(self, graph_id: str):
        self.graph_id = graph_id
        self.start_time = datetime.now()
        self.end_time: Optional[datetime] = None
        self.nodes_executed: List[str] = []
        self.transitions: List[Dict[str, Any]] = []
        self.checkpoints: List[Dict[str, Any]] = []
    
    def record_node(self, node_name: str, result: NodeResult):
        self.nodes_executed.append(node_name)
        self.transitions.append({
            "node": node_name,
            "success": result.success,
            "timestamp": datetime.now().isoformat(),
            "output_type": type(result.output).__name__,
        })
    
    def record_checkpoint(self, state: GraphState):
        self.checkpoints.append({
            "step": len(self.nodes_executed),
            "state": dict(state),
            "timestamp": datetime.now().isoformat(),
        })
    
    def finalize(self):
        self.end_time = datetime.now()
    
    @property
    def duration_ms(self) -> float:
        end = self.end_time or datetime.now()
        return (end - self.start_time).total_seconds() * 1000
    
    @property
    def success_rate(self) -> float:
        if not self.transitions:
            return 0.0
        successful = sum(1 for t in self.transitions if t["success"])
        return successful / len(self.transitions)
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "graph_id": self.graph_id,
            "start_time": self.start_time.isoformat(),
            "end_time": self.end_time.isoformat() if self.end_time else None,
            "duration_ms": self.duration_ms,
            "nodes_executed": self.nodes_executed,
            "success_rate": self.success_rate,
            "checkpoint_count": len(self.checkpoints),
        }


class GraphBuilder:
    """Builder for creating execution graphs"""
    
    def __init__(self, name: str = "default"):
        self.name = name
        self._nodes: Dict[str, Callable] = {}
        self._edges: Dict[str, List[str]] = {}
        self._entry_point: Optional[str] = None
        self._end_points: List[str] = []
        self._conditions: Dict[str, Callable] = {}
    
    def add_node(self, name: str, func: Callable) -> "GraphBuilder":
        self._nodes[name] = func
        return self
    
    def add_edge(self, from_node: str, to_node: str) -> "GraphBuilder":
        if from_node not in self._edges:
            self._edges[from_node] = []
        self._edges[from_node].append(to_node)
        return self
    
    def add_conditional_edge(
        self,
        from_node: str,
        condition: Callable,
        edges: Dict[str, str],
    ) -> "GraphBuilder":
        self._conditions[from_node] = (condition, edges)
        return self
    
    def set_entry_point(self, node: str) -> "GraphBuilder":
        self._entry_point = node
        return self
    
    def add_end_point(self, node: str) -> "GraphBuilder":
        self._end_points.append(node)
        return self
    
    def build(self) -> "CompiledGraph":
        if not self._entry_point:
            raise ValueError("Entry point not set")
        if self._entry_point not in self._nodes:
            raise ValueError(f"Entry point '{self._entry_point}' not in nodes")
        
        return CompiledGraph(
            name=self.name,
            nodes=self._nodes,
            edges=self._edges,
            entry_point=self._entry_point,
            end_points=self._end_points,
            conditions=self._conditions,
        )


class CompiledGraph:
    """A compiled execution graph"""
    
    def __init__(
        self,
        name: str,
        nodes: Dict[str, Callable],
        edges: Dict[str, List[str]],
        entry_point: str,
        end_points: List[str],
        conditions: Dict[str, tuple],
    ):
        self.name = name
        self._nodes = nodes
        self._edges = edges
        self._entry_point = entry_point
        self._end_points = end_points
        self._conditions = conditions
    
    async def execute(
        self,
        initial_state: GraphState,
        config: Optional[GraphConfig] = None,
    ) -> GraphState:
        config = config or GraphConfig()
        trace = ExecutionTrace(self.name)
        state = initial_state.copy()
        state.setdefault("step_count", 0)
        # 允许恢复执行时更新 max_steps
        state["max_steps"] = config.max_steps
        state.setdefault("metadata", {})
        # Graph run id for checkpoint persistence / audit correlation
        state["metadata"].setdefault("graph_run_id", str(uuid.uuid4()))

        callback_mgr = None
        if config.enable_callbacks:
            try:
                from .callbacks import CallbackManager

                callback_mgr = CallbackManager.get_instance()
            except Exception:
                callback_mgr = None

        if callback_mgr:
            try:
                await callback_mgr.trigger_graph_start(self.name, dict(state))
            except Exception:
                pass
        
        # 恢复语义：若 state 已包含 current_node（来自 checkpoint state），则从该节点继续
        current_node = state.get("current_node") or self._entry_point
        
        while current_node and state["step_count"] < state["max_steps"]:
            if current_node not in self._nodes:
                break
            
            node_func = self._nodes[current_node]
            
            try:
                # 将当前节点写入 state（使 checkpoint state 可用于恢复）
                state["current_node"] = current_node
                if callback_mgr:
                    try:
                        await callback_mgr.trigger_node_start(self.name, current_node, dict(state))
                    except Exception:
                        pass
                if asyncio.iscoroutinefunction(node_func):
                    result = await node_func(state)
                else:
                    result = node_func(state)
                
                if not isinstance(result, NodeResult):
                    result = NodeResult(success=True, output=result)

                if callback_mgr:
                    try:
                        await callback_mgr.trigger_node_end(self.name, current_node, dict(state), result)
                    except Exception:
                        pass
                
                trace.record_node(current_node, result)
                state["step_count"] += 1
                
                if config.enable_checkpoints and state["step_count"] % config.checkpoint_interval == 0:
                    trace.record_checkpoint(state)
                    if callback_mgr:
                        try:
                            await callback_mgr.trigger_checkpoint(
                                graph_name=self.name,
                                state=dict(state),
                                checkpoint_id=str(uuid.uuid4()),
                            )
                        except Exception:
                            pass
                
                if not result.should_continue:
                    break
                
                if result.next_node:
                    current_node = result.next_node
                elif current_node in self._conditions:
                    condition, edges = self._conditions[current_node]
                    next_key = condition(state, result)
                    current_node = edges.get(next_key)
                elif current_node in self._edges:
                    next_nodes = self._edges[current_node]
                    current_node = next_nodes[0] if len(next_nodes) == 1 else None
                else:
                    current_node = None
                state["current_node"] = current_node
                
                if current_node in self._end_points:
                    break
                    
            except Exception as e:
                result = NodeResult(success=False, output=None, error=str(e))
                trace.record_node(current_node, result)
                if callback_mgr:
                    try:
                        await callback_mgr.trigger_node_error(self.name, current_node, e, dict(state))
                        await callback_mgr.trigger_graph_error(self.name, e, dict(state))
                    except Exception:
                        pass
                state.setdefault("errors", []).append({
                    "node": current_node,
                    "error": str(e),
                    "timestamp": datetime.now().isoformat(),
                })
                break
        
        trace.finalize()
        state.setdefault("metadata", {})
        state["metadata"]["trace"] = trace.to_dict()
        if callback_mgr:
            try:
                await callback_mgr.trigger_graph_end(self.name, dict(state))
            except Exception:
                pass
        return state
    
    def get_nodes(self) -> List[str]:
        return list(self._nodes.keys())
    
    def get_edges(self) -> Dict[str, List[str]]:
        return dict(self._edges)


def create_graph_builder(name: str = "default") -> GraphBuilder:
    return GraphBuilder(name)


__all__ = [
    "GraphState",
    "NodeType",
    "NodeResult",
    "GraphConfig",
    "ExecutionTrace",
    "GraphBuilder",
    "CompiledGraph",
    "create_graph_builder",
]
