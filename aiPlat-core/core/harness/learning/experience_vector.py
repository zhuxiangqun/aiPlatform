"""
Experience Vector Cache — 经验向量存储与检索 (Phase 5.1)

将 PipelineTrace 的执行轨迹 Embedding 后存入向量库，AutoLearner 和 MetaAgent
通过语义相似度检索历史经验。

"软隐空间"核心: 用 Embedding 向量承载高信息密度的执行经验，在向量空间做语义检索。

Usage:
    cache = ExperienceVectorCache()
    # 存储经验
    await cache.store(run_id, trajectory_summary, label="success")
    # 检索相似经验
    experiences = await cache.search(error_description, top_k=3)
    # 为 AutoLearner 提供上下文
    context = await cache.enrich_skill_draft(error_description)
"""

from __future__ import annotations

import json
import os
import time
import hashlib
import asyncio
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple


@dataclass
class ExperienceEntry:
    """单条经验记录"""
    id: str
    run_id: str
    summary: str                    # 轨迹摘要 (文本)
    embedding: List[float] = field(default_factory=list)  # Embedding 向量
    label: str = ""                 # success / failure / exception
    domain_id: str = "default"
    tags: List[str] = field(default_factory=list)
    created_at: float = field(default_factory=time.time)


class ExperienceVectorCache:
    """经验向量缓存 — 在 Embedding 空间做经验检索。

    存储层: 内存 + JSON 文件 (轻量)
    检索层: Embedding cosine similarity

    环境变量:
        AIPLAT_EXPERIENCE_CACHE_SIZE: 最大条目 (默认: 5000)
        AIPLAT_EXPERIENCE_CACHE_ENABLED: 是否启用 (默认: true)
    """

    def __init__(self):
        self._entries: Dict[str, ExperienceEntry] = {}
        self._max_size = int(os.getenv("AIPLAT_EXPERIENCE_CACHE_SIZE", "5000"))
        self._enabled = os.getenv("AIPLAT_EXPERIENCE_CACHE_ENABLED", "true").lower() not in ("0", "false", "no")
        self._storage_path = os.path.expanduser("~/.aiplat/experience_cache.json")
        self._load_from_disk()

    # ── Public API ──────────────────────────────────────────────────────

    async def store(
        self,
        run_id: str,
        summary: str,
        *,
        label: str = "",
        domain_id: str = "default",
        tags: List[str] = None,
    ) -> Optional[str]:
        """存储一条执行经验。

        Args:
            run_id: 执行 ID
            summary: 执行轨迹摘要 (文本)
            label: success / failure / exception
            domain_id: 域标识
            tags: 标签

        Returns:
            经验 ID
        """
        if not self._enabled:
            return None

        # Generate embedding
        embedding = await self._embed(summary)
        if not embedding:
            return None

        entry_id = hashlib.md5(run_id.encode()).hexdigest()[:12]
        self._entries[entry_id] = ExperienceEntry(
            id=entry_id,
            run_id=run_id,
            summary=summary[:2000],
            embedding=embedding,
            label=label,
            domain_id=domain_id,
            tags=tags or [],
        )

        # Evict oldest if over limit
        if len(self._entries) > self._max_size:
            oldest = sorted(self._entries.values(), key=lambda e: e.created_at)[0]
            del self._entries[oldest.id]

        # Persist periodically (every 100 entries)
        if len(self._entries) % 100 == 0:
            await self._persist()

        return entry_id

    async def search(
        self,
        query: str,
        *,
        top_k: int = 5,
        label: str = "",
        domain_id: str = "",
    ) -> List[ExperienceEntry]:
        """检索相似经验 (cosine + keyword 混合)。

        Args:
            query: 查询文本 (如错误描述)
            top_k: 返回 Top-K
            label: 过滤标签
            domain_id: 过滤域

        Returns:
            相似经验列表 (按相似度降序)
        """
        if not self._enabled or not self._entries:
            return []

        query_vec = await self._embed(query)
        if not query_vec:
            return []

        # Extract query keywords for fallback scoring
        import re as _re
        query_kw = set(_re.findall(r'[a-zA-Z一-鿿]{2,}', query.lower()))

        scored = []
        for entry in self._entries.values():
            if label and entry.label != label:
                continue
            if domain_id and entry.domain_id != domain_id:
                continue
            cos_sim = self._cosine(query_vec, entry.embedding)
            # Keyword overlap bonus
            entry_kw = set(_re.findall(r'[a-zA-Z一-鿿]{2,}', entry.summary.lower()))
            kw_overlap = len(query_kw & entry_kw) / max(len(query_kw | entry_kw), 1)
            combined = 0.4 * cos_sim + 0.6 * kw_overlap
            if combined > 0.15:
                scored.append((combined, entry))

        scored.sort(key=lambda x: -x[0])
        return [e for _, e in scored[:top_k]]

    async def enrich_skill_draft(self, error_description: str) -> Dict[str, Any]:
        """为 AutoLearner 提供历史经验上下文。

        检索: 相似的失败经验 (看别人怎么修复的) + 相似的成功经验 (看别人怎么成功的)

        Returns:
            {"similar_failures": [...], "similar_successes": [...], "best_practice": str}
        """
        if not self._enabled:
            return {}

        failures = await self.search(error_description, top_k=3, label="failure")
        successes = await self.search(error_description, top_k=2, label="success")

        best_practice = ""
        if successes:
            best_practice = f"历史类似成功案例: {successes[0].summary[:300]}"

        return {
            "similar_failures": [
                {"summary": e.summary[:300], "run_id": e.run_id, "tags": e.tags}
                for e in failures
            ],
            "similar_successes": [
                {"summary": e.summary[:300], "run_id": e.run_id, "tags": e.tags}
                for e in successes
            ],
            "best_practice": best_practice,
        }

    def stats(self) -> Dict[str, Any]:
        return {
            "total_entries": len(self._entries),
            "max_size": self._max_size,
            "enabled": self._enabled,
            "labels": {
                "success": sum(1 for e in self._entries.values() if e.label == "success"),
                "failure": sum(1 for e in self._entries.values() if e.label == "failure"),
                "exception": sum(1 for e in self._entries.values() if e.label == "exception"),
            },
        }

    # ── Internal ────────────────────────────────────────────────────────

    async def _embed(self, text: str) -> List[float]:
        """文本 → Embedding 向量 (优先真实 Embedding，降级为关键词哈希)"""
        try:
            from core.harness.knowledge.embedder import embed_text
            return await embed_text(text)
        except Exception:
            # Fallback: keyword-based pseudo-embedding
            import re as _re
            h = hashlib.md5(text.encode()).digest()
            return [float(b) / 255.0 for b in h[:16]]

    def _cosine(self, a: List[float], b: List[float]) -> float:
        """Cosine similarity"""
        if not a or not b or len(a) != len(b):
            return 0.0
        dot = sum(x * y for x, y in zip(a, b))
        norm_a = sum(x * x for x in a) ** 0.5
        norm_b = sum(x * x for x in b) ** 0.5
        if norm_a == 0 or norm_b == 0:
            return 0.0
        return dot / (norm_a * norm_b)

    async def _persist(self):
        """持久化到磁盘"""
        try:
            data = {
                "entries": [
                    {
                        "id": e.id, "run_id": e.run_id, "summary": e.summary[:500],
                        "label": e.label, "domain_id": e.domain_id, "tags": e.tags,
                        "created_at": e.created_at,
                    }
                    for e in list(self._entries.values())[-1000:]  # 只保留最近 1000 条
                ]
            }
            with open(self._storage_path, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
        except Exception:
            pass

    def _load_from_disk(self):
        """从磁盘加载"""
        try:
            if os.path.exists(self._storage_path):
                with open(self._storage_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                for e in data.get("entries", [])[-500:]:  # 最多加载 500 条
                    self._entries[e["id"]] = ExperienceEntry(
                        id=e["id"], run_id=e["run_id"], summary=e["summary"],
                        label=e.get("label", ""), domain_id=e.get("domain_id", "default"),
                        tags=e.get("tags", []), created_at=e.get("created_at", time.time()),
                    )
        except Exception:
            pass


# ── Global singleton ─────────────────────────────────────────────────────────

_cache: Optional[ExperienceVectorCache] = None

def get_experience_cache() -> ExperienceVectorCache:
    global _cache
    if _cache is None:
        _cache = ExperienceVectorCache()
    return _cache
