from typing import Dict, Any, Optional, Callable, Awaitable, List
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from collections import defaultdict
import asyncio
import uuid


class EventType(Enum):
    AGENT_STARTED = "agent_started"
    AGENT_STOPPED = "agent_stopped"
    AGENT_ERROR = "agent_error"
    TOOL_INVOKED = "tool_invoked"
    TOOL_COMPLETED = "tool_completed"
    TOOL_FAILED = "tool_failed"
    LOOP_STARTED = "loop_started"
    LOOP_ITERATION = "loop_iteration"
    LOOP_COMPLETED = "loop_completed"
    LOOP_ERROR = "loop_error"
    MESSAGE_SENT = "message_sent"
    MESSAGE_RECEIVED = "message_received"
    CONTEXT_UPDATED = "context_updated"
    ADAPTER_CALLED = "adapter_called"
    ADAPTER_RESPONSE = "adapter_response"
    COORDINATION_STARTED = "coordination_started"
    COORDINATION_COMPLETED = "coordination_completed"
    SKILL_INVOKED = "skill_invoked"
    SKILL_COMPLETED = "skill_completed"


class EventPriority(Enum):
    LOW = 1
    NORMAL = 2
    HIGH = 3
    CRITICAL = 4


@dataclass
class Event:
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    type: EventType = EventType.MESSAGE_SENT
    source: str = ""
    timestamp: datetime = field(default_factory=datetime.now)
    priority: EventPriority = EventPriority.NORMAL
    data: Dict[str, Any] = field(default_factory=dict)
    metadata: Dict[str, Any] = field(default_factory=dict)


class EventFilter:
    def __init__(
        self,
        types: Optional[List[EventType]] = None,
        sources: Optional[List[str]] = None,
        priority_min: Optional[EventPriority] = None,
    ):
        self.types = types or []
        self.sources = sources or []
        self.priority_min = priority_min or EventPriority.LOW

    def matches(self, event: Event) -> bool:
        if self.types and event.type not in self.types:
            return False
        if self.sources and event.source not in self.sources:
            return False
        if event.priority.value < self.priority_min.value:
            return False
        return True


HandlerType = Callable[[Event], Awaitable[None]]


class EventBus:
    _instance: Optional["EventBus"] = None

    def __init__(self, max_queue_size: int = 10000):
        self.max_queue_size = max_queue_size
        self._handlers: Dict[EventType, List[HandlerType]] = defaultdict(list)
        self._global_handlers: List[HandlerType] = []
        self._queue: asyncio.Queue[Event] = asyncio.Queue(maxsize=max_queue_size)
        self._running = False
        self._processing_task: Optional[asyncio.Task] = None

    @classmethod
    def get_instance(cls) -> "EventBus":
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def subscribe(self, event_type: EventType, handler: HandlerType):
        self._handlers[event_type].append(handler)

    def subscribe_all(self, handler: HandlerType):
        self._global_handlers.append(handler)

    def unsubscribe(self, event_type: EventType, handler: HandlerType):
        if event_type in self._handlers:
            self._handlers[event_type] = [h for h in self._handlers[event_type] if h != handler]

    async def publish(self, event: Event):
        try:
            self._queue.put_nowait(event)
        except asyncio.QueueFull:
            try:
                self._queue.get_nowait()
                self._queue.put_nowait(event)
            except asyncio.QueueEmpty:
                pass

    def emit(
        self,
        event_type: EventType,
        source: str,
        data: Optional[Dict[str, Any]] = None,
        priority: EventPriority = EventPriority.NORMAL,
        **metadata,
    ):
        event = Event(
            type=event_type,
            source=source,
            data=data or {},
            metadata=metadata,
            priority=priority,
        )
        asyncio.create_task(self.publish(event))

    async def start(self):
        if self._running:
            return
        self._running = True
        self._processing_task = asyncio.create_task(self._process_events())

    async def stop(self):
        self._running = False
        if self._processing_task:
            await self._processing_task

    async def _process_events(self):
        while self._running:
            try:
                event = await asyncio.wait_for(self._queue.get(), timeout=1.0)
            except asyncio.TimeoutError:
                continue
            await self._dispatch(event)

    async def _dispatch(self, event: Event):
        for handler in self._global_handlers:
            try:
                await handler(event)
            except Exception:
                pass
        for handler in self._handlers.get(event.type, []):
            try:
                await handler(event)
            except Exception:
                pass

    def get_queue_size(self) -> int:
        return self._queue.qsize()

    def clear(self):
        while not self._queue.empty():
            try:
                self._queue.get_nowait()
            except asyncio.QueueEmpty:
                break


class EventRecorder:
    def __init__(self, max_events: int = 1000):
        self.max_events = max_events
        self._events: List[Event] = []
        self._by_type: Dict[EventType, List[Event]] = defaultdict(list)
        self._by_source: Dict[str, List[Event]] = defaultdict(list)

    def record(self, event: Event):
        self._events.append(event)
        self._by_type[event.type].append(event)
        self._by_source[event.source].append(event)
        if len(self._events) > self.max_events:
            removed = self._events.pop(0)
            self._by_type[removed.type].pop(0)
            self._by_source[removed.source].pop(0)

    def get_all(self, limit: Optional[int] = None) -> List[Event]:
        events = self._events
        if limit:
            events = events[-limit:]
        return events

    def get_by_type(self, event_type: EventType, limit: Optional[int] = None) -> List[Event]:
        events = self._by_type.get(event_type, [])
        if limit:
            events = events[-limit:]
        return events

    def get_by_source(self, source: str, limit: Optional[int] = None) -> List[Event]:
        events = self._by_source.get(source, [])
        if limit:
            events = events[-limit:]
        return events

    def get_by_time_range(
        self, start: datetime, end: datetime
    ) -> List[Event]:
        return [
            e for e in self._events
            if start <= e.timestamp <= end
        ]

    def clear(self):
        self._events.clear()
        self._by_type.clear()
        self._by_source.clear()


def create_event_bus(max_queue_size: int = 10000) -> EventBus:
    return EventBus(max_queue_size)


def create_event_recorder(max_events: int = 1000) -> EventRecorder:
    return EventRecorder(max_events)


event_bus = EventBus.get_instance()