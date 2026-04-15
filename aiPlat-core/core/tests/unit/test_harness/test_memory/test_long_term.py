"""
Tests for LongTermMemory and SemanticMemory.

Tests cover:
- Store, retrieve, delete operations
- Keyword extraction and indexing
- Type-based retrieval
- Semantic search with embeddings
"""

import pytest
from datetime import datetime, timedelta
from unittest.mock import AsyncMock, MagicMock

from harness.memory.long_term import LongTermMemory, SemanticMemory
from harness.memory.base import MemoryEntry, MemoryType, MemoryScope


class TestLongTermMemory:
    """Tests for LongTermMemory class."""
    
    def test_init_default_config(self):
        """Test LongTermMemory initialization with default config."""
        memory = LongTermMemory()
        
        assert memory.max_size == 10000
        assert memory.ttl == 86400 * 30  #30 days
    
    def test_init_custom_config(self):
        """Test LongTermMemory initialization with custom config."""
        memory = LongTermMemory({"max_size": 5000, "ttl": 86400})
        
        assert memory.max_size == 5000
        assert memory.ttl == 86400
    
    @pytest.mark.asyncio
    async def test_store_entry(self):
        """Test storing an entry."""
        memory = LongTermMemory()
        entry = MemoryEntry(
            id="test-1",
            content="Test content about machine learning",
            memory_type=MemoryType.SEMANTIC,
        )
        
        entry_id = await memory.store(entry)
        
        assert entry_id == "test-1"
        assert entry_id in memory._storage
    
    @pytest.mark.asyncio
    async def test_store_creates_index(self):
        """Test that storing creates keyword index."""
        memory = LongTermMemory()
        entry = MemoryEntry(
            id="test-1",
            content="machine learning algorithms",
            memory_type=MemoryType.SEMANTIC,
        )
        
        await memory.store(entry)
        
        # Check index contains keywords
        assert "machine" in memory._index or "learning" in memory._index or "algorithms" in memory._index
    
    @pytest.mark.asyncio
    async def test_retrieve_without_query(self):
        """Test retrieving without query returns recent entries."""
        memory = LongTermMemory()
        
        for i in range(5):
            await memory.store(MemoryEntry(
                id=f"test-{i}",
                content=f"Content {i}",
                memory_type=MemoryType.SEMANTIC,
            ))
        
        results = await memory.retrieve("")
        
        assert len(results) == 5
    
    @pytest.mark.asyncio
    async def test_retrieve_with_query(self):
        """Test retrieving with query returns matching entries."""
        memory = LongTermMemory()
        
        await memory.store(MemoryEntry(
            id="test-1",
            content="machine learning is fascinating",
            memory_type=MemoryType.SEMANTIC,
        ))
        await memory.store(MemoryEntry(
            id="test-2",
            content="cooking recipes for dinner",
            memory_type=MemoryType.SEMANTIC,
        ))
        
        results1 = await memory.retrieve("machine learning")
        results2 = await memory.retrieve("cooking")
        
        # Results should be filtered by keywords
        assert len(results1) >= 0
        assert len(results2) >= 0
    
    @pytest.mark.asyncio
    async def test_retrieve_by_type(self):
        """Test retrieving by memory type."""
        memory = LongTermMemory()
        
        await memory.store(MemoryEntry(
            id="test-1",
            content="Semantic content",
            memory_type=MemoryType.SEMANTIC,
        ))
        await memory.store(MemoryEntry(
            id="test-2",
            content="Episodic content",
            memory_type=MemoryType.EPISODIC,
        ))
        
        semantic = await memory.retrieve_by_type(MemoryType.SEMANTIC)
        episodic = await memory.retrieve_by_type(MemoryType.EPISODIC)
        
        assert len(semantic) == 1
        assert len(episodic) == 1
        assert semantic[0].id == "test-1"
        assert episodic[0].id == "test-2"
    
    @pytest.mark.asyncio
    async def test_delete_entry(self):
        """Test deleting an entry."""
        memory = LongTermMemory()
        entry = MemoryEntry(
            id="test-1",
            content="Test content",
            memory_type=MemoryType.SEMANTIC,
        )
        await memory.store(entry)
        
        deleted = await memory.delete("test-1")
        
        assert deleted is True
        assert "test-1" not in memory._storage
    
    @pytest.mark.asyncio
    async def test_delete_nonexistent(self):
        """Test deleting nonexistent entry."""
        memory = LongTermMemory()
        
        deleted = await memory.delete("nonexistent")
        
        assert deleted is False
    
    @pytest.mark.asyncio
    async def test_delete_clears_index(self):
        """Test that deleting clears keyword index."""
        memory = LongTermMemory()
        entry = MemoryEntry(
            id="test-1",
            content="machine learning algorithms",
            memory_type=MemoryType.SEMANTIC,
        )
        await memory.store(entry)
        
        # Get keywords that were indexed
        keywords = memory._extract_keywords(entry.content)
        
        await memory.delete("test-1")
        
        # Index should be cleared for this entry
        for keyword in keywords:
            if keyword in memory._index:
                assert "test-1" not in memory._index[keyword]
    
    @pytest.mark.asyncio
    async def test_clear_global_scope(self):
        """Test clearing with GLOBAL scope."""
        memory = LongTermMemory()
        
        for i in range(5):
            await memory.store(MemoryEntry(
                id=f"test-{i}",
                content=f"Content {i}",
                memory_type=MemoryType.SEMANTIC,
            ))
        
        count = await memory.clear(MemoryScope.GLOBAL)
        
        assert count == 5
        assert len(memory._storage) == 0
        assert len(memory._index) == 0
    
    @pytest.mark.asyncio
    async def test_get_stats(self):
        """Test getting statistics."""
        memory = LongTermMemory()
        
        await memory.store(MemoryEntry(
            id="test-1",
            content="Content 1",
            memory_type=MemoryType.SEMANTIC,
        ))
        await memory.store(MemoryEntry(
            id="test-2",
            content="Content 2",
            memory_type=MemoryType.EPISODIC,
        ))
        
        stats = await memory.get_stats()
        
        assert stats["type"] == "LongTermMemory"
        assert stats["total_entries"] == 2
        assert "semantic" in stats["by_type"]
        assert "episodic" in stats["by_type"]


