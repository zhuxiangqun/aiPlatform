"""
Session Management - 会话管理
"""

import asyncio
import uuid
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Dict, Optional

from .short_term import ConversationMemory
from .base import MemoryScope


@dataclass
class Session:
    """会话"""
    id: str
    user_id: str
    created_at: float
    updated_at: float
    metadata: Dict[str, Any]
    state: Dict[str, Any]
    
    def is_expired(self, ttl: int = 3600) -> bool:
        """检查是否过期"""
        return datetime.now().timestamp() - self.updated_at > ttl
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "user_id": self.user_id,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "metadata": self.metadata,
            "state": self.state
        }


from dataclasses import dataclass


class SessionManager:
    """会话管理器"""
    
    def __init__(self, config: Dict[str, Any] = None):
        self.config = config or {}
        self.session_ttl = self.config.get("session_ttl", 3600)  # 1小时
        self.max_sessions = self.config.get("max_sessions", 1000)
        
        self._sessions: Dict[str, Session] = {}
        self._user_sessions: Dict[str, set] = {}  # user_id -> session_ids
        self._conversation_memories: Dict[str, ConversationMemory] = {}
        self._lock = asyncio.Lock()
    
    async def create_session(self, user_id: str, metadata: Dict[str, Any] = None) -> Session:
        """创建新会话"""
        async with self._lock:
            session_id = str(uuid.uuid4())
            now = datetime.now().timestamp()
            
            session = Session(
                id=session_id,
                user_id=user_id,
                created_at=now,
                updated_at=now,
                metadata=metadata or {},
                state={}
            )
            
            self._sessions[session_id] = session
            
            if user_id not in self._user_sessions:
                self._user_sessions[user_id] = set()
            self._user_sessions[user_id].add(session_id)
            
            # 创建对话内存
            self._conversation_memories[session_id] = ConversationMemory()
            self._conversation_memories[session_id].set_session(session_id)
            
            # 清理旧会话
            await self._cleanup_user_sessions(user_id)
            
            return session
    
    async def get_session(self, session_id: str) -> Optional[Session]:
        """获取会话"""
        async with self._lock:
            session = self._sessions.get(session_id)
            if session and session.is_expired(self.session_ttl):
                await self.delete_session(session_id)
                return None
            return session
    
    async def update_session(self, session_id: str, state: Dict[str, Any] = None,
                            metadata: Dict[str, Any] = None) -> bool:
        """更新会话"""
        async with self._lock:
            session = self._sessions.get(session_id)
            if not session:
                return False
            
            session.updated_at = datetime.now().timestamp()
            
            if state:
                session.state.update(state)
            if metadata:
                session.metadata.update(metadata)
            
            return True
    
    async def delete_session(self, session_id: str) -> bool:
        """删除会话"""
        async with self._lock:
            if session_id not in self._sessions:
                return False
            
            session = self._sessions[session_id]
            user_id = session.user_id
            
            del self._sessions[session_id]
            
            if user_id in self._user_sessions:
                self._user_sessions[user_id].discard(session_id)
            
            if session_id in self._conversation_memories:
                del self._conversation_memories[session_id]
            
            return True
    
    async def get_user_sessions(self, user_id: str) -> list[Session]:
        """获取用户的所有会话"""
        async with self._lock:
            session_ids = self._user_sessions.get(user_id, set())
            sessions = []
            
            for sid in session_ids:
                session = self._sessions.get(sid)
                if session and not session.is_expired(self.session_ttl):
                    sessions.append(session)
            
            return sorted(sessions, key=lambda s: s.updated_at, reverse=True)
    
    async def get_conversation_memory(self, session_id: str) -> Optional[ConversationMemory]:
        """获取会话的对话内存"""
        return self._conversation_memories.get(session_id)
    
    async def _cleanup_user_sessions(self, user_id: str) -> int:
        """清理用户的旧会话"""
        if user_id not in self._user_sessions:
            return 0
        
        session_ids = list(self._user_sessions[user_id])
        
        if len(session_ids) <= self.max_sessions:
            return 0
        
        # 按更新时间排序，删除最旧的
        sessions_to_delete = sorted(
            [self._sessions[sid] for sid in session_ids if sid in self._sessions],
            key=lambda s: s.updated_at
        )[:-self.max_sessions]
        
        count = 0
        for session in sessions_to_delete:
            await self.delete_session(session.id)
            count += 1
        
        return count
    
    async def get_stats(self) -> Dict[str, Any]:
        """获取会话统计"""
        async with self._lock:
            active_sessions = sum(
                1 for s in self._sessions.values()
                if not s.is_expired(self.session_ttl)
            )
            
            return {
                "total_sessions": len(self._sessions),
                "active_sessions": active_sessions,
                "unique_users": len(self._user_sessions),
                "max_sessions": self.max_sessions
            }
    
    async def cleanup_expired(self) -> int:
        """清理所有过期会话"""
        async with self._lock:
            expired_ids = [
                sid for sid, session in self._sessions.items()
                if session.is_expired(self.session_ttl)
            ]
            
            for sid in expired_ids:
                await self.delete_session(sid)
            
            return len(expired_ids)