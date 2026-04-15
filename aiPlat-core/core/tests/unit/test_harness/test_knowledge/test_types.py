"""
Tests for Knowledge Types module.

Tests cover:
- KnowledgeType enum
- KnowledgeSource enum
- KnowledgeStatus enum
- KnowledgeMetadata dataclass
- KnowledgeEntry dataclass
- KnowledgeQuery dataclass
- KnowledgeResult dataclass
"""

import pytest
from datetime import datetime

from harness.knowledge.types import (
    KnowledgeType,
    KnowledgeSource,
    KnowledgeStatus,
    KnowledgeMetadata,
    KnowledgeEntry,
    KnowledgeQuery,
    KnowledgeResult,
)


class TestKnowledgeType:
    """Tests for KnowledgeType enum."""
    
    def test_knowledge_type_values(self):
        """Test KnowledgeType enum values."""
        assert KnowledgeType.DOCUMENT.value == "document"
        assert KnowledgeType.CODE.value == "code"
        assert KnowledgeType.API.value == "api"
        assert KnowledgeType.CONCEPT.value == "concept"
        assert KnowledgeType.PROCEDURE.value == "procedure"
        assert KnowledgeType.FACT.value == "fact"
        assert KnowledgeType.RELATION.value == "relation"
        assert KnowledgeType.METADATA.value == "metadata"
    
    def test_knowledge_type_count(self):
        """Test KnowledgeType has all expected types."""
        assert len(KnowledgeType) == 8


class TestKnowledgeSource:
    """Tests for KnowledgeSource enum."""
    
    def test_knowledge_source_values(self):
        """Test KnowledgeSource enum values."""
        assert KnowledgeSource.FILE.value == "file"
        assert KnowledgeSource.DATABASE.value == "database"
        assert KnowledgeSource.API.value == "api"
        assert KnowledgeSource.WEB.value == "web"
        assert KnowledgeSource.USER.value == "user"
        assert KnowledgeSource.SYSTEM.value == "system"
    
    def test_knowledge_source_count(self):
        """Test KnowledgeSource has all expected sources."""
        assert len(KnowledgeSource) == 6


class TestKnowledgeStatus:
    """Tests for KnowledgeStatus enum."""
    
    def test_knowledge_status_values(self):
        """Test KnowledgeStatus enum values."""
        assert KnowledgeStatus.ACTIVE.value == "active"
        assert KnowledgeStatus.ARCHIVED.value == "archived"
        assert KnowledgeStatus.DEPRECATED.value == "deprecated"
        assert KnowledgeStatus.PENDING.value == "pending"
    
    def test_knowledge_status_count(self):
        """Test KnowledgeStatus has all expected statuses."""
        assert len(KnowledgeStatus) == 4


class TestKnowledgeMetadata:
    """Tests for KnowledgeMetadata dataclass."""
    
    def test_knowledge_metadata_creation(self):
        """Test creating KnowledgeMetadata."""
        metadata = KnowledgeMetadata(source=KnowledgeSource.FILE)
        
        assert metadata.source == KnowledgeSource.FILE
        assert metadata.author is None
        assert metadata.version == "1.0.0"
        assert metadata.tags == []
        assert metadata.confidence == 1.0
        assert metadata.relevance == 1.0
    
    def test_knowledge_metadata_with_author(self):
        """Test KnowledgeMetadata with author."""
        metadata = KnowledgeMetadata(
            source=KnowledgeSource.USER,
            author="test-user"
        )
        
        assert metadata.author == "test-user"
    
    def test_knowledge_metadata_with_tags(self):
        """Test KnowledgeMetadata with tags."""
        metadata = KnowledgeMetadata(
            source=KnowledgeSource.FILE,
            tags=["python", "testing"]
        )
        
        assert len(metadata.tags) == 2
        assert "python" in metadata.tags
    
    def test_knowledge_metadata_to_dict(self):
        """Test KnowledgeMetadata to_dict method."""
        metadata = KnowledgeMetadata(
            source=KnowledgeSource.FILE,
            author="test-author",
            tags=["tag1", "tag2"]
        )
        
        result = metadata.to_dict()
        
        assert result["source"] == "file"
        assert result["author"] == "test-author"
        assert "tag1" in result["tags"]
        assert "created_at" in result
        assert "updated_at" in result


