"""
AgentMessage protocol — standard inter-agent communication types.

Per §5.15 of CLAUDE.md, agents communicate via typed messages, not direct
method calls. This module defines the message types and a lightweight
message bus for agent-to-agent coordination.
"""

from __future__ import annotations

import asyncio
import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional


class AgentMessageType(Enum):
    TASK_ASSIGN = "task_assign"
    PROGRESS_UPDATE = "progress_update"
    RESULT = "result"
    ERROR = "error"
    CANCEL = "cancel"
    REQUEST = "request"
    RESPONSE = "response"
    GRAPH_DELTA = "graph_delta"
    GRAPH_CONFLICT = "graph_conflict"


@dataclass
class AgentMessage:
    msg_id: str
    type: AgentMessageType
    sender_id: str
    receiver_id: str = ""
    payload: Dict[str, Any] = field(default_factory=dict)
    parent_msg_id: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "msg_id": self.msg_id,
            "type": self.type.value,
            "sender_id": self.sender_id,
            "receiver_id": self.receiver_id,
            "payload": self.payload,
            "parent_msg_id": self.parent_msg_id,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "AgentMessage":
        return cls(
            msg_id=str(data.get("msg_id", "")),
            type=AgentMessageType(str(data.get("type", "task_assign"))),
            sender_id=str(data.get("sender_id", "")),
            receiver_id=str(data.get("receiver_id", "")),
            payload=data.get("payload", {}) or {},
            parent_msg_id=data.get("parent_msg_id"),
        )


class AgentMessageBus:
    """Message bus for agent-to-agent communication with request-response protocol.

    Supports broadcast (send/receive/drain) and point-to-point request/response
    with timeout. Messages are stored in-memory; for production, replace with a
    persistent queue.
    """

    def __init__(self):
        self._inbox: Dict[str, List[AgentMessage]] = {}
        self._sent: List[AgentMessage] = []
        self._requests: Dict[str, asyncio.Future] = {}

    def send(self, msg: AgentMessage) -> None:
        target = msg.receiver_id or "broadcast"
        if target not in self._inbox:
            self._inbox[target] = []
        self._inbox[target].append(msg)
        self._sent.append(msg)

    def receive(self, agent_id: str, msg_type: Optional[AgentMessageType] = None) -> List[AgentMessage]:
        inbox = list(self._inbox.get(agent_id, []))
        if msg_type is not None:
            inbox = [m for m in inbox if m.type == msg_type]
        return inbox

    def drain(self, agent_id: str) -> List[AgentMessage]:
        msgs = self._inbox.pop(agent_id, [])
        return msgs

    def clear(self) -> None:
        self._inbox.clear()
        self._sent.clear()

    async def request(
        self,
        target_agent: str,
        sender_agent: str,
        # Pipeline Agent-to-Agent request/response protocol
        msg_type: str = "request",
        payload: Optional[Dict[str, Any]] = None,
        timeout: float = 30.0,
    ) -> Optional[Dict[str, Any]]:
        """Send a request to a specific agent and await its response.

        Returns the response payload, or None on timeout.
        """
        request_id = str(uuid.uuid4())
        self._requests[request_id] = asyncio.get_event_loop().create_future()
        msg = AgentMessage(
            msg_id=request_id,
            type=AgentMessageType.REQUEST,
            sender_id=sender_agent,
            receiver_id=target_agent,
            payload=dict(payload or {}, _request_id=request_id),
        )
        self.send(msg)
        try:
            return await asyncio.wait_for(self._requests[request_id], timeout=timeout)
        except asyncio.TimeoutError:
            self._requests.pop(request_id, None)
            return None
        finally:
            self._requests.pop(request_id, None)

    def respond(self, request_id: str, result: Dict[str, Any], sender_agent: str, target_agent: str) -> None:
        """Respond to a pending request."""
        future = self._requests.get(request_id)
        if future is not None and not future.done():
            future.set_result(result)
        msg = AgentMessage(
            msg_id=str(uuid.uuid4()),
            type=AgentMessageType.RESPONSE,
            sender_id=sender_agent,
            receiver_id=target_agent,
            payload=result,
            parent_msg_id=request_id,
        )
        self.send(msg)

    def collect_requests(self, agent_id: str) -> List[AgentMessage]:
        """Collect pending REQUEST messages for an agent (non-destructive)."""
        return self.receive(agent_id, AgentMessageType.REQUEST)


_global_bus: Optional[AgentMessageBus] = None


def get_message_bus() -> AgentMessageBus:
    """Get or create the global shared AgentMessageBus singleton."""
    global _global_bus
    if _global_bus is None:
        _global_bus = AgentMessageBus()
    return _global_bus
