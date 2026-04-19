"""
Event Bus - 事件总线

提供发布-订阅模式的事件驱动机制。
"""

import uuid
from datetime import datetime
from typing import Any, Callable, Optional, Dict, List
from dataclasses import dataclass, field
from enum import Enum
from threading import Lock


class EventPriority(str, Enum):
    HIGH = "high"
    NORMAL = "normal"
    LOW = "low"


@dataclass
class Event:
    """事件"""
    event_id: str = field(default_factory=lambda: f"evt_{uuid.uuid4().hex[:16]}")
    event_type: str = ""
    payload: Any = None
    tenant_id: str = "default"
    trace_id: Optional[str] = None
    source: str = ""
    timestamp: datetime = field(default_factory=datetime.now)
    metadata: Dict[str, Any] = field(default_factory=dict)


class EventBus:
    """事件总线"""

    def __init__(self):
        self._subscribers: Dict[str, List[Callable]] = {}
        self._handlers: Dict[str, Callable] = {}
        self._lock = Lock()
        self._event_history: List[Event] = []
        self._max_history: int = 1000

    def subscribe(self, event_type: str, handler: Callable[[Event], None]) -> None:
        """订阅事件"""
        with self._lock:
            if event_type not in self._subscribers:
                self._subscribers[event_type] = []
            self._subscribers[event_type].append(handler)

    def unsubscribe(self, event_type: str, handler: Callable[[Event], None]) -> bool:
        """取消订阅"""
        with self._lock:
            if event_type in self._subscribers and handler in self._subscribers[event_type]:
                self._subscribers[event_type].remove(handler)
                return True
        return False

    def publish(self, event: Event) -> str:
        """发布事件"""
        with self._lock:
            self._event_history.append(event)
            if len(self._event_history) > self._max_history:
                self._event_history = self._event_history[-self._max_history:]

        for handler in self._subscribers.get(event.event_type, []):
            try:
                handler(event)
            except Exception:
                pass

        return event.event_id

    def emit(
        self,
        event_type: str,
        payload: Any,
        tenant_id: str = "default",
        trace_id: Optional[str] = None,
        source: str = "",
    ) -> str:
        """发射事件"""
        event = Event(
            event_type=event_type,
            payload=payload,
            tenant_id=tenant_id,
            trace_id=trace_id,
            source=source,
        )
        return self.publish(event)

    def register_handler(self, event_type: str, handler: Callable[[Event], None]) -> None:
        """注册处理器"""
        self._handlers[event_type] = handler

    def handle_event(self, event: Event) -> None:
        """处理事件"""
        handler = self._handlers.get(event.event_type)
        if handler:
            try:
                handler(event)
            except Exception:
                pass

    def get_history(
        self,
        event_type: Optional[str] = None,
        tenant_id: Optional[str] = None,
        limit: int = 100,
    ) -> List[Event]:
        """获取事件历史"""
        history = self._event_history.copy()

        if event_type:
            history = [e for e in history if e.event_type == event_type]
        if tenant_id:
            history = [e for e in history if e.tenant_id == tenant_id]

        history.sort(key=lambda x: x.timestamp, reverse=True)
        return history[:limit]

    def clear_history(self) -> None:
        """清空历史"""
        with self._lock:
            self._event_history = []


event_bus = EventBus()