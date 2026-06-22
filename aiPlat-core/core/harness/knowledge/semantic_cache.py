"""
Semantic Cache — 多级缓存系统降低 LLM API 成本。

三层缓存:
  Layer 1 (L1): 精确匹配 — md5(query+domain_id) → Redis GET
  Layer 2 (L2): 语义相似 — embedding cosine ≥ 0.95 → 返回缓存
  Layer 3 (L3): 无命中 → 走正常 Pipeline → 写入缓存

失效策略:
  知识库更新 → 清空相关 domain 的 L1/L2 缓存
  
Usage:
    cache = SemanticCache()
    cached = await cache.get(query, domain_id)
    if cached:
        return cached  # TTFT < 50ms
    result = await pipeline(query)
    await cache.set(query, domain_id, result)
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import os
import time
from typing import Any, Dict, List, Optional, Tuple


class SemanticCache:
    """多级语义缓存。

    环境变量:
        AIPLAT_CACHE_REDIS_URL: Redis 连接 URL (默认: redis://localhost:6379)
        AIPLAT_CACHE_ENABLED: 是否启用缓存 (默认: true)
        AIPLAT_CACHE_TTL: 缓存过期秒数 (默认: 3600=1h)
        AIPLAT_CACHE_L2_SIMILARITY: L2 相似度阈值 (默认: 0.95)
    """

    def __init__(
        self,
        redis_url: str = "",
        ttl: int = 0,
        l2_threshold: float = 0.0,
    ):
        self._redis_url = redis_url or os.getenv("AIPLAT_CACHE_REDIS_URL", "redis://localhost:6379")
        self._ttl = ttl or int(os.getenv("AIPLAT_CACHE_TTL", "3600"))
        self._l2_threshold = l2_threshold or float(os.getenv("AIPLAT_CACHE_L2_SIMILARITY", "0.95"))
        self._enabled = os.getenv("AIPLAT_CACHE_ENABLED", "true").lower() not in ("0", "false", "no")
        self._redis: Any = None
        self._l1_hits: int = 0
        self._l2_hits: int = 0
        self._misses: int = 0
        self._latent: Any = LatentStageCache()

    @property
    def enabled(self) -> bool:
        return self._enabled

    @property
    def stats(self) -> Dict[str, Any]:
        total = self._l1_hits + self._l2_hits + self._misses
        return {
            "l1_hits": self._l1_hits,
            "l2_hits": self._l2_hits,
            "misses": self._misses,
            "hit_rate": f"{((self._l1_hits + self._l2_hits) / max(total, 1)) * 100:.1f}%",
            "total_requests": total,
        }

    async def _ensure_redis(self):
        if self._redis is not None:
            return
        try:
            import redis.asyncio as aioredis
            self._redis = aioredis.from_url(
                self._redis_url,
                socket_connect_timeout=2,
                socket_timeout=1,
                decode_responses=True,
            )
            await self._redis.ping()
        except Exception:
            self._redis = False  # type: ignore[assignment]
            self._enabled = False

    def _cache_key(self, query: str, domain_id: str) -> str:
        raw = f"aiplat:cache:v1:{domain_id}:{query.strip().lower()}"
        return hashlib.md5(raw.encode()).hexdigest()

    def _l1_key(self, query: str, domain_id: str) -> str:
        return f"l1:{self._cache_key(query, domain_id)}"

    def _embed_key(self, query: str, domain_id: str) -> str:
        return f"l2:{self._cache_key(query, domain_id)}"

    # ── Layer 1: Exact Match ────────────────────────────────────────────

    async def get_l1(self, query: str, domain_id: str) -> Optional[Dict[str, Any]]:
        """精确匹配缓存。"""
        await self._ensure_redis()
        if not self._enabled or self._redis is False:
            return None
        try:
            raw = await self._redis.get(self._l1_key(query, domain_id))
            if raw:
                self._l1_hits += 1
                return json.loads(raw)
        except Exception:
            pass
        return None

    async def set_l1(self, query: str, domain_id: str, result: Dict[str, Any]):
        await self._ensure_redis()
        if not self._enabled or self._redis is False:
            return
        try:
            await self._redis.setex(
                self._l1_key(query, domain_id),
                self._ttl,
                json.dumps(result, ensure_ascii=False),
            )
        except Exception:
            pass

    # ── Layer 2: Semantic Similarity ─────────────────────────────────────

    async def _embed(self, text: str) -> list:
        """Get embedding vector for text."""
        try:
            from core.harness.knowledge.embedder import embed_text
            return await embed_text(text)
        except Exception:
            return []

    async def get_l2(self, query: str, domain_id: str) -> Optional[Dict[str, Any]]:
        """语义相似缓存。"""
        await self._ensure_redis()
        if not self._enabled or self._redis is False:
            return None
        try:
            query_vec = await self._embed(query)
            if not query_vec:
                return None
            # Search for similar embeddings in Redis
            vec_bytes = json.dumps(query_vec)
            # Use simple key scan (Redis VECTOR_SIM requires Redis Stack)
            # Fallback: iterate known L2 keys and compute cosine
            pattern = f"l2:{domain_id}:*"
            keys = []
            async for key in self._redis.scan_iter(match=f"aiplat:cache:v1:{domain_id}:*"):
                keys.append(key)
            for key in keys[:20]:  # limit to 20 candidates
                raw = await self._redis.get(key)
                if not raw:
                    continue
                try:
                    cached_vec = json.loads(raw)
                    sim = self._cosine_similarity(query_vec, cached_vec)
                    if sim >= self._l2_threshold:
                        self._l2_hits += 1
                        # Retrieve the actual result
                        result_key = key.replace("l2:", "l1:", 1)
                        result_raw = await self._redis.get(result_key)
                        if result_raw:
                            return json.loads(result_raw)
                except Exception:
                    continue
        except Exception:
            pass
        return None

    async def set_l2(self, query: str, domain_id: str, result: Dict[str, Any]):
        """Store embedding vector for semantic search."""
        await self._ensure_redis()
        if not self._enabled or self._redis is False:
            return
        try:
            query_vec = await self._embed(query)
            if not query_vec:
                return
            await self._redis.setex(
                self._embed_key(query, domain_id),
                self._ttl,
                json.dumps(query_vec),
            )
        except Exception:
            pass

    # ── Public API ────────────────────────────────────────────────────────

    async def get(self, query: str, domain_id: str = "default") -> Optional[Dict[str, Any]]:
        """Try L1 → L2(Latent) → L3(Redis)."""
        if not self._enabled:
            return None
        # L1
        result = await self.get_l1(query, domain_id)
        if result:
            return result
        # L2: LatentStageCache — in-memory multi-stage vector match (primary semantic layer)
        try:
            query_vec = await self._embed(query)
            if query_vec and len(query_vec) > 0:
                matches = await self._latent.match(query_vec, top_k=1)
                if matches and matches[0].get("score", 0) >= 0.85:
                    self._l2_hits += 1
                    return matches[0].get("result") or matches[0]
        except Exception:
            pass
        # L3: Redis semantic similarity (backup)
        result = await self.get_l2(query, domain_id)
        if result:
            return result
        self._misses += 1
        return None

    async def set(self, query: str, domain_id: str, result: Dict[str, Any]):
        """Store in L1 + L2."""
        if not self._enabled:
            return
        await self.set_l1(query, domain_id, result)
        await self.set_l2(query, domain_id, result)
        # Store in LatentStageCache for multi-stage matching
        try:
            query_vec = await self._embed(query)
            if query_vec:
                await self._latent.store_stage(
                    self._cache_key(query, domain_id), "query", query_vec,
                    metadata={"domain": domain_id, "result": result},
                )
        except Exception:
            pass

    async def invalidate_domain(self, domain_id: str):
        """Invalidate all cache for a domain (e.g., after KB update)."""
        await self._ensure_redis()
        if not self._enabled or self._redis is False:
            return
        try:
            pattern = f"aiplat:cache:v1:{domain_id}:*"
            keys = []
            async for key in self._redis.scan_iter(match=pattern):
                keys.append(key)
            if keys:
                await self._redis.delete(*keys)
        except Exception:
            pass

    def _cosine_similarity(self, a: list, b: list) -> float:
        """Compute cosine similarity between two vectors."""
        if not a or not b or len(a) != len(b):
            return 0.0
        dot = sum(x * y for x, y in zip(a, b))
        norm_a = sum(x * x for x in a) ** 0.5
        norm_b = sum(x * x for x in b) ** 0.5
        if norm_a == 0 or norm_b == 0:
            return 0.0
        return dot / (norm_a * norm_b)


# ── Phase 5.2: Latent Stage Cache ── 多阶段隐空间缓存 ───────────────────────

class LatentStageCache:
    """多阶段隐空间缓存 — 缓存 RAG Pipeline 中间状态的向量"足迹"。

    不仅缓存最终答案，还缓存整个推理路径的中间状态向量:
      - Stage 1: 查询改写后的 query_embedding
      - Stage 2: 域路由后的 domain_vector
      - Stage 3: 检索结果聚和的 retrieval_vector
      - Stage N: 最终答案的 answer_embedding

    检索时使用多级相似度组合: 
      combined_score = α·query_sim + β·domain_sim + γ·retrieval_sim

    环境变量:
        AIPLAT_LATENT_CACHE_ENABLED: 是否启用 (默认: true)
        AIPLAT_LATENT_CACHE_ALPHA: query 权重 (默认: 0.4)
        AIPLAT_LATENT_CACHE_BETA: domain 权重 (默认: 0.2)
        AIPLAT_LATENT_CACHE_GAMMA: retrieval 权重 (默认: 0.4)
    """

    def __init__(self):
        self._enabled = os.getenv("AIPLAT_LATENT_CACHE_ENABLED", "true").lower() not in ("0", "false", "no")
        self._alpha = float(os.getenv("AIPLAT_LATENT_CACHE_ALPHA", "0.4"))
        self._beta = float(os.getenv("AIPLAT_LATENT_CACHE_BETA", "0.2"))
        self._gamma = float(os.getenv("AIPLAT_LATENT_CACHE_GAMMA", "0.4"))
        self._stages: Dict[str, Dict[str, Any]] = {}  # run_id → stage vectors
        self._max_entries = 2000

    async def store_stage(
        self,
        run_id: str,
        stage_name: str,
        vector: List[float],
        metadata: Dict[str, Any] = None,
    ):
        """存储单个阶段的向量"""
        if not self._enabled:
            return
        if run_id not in self._stages:
            self._stages[run_id] = {}
        self._stages[run_id][stage_name] = {
            "vector": vector,
            "metadata": metadata or {},
            "ts": time.time(),
        }
        # Evict oldest
        if len(self._stages) > self._max_entries:
            oldest = sorted(self._stages.keys(), key=lambda r: self._stages[r].get("ts", 0))[0]
            del self._stages[oldest]

    async def match(
        self,
        query_vector: List[float],
        domain_vector: List[float] = None,
        top_k: int = 3,
    ) -> List[Dict[str, Any]]:
        """多级隐空间相似度匹配。

        combined_score = α·query_sim + β·domain_sim + γ·retrieval_sim

        Returns:
            匹配结果列表 [{run_id, score, results, domain}]
        """
        if not self._enabled or not self._stages:
            return []

        scored = []
        for run_id, stages in self._stages.items():
            q_vec = stages.get("query_embedding", {}).get("vector", [])
            d_vec = stages.get("domain_vector", {}).get("vector", [])
            r_vec = stages.get("retrieval_vector", {}).get("vector", [])

            query_sim = self._cosine(query_vector, q_vec) if q_vec else 0.0
            domain_sim = self._cosine(domain_vector or [], d_vec) if d_vec else 0.0
            retrieval_sim = self._cosine(query_vector, r_vec) if r_vec else 0.0  # reuse query_vec

            combined = (
                self._alpha * query_sim +
                self._beta * domain_sim +
                self._gamma * retrieval_sim
            )

            if combined > 0.5:  # minimum combined threshold
                result = stages.get("result", {})
                scored.append({
                    "run_id": run_id,
                    "score": round(combined, 3),
                    "query_sim": round(query_sim, 3),
                    "domain_sim": round(domain_sim, 3),
                    "answer": result.get("answer", "")[:200] if isinstance(result, dict) else str(result)[:200],
                })

        scored.sort(key=lambda x: -x["score"])
        return scored[:top_k]

    def _cosine(self, a: List[float], b: List[float]) -> float:
        if not a or not b or len(a) != len(b):
            return 0.0
        dot = sum(x * y for x, y in zip(a, b))
        norm_a = sum(x * x for x in a) ** 0.5
        norm_b = sum(x * x for x in b) ** 0.5
        if norm_a == 0 or norm_b == 0:
            return 0.0
        return dot / (norm_a * norm_b)

    def stats(self) -> Dict[str, Any]:
        return {
            "enabled": self._enabled,
            "entries": len(self._stages),
            "weights": {"alpha": self._alpha, "beta": self._beta, "gamma": self._gamma},
        }


# ── Global singleton ─────────────────────────────────────────────────────────

_cache: Optional[SemanticCache] = None


def get_semantic_cache() -> SemanticCache:
    global _cache
    if _cache is None:
        _cache = SemanticCache()
    return _cache
