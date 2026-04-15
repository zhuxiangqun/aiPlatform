"""
Tests for Session and SessionManager.

Tests cover:
- Session creation, update, deletion
- User session management
- Conversation memory integration
- Session expiration and cleanup
"""

import pytest
from datetime import datetime, timedelta
from unittest.mock import AsyncMock, MagicMock

from harness.memory.session import Session, SessionManager


class TestSession:
    """Tests for Session dataclass."""
    
    def test_session_creation(self):
        """Test creating a session."""
        session = Session(
            id="session-1",
            user_id="user-1",
            created_at=datetime.now().timestamp(),
            updated_at=datetime.now().timestamp(),
            metadata={"key": "value"},
            state={"context": "test"}
        )
        
        assert session.id == "session-1"
        assert session.user_id == "user-1"
        assert session.metadata["key"] == "value"
        assert session.state["context"] == "test"
    
    def test_session_is_expired_not_expired(self):
        """Test session expiration check when not expired."""
        session = Session(
            id="session-1",
            user_id="user-1",
            created_at=datetime.now().timestamp(),
            updated_at=datetime.now().timestamp(),
            metadata={},
            state={}
        )
        
        assert session.is_expired(ttl=3600) is False
    
    def test_session_is_expired_expired(self):
        """Test session expiration check when expired."""
        session = Session(
            id="session-1",
            user_id="user-1",
            created_at=datetime.now().timestamp() - 7200,  # 2 hours ago
            updated_at=datetime.now().timestamp() - 7200,
            metadata={},
            state={}
        )
        
        assert session.is_expired(ttl=3600) is True
    
    def test_session_to_dict(self):
        """Test converting session to dict."""
        now = datetime.now().timestamp()
        session = Session(
            id="session-1",
            user_id="user-1",
            created_at=now,
            updated_at=now,
            metadata={"key": "value"},
            state={"context": "test"}
        )
        
        result = session.to_dict()
        
        assert result["id"] == "session-1"
        assert result["user_id"] == "user-1"
        assert result["created_at"] == now
        assert result["metadata"]["key"] == "value"
        assert result["state"]["context"] == "test"


