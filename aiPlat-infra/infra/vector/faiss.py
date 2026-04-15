import asyncio
import json
import os
import uuid
from pathlib import Path
from typing import List, Optional, Dict, Any

import numpy as np

from .base import VectorStore
from .schemas import Vector, SearchResult, VectorConfig


class FaissStore(VectorStore):
    def __init__(self, config: VectorConfig):
        self.config = config
        self._index = None
        self._id_to_idx: Dict[str, int] = {}
        self._idx_to_id: Dict[int, str] = {}
        self._metadata: Dict[str, Dict] = {}
        self._dimension = config.dimension
        self._next_idx = 0
        self._lock = asyncio.Lock()
        self._persist_path: Optional[str] = None
        self._index_type = "IndexFlatIP"
        
        if config.index:
            self._index_type = config.index.type
        
        if config.collection and config.collection.name:
            self._persist_path = config.collection.name

    async def _ensure_initialized(self):
        if self._index is not None:
            return
        async with self._lock:
            if self._index is not None:
                return
            await self._init_index()

    async def _init_index(self):
        import faiss
        
        self._index = self._create_index()
        
        if self._persist_path and os.path.exists(f"{self._persist_path}.index"):
            try:
                self._index = faiss.read_index(f"{self._persist_path}.index")
                if os.path.exists(f"{self._persist_path}.meta"):
                    with open(f"{self._persist_path}.meta", "r") as f:
                        meta_data = json.load(f)
                        self._id_to_idx = {k: int(v) for k, v in meta_data.get("id_to_idx", {}).items()}
                        self._idx_to_id = {int(k): v for k, v in meta_data.get("idx_to_id", {}).items()}
                        self._metadata = meta_data.get("metadata", {})
                        self._next_idx = meta_data.get("next_idx", 0)
            except Exception:
                self._index = self._create_index()

    def _create_index(self):
        import faiss
        
        if self._index_type == "IndexFlatIP":
            return faiss.IndexFlatIP(self._dimension)
        elif self._index_type == "IndexFlatL2":
            return faiss.IndexFlatL2(self._dimension)
        elif self._index_type == "IndexIVFFlat":
            quantizer = faiss.IndexFlatIP(self._dimension)
            return faiss.IndexIVFFlat(quantizer, self._dimension, 100)
        elif self._index_type == "IndexIVFPQ":
            quantizer = faiss.IndexFlatIP(self._dimension)
            return faiss.IndexIVFPQ(quantizer, self._dimension, 100, 8, 8)
        elif self._index_type == "IndexHNSW":
            index = faiss.IndexHNSWFlat(self._dimension, 32)
            return index
        else:
            return faiss.IndexFlatIP(self._dimension)

    async def _persist(self):
        if not self._persist_path:
            return
        
        import faiss
        
        faiss.write_index(self._index, f"{self._persist_path}.index")
        
        meta_data = {
            "id_to_idx": self._id_to_idx,
            "idx_to_id": self._idx_to_id,
            "metadata": self._metadata,
            "next_idx": self._next_idx
        }
        
        with open(f"{self._persist_path}.meta", "w") as f:
            json.dump(meta_data, f)

    async def add(
        self, vectors: List[Vector], metadata: List[Dict] = None
    ) -> List[str]:
        await self._ensure_initialized()
        
        if not vectors:
            return []
        
        async with self._lock:
            ids = []
            embeddings = []
            
            for i, vector in enumerate(vectors):
                vec_id = vector.id or str(uuid.uuid4())
                
                if vec_id in self._id_to_idx:
                    ids.append(vec_id)
                    continue
                
                ids.append(vec_id)
                embeddings.append(vector.values)
                
                meta = vector.metadata.copy()
                if metadata and i < len(metadata):
                    meta.update(metadata[i])
                
                self._id_to_idx[vec_id] = self._next_idx
                self._idx_to_id[self._next_idx] = vec_id
                self._metadata[vec_id] = meta
                self._next_idx += 1
            
            if embeddings:
                embeddings_array = np.array(embeddings, dtype=np.float32)
                self._index.add(embeddings_array)
            
            await self._persist()
            
            return ids

    async def search(
        self, query_vector: List[float], top_k: int = 10, filter: Dict = None
    ) -> List[SearchResult]:
        await self._ensure_initialized()
        
        if self._index.ntotal == 0:
            return []
        
        query_array = np.array([query_vector], dtype=np.float32)
        
        actual_k = min(top_k, self._index.ntotal)
        if actual_k == 0:
            return []
        
        distances, indices = self._index.search(query_array, actual_k)
        
        results = []
        for i in range(actual_k):
            idx = int(indices[0][i])
            if idx == -1:
                continue
            
            vec_id = self._idx_to_id.get(idx)
            if vec_id is None:
                continue
            
            meta = self._metadata.get(vec_id, {}).copy()
            
            if filter:
                match = True
                for key, value in filter.items():
                    if key not in meta or meta[key] != value:
                        match = False
                        break
                if not match:
                    continue
            
            score = float(distances[0][i])
            
            results.append(SearchResult(
                id=vec_id,
                score=score,
                metadata=meta
            ))
        
        return results

    async def delete(self, ids: List[str]) -> bool:
        await self._ensure_initialized()
        
        if not ids:
            return True
        
        async with self._lock:
            ids_to_remove = []
            
            for vec_id in ids:
                if vec_id in self._id_to_idx:
                    ids_to_remove.append(vec_id)
            
            for vec_id in ids_to_remove:
                idx = self._id_to_idx.pop(vec_id, None)
                if idx is not None:
                    self._idx_to_id.pop(idx, None)
                self._metadata.pop(vec_id, None)
            
            await self._persist()
        
        return True

    async def get(self, id: str) -> Optional[Vector]:
        await self._ensure_initialized()
        
        if id not in self._id_to_idx:
            return None
        
        idx = self._id_to_idx[id]
        
        import faiss
        
        try:
            if hasattr(self._index, 'xb'):
                vector_data = self._index.xb[idx]
            elif hasattr(self._index, 'storage'):
                vector_data = self._index.storage.xb[idx]
            else:
                self._index.reconstruct(idx)
                vector_data = self._index.reconstruct(idx)
        except Exception:
            return None
        
        return Vector(
            id=id,
            values=vector_data.tolist() if hasattr(vector_data, 'tolist') else list(vector_data),
            metadata=self._metadata.get(id, {}).copy()
        )

    async def count(self) -> int:
        await self._ensure_initialized()
        return self._index.ntotal

    async def upsert(self, vectors: List[Vector]) -> List[str]:
        await self._ensure_initialized()
        
        if not vectors:
            return []
        
        async with self._lock:
            ids = []
            embeddings_to_add = []
            ids_to_remove = []
            
            for vector in vectors:
                vec_id = vector.id or str(uuid.uuid4())
                ids.append(vec_id)
                
                if vec_id in self._id_to_idx:
                    ids_to_remove.append(vec_id)
            
            for vec_id in ids_to_remove:
                idx = self._id_to_idx.pop(vec_id, None)
                if idx is not None:
                    self._idx_to_id.pop(idx, None)
            
            for vector in vectors:
                vec_id = vector.id or str(uuid.uuid4())
                
                if vec_id not in ids:
                    ids.append(vec_id)
                
                embeddings_to_add.append(vector.values)
                self._id_to_idx[vec_id] = self._next_idx
                self._idx_to_id[self._next_idx] = vec_id
                self._metadata[vec_id] = vector.metadata.copy()
                self._next_idx += 1
            
            if embeddings_to_add:
                embeddings_array = np.array(embeddings_to_add, dtype=np.float32)
                self._index.add(embeddings_array)
            
            await self._persist()
            
            return ids

    async def create_index(self, index_type: str, params: Dict) -> None:
        await self._ensure_initialized()
        
        self._index_type = index_type
        
        if self._index.ntotal > 0:
            vectors = []
            for idx in range(self._index.ntotal):
                try:
                    vec = self._index.reconstruct(idx)
                    vectors.append(vec)
                except Exception:
                    pass
            
            if vectors:
                import faiss
                
                old_ids = list(self._id_to_idx.keys())
                old_metas = [self._metadata.get(id, {}) for id in old_ids]
                
                self._index = self._create_index()
                
                vectors_array = np.array(vectors, dtype=np.float32)
                self._index.add(vectors_array)
                
                self._id_to_idx = {}
                self._idx_to_id = {}
                self._next_idx = 0
                
                for i, old_id in enumerate(old_ids):
                    self._id_to_idx[old_id] = i
                    self._idx_to_id[i] = old_id
                    self._metadata[old_id] = old_metas[i]
                    self._next_idx = i + 1
        else:
            import faiss
            self._index = self._create_index()
        
        await self._persist()

    async def close(self) -> None:
        async with self._lock:
            if self._persist_path:
                await self._persist()
            self._index = None


