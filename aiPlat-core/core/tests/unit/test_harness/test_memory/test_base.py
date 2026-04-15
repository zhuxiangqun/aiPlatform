"""
Tests for memory base classes.

Tests cover:
- MemoryType enum
- MemoryScope enum
- MemoryEntry dataclass
- MemoryBase abstract class
"""

import pytest
from datetime import datetime, timedelta
from unittest.mock import AsyncMock, MagicMock

from harness.memory.base import (
    MemoryType,
    MemoryScope,
    MemoryEntry,
    MemoryBase,
)


class TestMemoryType:
    """Tests for MemoryType enum."""
    
    def test_memory_type_values(self):
        """Test MemoryType enum values."""
        assert MemoryType.CONVERSATION.value == "conversation"
        assert MemoryType.SEMANTIC.value == "semantic"
        assert MemoryType.EPISODIC.value == "episodic"
        assert MemoryType.PROCEDURAL.value == "procedural"
        assert MemoryType.WORKING.value == "working"
    
    def test_memory_type_count(self):
        """Test MemoryType has all expected types."""
        assert len(MemoryType) == 5


class TestMemoryScope:
    """Tests for MemoryScope enum."""
    
    def test_memory_scope_values(self):
        """Test MemoryScope enum values."""
        assert MemoryScope.SESSION.value == "session"
        assert MemoryScope.USER.value == "user"
        assert MemoryScope.GLOBAL.value == "global"
    
    def test_memory_scope_count(self):
        """Test MemoryScope has all expected scopes."""
        assert len(MemoryScope) == 3


class TestMemoryEntry:
    """Tests for MemoryEntry dataclass."""
    
    def test_memory_entry_creation(self):
        """Test creating a MemoryEntry."""
        entry = MemoryEntry(
            id="test-1",
            content="Test content",
            memory_type=MemoryType.CONVERSATION,
        )
        
        assert entry.id == "test-1"
        assert entry.content == "Test content"
        assert entry.memory_type == MemoryType.CONVERSATION
        assert entry.metadata == {}
        assert entry.importance == 0.5
    
    def test_memory_entry_with_metadata(self):
        """Test creating a MemoryEntry with metadata."""
        entry = MemoryEntry(
            id="test-2",
            content="Test content with metadata",
            memory_type=MemoryType.SEMANTIC,
            metadata={"key": "value", "source": "test"},
            importance=0.8,
        )
        
        assert entry.metadata["key"] == "value"
        assert entry.metadata["source"] == "test"
        assert entry.importance == 0.8
    
    def test_memory_entry_is_expired_not_set(self):
        """test MemoryEntry is_expired when expires_at is not set."""
        entry = MemoryEntry(
            id="test-3",
            content="Test content",
            memory_type=MemoryType.CONVERSATION,
        )
        
        assert entry.is_expired() is False
    
    def test_memory_entry_is_expired_future(self):
        """test MemoryEntry is_expired when expires_at is in the future."""
        future_time = (datetime.now() + timedelta(hours=1)).timestamp()
        entry = MemoryEntry(
            id="test-4",
            content="Test content",
            memory_type=MemoryType.CONVERSATION,
            expires_at=future_time,
        )
        
        assert entry.is_expired() is False
    
    def test_memory_entry_is_expired_past(self):
        """test MemoryEntry is_expired when expires_at is in the past."""
        past_time = (datetime.now() - timedelta(hours=1)).timestamp()
        entry = MemoryEntry(
            id="test-5",
            content="Test content",
            memory_type=MemoryType.CONVERSATION,
            expires_at=past_time,
        )
        
        assert entry.is_expired() is True
    
    def test_memory_entry_to_dict(self):
        """Test MemoryEntry to_dict method."""
        entry = MemoryEntry(
            id="test-6",
            content="Test content",
            memory_type=MemoryType.CONVERSATION,
            metadata={"key": "value"},
            importance=0.7,
        )
        
        result = entry.to_dict()
        
        assert result["id"] == "test-6"
        assert result["content"] == "Test content"
        assert result["memory_type"] == "conversation"
        assert result["metadata"]["key"] == "value"
        assert result["importance"] == 0.7