class TestSessionManager:
    """Tests for SessionManager class."""
    
    def test_init_default_config(self):
        """Test SessionManager initialization with default config."""
        manager = SessionManager()
        
        assert manager.session_ttl == 3600
        assert manager.max_sessions == 1000
    
    def test_init_custom_config(self):
        """Test SessionManager initialization with custom config."""
        manager = SessionManager({"session_ttl": 7200, "max_sessions": 500})
        
        assert manager.session_ttl == 7200
        assert manager.max_sessions == 500
    
    @pytest.mark.asyncio
    async def test_create_session(self):
        """Test creating a session."""
        manager = SessionManager()
        
        session = await manager.create_session("user-1", {"source": "test"})
        
        assert session.id is not None
        assert session.user_id == "user-1"
        assert session.metadata["source"] == "test"
    
    @pytest.mark.asyncio
    async def test_create_session_creates_conversation_memory(self):
        """Test that creating session creates conversation memory."""
        manager = SessionManager()
        
        session = await manager.create_session("user-1")
        
        conv_memory = await manager.get_conversation_memory(session.id)
        
        assert conv_memory is not None
        assert conv_memory.session_id == session.id
    
    @pytest.mark.asyncio
    async def test_get_session(self):
        """Test getting a session."""
        manager = SessionManager()
        
        created = await manager.create_session("user-1")
        retrieved = await manager.get_session(created.id)
        
        assert retrieved is not None
        assert retrieved.id == created.id
    
    @pytest.mark.asyncio
    async def test_get_session_nonexistent(self):
        """Test getting a nonexistent session."""
        manager = SessionManager()
        
        session = await manager.get_session("nonexistent")
        
        assert session is None
    
    @pytest.mark.asyncio
    async def test_update_session(self):
        """Test updating a session."""
        manager = SessionManager()
        
        session = await manager.create_session("user-1")
        
        updated = await manager.update_session(
            session.id,
            state={"context": "new"},
            metadata={"key": "value"}
        )
        
        assert updated is True
        
        retrieved = await manager.get_session(session.id)
        assert retrieved.state["context"] == "new"
        assert retrieved.metadata["key"] == "value"
    
    @pytest.mark.asyncio
    async def test_update_session_nonexistent(self):
        """Test updating a nonexistent session."""
        manager = SessionManager()
        
        updated = await manager.update_session("nonexistent", state={"key": "value"})
        
        assert updated is False
    
    @pytest.mark.asyncio
    async def test_delete_session(self):
        """Test deleting a session."""
        manager = SessionManager()
        
        session = await manager.create_session("user-1")
        
        deleted = await manager.delete_session(session.id)
        
        assert deleted is True
        
        retrieved = await manager.get_session(session.id)
        assert retrieved is None
    
    @pytest.mark.asyncio
    async def test_delete_session_nonexistent(self):
        """Test deleting a nonexistent session."""
        manager = SessionManager()
        
        deleted = await manager.delete_session("nonexistent")
        
        assert deleted is False
    
    @pytest.mark.asyncio
    async def test_get_user_sessions(self):
        """Test getting all sessions for a user."""
        manager = SessionManager()
        
        await manager.create_session("user-1")
        await manager.create_session("user-1")
        await manager.create_session("user-2")
        
        sessions = await manager.get_user_sessions("user-1")
        
        assert len(sessions) == 2
    
    @pytest.mark.asyncio
    async def test_get_user_sessions_sorted(self):
        """Test that user sessions are sorted by update time."""
        manager = SessionManager()
        
        s1 = await manager.create_session("user-1")
        import asyncio
        await asyncio.sleep(0.01)  # Ensure different timestamps
        s2 = await manager.create_session("user-1")
        
        sessions = await manager.get_user_sessions("user-1")
        
        # Most recent first
        assert sessions[0].id == s2.id
        assert sessions[1].id == s1.id
    
    @pytest.mark.asyncio
    async def test_cleanup_user_sessions(self):
        """Test cleanup of old sessions."""
        manager = SessionManager({"max_sessions": 2})
        
        # Create more than max_sessions
        s1 = await manager.create_session("user-1")
        s2 = await manager.create_session("user-1")
        s3 = await manager.create_session("user-1")
        
        # Should only keep 2 most recent
        sessions = await manager.get_user_sessions("user-1")
        
        assert len(sessions) <= 2
    
    @pytest.mark.asyncio
    async def test_get_conversation_memory(self):
        """Test getting conversation memory for a session."""
        manager = SessionManager()
        
        session = await manager.create_session("user-1")
        
        memory = await manager.get_conversation_memory(session.id)
        
        assert memory is not None
    
    @pytest.mark.asyncio
    async def test_get_conversation_memory_nonexistent_session(self):
        """Test getting conversation memory for nonexistent session."""
        manager = SessionManager()
        
        memory = await manager.get_conversation_memory("nonexistent")
        
        assert memory is None
    
    @pytest.mark.asyncio
    async def test_get_stats(self):
        """Test getting session statistics."""
        manager = SessionManager()
        
        await manager.create_session("user-1")
        await manager.create_session("user-1")
        await manager.create_session("user-2")
        
        stats = await manager.get_stats()
        
        assert stats["total_sessions"] == 3
        assert stats["active_sessions"] == 3
        assert stats["unique_users"] == 2
    
    @pytest.mark.asyncio
    async def test_cleanup_expired(self):
        """Test cleanup of expired sessions."""
        manager = SessionManager({"session_ttl": 0.1})  # Very short TTL
        
        session = await manager.create_session("user-1")
        
        # Wait for expiration
        import asyncio
        await asyncio.sleep(0.2)
        
        count = await manager.cleanup_expired()
        
        assert count >= 1
    
    @pytest.mark.asyncio
    async def test_delete_session_removes_conversation_memory(self):
        """Test that deleting session removes conversation memory."""
        manager = SessionManager()
        
        session = await manager.create_session("user-1")
        session_id = session.id
        
        await manager.delete_session(session_id)
        
        memory = await manager.get_conversation_memory(session_id)
        
        assert memory is None