FaissClient = FaissStore


class LegacyFaissStore(VectorStore):
    def __init__(self, config: VectorConfig):
        self.config = config
        self._index = None
        self._id_to_idx: Dict[str, int] = {}
        self._idx_to_id: Dict[int, str] = {}
        self._metadata: Dict[str, Dict] = {}
        self._dimension = config.dimension
        self._next_idx = 0
        self._lock = asyncio.Lock()
        self._persist_path: Optional[str] = None
        
        if config.collection and config.collection.name:
            self._persist_path = config.collection.name

    async def _ensure_initialized(self):
        if self._index is not None:
            return
        async with self._lock:
            if self._index is not None:
                return
            await self._init_index()

    async def _init_index(self):
        import faiss
        
        self._index = faiss.IndexFlatIP(self._dimension)
        
        if self._persist_path and os.path.exists(f"{self._persist_path}.index"):
            try:
                self._index = faiss.read_index(f"{self._persist_path}.index")
                if os.path.exists(f"{self._persist_path}.meta"):
                    with open(f"{self._persist_path}.meta", "r") as f:
                        meta_data = json.load(f)
                        self._id_to_idx = {k: int(v) for k, v in meta_data.get("id_to_idx", {}).items()}
                        self._idx_to_id = {int(k): v for k, v in meta_data.get("idx_to_id", {}).items()}
                        self._metadata = meta_data.get("metadata", {})
                        self._next_idx = meta_data.get("next_idx", 0)
            except Exception:
                self._index = faiss.IndexFlatIP(self._dimension)

    async def add(
        self, vectors: List[Vector], metadata: List[Dict] = None
    ) -> List[str]:
        await self._ensure_initialized()
        
        if not vectors:
            return []
        
        async with self._lock:
            ids = []
            embeddings = []
            
            for i, vector in enumerate(vectors):
                vec_id = vector.id or str(uuid.uuid4())
                ids.append(vec_id)
                embeddings.append(vector.values)
                
                meta = vector.metadata.copy()
                if metadata and i < len(metadata):
                    meta.update(metadata[i])
                
                self._id_to_idx[vec_id] = self._next_idx
                self._idx_to_id[self._next_idx] = vec_id
                self._metadata[vec_id] = meta
                self._next_idx += 1
            
            embeddings_array = np.array(embeddings, dtype=np.float32)
            self._index.add(embeddings_array)
            
            return ids

    async def search(
        self, query_vector: List[float], top_k: int = 10, filter: Dict = None
    ) -> List[SearchResult]:
        await self._ensure_initialized()
        
        if self._index.ntotal == 0:
            return []
        
        query_array = np.array([query_vector], dtype=np.float32)
        actual_k = min(top_k, self._index.ntotal)
        
        distances, indices = self._index.search(query_array, actual_k)
        
        results = []
        for i in range(actual_k):
            idx = int(indices[0][i])
            if idx == -1:
                continue
            
            vec_id = self._idx_to_id.get(idx)
            if vec_id is None:
                continue
            
            meta = self._metadata.get(vec_id, {}).copy()
            
            if filter:
                match = True
                for key, value in filter.items():
                    if key not in meta or meta[key] != value:
                        match = False
                        break
                if not match:
                    continue
            
            results.append(SearchResult(
                id=vec_id,
                score=float(distances[0][i]),
                metadata=meta
            ))
        
        return results

    async def delete(self, ids: List[str]) -> bool:
        await self._ensure_initialized()
        
        async with self._lock:
            for vec_id in ids:
                if vec_id in self._id_to_idx:
                    self._id_to_idx.pop(vec_id)
                    self._idx_to_id.pop(self._id_to_idx.get(vec_id))
                    self._metadata.pop(vec_id, None)
        
        return True

    async def get(self, id: str) -> Optional[Vector]:
        await self._ensure_initialized()
        
        if id not in self._id_to_idx:
            return None
        
        idx = self._id_to_idx[id]
        
        try:
            vector_data = self._index.reconstruct(idx)
        except Exception:
            return None
        
        return Vector(
            id=id,
            values=vector_data.tolist(),
            metadata=self._metadata.get(id, {}).copy()
        )

    async def count(self) -> int:
        await self._ensure_initialized()
        return self._index.ntotal

    async def upsert(self, vectors: List[Vector]) -> List[str]:
        return await self.add(vectors)

    async def create_index(self, index_type: str, params: Dict) -> None:
        await self._ensure_initialized()

    async def close(self):
        async with self._lock:
            if self._persist_path:
                import faiss
                faiss.write_index(self._index, f"{self._persist_path}.index")
                meta_data = {
                    "id_to_idx": self._id_to_idx,
                    "idx_to_id": self._idx_to_id,
                    "metadata": self._metadata,
                    "next_idx": self._next_idx
                }
                with open(f"{self._persist_path}.meta", "w") as f:
                    json.dump(meta_data, f)
            self._index = None