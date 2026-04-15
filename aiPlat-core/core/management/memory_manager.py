"""
Memory Manager - Manages memory sessions

Provides session management and memory storage operations.
"""

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Any
from datetime import datetime
import uuid


@dataclass
class SessionInfo:
    """Session information"""
    id: str
    agent_type: str
    user_id: str
    status: str  # active, idle, ended
    session_type: str  # short_term, long_term, session
    config: Dict[str, Any]
    message_count: int
    memory_size_mb: float
    created_at: datetime
    last_activity: datetime
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class Message:
    """Session message"""
    id: str
    session_id: str
    role: str  # user, agent, system
    content: str
    metadata: Dict[str, Any]
    created_at: datetime


@dataclass
class MemoryStats:
    """Memory statistics"""
    total_sessions: int = 0
    active_sessions: int = 0
    idle_sessions: int = 0
    ended_sessions: int = 0
    total_messages: int = 0
    storage_size_mb: float = 0.0
    today_queries: int = 0


class MemoryManager:
    """
    Memory Manager - Manages memory sessions
    
    Provides:
    - Session CRUD operations
    - Message management
    - Memory statistics
    """
    
    def __init__(self, seed: bool = True):
        self._sessions: Dict[str, SessionInfo] = {}
        self._messages: Dict[str, List[Message]] = {}
        self._stats = MemoryStats()
        if seed:
            self._seed_data()
    
    def _seed_data(self):
        now = datetime.utcnow()
        demo_sessions = [
            ("sess-react-001", "react", "user-001", "active", "short_term", {"model": "gpt-4"}),
            ("sess-rag-001", "rag", "user-002", "active", "long_term", {"model": "gpt-4", "retrieval_count": 5}),
            ("sess-plan-001", "plan", "user-001", "idle", "session", {"model": "gpt-4"}),
            ("sess-conv-001", "conversational", "user-003", "idle", "short_term", {"model": "gpt-3.5-turbo"}),
            ("sess-tool-001", "tool", "user-002", "ended", "session", {"model": "gpt-3.5-turbo"}),
        ]
        for sid, agent_type, user_id, status, stype, config in demo_sessions:
            self._sessions[sid] = SessionInfo(
                id=sid, agent_type=agent_type, user_id=user_id, status=status,
                session_type=stype, config=config, message_count=3 if status != "ended" else 0,
                memory_size_mb=round(0.1 if status != "ended" else 0, 2), created_at=now, last_activity=now, metadata={}
            )
            self._messages[sid] = [
                Message(id=f"{sid}-1", session_id=sid, role="user", content="你好，请帮我完成一个任务", metadata={}, created_at=now),
                Message(id=f"{sid}-2", session_id=sid, role="agent", content="好的，我来帮你。请告诉我具体需求。", metadata={}, created_at=now),
                Message(id=f"{sid}-3", session_id=sid, role="user", content="我需要一个数据分析报告", metadata={}, created_at=now),
            ] if status != "ended" else []
        self._stats = MemoryStats(
            total_sessions=len(demo_sessions), active_sessions=2,
            idle_sessions=2, ended_sessions=1, total_messages=0,
            storage_size_mb=0.0, today_queries=0
        )
    
    async def create_session(
        self,
        agent_type: str,
        user_id: str,
        session_type: str = "short_term",
        config: Optional[Dict[str, Any]] = None,
        metadata: Optional[Dict[str, Any]] = None
    ) -> SessionInfo:
        """Create a new session"""
        session_id = f"sess-{uuid.uuid4().hex[:8]}"
        now = datetime.utcnow()
        
        session = SessionInfo(
            id=session_id,
            agent_type=agent_type,
            user_id=user_id,
            status="active",
            session_type=session_type,
            config=config or {"max_history": 100, "recall_count": 5},
            message_count=0,
            memory_size_mb=0.0,
            created_at=now,
            last_activity=now,
            metadata=metadata or {}
        )
        
        self._sessions[session_id] = session
        self._messages[session_id] = []
        self._stats.total_sessions += 1
        self._stats.active_sessions += 1
        
        return session
    
    async def get_session(self, session_id: str) -> Optional[SessionInfo]:
        """Get session by ID"""
        return self._sessions.get(session_id)
    
    async def list_sessions(
        self,
        status: Optional[str] = None,
        agent_type: Optional[str] = None,
        limit: int = 100,
        offset: int = 0
    ) -> List[SessionInfo]:
        """List sessions with filters"""
        sessions = list(self._sessions.values())
        
        if status:
            sessions = [s for s in sessions if s.status == status]
        if agent_type:
            sessions = [s for s in sessions if s.agent_type == agent_type]
        
        return sessions[offset:offset + limit]
    
    async def delete_session(self, session_id: str) -> bool:
        """Delete session"""
        if session_id not in self._sessions:
            return False
        
        session = self._sessions[session_id]
        self._stats.total_sessions -= 1
        if session.status == "active":
            self._stats.active_sessions -= 1
        elif session.status == "idle":
            self._stats.idle_sessions -= 1
        
        del self._sessions[session_id]
        del self._messages[session_id]
        
        return True
    
    async def add_message(
        self,
        session_id: str,
        role: str,
        content: str,
        metadata: Optional[Dict[str, Any]] = None
    ) -> Message:
        """Add message to session"""
        message_id = f"msg-{uuid.uuid4().hex[:8]}"
        
        message = Message(
            id=message_id,
            session_id=session_id,
            role=role,
            content=content,
            metadata=metadata or {},
            created_at=datetime.utcnow()
        )
        
        self._messages[session_id].append(message)
        
        # Update session
        session = self._sessions[session_id]
        session.message_count += 1
        session.last_activity = datetime.utcnow()
        self._stats.total_messages += 1
        
        return message
    
    async def get_messages(
        self,
        session_id: str,
        limit: int = 100,
        offset: int = 0
    ) -> List[Message]:
        """Get messages for session"""
        messages = self._messages.get(session_id, [])
        return messages[offset:offset + limit]
    
    async def get_context(self, session_id: str) -> Dict[str, Any]:
        """Get session context"""
        session = self._sessions.get(session_id)
        if not session:
            return {}
        
        messages = self._messages.get(session_id, [])
        
        return {
            "session_id": session_id,
            "agent_type": session.agent_type,
            "user_id": session.user_id,
            "messages": [
                {"role": m.role, "content": m.content}
                for m in messages
            ]
        }
    
    async def get_stats(self) -> MemoryStats:
        """Get memory statistics"""
        return self._stats
    
    def get_session_count(self) -> Dict[str, int]:
        """Get session count by status"""
        return {
            "total": self._stats.total_sessions,
            "active": self._stats.active_sessions,
            "idle": self._stats.idle_sessions,
            "ended": self._stats.ended_sessions
        }
    
    async def search_memory(self, query: str, limit: int = 10) -> List[Dict[str, Any]]:
        """Search memory for matching messages"""
        query_lower = query.lower()
        results = []
        
        for session_id, messages in self._messages.items():
            for msg in messages:
                if query_lower in msg.content.lower():
                    results.append({
                        "session_id": session_id,
                        "role": msg.role,
                        "content": msg.content[:200],
                        "score": 1.0,
                        "timestamp": msg.created_at.isoformat() if msg.created_at else None
                    })
        
        return results[:limit]
    
    async def cleanup_memory(self, max_messages: int = 100) -> int:
        """Cleanup old messages, keeping only the most recent max_messages per session"""
        cleaned = 0
        for session_id, messages in self._messages.items():
            if len(messages) > max_messages:
                self._messages[session_id] = messages[-max_messages:]
                cleaned += 1
        return cleaned