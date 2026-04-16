"""
LangGraph Callbacks Module

Provides callback system for graph execution lifecycle hooks.
"""

from typing import Any, Dict, List, Optional, Callable, Awaitable
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
import asyncio


class CallbackEvent(Enum):
    """Callback event types"""
    GRAPH_START = "graph_start"
    GRAPH_END = "graph_end"
    GRAPH_ERROR = "graph_error"
    NODE_START = "node_start"
    NODE_END = "node_end"
    NODE_ERROR = "node_error"
    EDGE_TRAVERSE = "edge_traverse"
    STATE_UPDATE = "state_update"
    CHECKPOINT = "checkpoint"
    CHECKPOINT_RESTORE = "checkpoint_restore"


@dataclass
class CallbackContext:
    """Context passed to callbacks"""
    event: CallbackEvent
    graph_name: str
    node_name: Optional[str] = None
    state: Dict[str, Any] = field(default_factory=dict)
    result: Optional[Any] = None
    error: Optional[Exception] = None
    timestamp: datetime = field(default_factory=datetime.now)
    metadata: Dict[str, Any] = field(default_factory=dict)


CallbackHandler = Callable[[CallbackContext], Awaitable[None]]


class CallbackRegistry:
    """Registry for callback handlers"""
    
    def __init__(self):
        self._handlers: Dict[CallbackEvent, List[CallbackHandler]] = {
            event: [] for event in CallbackEvent
        }
        self._global_handlers: List[CallbackHandler] = []
    
    def register(self, event: CallbackEvent, handler: CallbackHandler):
        self._handlers[event].append(handler)
        return self
    
    def register_global(self, handler: CallbackHandler):
        self._global_handlers.append(handler)
        return self
    
    def unregister(self, event: CallbackEvent, handler: CallbackHandler):
        if handler in self._handlers[event]:
            self._handlers[event].remove(handler)
        return self
    
    def unregister_global(self, handler: CallbackHandler):
        if handler in self._global_handlers:
            self._global_handlers.remove(handler)
        return self
    
    async def trigger(self, context: CallbackContext):
        for handler in self._handlers[context.event]:
            try:
                await handler(context)
            except Exception:
                pass
        
        for handler in self._global_handlers:
            try:
                await handler(context)
            except Exception:
                pass


