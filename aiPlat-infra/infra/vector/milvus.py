import asyncio
import uuid
from typing import List, Optional, Dict, Any

from .base import VectorStore
from .schemas import Vector, SearchResult, VectorConfig


class MilvusStore(VectorStore):
    def __init__(self, config: VectorConfig):
        self.config = config
        self._client = None
        self._collection_name = None
        self._dimension = config.dimension
        self._initialized = False
        self._lock = asyncio.Lock()

    async def _ensure_initialized(self):
        if self._initialized:
            return
        async with self._lock:
            if self._initialized:
                return
            await self._init_client()
            self._initialized = True

    async def _init_client(self):
        from pymilvus import MilvusClient

        uri = f"http://{self.config.host}:{self.config.port}"
        self._client = MilvusClient(uri=uri)
        
        collection_name = "default_collection"
        if self.config.collection:
            collection_name = self.config.collection.name
        self._collection_name = collection_name
        
        if not self._client.has_collection(self._collection_name):
            self._client.create_collection(
                collection_name=self._collection_name,
                dimension=self._dimension,
                auto_id=False,
            )
            
            if self.config.index:
                await self.create_index(self.config.index.type, self.config.index.params)

    async def add(
        self, vectors: List[Vector], metadata: List[Dict] = None
    ) -> List[str]:
        await self._ensure_initialized()
        
        if not vectors:
            return []
        
        ids = []
        data = []
        
        for i, vector in enumerate(vectors):
            vec_id = vector.id or str(uuid.uuid4())
            ids.append(vec_id)
            
            meta = vector.metadata.copy()
            if metadata and i < len(metadata):
                meta.update(metadata[i])
            
            row = {
                "id": vec_id,
                "vector": vector.values,
                **meta
            }
            data.append(row)
        
        self._client.insert(
            collection_name=self._collection_name,
            data=data
        )
        
        return ids

    async def search(
        self, query_vector: List[float], top_k: int = 10, filter: Dict = None
    ) -> List[SearchResult]:
        await self._ensure_initialized()
        
        search_params = {}
        if self.config.search:
            search_params["metric_type"] = self.config.search.metric_type
            search_params["params"] = {"ef": self.config.search.ef}
        
        filter_expr = None
        if filter:
            filter_parts = []
            for key, value in filter.items():
                if isinstance(value, str):
                    filter_parts.append(f'{key} == "{value}"')
                elif isinstance(value, (int, float)):
                    filter_parts.append(f"{key} == {value}")
                elif isinstance(value, list):
                    values_str = ", ".join(f'"{v}"' if isinstance(v, str) else str(v) for v in value)
                    filter_parts.append(f"{key} in [{values_str}]")
            if filter_parts:
                filter_expr = " && ".join(filter_parts)
        
        results = self._client.search(
            collection_name=self._collection_name,
            data=[query_vector],
            limit=top_k,
            filter=filter_expr,
            output_fields=["*"],
            search_params=search_params if search_params else None
        )
        
        search_results = []
        if results and len(results) > 0:
            for hit in results[0]:
                metadata = {k: v for k, v in hit.get("entity", {}).items() if k not in ["id", "vector"]}
                search_results.append(SearchResult(
                    id=str(hit.get("id", "")),
                    score=hit.get("distance", 0.0),
                    metadata=metadata
                ))
        
        return search_results

    async def delete(self, ids: List[str]) -> bool:
        await self._ensure_initialized()
        
        if not ids:
            return True
        
        self._client.delete(
            collection_name=self._collection_name,
            ids=ids
        )
        
        return True

    async def get(self, id: str) -> Optional[Vector]:
        await self._ensure_initialized()
        
        results = self._client.get(
            collection_name=self._collection_name,
            ids=[id],
            output_fields=["*"]
        )
        
        if not results:
            return None
        
        result = results[0]
        values = result.get("vector", [])
        metadata = {k: v for k, v in result.items() if k not in ["id", "vector"]}
        
        return Vector(
            id=str(result.get("id", "")),
            values=values,
            metadata=metadata
        )

    async def count(self) -> int:
        await self._ensure_initialized()
        
        stats = self._client.get_collection_stats(self._collection_name)
        return stats.get("row_count", 0)

    async def upsert(self, vectors: List[Vector]) -> List[str]:
        await self._ensure_initialized()
        
        if not vectors:
            return []
        
        ids = []
        data = []
        
        for vector in vectors:
            vec_id = vector.id or str(uuid.uuid4())
            ids.append(vec_id)
            
            row = {
                "id": vec_id,
                "vector": vector.values,
                **vector.metadata
            }
            data.append(row)
        
        self._client.upsert(
            collection_name=self._collection_name,
            data=data
        )
        
        return ids

    async def create_index(self, index_type: str, params: Dict) -> None:
        await self._ensure_initialized()
        
        self._client.create_index(
            collection_name=self._collection_name,
            field_name="vector",
            index_type=index_type,
            metric_type=params.get("metric_type", "IP"),
            params=params.get("params", {})
        )

    async def close(self) -> None:
        if self._client:
            self._client.close()
            self._client = None
            self._initialized = False


