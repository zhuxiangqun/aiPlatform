from typing import Dict, Any, Optional, Callable, List, Awaitable
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
import asyncio
import aiohttp


class PushDestination(Enum):
    WEBHOOK = "webhook"
    KAFKA = "kafka"
    RABBITMQ = "rabbitmq"
    REDIS = "redis"
    S3 = "s3"
    CUSTOM = "custom"


class PushStatus(Enum):
    PENDING = "pending"
    SENT = "sent"
    FAILED = "failed"
    RETRYING = "retrying"


@dataclass
class PushTarget:
    name: str
    destination: PushDestination
    endpoint: str
    enabled: bool = True
    retry_count: int = 3
    timeout_seconds: float = 30.0
    headers: Dict[str, str] = field(default_factory=dict)
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class PushMessage:
    id: str
    target: PushTarget
    payload: Dict[str, Any]
    status: PushStatus = PushStatus.PENDING
    created_at: datetime = field(default_factory=datetime.now)
    sent_at: Optional[datetime] = None
    error: Optional[str] = None
    retry_attempts: int = 0


PushSender = Callable[[PushTarget, Dict[str, Any]], Awaitable[bool]]


class PushManager:
    def __init__(self, max_queue_size: int = 1000):
        self.max_queue_size = max_queue_size
        self._targets: Dict[str, PushTarget] = {}
        self._queue: asyncio.Queue[PushMessage] = asyncio.Queue(maxsize=max_queue_size)
        self._running = False
        self._processing_task: Optional[asyncio.Task] = None
        self._custom_senders: Dict[PushDestination, PushSender] = {}

    def register_target(
        self,
        name: str,
        destination: PushDestination,
        endpoint: str,
        enabled: bool = True,
        retry_count: int = 3,
        timeout_seconds: float = 30.0,
        headers: Optional[Dict[str, str]] = None,
        **metadata,
    ):
        target = PushTarget(
            name=name,
            destination=destination,
            endpoint=endpoint,
            enabled=enabled,
            retry_count=retry_count,
            timeout_seconds=timeout_seconds,
            headers=headers or {},
            metadata=metadata,
        )
        self._targets[name] = target
        return target

    def remove_target(self, name: str) -> bool:
        if name in self._targets:
            del self._targets[name]
            return True
        return False

    def get_target(self, name: str) -> Optional[PushTarget]:
        return self._targets.get(name)

    def register_sender(self, destination: PushDestination, sender: PushSender):
        self._custom_senders[destination] = sender

    async def push(
        self,
        target_name: str,
        payload: Dict[str, Any],
    ) -> bool:
        target = self._targets.get(target_name)
        if not target or not target.enabled:
            return False

        message = PushMessage(
            id=f"push_{target_name}_{datetime.now().timestamp()}",
            target=target,
            payload=payload,
        )

        try:
            self._queue.put_nowait(message)
        except asyncio.QueueFull:
            return False
        return True

    async def emit(
        self,
        target_name: str,
        event_type: str,
        data: Dict[str, Any],
    ):
        payload = {
            "event_type": event_type,
            "timestamp": datetime.now().isoformat(),
            "data": data,
        }
        await self.push(target_name, payload)

    async def start(self):
        if self._running:
            return
        self._running = True
        self._processing_task = asyncio.create_task(self._process_messages())

    async def stop(self):
        self._running = False
        if self._processing_task:
            await self._processing_task

    async def _process_messages(self):
        while self._running:
            try:
                message = await asyncio.wait_for(self._queue.get(), timeout=1.0)
            except asyncio.TimeoutError:
                continue
            await self._send_message(message)

    async def _send_message(self, message: PushMessage):
        target = message.target

        if target.destination == PushDestination.WEBHOOK:
            success = await self._send_webhook(target, message.payload)
        elif target.destination in self._custom_senders:
            sender = self._custom_senders[target.destination]
            success = await sender(target, message.payload)
        else:
            success = False
            message.error = f"No sender for destination {target.destination}"

        if success:
            message.status = PushStatus.SENT
            message.sent_at = datetime.now()
        else:
            if message.retry_attempts < target.retry_count:
                message.status = PushStatus.RETRYING
                message.retry_attempts += 1
                await asyncio.sleep(2 ** message.retry_attempts)
                await self._queue.put(message)
            else:
                message.status = PushStatus.FAILED

    async def _send_webhook(self, target: PushTarget, payload: Dict[str, Any]) -> bool:
        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    target.endpoint,
                    json=payload,
                    headers=target.headers,
                    timeout=aiohttp.ClientTimeout(total=target.timeout_seconds),
                ) as resp:
                    return resp.status < 400
        except Exception:
            return False

    def get_queue_size(self) -> int:
        return self._queue.qsize()

    def get_target_status(self) -> Dict[str, Dict[str, Any]]:
        return {
            name: {
                "enabled": target.enabled,
                "destination": target.destination.value,
                "endpoint": target.endpoint,
            }
            for name, target in self._targets.items()
        }


class PushFeedbackHandler:
    def __init__(self, push_manager: PushManager, target_name: str):
        self.push_manager = push_manager
        self.target_name = target_name

    async def handle(self, event_type: str, data: Dict[str, Any]):
        await self.push_manager.emit(self.target_name, event_type, data)


def create_push_manager(max_queue_size: int = 1000) -> PushManager:
    return PushManager(max_queue_size)


_push_manager = PushManager()


def get_push_manager() -> PushManager:
    return _push_manager