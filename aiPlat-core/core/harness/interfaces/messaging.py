"""
AgentMessage protocol — standard inter-agent communication types.

Per §5.15 of CLAUDE.md, agents communicate via typed messages, not direct
method calls. This module defines the message types and a lightweight
message bus for agent-to-agent coordination.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional


class AgentMessageType(Enum):
    TASK_ASSIGN = "task_assign"
    PROGRESS_UPDATE = "progress_update"
    RESULT = "result"
    ERROR = "error"
    CANCEL = "cancel"


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
    """Lightweight message bus for agent-to-agent communication.

    Stores messages in memory. For production, replace with a persistent
    queue backed by the execution store.
    """

    def __init__(self):
        self._inbox: Dict[str, List[AgentMessage]] = {}   # agent_id → messages
        self._sent: List[AgentMessage] = []

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
        """Consume and remove all messages for an agent."""
        msgs = self._inbox.pop(agent_id, [])
        return msgs

    def clear(self) -> None:
        self._inbox.clear()
        self._sent.clear()
