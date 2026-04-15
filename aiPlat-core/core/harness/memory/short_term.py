"""
Short-term Memory - 短期记忆
"""

import asyncio
import uuid
from collections import deque
from datetime import datetime
from typing import Any, Dict, List, Optional

from .base import MemoryBase, MemoryEntry, MemoryScope, MemoryType


class ShortTermMemory(MemoryBase):
    """短期记忆 - 工作记忆、快速存取"""
    
    def __init__(self, config: Dict[str, Any] = None):
        super().__init__(config)
        self.max_size = self.config.get("max_size", 100)
        self.ttl = self.config.get("ttl", 3600)           # 1小时
        self._storage: deque[MemoryEntry] = deque(maxlen=self.max_size)
        self._lock = asyncio.Lock()
    
    async def store(self, entry: MemoryEntry) -> str:
        """存储短期记忆"""
        async with self._lock:
            entry.id = entry.id or str(uuid.uuid4())
            entry.expires_at = datetime.now().timestamp() + self.ttl
            self._storage.append(entry)
            return entry.id
    
    async def retrieve(self, query: str, limit: int = 10) -> List[MemoryEntry]:
        """检索短期记忆（返回最近的记忆）"""
        async with self._lock:
            valid_entries = [
                e for e in self._storage 
                if not e.is_expired()
            ]
            return valid_entries[-limit:]
    
    async def delete(self, entry_id: str) -> bool:
        """删除记忆"""
        async with self._lock:
            for i, entry in enumerate(self._storage):
                if entry.id == entry_id:
                    del self._storage[i]
                    return True
            return False
    
    async def clear(self, scope: MemoryScope = MemoryScope.SESSION) -> int:
        """清除短期记忆"""
        async with self._lock:
            count = len(self._storage)
            self._storage.clear()
            return count
    
    async def get_all(self) -> List[MemoryEntry]:
        """获取所有短期记忆"""
        async with self._lock:
            return list(self._storage)
    
    async def get_recent(self, count: int = 10) -> List[MemoryEntry]:
        """获取最近的N条记忆"""
        async with self._lock:
            return list(self._storage)[-count:]


class ConversationMemory(ShortTermMemory):
    """对话记忆 - 管理对话上下文"""
    
    def __init__(self, config: Dict[str, Any] = None):
        config = config or {}
        config.setdefault("max_size", 50)
        config.setdefault("ttl", 1800)       # 30分钟
        super().__init__(config)
        self.session_id: Optional[str] = None
    
    async def add_message(self, role: str, content: str, metadata: Dict[str, Any] = None) -> str:
        """添加对话消息"""
        entry = MemoryEntry(
            id=str(uuid.uuid4()),
            content=content,
            memory_type=MemoryType.CONVERSATION,
            metadata={
                "role": role,
                "session_id": self.session_id,
                **(metadata or {})
            },
            importance=0.8
        )
        return await self.store(entry)
    
    async def get_messages(self, limit: int = 20) -> List[Dict[str, Any]]:
        """获取对话消息历史"""
        entries = await self.retrieve("", limit=limit)
        return [
            {
                "role": e.metadata.get("role", "user"),
                "content": e.content,
                "timestamp": e.timestamp
            }
            for e in entries
        ]
    
    async def get_context(self, max_tokens: int = 2000) -> str:
        """获取对话上下文（限制token数）"""
        messages = await self.get_messages(limit=50)
        context_parts = []
        total_length = 0
        
        for msg in reversed(messages):
            msg_str = f"{msg['role']}: {msg['content']}\n"
            if total_length + len(msg_str) > max_tokens:
                break
            context_parts.append(msg_str)
            total_length += len(msg_str)
        
        return "".join(reversed(context_parts))
    
    def set_session(self, session_id: str):
        """设置会话ID"""
        self.session_id = session_id
    
    async def clear_session(self) -> int:
        """清除当前会话"""
        self.session_id = None
        return await self.clear(MemoryScope.SESSION)