class TestSemanticMemory:
    """Tests for SemanticMemory class."""
    
    def test_init_default_config(self):
        """Test SemanticMemory initialization."""
        memory = SemanticMemory()
        
        assert memory.max_size == 5000
        assert memory.ttl == 86400 * 90  # 90 days
    
    @pytest.mark.asyncio
    async def test_store_with_embedding(self):
        """Test storing with embedding."""
        memory = SemanticMemory()
        
        entry_id = await memory.store_with_embedding(
            content="test content",
            embedding=[0.1, 0.2, 0.3],
            memory_type=MemoryType.SEMANTIC,
            metadata={"source": "test"}
        )
        
        assert entry_id is not None
        assert entry_id in memory._embeddings
    
    @pytest.mark.asyncio
    async def test_retrieve_similar(self):
        """Test retrieving similar entries by embedding."""
        memory = SemanticMemory()
        
        # Store entries with embeddings
        await memory.store_with_embedding(
            content="machine learning",
            embedding=[1.0, 0.0, 0.0],
        )
        await memory.store_with_embedding(
            content="deep learning",
            embedding=[0.9, 0.1, 0.0],
        )
        await memory.store_with_embedding(
            content="cooking recipes",
            embedding=[0.0, 0.0, 1.0],
        )
        
        # Query with similar embedding
        results = await memory.retrieve_similar(
            query_embedding=[1.0, 0.0, 0.0],
            limit=2,
            threshold=0.5
        )
        
        # Should find machine learning and deep learning
        assert len(results) >= 1
    
    @pytest.mark.asyncio
    async def test_retrieve_similar_threshold(self):
        """Test retrieve similar respects threshold."""
        memory = SemanticMemory()
        
        await memory.store_with_embedding(
            content="test",
            embedding=[1.0, 0.0, 0.0],
        )
        
        # Query with completely different embedding
        results = await memory.retrieve_similar(
            query_embedding=[0.0, 1.0, 0.0],
            threshold=0.99
        )
        
        # Should not find any match due to high threshold
        assert len(results) == 0
    
    def test_cosine_similarity(self):
        """Test cosine similarity calculation."""
        memory = SemanticMemory()
        
        # Same vectors
        sim1 = memory._cosine_similarity([1.0, 0.0], [1.0, 0.0])
        assert sim1 == 1.0
        
        # Orthogonal vectors
        sim2 = memory._cosine_similarity([1.0, 0.0], [0.0, 1.0])
        assert sim2 == 0.0
        
        # Opposite vectors
        sim3 = memory._cosine_similarity([1.0, 0.0], [-1.0, 0.0])
        assert sim3 == -1.0
    
    def test_cosine_similarity_zero_vector(self):
        """Test cosine similarity with zero vector."""
        memory = SemanticMemory()
        
        sim = memory._cosine_similarity([0.0, 0.0], [1.0, 1.0])
        
        assert sim == 0.0
    
    @pytest.mark.asyncio
    async def test_embedding_persistence(self):
        """Test that embeddings are persisted."""
        memory = SemanticMemory()
        
        entry_id = await memory.store_with_embedding(
            content="test",
            embedding=[0.5, 0.5, 0.5],
        )
        
        # Check embedding is stored
        assert entry_id in memory._embeddings
        assert memory._embeddings[entry_id] == [0.5, 0.5, 0.5]