class CallbackManager:
    """Manages callbacks for graph execution"""
    
    _instance: Optional["CallbackManager"] = None
    
    def __init__(self):
        self._registry = CallbackRegistry()
        self._enabled = True
        self._history: List[CallbackContext] = []
        self._max_history = 1000
    
    @classmethod
    def get_instance(cls) -> "CallbackManager":
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance
    
    def enable(self):
        self._enabled = True
    
    def disable(self):
        self._enabled = False
    
    def on_graph_start(self, handler: CallbackHandler):
        self._registry.register(CallbackEvent.GRAPH_START, handler)
        return self
    
    def on_graph_end(self, handler: CallbackHandler):
        self._registry.register(CallbackEvent.GRAPH_END, handler)
        return self
    
    def on_graph_error(self, handler: CallbackHandler):
        self._registry.register(CallbackEvent.GRAPH_ERROR, handler)
        return self
    
    def on_node_start(self, handler: CallbackHandler):
        self._registry.register(CallbackEvent.NODE_START, handler)
        return self
    
    def on_node_end(self, handler: CallbackHandler):
        self._registry.register(CallbackEvent.NODE_END, handler)
        return self
    
    def on_node_error(self, handler: CallbackHandler):
        self._registry.register(CallbackEvent.NODE_ERROR, handler)
        return self
    
    def on_state_update(self, handler: CallbackHandler):
        self._registry.register(CallbackEvent.STATE_UPDATE, handler)
        return self
    
    def on_checkpoint(self, handler: CallbackHandler):
        self._registry.register(CallbackEvent.CHECKPOINT, handler)
        return self

    def register_global(self, handler: CallbackHandler):
        """Register handler for all events (用于进程级持久化/审计接线)."""
        self._registry.register_global(handler)
        return self
    
    async def trigger(self, context: CallbackContext):
        if not self._enabled:
            return
        
        self._history.append(context)
        if len(self._history) > self._max_history:
            self._history = self._history[-self._max_history:]
        
        await self._registry.trigger(context)
    
    async def trigger_graph_start(self, graph_name: str, state: Dict[str, Any]):
        await self.trigger(CallbackContext(
            event=CallbackEvent.GRAPH_START,
            graph_name=graph_name,
            state=state,
        ))
    
    async def trigger_graph_end(self, graph_name: str, state: Dict[str, Any]):
        await self.trigger(CallbackContext(
            event=CallbackEvent.GRAPH_END,
            graph_name=graph_name,
            state=state,
        ))
    
    async def trigger_graph_error(
        self,
        graph_name: str,
        error: Exception,
        state: Dict[str, Any],
    ):
        await self.trigger(CallbackContext(
            event=CallbackEvent.GRAPH_ERROR,
            graph_name=graph_name,
            error=error,
            state=state,
        ))
    
    async def trigger_node_start(
        self,
        graph_name: str,
        node_name: str,
        state: Dict[str, Any],
    ):
        await self.trigger(CallbackContext(
            event=CallbackEvent.NODE_START,
            graph_name=graph_name,
            node_name=node_name,
            state=state,
        ))
    
    async def trigger_node_end(
        self,
        graph_name: str,
        node_name: str,
        state: Dict[str, Any],
        result: Any,
    ):
        await self.trigger(CallbackContext(
            event=CallbackEvent.NODE_END,
            graph_name=graph_name,
            node_name=node_name,
            state=state,
            result=result,
        ))
    
    async def trigger_node_error(
        self,
        graph_name: str,
        node_name: str,
        error: Exception,
        state: Dict[str, Any],
    ):
        await self.trigger(CallbackContext(
            event=CallbackEvent.NODE_ERROR,
            graph_name=graph_name,
            node_name=node_name,
            error=error,
            state=state,
        ))
    
    async def trigger_checkpoint(
        self,
        graph_name: str,
        state: Dict[str, Any],
        checkpoint_id: str,
    ):
        await self.trigger(CallbackContext(
            event=CallbackEvent.CHECKPOINT,
            graph_name=graph_name,
            state=state,
            metadata={"checkpoint_id": checkpoint_id},
        ))
    
    def get_history(
        self,
        event: Optional[CallbackEvent] = None,
        limit: int = 100,
    ) -> List[CallbackContext]:
        history = self._history
        if event:
            history = [c for c in history if c.event == event]
        return history[-limit:]


class LoggingCallback:
    """Built-in callback for logging"""
    
    def __init__(self, log_level: str = "INFO"):
        self.log_level = log_level
    
    async def __call__(self, context: CallbackContext):
        timestamp = context.timestamp.isoformat()
        node_info = f" [{context.node_name}]" if context.node_name else ""
        error_info = f" ERROR: {context.error}" if context.error else ""
        print(f"[{timestamp}] {self.log_level}: {context.event.value}{node_info}{error_info}")


class MetricsCallback:
    """Built-in callback for collecting metrics"""
    
    def __init__(self):
        self._metrics: Dict[str, List[float]] = {}
    
    async def __call__(self, context: CallbackContext):
        metric_name = f"{context.graph_name}.{context.event.value}"
        if metric_name not in self._metrics:
            self._metrics[metric_name] = []
        timestamp = context.timestamp.timestamp()
        self._metrics[metric_name].append(timestamp)
    
    def get_metrics(self) -> Dict[str, Dict[str, float]]:
        result = {}
        for name, values in self._metrics.items():
            if values:
                result[name] = {
                    "count": len(values),
                    "first": values[0],
                    "last": values[-1],
                }
        return result


def create_callback_manager() -> CallbackManager:
    return CallbackManager()


def create_logging_callback(log_level: str = "INFO") -> LoggingCallback:
    return LoggingCallback(log_level)


def create_metrics_callback() -> MetricsCallback:
    return MetricsCallback()


__all__ = [
    "CallbackEvent",
    "CallbackContext",
    "CallbackHandler",
    "CallbackRegistry",
    "CallbackManager",
    "LoggingCallback",
    "MetricsCallback",
    "create_callback_manager",
    "create_logging_callback",
    "create_metrics_callback",
]