class TestKnowledgeEntry:
    """Tests for KnowledgeEntry dataclass."""
    
    def test_knowledge_entry_creation(self):
        """Test creating KnowledgeEntry."""
        entry = KnowledgeEntry(
            id="test-1",
            type=KnowledgeType.DOCUMENT,
            content="Test content"
        )
        
        assert entry.id == "test-1"
        assert entry.type == KnowledgeType.DOCUMENT
        assert entry.content == "Test content"
        assert entry.status == KnowledgeStatus.ACTIVE
    
    def test_knowledge_entry_with_title(self):
        """Test KnowledgeEntry with title."""
        entry = KnowledgeEntry(
            id="test-1",
            type=KnowledgeType.DOCUMENT,
            content="Test content",
            title="Test Title"
        )
        
        assert entry.title == "Test Title"
    
    def test_knowledge_entry_with_embedding(self):
        """Test KnowledgeEntry with embedding."""
        entry = KnowledgeEntry(
            id="test-1",
            type=KnowledgeType.DOCUMENT,
            content="Test content",
            embedding=[0.1, 0.2, 0.3]
        )
        
        assert entry.embedding == [0.1, 0.2, 0.3]
    
    def test_knowledge_entry_with_references(self):
        """Test KnowledgeEntry with references."""
        entry = KnowledgeEntry(
            id="test-1",
            type=KnowledgeType.DOCUMENT,
            content="Test content",
            references=["ref1", "ref2"]
        )
        
        assert len(entry.references) == 2
    
    def test_knowledge_entry_to_dict(self):
        """Test KnowledgeEntry to_dict method."""
        entry = KnowledgeEntry(
            id="test-1",
            type=KnowledgeType.DOCUMENT,
            content="Test content",
            title="Test Title",
            metadata=KnowledgeMetadata(source=KnowledgeSource.FILE)
        )
        
        result = entry.to_dict()
        
        assert result["id"] == "test-1"
        assert result["type"] == "document"
        assert result["content"] == "Test content"
        assert result["title"] == "Test Title"
        assert "metadata" in result


class TestKnowledgeQuery:
    """Tests for KnowledgeQuery dataclass."""
    
    def test_knowledge_query_creation(self):
        """Test creating KnowledgeQuery."""
        query = KnowledgeQuery(query="test query")
        
        assert query.query == "test query"
        assert query.limit == 10
        assert query.min_confidence == 0.0
    
    def test_knowledge_query_with_types(self):
        """Test KnowledgeQuery with type filters."""
        query = KnowledgeQuery(
            query="test query",
            types=[KnowledgeType.DOCUMENT, KnowledgeType.CODE],
            limit=20
        )
        
        assert len(query.types) == 2
        assert query.limit == 20
    
    def test_knowledge_query_to_dict(self):
        """Test KnowledgeQuery to_dict method."""
        query = KnowledgeQuery(
            query="test query",
            limit=5,
            min_confidence=0.5
        )
        
        result = query.to_dict()
        
        assert result["query"] == "test query"
        assert result["limit"] == 5
        assert result["min_confidence"] == 0.5


class TestKnowledgeResult:
    """Tests for KnowledgeResult dataclass."""
    
    def test_knowledge_result_creation(self):
        """Test creating KnowledgeResult."""
        entry = KnowledgeEntry(
            id="test-1",
            type=KnowledgeType.DOCUMENT,
            content="Test content"
        )
        result = KnowledgeResult(
            entry=entry,
            score=0.95
        )
        
        assert result.entry.id == "test-1"
        assert result.score == 0.95
    
    def test_knowledge_result_with_highlight(self):
        """Test KnowledgeResult with highlight."""
        entry = KnowledgeEntry(
            id="test-1",
            type=KnowledgeType.DOCUMENT,
            content="Test content"
        )
        result = KnowledgeResult(
            entry=entry,
            score=0.95,
            highlight="highlighted text"
        )
        
        assert result.highlight == "highlighted text"
    
    def test_knowledge_result_to_dict(self):
        """Test KnowledgeResult to_dict method."""
        entry = KnowledgeEntry(
            id="test-1",
            type=KnowledgeType.DOCUMENT,
            content="Test content"
        )
        result = KnowledgeResult(
            entry=entry,
            score=0.95
        )
        
        dict_result = result.to_dict()
        
        assert "entry" in dict_result
        assert dict_result["score"] == 0.95