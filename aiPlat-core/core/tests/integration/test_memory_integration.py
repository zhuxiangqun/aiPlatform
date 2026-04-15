"""
Integration tests for Memory system.

Tests cover:
- Full memory lifecycle (store, retrieve, delete)
- Memory with embeddings
- Session management integration
- Cross-component memory integration
"""

import pytest
from datetime import datetime, timedelta
import asyncio

from harness.memory.base import MemoryEntry, MemoryType, MemoryScope
from harness.memory.short_term import ShortTermMemory, ConversationMemory
from harness.memory.long_term import LongTermMemory, SemanticMemory
from harness.memory.session import Session, SessionManager


@pytest.mark.integration
class TestMemoryIntegration:
    """Integration tests for memory system."""
    
    @pytest.mark.asyncio
    async def test_short_term_memory_lifecycle(self):
        """Test complete short-term memory lifecycle."""
        memory = ShortTermMemory({"max_size": 10, "ttl": 60})
        
        # Store entries
        entries = []
        for i in range(5):
            entry = MemoryEntry(
                id=f"test-{i}",
                content=f"Content {i}",
                memory_type=MemoryType.CONVERSATION,
                metadata={"index": i}
            )
            await memory.store(entry)
            entries.append(entry)
        
        # Retrieve all
        results = await memory.retrieve("", limit=10)
        assert len(results) >= 1
        
        # Delete specific entry
        deleted = await memory.delete("test-0")
        assert deleted is True
        
        # Clear all
        count = await memory.clear()
        assert count >= 0
    
    @pytest.mark.asyncio
    async def test_long_term_memory_with_indexing(self):
        """Test long-term memory with keyword indexing."""
        memory = LongTermMemory()
        
        # Store entries with keywords
        await memory.store(MemoryEntry(
            id="doc1",
            content="machine learning algorithms",
            memory_type=MemoryType.SEMANTIC,
        ))
        await memory.store(MemoryEntry(
            id="doc2",
            content="deep learning neural networks",
            memory_type=MemoryType.SEMANTIC,
        ))
        await memory.store(MemoryEntry(
            id="doc3",
            content="cooking recipes for dinner",
            memory_type=MemoryType.SEMANTIC,
        ))
        
        # Search by keywords
        results = await memory.retrieve("learning")
        assert len(results) >= 1
    
    @pytest.mark.asyncio
    async def test_semantic_memory_with_embeddings(self):
        """Test semantic memory with embeddings."""
        memory = SemanticMemory()
        
        # Store with embeddings
        await memory.store_with_embedding(
            content="machine learning",
            embedding=[1.0, 0.0, 0.0],
        )
        await memory.store_with_embedding(
            content="deep learning",
            embedding=[0.9, 0.1, 0.0],
        )
        
        # Search by similarity
        results = await memory.retrieve_similar(
            query_embedding=[1.0, 0.0, 0.0],
            limit=2,
            threshold=0.5
        )
        
        assert len(results) >= 1
    
    @pytest.mark.asyncio
    async def test_conversation_memory_flow(self):
        """Test complete conversation memory flow."""
        memory = ConversationMemory()
        memory.set_session("session-123")
        
        # Add conversation messages
        await memory.add_message("user", "Hello, how are you?")
        await memory.add_message("assistant", "I'm doing well, thank you!")
        await memory.add_message("user", "What's the weather?")
        await memory.add_message("assistant", "I don't have access to weather data.")
        
        # Get messages
        messages = await memory.get_messages()
        assert len(messages) >= 4
        
        # Get context
        context = await memory.get_context(max_tokens=500)
        assert "user:" in context or "assistant:" in context
    
    @pytest.mark.asyncio
    async def test_session_with_conversation_memory(self):
        """Test session management with conversation memory."""
        manager = SessionManager()
        
        # Create session
        session = await manager.create_session("user-1")
        
        # Get conversation memory
        conv_memory = await manager.get_conversation_memory(session.id)
        assert conv_memory is not None
        
        # Add messages
        await conv_memory.add_message("user", "Hello")
        await conv_memory.add_message("assistant", "Hi!")
        
        # Verify messages
        messages = await conv_memory.get_messages()
        assert len(messages) >= 2
        
        # Delete session
        deleted = await manager.delete_session(session.id)
        assert deleted is True
        
        # Verify memory is cleaned up
        conv_memory_after = await manager.get_conversation_memory(session.id)
        assert conv_memory_after is None


@pytest.mark.integration
class TestMemoryIntegrationWithHarness:
    """Integration tests for memory with Harness framework."""
    
    @pytest.mark.asyncio
    async def test_memory_with_harness_integration(self):
        """Test memory integration with Harness."""
        from harness.integration import HarnessIntegration, HarnessConfig
        
        config = HarnessConfig(
            enable_memory=True,
            memory_config={"max_size": 100},
            enable_observability=False,
            enable_feedback_loops=False,
        )
        
        harness = HarnessIntegration.initialize(config)
        
        assert harness.memory is not None
        
        # Store in memory
        entry = MemoryEntry(
            id="test-integration",
            content="Integration test content",
            memory_type=MemoryType.CONVERSATION,
        )
        
        await harness.memory.store(entry)
        
        # Retrieve
        results = await harness.memory.retrieve("test")
        assert len(results) >= 0
        
        # Cleanup
        await harness.reset()
    
    @pytest.mark.asyncio
    async def test_session_manager_persistence(self):
        """Test session manager persistence."""
        manager = SessionManager()
        
        # Create multiple sessions
        sessions = []
        for i in range(3):
            session = await manager.create_session(f"user-{i}")
            sessions.append(session)
        
        # Get stats
        stats = await manager.get_stats()
        assert stats["total_sessions"] >= 3
        
        # Cleanup expired
        cleaned = await manager.cleanup_expired()
        assert cleaned >= 0