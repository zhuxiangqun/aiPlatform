"""
Working Memory

Short-term memory for current task context.
"""

from collections import deque
from typing import List, Dict, Any, Optional
from dataclasses import dataclass, field
from datetime import datetime


@dataclass
class Message:
    """A message in the memory"""
    role: str  # system, user, assistant, tool
    content: str
    timestamp: datetime = field(default_factory=datetime.utcnow)
    metadata: Dict[str, Any] = field(default_factory=dict)


class WorkingMemory:
    """Working memory - maintains current task context with sliding window"""
    
    def __init__(self, max_tokens: int = 30000, max_messages: int = 20):
        self._max_tokens = max_tokens
        self._max_messages = max_messages
        self._messages: deque = deque(maxlen=max_messages)
        self._token_estimate = 0
    
    def add(self, role: str, content: str, metadata: Optional[Dict] = None):
        """Add a message to working memory"""
        message = Message(
            role=role,
            content=content,
            metadata=metadata or {}
        )
        self._messages.append(message)
        self._token_estimate += self._estimate_tokens(content)
    
    def get_context(self) -> List[Dict[str, Any]]:
        """Get current context as message list"""
        return [
            {"role": m.role, "content": m.content, **m.metadata}
            for m in self._messages
        ]
    
    def get_last_n(self, n: int) -> List[Message]:
        """Get last N messages"""
        return list(self._messages)[-n:]
    
    def clear(self):
        """Clear all messages"""
        self._messages.clear()
        self._token_estimate = 0
    
    @property
    def token_count(self) -> int:
        return self._token_estimate
    
    @property
    def message_count(self) -> int:
        return len(self._messages)
    
    def _ensure_within_limit(self):
        """Ensure memory stays within token limit"""
        while self._token_estimate > self._max_tokens * 0.9 and len(self._messages) > 2:
            # Remove oldest message
            oldest = self._messages.popleft()
            self._token_estimate -= self._estimate_tokens(oldest.content)
    
    def _estimate_tokens(self, text: str) -> int:
        """Estimate token count"""
        words = text.split()
        return int(len(words) * 1.3)


__all__ = ["WorkingMemory", "Message"]