class ConcreteMemory(MemoryBase):
    """Concrete implementation of MemoryBase for testing."""
    
    def __init__(self, config: dict = None):
        super().__init__(config)
        self._entries: dict = {}
    
    async def store(self, entry: MemoryEntry) -> str:
        self._entries[entry.id] = entry
        return entry.id
    
    async def retrieve(self, query: str, limit: int = 10):
        return list(self._entries.values())[:limit]
    
    async def delete(self, entry_id: str) -> bool:
        if entry_id in self._entries:
            del self._entries[entry_id]
            return True
        return False
    
    async def clear(self, scope: MemoryScope = MemoryScope.SESSION) -> int:
        count = len(self._entries)
        self._entries.clear()
        return count


class TestMemoryBase:
    """Tests for MemoryBase abstract class."""
    
    def test_memory_base_init_default_config(self):
        """Test MemoryBase initialization with default config."""
        memory = ConcreteMemory()
        
        assert memory.config == {}
        assert memory.max_size == 1000
        assert memory.ttl == 3600
    
    def test_memory_base_init_custom_config(self):
        """Test MemoryBase initialization with custom config."""
        memory = ConcreteMemory(config={"max_size": 500, "ttl": 7200})
        
        assert memory.config["max_size"] == 500
        assert memory.config["ttl"] == 7200
        assert memory.max_size == 500
        assert memory.ttl == 7200
    
    @pytest.mark.asyncio
    async def test_memory_base_store_and_retrieve(self):
        """Test MemoryBase store and retrieve methods."""
        memory = ConcreteMemory()
        entry = MemoryEntry(
            id="test-1",
            content="Test content",
            memory_type=MemoryType.CONVERSATION,
        )
        
        # Store entry
        entry_id = await memory.store(entry)
        assert entry_id == "test-1"
        
        # Retrieve entry
        results = await memory.retrieve("test")
        assert len(results) == 1
        assert results[0].id == "test-1"
    
    @pytest.mark.asyncio
    async def test_memory_base_delete(self):
        """Test MemoryBase delete method."""
        memory = ConcreteMemory()
        entry = MemoryEntry(
            id="test-1",
            content="Test content",
            memory_type=MemoryType.CONVERSATION,
        )
        
        # Store and delete
        await memory.store(entry)
        deleted = await memory.delete("test-1")
        
        assert deleted is True
        
        # Verify deleted
        results = await memory.retrieve("test")
        assert len(results) == 0
    
    @pytest.mark.asyncio
    async def test_memory_base_delete_nonexistent(self):
        """Test MemoryBase delete with nonexistent id."""
        memory = ConcreteMemory()
        
        deleted = await memory.delete("nonexistent")
        assert deleted is False
    
    @pytest.mark.asyncio
    async def test_memory_base_clear(self):
        """Test MemoryBase clear method."""
        memory = ConcreteMemory()
        
        # Store multiple entries
        for i in range(5):
            await memory.store(MemoryEntry(
                id=f"test-{i}",
                content=f"Content {i}",
                memory_type=MemoryType.CONVERSATION,
            ))
        
        # Clear all
        count = await memory.clear()
        
        assert count == 5
        
        # Verify cleared
        results = await memory.retrieve("test")
        assert len(results) == 0
    
    @pytest.mark.asyncio
    async def test_memory_base_get_stats(self):
        """Test MemoryBase get_stats method."""
        memory = ConcreteMemory(config={"max_size": 500, "ttl": 7200})
        
        stats = await memory.get_stats()
        
        assert stats["type"] == "ConcreteMemory"
        assert stats["max_size"] == 500
        assert stats["ttl"] == 7200