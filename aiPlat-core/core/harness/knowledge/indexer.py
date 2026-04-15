"""
Knowledge Indexer Module

Provides knowledge indexing capabilities.
"""

from typing import Any, Dict, List, Optional, Callable, Awaitable
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
import asyncio
import re

from .types import (
    KnowledgeEntry,
    KnowledgeType,
    KnowledgeSource,
    KnowledgeMetadata,
)


class IndexType(Enum):
    """Index types"""
    KEYWORD = "keyword"
    SEMANTIC = "semantic"
    HYBRID = "hybrid"


@dataclass
class IndexConfig:
    """Index configuration"""
    index_type: IndexType = IndexType.HYBRID
    chunk_size: int = 500
    chunk_overlap: int = 50
    min_keyword_length: int = 3
    max_keywords: int = 10
    enable_updates: bool = True


class KeywordExtractor:
    """Extracts keywords from text"""
    
    def __init__(self, min_length: int = 3, max_keywords: int = 10):
        self._min_length = min_length
        self._max_keywords = max_keywords
        self._stop_words = {
            "the", "a", "an", "and", "or", "but", "in", "on", "at", "to",
            "for", "of", "with", "by", "from", "as", "is", "was", "are",
            "were", "been", "be", "have", "has", "had", "do", "does", "did",
            "will", "would", "could", "should", "may", "might", "must",
        }
    
    def extract(self, text: str) -> List[str]:
        words = re.findall(r"\b[a-zA-Z]+\b", text.lower())
        keywords = {}
        for word in words:
            if len(word) >= self._min_length and word not in self._stop_words:
                keywords[word] = keywords.get(word, 0) + 1
        
        sorted_keywords = sorted(
            keywords.items(),
            key=lambda x: x[1],
            reverse=True,
        )
        return [k for k, _ in sorted_keywords[: self._max_keywords]]


class TextChunker:
    """Chunks text into smaller pieces"""
    
    def __init__(self, chunk_size: int = 500, overlap: int = 50):
        self._chunk_size = chunk_size
        self._overlap = overlap
    
    def chunk(self, text: str) -> List[str]:
        if len(text) <= self._chunk_size:
            return [text]
        
        chunks = []
        start = 0
        while start < len(text):
            end = start + self._chunk_size
            if end < len(text):
                last_space = text.rfind(" ", start, end)
                if last_space > start:
                    end = last_space
            
            chunk = text[start:end].strip()
            if chunk:
                chunks.append(chunk)
            
            start = end - self._overlap
            if start < 0:
                start = 0
            if start >= len(text):
                break
        
        return chunks


IndexHandler = Callable[[KnowledgeEntry, List[str]], Awaitable[None]]


class KnowledgeIndexer:
    """Indexes knowledge entries"""
    
    def __init__(self, config: Optional[IndexConfig] = None):
        self._config = config or IndexConfig()
        self._keyword_extractor = KeywordExtractor(
            min_length=self._config.min_keyword_length,
            max_keywords=self._config.max_keywords,
        )
        self._text_chunker = TextChunker(
            chunk_size=self._config.chunk_size,
            overlap=self._config.chunk_overlap,
        )
        self._keyword_index: Dict[str, List[str]] = {}
        self._entries: Dict[str, KnowledgeEntry] = {}
        self._handlers: List[IndexHandler] = []
    
    def register_handler(self, handler: IndexHandler):
        self._handlers.append(handler)
    
    async def index(self, entry: KnowledgeEntry) -> List[str]:
        chunks = self._text_chunker.chunk(entry.content)
        keywords = self._keyword_extractor.extract(entry.content)
        
        self._entries[entry.id] = entry
        
        for keyword in keywords:
            if keyword not in self._keyword_index:
                self._keyword_index[keyword] = []
            if entry.id not in self._keyword_index[keyword]:
                self._keyword_index[keyword].append(entry.id)
        
        for handler in self._handlers:
            try:
                await handler(entry, chunks)
            except Exception:
                pass
        
        return chunks
    
    async def index_batch(self, entries: List[KnowledgeEntry]) -> Dict[str, List[str]]:
        results = {}
        for entry in entries:
            results[entry.id] = await self.index(entry)
        return results
    
    async def remove(self, entry_id: str) -> bool:
        if entry_id not in self._entries:
            return False
        
        entry = self._entries[entry_id]
        keywords = self._keyword_extractor.extract(entry.content)
        
        for keyword in keywords:
            if keyword in self._keyword_index:
                if entry_id in self._keyword_index[keyword]:
                    self._keyword_index[keyword].remove(entry_id)
                if not self._keyword_index[keyword]:
                    del self._keyword_index[keyword]
        
        del self._entries[entry_id]
        return True
    
    def search_by_keyword(self, keyword: str) -> List[KnowledgeEntry]:
        entry_ids = self._keyword_index.get(keyword.lower(), [])
        return [self._entries[eid] for eid in entry_ids if eid in self._entries]
    
    def search_by_keywords(self, keywords: List[str]) -> List[KnowledgeEntry]:
        results: Dict[str, int] = {}
        for keyword in keywords:
            entries = self.search_by_keyword(keyword)
            for entry in entries:
                results[entry.id] = results.get(entry.id, 0) + 1
        
        sorted_results = sorted(
            results.items(),
            key=lambda x: x[1],
            reverse=True,
        )
        return [self._entries[eid] for eid, _ in sorted_results if eid in self._entries]
    
    def get_stats(self) -> Dict[str, Any]:
        return {
            "total_entries": len(self._entries),
            "total_keywords": len(self._keyword_index),
            "index_type": self._config.index_type.value,
            "config": {
                "chunk_size": self._config.chunk_size,
                "chunk_overlap": self._config.chunk_overlap,
                "min_keyword_length": self._config.min_keyword_length,
                "max_keywords": self._config.max_keywords,
            },
        }
    
    def clear(self):
        self._entries.clear()
        self._keyword_index.clear()


def create_indexer(config: Optional[IndexConfig] = None) -> KnowledgeIndexer:
    return KnowledgeIndexer(config)


__all__ = [
    "IndexType",
    "IndexConfig",
    "KeywordExtractor",
    "TextChunker",
    "KnowledgeIndexer",
    "create_indexer",
]