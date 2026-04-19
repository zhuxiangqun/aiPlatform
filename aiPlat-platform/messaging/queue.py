"""
Message Queue - 消息队列服务
"""

import uuid
from datetime import datetime
from typing import Any, Optional, Callable, List
from dataclasses import dataclass, field
from enum import Enum
from queue import Queue as PyQueue
from threading import Lock


class MessagePriority(str, Enum):
    HIGH = "high"
    NORMAL = "normal"
    LOW = "low"


@dataclass
class Message:
    """消息"""
    message_id: str = field(default_factory=lambda: f"msg_{uuid.uuid4().hex[:16]}")
    topic: str = ""
    payload: Any = None
    priority: MessagePriority = MessagePriority.NORMAL
    tenant_id: str = "default"
    trace_id: Optional[str] = None
    run_id: Optional[str] = None
    created_at: datetime = field(default_factory=datetime.now)
    expires_at: Optional[datetime] = None
    retry_count: int = 0
    max_retries: int = 3


class MessageQueue:
    """消息队列服务"""

    def __init__(self):
        self._queues: dict = {}
        self._subscribers: dict = {}
        self._lock = Lock()

    def create_topic(self, topic: str) -> None:
        """创建主题"""
        with self._lock:
            if topic not in self._queues:
                self._queues[topic] = PyQueue()
                self._subscribers[topic] = []

    def publish(self, topic: str, message: Message) -> str:
        """发布消息"""
        with self._lock:
            if topic not in self._queues:
                self.create_topic(topic)

        if message.priority == MessagePriority.HIGH:
            self._queues[topic].putleft(message)
        else:
            self._queues[topic].put(message)

        self._notify_subscribers(topic, message)
        return message.message_id

    def subscribe(self, topic: str, callback: Callable) -> None:
        """订阅主题"""
        with self._lock:
            if topic not in self._subscribers:
                self._subscribers[topic] = []
            self._subscribers[topic].append(callback)

    def unsubscribe(self, topic: str, callback: Callable) -> bool:
        """取消订阅"""
        with self._lock:
            if topic in self._subscribers and callback in self._subscribers[topic]:
                self._subscribers[topic].remove(callback)
                return True
        return False

    def consume(self, topic: str, timeout: Optional[float] = None) -> Optional[Message]:
        """消费消息"""
        if topic not in self._queues:
            return None
        try:
            message = self._queues[topic].get(timeout=timeout)
            return message
        except:
            return None

    def _notify_subscribers(self, topic: str, message: Message) -> None:
        """通知订阅者"""
        for callback in self._subscribers.get(topic, []):
            try:
                callback(message)
            except Exception:
                pass

    def get_queue_size(self, topic: str) -> int:
        """获取队列大小"""
        return self._queues.get(topic, PyQueue()).qsize()

    def list_topics(self) -> List[str]:
        """列出所有主题"""
        return list(self._queues.keys())


message_queue = MessageQueue()