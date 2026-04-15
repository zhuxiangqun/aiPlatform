"""
Knowledge Manager - Manages knowledge collections

Provides knowledge base management operations.
"""

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Any
from datetime import datetime
import uuid


@dataclass
class CollectionInfo:
    """Knowledge collection information"""
    id: str
    name: str
    description: str
    status: str  # active, indexing, error
    config: Dict[str, Any]
    document_count: int
    total_size_mb: float
    created_at: datetime
    updated_at: datetime
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class DocumentInfo:
    """Document information"""
    id: str
    collection_id: str
    name: str
    type: str  # pdf, docx, md, txt, etc.
    size_mb: float
    status: str  # parsing, chunking, embedding, indexed, error
    chunks: int
    metadata: Dict[str, Any]
    created_at: datetime
    indexed_at: Optional[datetime]


@dataclass
class IndexStatus:
    """Index status"""
    collection_id: str
    status: str  # ready, indexing, error
    progress: float
    documents_indexed: int
    total_documents: int
    last_indexed_at: datetime


@dataclass
class SearchResult:
    """Search result"""
    content: str
    score: float
    metadata: Dict[str, Any]


class KnowledgeManager:
    """
    Knowledge Manager - Manages knowledge collections
    
    Provides:
    - Collection CRUD operations
    - Document management
    - Index management
    - Search operations
    """
    
    def __init__(self):
        self._collections: Dict[str, CollectionInfo] = {}
        self._documents: Dict[str, List[DocumentInfo]] = {}
        self._index_status: Dict[str, IndexStatus] = {}
    
    async def create_collection(
        self,
        name: str,
        description: str,
        config: Optional[Dict[str, Any]] = None,
        metadata: Optional[Dict[str, Any]] = None
    ) -> CollectionInfo:
        """Create a new collection"""
        collection_id = f"kb-{uuid.uuid4().hex[:8]}"
        now = datetime.utcnow()
        
        collection = CollectionInfo(
            id=collection_id,
            name=name,
            description=description,
            status="active",
            config=config or {
                "embedding_model": "text-embedding-ada-002",
                "dimension": 1536,
                "chunk_size": 512,
                "chunk_overlap": 50,
                "similarity_threshold": 0.75
            },
            document_count=0,
            total_size_mb=0.0,
            created_at=now,
            updated_at=now,
            metadata=metadata or {}
        )
        
        self._collections[collection_id] = collection
        self._documents[collection_id] = []
        self._index_status[collection_id] = IndexStatus(
            collection_id=collection_id,
            status="ready",
            progress=100.0,
            documents_indexed=0,
            total_documents=0,
            last_indexed_at=now
        )
        
        return collection
    
    async def get_collection(self, collection_id: str) -> Optional[CollectionInfo]:
        """Get collection by ID"""
        return self._collections.get(collection_id)
    
    async def list_collections(
        self,
        status: Optional[str] = None,
        limit: int = 100,
        offset: int = 0
    ) -> List[CollectionInfo]:
        """List collections with filters"""
        collections = list(self._collections.values())
        
        if status:
            collections = [c for c in collections if c.status == status]
        
        return collections[offset:offset + limit]
    
    async def update_collection(
        self,
        collection_id: str,
        name: Optional[str] = None,
        description: Optional[str] = None,
        config: Optional[Dict[str, Any]] = None
    ) -> Optional[CollectionInfo]:
        """Update collection"""
        collection = self._collections.get(collection_id)
        if not collection:
            return None
        
        if name:
            collection.name = name
        if description:
            collection.description = description
        if config:
            collection.config.update(config)
        
        collection.updated_at = datetime.utcnow()
        
        return collection
    
    async def delete_collection(self, collection_id: str) -> bool:
        """Delete collection"""
        if collection_id not in self._collections:
            return False
        
        del self._collections[collection_id]
        del self._documents[collection_id]
        del self._index_status[collection_id]
        
        return True
    
    async def upload_document(
        self,
        collection_id: str,
        name: str,
        doc_type: str,
        content: bytes,
        metadata: Optional[Dict[str, Any]] = None
    ) -> DocumentInfo:
        """Upload document to collection"""
        document_id = f"doc-{uuid.uuid4().hex[:8]}"
        now = datetime.utcnow()
        
        document = DocumentInfo(
            id=document_id,
            collection_id=collection_id,
            name=name,
            type=doc_type,
            size_mb=len(content) / (1024 * 1024),
            status="parsing",
            chunks=0,
            metadata=metadata or {},
            created_at=now,
            indexed_at=None
        )
        
        self._documents[collection_id].append(document)
        
        # Update collection
        collection = self._collections[collection_id]
        collection.document_count += 1
        collection.total_size_mb += document.size_mb
        collection.updated_at = now
        
        return document
    
    async def get_document(self, document_id: str) -> Optional[DocumentInfo]:
        """Get document by ID"""
        for documents in self._documents.values():
            for doc in documents:
                if doc.id == document_id:
                    return doc
        return None
    
    async def list_documents(
        self,
        collection_id: str,
        status: Optional[str] = None,
        limit: int = 100,
        offset: int = 0
    ) -> List[DocumentInfo]:
        """List documents in collection"""
        documents = self._documents.get(collection_id, [])
        
        if status:
            documents = [d for d in documents if d.status == status]
        
        return documents[offset:offset + limit]
    
    async def delete_document(self, document_id: str) -> bool:
        """Delete document"""
        for collection_id, documents in self._documents.items():
            for i, doc in enumerate(documents):
                if doc.id == document_id:
                    documents.pop(i)
                    collection = self._collections[collection_id]
                    collection.document_count -= 1
                    collection.total_size_mb -= doc.size_mb
                    return True
        return False
    
    async def reindex_collection(self, collection_id: str) -> bool:
        """Reindex collection"""
        collection = self._collections.get(collection_id)
        if not collection:
            return False
        
        collection.status = "indexing"
        self._index_status[collection_id].status = "indexing"
        self._index_status[collection_id].progress = 0.0
        
        return True
    
    async def get_index_status(self, collection_id: str) -> Optional[IndexStatus]:
        """Get index status"""
        return self._index_status.get(collection_id)
    
    async def search(
        self,
        collection_id: str,
        query: str,
        top_k: int = 5,
        similarity_threshold: float = 0.75,
        filters: Optional[Dict[str, Any]] = None
    ) -> List[SearchResult]:
        """Search in collection"""
        # Placeholder implementation
        results = [
            SearchResult(
                content=f"Result {i} for query: {query}",
                score=0.95 - i *0.1,
                metadata={"document_id": f"doc-{i}", "source": f"source-{i}"}
            )
            for i in range(min(top_k, 5))
        ]
        
        return results
    
    def get_collection_count(self) -> Dict[str, int]:
        """Get collection count"""
        return {
            "total": len(self._collections),
            "active": sum(1 for c in self._collections.values() if c.status == "active"),
            "indexing": sum(1 for c in self._collections.values() if c.status == "indexing"),
            "error": sum(1 for c in self._collections.values() if c.status == "error")
        }