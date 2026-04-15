"""
Memory Base Classes - 记忆系统基类
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional


class MemoryType(Enum):
    """记忆类型"""
    CONVERSATION = "conversation"      # 对话记忆
    SEMANTIC = "semantic"             # 语义记忆
    EPISODIC = "episodic"            # 情景记忆
    PROCEDURAL = "procedural"        # 程序记忆
    WORKING = "working"              # 工作记忆


class MemoryScope(Enum):
    """记忆范围"""
    SESSION = "session"              # 会话级
    USER = "user"                    # 用户级
    GLOBAL = "global"                # 全局级


@dataclass
class MemoryEntry:
    """记忆条目"""
    id: str
    content: str
    memory_type: MemoryType
    metadata: Dict[str, Any] = field(default_factory=dict)
    embeddings: Optional[List[float]] = None
    importance: float = 0.5           # 重要性 0-1
    timestamp: float = field(default_factory=lambda: datetime.now().timestamp())
    expires_at: Optional[float] = None
    
    def is_expired(self) -> bool:
        """检查是否过期"""
        if self.expires_at is None:
            return False
        return datetime.now().timestamp() > self.expires_at
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return {
            "id": self.id,
            "content": self.content,
            "memory_type": self.memory_type.value,
            "metadata": self.metadata,
            "importance": self.importance,
            "timestamp": self.timestamp,
            "expires_at": self.expires_at
        }


class MemoryBase(ABC):
    """记忆系统基类"""
    
    def __init__(self, config: Dict[str, Any] = None):
        self.config = config or {}
        self.max_size = self.config.get("max_size", 1000)
        self.ttl = self.config.get("ttl", 3600)           # 默认1小时过期
    
    @abstractmethod
    async def store(self, entry: MemoryEntry) -> str:
        """存储记忆"""
        pass
    
    @abstractmethod
    async def retrieve(self, query: str, limit: int = 10) -> List[MemoryEntry]:
        """检索记忆"""
        pass
    
    @abstractmethod
    async def delete(self, entry_id: str) -> bool:
        """删除记忆"""
        pass
    
    @abstractmethod
    async def clear(self, scope: MemoryScope = MemoryScope.SESSION) -> int:
        """清除记忆"""
        pass
    
    async def get_stats(self) -> Dict[str, Any]:
        """获取记忆统计"""
        return {
            "type": self.__class__.__name__,
            "max_size": self.max_size,
            "ttl": self.ttl
        }