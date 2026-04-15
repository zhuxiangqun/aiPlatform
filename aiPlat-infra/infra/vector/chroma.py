import asyncio
import uuid
from typing import List, Optional, Dict, Any

from .base import VectorStore
from .schemas import Vector, SearchResult, VectorConfig


class ChromaStore(VectorStore):
    def __init__(self, config: VectorConfig):
        self.config = config
        self._client = None
        self._collection = None
        self._collection_name = "default_collection"
        self._dimension = config.dimension
        self._initialized = False
        self._lock = asyncio.Lock()
        
        if config.collection:
            self._collection_name = config.collection.name

    async def _ensure_initialized(self):
        if self._initialized:
            return
        async with self._lock:
            if self._initialized:
                return
            await self._init_client()
            self._initialized = True

    async def _init_client(self):
        import chromadb
        
        if self.config.host and self.config.port:
            self._client = chromadb.HttpClient(
                host=self.config.host,
                port=self.config.port
            )
        else:
            self._client = chromadb.Client()
        
        metadata = {}
        if self.config.index and self.config.index.params:
            metadata = self.config.index.params.copy()
        
        self._collection = self._client.get_or_create_collection(
            name=self._collection_name,
            metadata=metadata if metadata else None
        )

    async def add(
        self, vectors: List[Vector], metadata: List[Dict] = None
    ) -> List[str]:
        await self._ensure_initialized()
        
        if not vectors:
            return []
        
        ids = []
        embeddings = []
        metadatas = []
        documents = []
        
        for i, vector in enumerate(vectors):
            vec_id = vector.id or str(uuid.uuid4())
            ids.append(vec_id)
            embeddings.append(vector.values)
            
            meta = vector.metadata.copy()
            if metadata and i < len(metadata):
                meta.update(metadata[i])
            metadatas.append(meta if meta else None)
            
            if "text" in vector.metadata:
                documents.append(vector.metadata["text"])
            else:
                documents.append(None)
        
        self._collection.add(
            ids=ids,
            embeddings=embeddings,
            metadatas=metadatas if any(m for m in metadatas) else None,
            documents=documents if any(d for d in documents) else None
        )
        
        return ids

    async def search(
        self, query_vector: List[float], top_k: int = 10, filter: Dict = None
    ) -> List[SearchResult]:
        await self._ensure_initialized()
        
        where_filter = None
        if filter:
            where_filter = {}
            for key, value in filter.items():
                if isinstance(value, list):
                    where_filter[key] = {"$in": value}
                else:
                    where_filter[key] = value
        
        results = self._collection.query(
            query_embeddings=[query_vector],
            n_results=top_k,
            where=where_filter,
            include=["metadatas", "distances", "documents"]
        )
        
        search_results = []
        
        if results and results.get("ids") and len(results["ids"]) > 0:
            ids = results["ids"][0]
            distances = results.get("distances", [[]])[0]
            metadatas = results.get("metadatas", [[]])[0]
            
            for i, vec_id in enumerate(ids):
                distance = distances[i] if i < len(distances) else 0.0
                meta = metadatas[i] if i < len(metadatas) and metadatas[i] else {}
                
                if self.config.search and self.config.search.metric_type == "IP":
                    score = 1.0 - distance
                else:
                    score = 1.0 / (1.0 + distance)
                
                search_results.append(SearchResult(
                    id=vec_id,
                    score=score,
                    metadata=meta
                ))
        
        return search_results

    async def delete(self, ids: List[str]) -> bool:
        await self._ensure_initialized()
        
        if not ids:
            return True
        
        self._collection.delete(ids=ids)
        
        return True

    async def get(self, id: str) -> Optional[Vector]:
        await self._ensure_initialized()
        
        results = self._collection.get(
            ids=[id],
            include=["embeddings", "metadatas", "documents"]
        )
        
        if not results or not results.get("ids") or len(results["ids"]) == 0:
            return None
        
        vec_id = results["ids"][0]
        embeddings = results.get("embeddings", [[]])
        metadatas = results.get("metadatas", [{}])
        
        embedding = embeddings[0] if embeddings and len(embeddings) > 0 else []
        metadata = metadatas[0] if metadatas and len(metadatas) > 0 else {}
        
        return Vector(
            id=vec_id,
            values=embedding if embedding else [],
            metadata=metadata if metadata else {}
        )

    async def count(self) -> int:
        await self._ensure_initialized()
        
        return self._collection.count()

    async def upsert(self, vectors: List[Vector]) -> List[str]:
        await self._ensure_initialized()
        
        if not vectors:
            return []
        
        ids = []
        embeddings = []
        metadatas = []
        documents = []
        
        for vector in vectors:
            vec_id = vector.id or str(uuid.uuid4())
            ids.append(vec_id)
            embeddings.append(vector.values)
            
            meta = vector.metadata.copy()
            metadatas.append(meta if meta else None)
            
            if "text" in vector.metadata:
                documents.append(vector.metadata["text"])
            else:
                documents.append(None)
        
        self._collection.upsert(
            ids=ids,
            embeddings=embeddings,
            metadatas=metadatas if any(m for m in metadatas) else None,
            documents=documents if any(d for d in documents) else None
        )
        
        return ids

    async def create_index(self, index_type: str, params: Dict) -> None:
        await self._ensure_initialized()
        
        pass

    async def close(self):
        if self._client:
            try:
                if hasattr(self._client, '_heartbeat'):
                    del self._client
            except Exception:
                pass
            self._client = None
            self._collection = None
            self._initialized = False


ChromaClient = ChromaStore