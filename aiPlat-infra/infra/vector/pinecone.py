import asyncio
import uuid
from typing import List, Optional, Dict, Any

from .base import VectorStore
from .schemas import Vector, SearchResult, VectorConfig


class PineconeStore(VectorStore):
    def __init__(self, config: VectorConfig):
        self.config = config
        self._client = None
        self._index = None
        self._index_name = None
        self._dimension = config.dimension
        self._initialized = False
        self._lock = asyncio.Lock()
        self._namespace = ""
        
        if config.collection:
            self._index_name = config.collection.name
            if config.collection.description:
                self._namespace = config.collection.description

    async def _ensure_initialized(self):
        if self._initialized:
            return
        async with self._lock:
            if self._initialized:
                return
            await self._init_client()
            self._initialized = True

    async def _init_client(self):
        import pinecone
        
        api_key = self.config.index.params.get("api_key") if self.config.index else None
        if not api_key:
            api_key = self.config.index.params.get("api_key", "") if self.config.index and self.config.index.params else ""
        
        if not api_key:
            raise ValueError("Pinecone API key is required in config.index.params['api_key']")
        
        environment = self.config.index.params.get("environment", "us-east-1") if self.config.index else "us-east-1"
        
        pc = pinecone.Pinecone(api_key=api_key)
        self._client = pc
        
        if not self._index_name:
            self._index_name = "default-index"
        
        existing_indexes = [idx.name for idx in pc.list_indexes()]
        
        if self._index_name not in existing_indexes:
            pc.create_index(
                name=self._index_name,
                dimension=self._dimension,
                metric=self.config.search.metric_type.lower() if self.config.search else "cosine",
                spec=pinecone.ServerlessSpec(
                    cloud="aws",
                    region=environment
                )
            )
        
        self._index = pc.Index(self._index_name)

    async def add(
        self, vectors: List[Vector], metadata: List[Dict] = None
    ) -> List[str]:
        await self._ensure_initialized()
        
        if not vectors:
            return []
        
        ids = []
        vectors_to_upsert = []
        
        for i, vector in enumerate(vectors):
            vec_id = vector.id or str(uuid.uuid4())
            ids.append(vec_id)
            
            meta = vector.metadata.copy()
            if metadata and i < len(metadata):
                meta.update(metadata[i])
            
            meta = {k: v for k, v in meta.items() if isinstance(v, (str, int, float, bool, list))}
            
            vectors_to_upsert.append((vec_id, vector.values, meta))
        
        batch_size = 100
        for i in range(0, len(vectors_to_upsert), batch_size):
            batch = vectors_to_upsert[i:i + batch_size]
            self._index.upsert(vectors=batch, namespace=self._namespace)
        
        return ids

    async def search(
        self, query_vector: List[float], top_k: int = 10, filter: Dict = None
    ) -> List[SearchResult]:
        await self._ensure_initialized()
        
        filter_dict = None
        if filter:
            filter_dict = {}
            for key, value in filter.items():
                if isinstance(value, list):
                    filter_dict[key] = {"$in": value}
                else:
                    filter_dict[key] = {"$eq": value}
        
        results = self._index.query(
            vector=query_vector,
            top_k=top_k,
            namespace=self._namespace,
            filter=filter_dict,
            include_metadata=True
        )
        
        search_results = []
        
        if results and hasattr(results, 'matches'):
            for match in results.matches:
                search_results.append(SearchResult(
                    id=match.id,
                    score=float(match.score),
                    metadata=dict(match.metadata) if hasattr(match, 'metadata') and match.metadata else {}
                ))
        
        return search_results

    async def delete(self, ids: List[str]) -> bool:
        await self._ensure_initialized()
        
        if not ids:
            return True
        
        self._index.delete(ids=ids, namespace=self._namespace)
        
        return True

    async def get(self, id: str) -> Optional[Vector]:
        await self._ensure_initialized()
        
        results = self._index.fetch(ids=[id], namespace=self._namespace)
        
        if not results or not hasattr(results, 'vectors') or id not in results.vectors:
            return None
        
        vec = results.vectors[id]
        
        return Vector(
            id=id,
            values=list(vec.values) if hasattr(vec, 'values') else [],
            metadata=dict(vec.metadata) if hasattr(vec, 'metadata') and vec.metadata else {}
        )

    async def count(self) -> int:
        await self._ensure_initialized()
        
        stats = self._index.describe_index_stats()
        
        if self._namespace and hasattr(stats, 'namespaces') and self._namespace in stats.namespaces:
            return stats.namespaces[self._namespace].vector_count
        
        return stats.total_vector_count if hasattr(stats, 'total_vector_count') else 0

    async def upsert(self, vectors: List[Vector]) -> List[str]:
        await self._ensure_initialized()
        
        if not vectors:
            return []
        
        ids = []
        vectors_to_upsert = []
        
        for vector in vectors:
            vec_id = vector.id or str(uuid.uuid4())
            ids.append(vec_id)
            
            meta = vector.metadata.copy()
            meta = {k: v for k, v in meta.items() if isinstance(v, (str, int, float, bool, list))}
            
            vectors_to_upsert.append((vec_id, vector.values, meta))
        
        batch_size = 100
        for i in range(0, len(vectors_to_upsert), batch_size):
            batch = vectors_to_upsert[i:i + batch_size]
            self._index.upsert(vectors=batch, namespace=self._namespace)
        
        return ids

    async def create_index(self, index_type: str, params: Dict) -> None:
        await self._ensure_initialized()
        
        pass

    async def close(self) -> None:
        if self._index:
            self._index = None
        if self._client:
            self._client = None
        self._initialized = False


PineconeClient = PineconeStore