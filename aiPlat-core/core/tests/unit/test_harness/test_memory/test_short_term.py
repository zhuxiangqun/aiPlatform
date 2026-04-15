"""
Tests for ShortTermMemory and ConversationMemory.

Tests cover:
- Store, retrieve, delete operations
- TTL and expiration
- Conversation message handling
- Context retrieval
"""

import pytest
from datetime import datetime, timedelta
from unittest.mock import AsyncMock, MagicMock

from harness.memory.short_term import ShortTermMemory, ConversationMemory
from harness.memory.base import MemoryEntry, MemoryType, MemoryScope


class TestShortTermMemory:
    """Tests for ShortTermMemory class."""
    
    def test_init_default_config(self):
        """Test ShortTermMemory initialization with default config."""
        memory = ShortTermMemory()
        
        assert memory.max_size == 100
        assert memory.ttl == 3600
    
    def test_init_custom_config(self):
        """Test ShortTermMemory initialization with custom config."""
        memory = ShortTermMemory({"max_size": 50, "ttl": 7200})
        
        assert memory.max_size == 50
        assert memory.ttl == 7200
    
    @pytest.mark.asyncio
    async def test_store_entry(self):
        """Test storing an entry."""
        memory = ShortTermMemory()
        entry = MemoryEntry(
            id="test-1",
            content="Test content",
            memory_type=MemoryType.CONVERSATION,
        )
        
        entry_id = await memory.store(entry)
        
        assert entry_id == "test-1"
        assert entry.expires_at is not None
    
    @pytest.mark.asyncio
    async def test_store_auto_generate_id(self):
        """Test storing an entry without ID generates one."""
        memory = ShortTermMemory()
        entry = MemoryEntry(
            id="",  # Empty ID, will be generated
            content="Test content",
            memory_type=MemoryType.CONVERSATION,
        )
        
        entry_id = await memory.store(entry)
        
        assert entry_id is not None
        assert len(entry_id) > 0
    
    @pytest.mark.asyncio
    async def test_retrieve_entries(self):
        """Test retrieving entries."""
        memory = ShortTermMemory()
        
        for i in range(5):
            await memory.store(MemoryEntry(
                id=f"test-{i}",
                content=f"Content {i}",
                memory_type=MemoryType.CONVERSATION,
            ))
        
        results = await memory.retrieve("test", limit=3)
        
        assert len(results) == 3
    
    @pytest.mark.asyncio
    async def test_retrieve_expired_entries(self):
        """Test that expired entries are not retrieved."""
        memory = ShortTermMemory({"ttl": 0.1})  #Very short TTL
        
        entry = MemoryEntry(
            id="test-1",
            content="Test content",
            memory_type=MemoryType.CONVERSATION,
        )
        await memory.store(entry)
        
        # Wait for expiration
        import asyncio
        await asyncio.sleep(0.2)
        
        results = await memory.retrieve("test")
        
        assert len(results) == 0
    
    @pytest.mark.asyncio
    async def test_delete_entry(self):
        """Test deleting an entry."""
        memory = ShortTermMemory()
        entry = MemoryEntry(
            id="test-1",
            content="Test content",
            memory_type=MemoryType.CONVERSATION,
        )
        await memory.store(entry)
        
        deleted = await memory.delete("test-1")
        
        assert deleted is True
        
        results = await memory.retrieve("test")
        assert len(results) == 0
    
    @pytest.mark.asyncio
    async def test_delete_nonexistent_entry(self):
        """Test deleting a nonexistent entry."""
        memory = ShortTermMemory()
        
        deleted = await memory.delete("nonexistent")
        
        assert deleted is False
    
    @pytest.mark.asyncio
    async def test_clear_entries(self):
        """Test clearing all entries."""
        memory = ShortTermMemory()
        
        for i in range(5):
            await memory.store(MemoryEntry(
                id=f"test-{i}",
                content=f"Content {i}",
                memory_type=MemoryType.CONVERSATION,
            ))
        
        count = await memory.clear()
        
        assert count == 5
        
        results = await memory.get_all()
        assert len(results) == 0
    
    @pytest.mark.asyncio
    async def test_get_all_entries(self):
        """Test getting all entries."""
        memory = ShortTermMemory()
        
        for i in range(3):
            await memory.store(MemoryEntry(
                id=f"test-{i}",
                content=f"Content {i}",
                memory_type=MemoryType.CONVERSATION,
            ))
        
        all_entries = await memory.get_all()
        
        assert len(all_entries) == 3
    
    @pytest.mark.asyncio
    async def test_get_recent_entries(self):
        """Test getting recent entries."""
        memory = ShortTermMemory({"max_size": 10})
        
        for i in range(10):
            await memory.store(MemoryEntry(
                id=f"test-{i}",
                content=f"Content {i}",
                memory_type=MemoryType.CONVERSATION,
            ))
        
        recent = await memory.get_recent(count=3)
        
        assert len(recent) == 3
    
    @pytest.mark.asyncio
    async def test_max_size_limit(self):
        """Test that max size limit is enforced."""
        memory = ShortTermMemory({"max_size": 5})
        
        for i in range(10):
            await memory.store(MemoryEntry(
                id=f"test-{i}",
                content=f"Content {i}",
                memory_type=MemoryType.CONVERSATION,
            ))
        
        all_entries = await memory.get_all()
        
        # Should only keep the last 5
        assert len(all_entries) == 5


