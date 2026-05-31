"""
Working Memory

Short-term memory for current task context.
"""

from collections import deque
from typing import List, Dict, Any, Optional
from dataclasses import dataclass, field
from datetime import datetime, timezone


@dataclass
class Message:
    """A message in the memory"""
    role: str  # system, user, assistant, tool
    content: str
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
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
        self._ensure_within_limit()
    
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

    def snapshot(self) -> Dict[str, Any]:
        import copy
        return {
            "messages": copy.deepcopy(list(self._messages)),
            "token_estimate": self._token_estimate,
        }

    def restore(self, snap: Dict[str, Any]) -> None:
        self._messages = deque(snap.get("messages", []), maxlen=self._max_messages)
        self._token_estimate = snap.get("token_estimate", 0)
    
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
        """Estimate token count. ~3.5 chars per token on average for mixed CJK/English.
        Falls back to tiktoken if available (preferred: ~30x more accurate)."""
        try:
            import tiktoken
            enc = tiktoken.get_encoding("cl100k_base")
            return len(enc.encode(text))
        except Exception:
            return max(1, int(len(text) / 3.5))


__all__ = ["WorkingMemory", "Message"]