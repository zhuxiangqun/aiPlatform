"""Tests for knowledge/retriever.py — retrieval interface and implementations."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[4] / "aiPlat-core"))

import pytest

from core.harness.knowledge.retriever import (
    InMemoryRetriever, HashEmbedder
)
from core.harness.knowledge.types import KnowledgeEntry, KnowledgeType


class TestHashEmbedder:
    @pytest.mark.asyncio
    async def test_embed_single(self):
        he = HashEmbedder()
        vec = await he.embed("hello world")
        assert len(vec) > 0

    @pytest.mark.asyncio
    async def test_embed_consistent(self):
        he = HashEmbedder()
        v1 = await he.embed("test")
        v2 = await he.embed("test")
        assert v1 == v2

    @pytest.mark.asyncio
    async def test_embed_different(self):
        he = HashEmbedder()
        v1 = await he.embed("hello")
        v2 = await he.embed("world")
        assert v1 != v2


class TestInMemoryRetriever:
    @pytest.mark.asyncio
    async def test_add_and_retrieve(self):
        ir = InMemoryRetriever()
        await ir.add_batch([
            KnowledgeEntry(id="1", content="hello world", type=KnowledgeType.DOCUMENT),
        ])
        from core.harness.knowledge.retriever import KnowledgeQuery
        results = await ir.retrieve(KnowledgeQuery(query="hello"))
        assert len(results) > 0
        assert results[0].entry.id == "1"

    @pytest.mark.asyncio
    async def test_empty_search(self):
        ir = InMemoryRetriever()
        from core.harness.knowledge.retriever import KnowledgeQuery
        results = await ir.retrieve(KnowledgeQuery(query="nothing"))
        assert results == []

    @pytest.mark.asyncio
    async def test_get_by_id(self):
        ir = InMemoryRetriever()
        await ir.add_batch([KnowledgeEntry(id="x", content="test doc", type=KnowledgeType.DOCUMENT)])
        entry = await ir.get_by_id("x")
        assert entry is not None
        assert entry.id == "x"

    @pytest.mark.asyncio
    async def test_get_by_id_missing(self):
        ir = InMemoryRetriever()
        entry = await ir.get_by_id("nonexistent")
        assert entry is None