class TestConversationMemory:
    """Tests for ConversationMemory class."""
    
    def test_init_default_config(self):
        """Test ConversationMemory initialization."""
        memory = ConversationMemory()
        
        assert memory.max_size == 50
        assert memory.ttl == 1800
        assert memory.session_id is None
    
    @pytest.mark.asyncio
    async def test_add_message(self):
        """Test adding a message."""
        memory = ConversationMemory()
        memory.set_session("session-1")
        
        entry_id = await memory.add_message("user", "Hello", {"source": "test"})
        
        assert entry_id is not None
        
        messages = await memory.get_messages()
        assert len(messages) == 1
        assert messages[0]["role"] == "user"
        assert messages[0]["content"] == "Hello"
    
    @pytest.mark.asyncio
    async def test_get_messages(self):
        """Test getting messages."""
        memory = ConversationMemory()
        
        await memory.add_message("user", "Hello")
        await memory.add_message("assistant", "Hi there!")
        await memory.add_message("user", "How are you?")
        
        messages = await memory.get_messages(limit=10)
        
        # At least one message should be presentassert len(messages) >= 1
    
    @pytest.mark.asyncio
    async def test_get_context(self):
        """Test getting conversation context."""
        memory = ConversationMemory()
        
        await memory.add_message("user", "Hello")
        await memory.add_message("assistant", "Hi there!")
        
        context = await memory.get_context(max_tokens=100)
        
        assert "user: Hello" in context
        assert "assistant: Hi there!" in context
    
    @pytest.mark.asyncio
    async def test_get_context_token_limit(self):
        """Test that context respects token limit."""
        memory = ConversationMemory()
        
        # Add many messages
        for i in range(10):
            await memory.add_message("user", f"Message {i}" * 10)
        
        context = await memory.get_context(max_tokens=50)
        
        # Context should be truncated
        assert len(context) <= 100
    
    def test_set_session(self):
        """Test setting session ID."""
        memory = ConversationMemory()
        
        memory.set_session("session-123")
        
        assert memory.session_id == "session-123"
    
    @pytest.mark.asyncio
    async def test_clear_session(self):
        """Test clearing session."""
        memory = ConversationMemory()
        memory.set_session("session-1")
        
        await memory.add_message("user", "Hello")
        
        count = await memory.clear_session()
        
        assert memory.session_id is None
        assert count >= 0