MilvusClient = MilvusStore


class LegacyMilvusStore(VectorStore):
    def __init__(self, config: VectorConfig):
        self.config = config
        self._client = None
        self._collection = None
        self._collection_name = None
        self._dimension = config.dimension
        self._initialized = False
        self._lock = asyncio.Lock()

    async def _ensure_initialized(self):
        if self._initialized:
            return
        async with self._lock:
            if self._initialized:
                return
            await self._connect()
            self._initialized = True

    async def _connect(self):
        from pymilvus import connections, Collection, FieldSchema, CollectionSchema, DataType
        
        connections.connect(
            "default",
            host=self.config.host,
            port=self.config.port,
        )
        
        collection_name = "default_collection"
        if self.config.collection:
            collection_name = self.config.collection.name
        self._collection_name = collection_name
        
        from pymilvus import utility
        
        if not utility.has_collection(self._collection_name):
            fields = [
                FieldSchema(name="id", dtype=DataType.VARCHAR, max_length=256, is_primary=True, auto_id=False),
                FieldSchema(name="embedding", dtype=DataType.FLOAT_VECTOR, dim=self._dimension)
            ]
            schema = CollectionSchema(fields, description="Vector collection")
            self._collection = Collection(self._collection_name, schema)
        else:
            self._collection = Collection(self._collection_name)
        
        if self.config.index:
            await self.create_index(self.config.index.type, self.config.index.params)

    async def add(
        self, vectors: List[Vector], metadata: List[Dict] = None
    ) -> List[str]:
        await self._ensure_initialized()
        
        if not vectors:
            return []
        
        ids = []
        embeddings = []
        
        for i, vector in enumerate(vectors):
            vec_id = vector.id or str(uuid.uuid4())
            ids.append(vec_id)
            embeddings.append(vector.values)
        
        self._collection.insert([ids, embeddings])
        self._collection.flush()
        
        return ids

    async def search(
        self, query_vector: List[float], top_k: int = 10, filter: Dict = None
    ) -> List[SearchResult]:
        await self._ensure_initialized()
        
        search_params = {"metric_type": "IP", "params": {"nprobe": 10}}
        if self.config.search:
            search_params["metric_type"] = self.config.search.metric_type
        
        self._collection.load()
        
        results = self._collection.search(
            data=[query_vector],
            anns_field="embedding",
            param=search_params,
            limit=top_k,
        )
        
        search_results = []
        if results and len(results) > 0:
            for hit in results[0]:
                search_results.append(SearchResult(
                    id=str(hit.id),
                    score=float(hit.distance),
                    metadata={}
                ))
        
        return search_results

    async def delete(self, ids: List[str]) -> bool:
        await self._ensure_initialized()
        
        if not ids:
            return True
        
        expr = f"id in {ids}"
        self._collection.delete(expr)
        self._collection.flush()
        
        return True

    async def get(self, id: str) -> Optional[Vector]:
        await self._ensure_initialized()
        
        self._collection.load()
        
        results = self._collection.query(
            expr=f'id == "{id}"',
            output_fields=["id", "embedding"]
        )
        
        if not results:
            return None
        
        result = results[0]
        return Vector(
            id=str(result.get("id", "")),
            values=result.get("embedding", []),
            metadata={}
        )

    async def count(self) -> int:
        await self._ensure_initialized()
        
        stats = self._collection.num_entities
        return stats

    async def upsert(self, vectors: List[Vector]) -> List[str]:
        return await self.add(vectors)

    async def create_index(self, index_type: str, params: Dict) -> None:
        await self._ensure_initialized()
        
        index_params = {
            "metric_type": params.get("metric_type", "IP"),
            "index_type": index_type,
            "params": params.get("params", {})
        }
        
        self._collection.create_index("embedding", index_params)

    async def close(self):
        from pymilvus import connections
        
        if self._collection:
            self._collection.release()
            self._collection = None
        
        connections.disconnect("default")
        self._initialized = False