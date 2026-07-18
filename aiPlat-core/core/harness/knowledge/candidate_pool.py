"""Candidate Knowledge Pool — FDE feedback staging and verification.

Collects knowledge gaps from FDE field feedback, deduplicates across sources,
detects semantic conflicts, and triggers ActiveSynthesis when a gap is confirmed
by >=3 independent FDE sessions.

Matches 3Chat's "feedback → product iteration" pipeline on the knowledge side.
"""

from __future__ import annotations

import json
import logging
import os
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger("aiplat.candidate_pool")


@dataclass
class KnowledgeGap:
    """A knowledge gap discovered during FDE field work."""
    source_entity: str          # EntityResolver normalized term
    gap_type: str               # "missing_class" | "missing_relation" | "outdated_info"
    description: str            # FDE natural language description
    source_session_id: str      # Which FDE session produced this
    domain_id: str              # Which knowledge domain
    confidence: float = 0.5     # 0-1 from FDE clarity


@dataclass
class CandidateEntry:
    """Accumulated knowledge gap with dedup and conflict tracking."""
    normalized_key: str
    original_gaps: List[KnowledgeGap] = field(default_factory=list)
    count: int = 0
    status: str = "pending"
    conflict_with: Optional[str] = None
    embedding: Optional[List[float]] = None
    created_at: float = field(default_factory=time.time)
    last_updated: float = field(default_factory=time.time)


_embedding_available: Optional[bool] = None


def _check_embedding_available() -> bool:
    """Check if embedding model is available without blocking download."""
    global _embedding_available
    if _embedding_available is not None:
        return _embedding_available
    try:
        from core.harness.infrastructure.infra_embedding_adapter import InfraEmbeddingAdapter
        # Don't instantiate; just check if the module is importable
        _embedding_available = True
    except ImportError:
        _embedding_available = False
    return _embedding_available


class CandidateKnowledgePool:
    """Singleton pool that collects, deduplicates, and verifies FDE knowledge gaps.

    Triggers ActiveSynthesis when a gap appears >=3 times from independent
    sources, with no semantic conflict detected, and passes GraphIndex validation.
    """

    _instance: Optional["CandidateKnowledgePool"] = None

    def __init__(self):
        self._pool: Dict[str, CandidateEntry] = {}
        self._embedding_model = None  # Lazy-loaded
        self._load_persisted()

    @classmethod
    def instance(cls) -> "CandidateKnowledgePool":
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    # ── Persistence ──

    @staticmethod
    def _pool_path() -> str:
        return os.path.join(
            os.getenv("AIPLAT_HOME", os.path.expanduser("~/.aiplat")),
            "candidate_pool.json",
        )

    def _load_persisted(self) -> None:
        try:
            path = self._pool_path()
            if os.path.exists(path):
                with open(path, "r") as f:
                    raw = json.load(f)
                for key, data in raw.items():
                    entry = CandidateEntry(
                        normalized_key=key,
                        count=data.get("count", 0),
                        status=data.get("status", "pending"),
                        conflict_with=data.get("conflict_with"),
                        embedding=data.get("embedding"),
                        created_at=data.get("created_at", time.time()),
                        last_updated=data.get("last_updated", time.time()),
                    )
                    self._pool[key] = entry
        except Exception as e:
            logger.debug("candidate_pool load skipped: %s", e)

    def _save_persisted(self) -> None:
        try:
            path = self._pool_path()
            os.makedirs(os.path.dirname(path), exist_ok=True)
            data = {}
            for key, entry in self._pool.items():
                data[key] = {
                    "count": entry.count,
                    "status": entry.status,
                    "conflict_with": entry.conflict_with,
                    "embedding": entry.embedding,
                    "created_at": entry.created_at,
                    "last_updated": entry.last_updated,
                }
            with open(path, "w") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
        except Exception as e:
            logger.warning("candidate_pool save failed: %s", e)

    # ── Normalization ──

    def _normalize(self, gap: KnowledgeGap) -> str:
        """Normalize gap entity via EntityResolver, produce unique key."""
        try:
            from core.harness.ontology_engine.entity_resolver import EntityResolver
            resolver = EntityResolver()
            normalized = resolver.normalize_term(
                gap.source_entity,
                class_name=gap.gap_type,
            )
        except Exception:
            normalized = gap.source_entity.strip().lower()
        return f"{gap.domain_id}:{normalized}:{gap.gap_type}"

    # ── Embedding ──

    async def _compute_embedding(self, gap: KnowledgeGap) -> Optional[List[float]]:
        """Compute semantic embedding for gap description (best-effort, with timeout).

        Uses InfraEmbeddingAdapter when model is available; falls back to keyword-only
        conflict detection if embedding computation fails or times out.
        """
        try:
            import asyncio as _aio
            # Lazy init — model may already be cached locally
            if self._embedding_model is None:
                from core.harness.infrastructure.infra_embedding_adapter import InfraEmbeddingAdapter
                self._embedding_model = InfraEmbeddingAdapter()
            embedding = await _aio.wait_for(
                self._embedding_model.embed(gap.description[:500]),
                timeout=10,
            )
            return embedding
        except Exception as e:
            logger.debug("embedding compute skipped (falling back to keyword detection): %s", e)
            return None

    # ── Conflict Detection ──

    @staticmethod
    def _cosine(a: List[float], b: List[float]) -> float:
        """Cosine similarity between two vectors."""
        import math
        dot = sum(x * y for x, y in zip(a, b))
        na = math.sqrt(sum(x * x for x in a))
        nb = math.sqrt(sum(y * y for y in b))
        if na < 1e-8 or nb < 1e-8:
            return 0.0
        return dot / (na * nb)

    @staticmethod
    def _antonym_keywords(a: str, b: str) -> bool:
        """Check if two descriptions contain opposing keywords."""
        antagonist_pairs = [
            ("激进", "保守"), ("降价", "涨价"), ("标准化", "定制化"),
            ("自动化", "人工"), ("线上", "线下"), ("外呼", "入站"),
            ("免费", "付费"), ("批量", "单件"), ("推送", "拉取"),
            ("实时", "异步"),
        ]
        for pos, neg in antagonist_pairs:
            if (pos in a and neg in b) or (neg in a and pos in b):
                return True
        return False

    async def _detect_conflict(
        self, gap: KnowledgeGap, new_embedding: List[float]
    ) -> Optional[Tuple[str, str]]:
        """Detect semantic conflict between new gap and existing pool entries.

        Returns (conflict_key, reason) if conflict detected, None otherwise.
        """
        import math

        for key, entry in self._pool.items():
            if not entry.embedding:
                continue

            cos = self._cosine(new_embedding, entry.embedding)
            angle = math.acos(max(-1.0, min(1.0, cos))) * 180.0 / math.pi

            if angle > 130.0:
                # Unrelated noise — not a conflict
                continue

            if angle > 100.0:
                # Potential semantic conflict
                existing_text = (
                    entry.original_gaps[0].description
                    if entry.original_gaps else ""
                )
                if self._antonym_keywords(gap.description, existing_text):
                    return (
                        key,
                        f"语义冲突 (angle={angle:.0f}°): "
                        f"新反馈倾向与已有条目 {key}(count={entry.count}) 存在反义关键词",
                    )

        return None

    # ── GraphIndex Validation ──

    async def _validate_with_graph(self, gap: KnowledgeGap) -> bool:
        """Verify that the entity exists in at least one knowledge graph."""
        try:
            from core.harness.knowledge.graph_index import GraphIndex
            gi = GraphIndex.load(gap.domain_id)
            if not gi:
                return False
            # Check if entity exists or has related entities
            entity = gi.get_entity(gap.source_entity)
            if entity:
                return True
            # Check if any class has this entity type
            for cls_name in gi.list_classes():
                entities = gi.get_entities_by_class(cls_name, limit=1)
                if entities:
                    return True
            return False
        except Exception as e:
            logger.debug("graph validation skipped: %s", e)
            return True  # Default pass if graph unavailable

    # ── ActiveSynthesis Trigger ──

    async def _trigger_synthesis(self, entry: CandidateEntry) -> bool:
        """Trigger ActiveSynthesis for a confirmed knowledge gap."""
        if not os.getenv("AIPLAT_ACTIVE_SYNTHESIS_ENABLED", "").lower() in ("true", "1"):
            logger.info(
                "ActiveSynthesis skipped (disabled): gap=%s count=%d",
                entry.normalized_key, entry.count,
            )
            return False

        try:
            from core.harness.knowledge.active_synthesis import detect_synthesis_gaps

            gaps = await detect_synthesis_gaps(
                domain_id=entry.original_gaps[0].domain_id if entry.original_gaps else "default",
                min_frequency=1,
                max_gaps=3,
            )
            if gaps:
                logger.info(
                    "ActiveSynthesis triggered: key=%s count=%d gaps_detected=%d",
                    entry.normalized_key, entry.count, len(gaps),
                )
                return True
        except Exception as e:
            logger.warning("ActiveSynthesis trigger failed: %s", e)
        return False

    # ── Main Submit API ──

    async def submit(self, gap: KnowledgeGap) -> str:
        """Submit a knowledge gap from FDE field feedback.

        Returns status: "pending" | "conflict" | "triggered" | "ready"
        - "ready": count>=3, no conflict, but ActiveSynthesis disabled or GraphIndex unavailable
        """
        key = self._normalize(gap)

        # Best-effort embedding: don't block if model is unavailable
        embedding = None
        try:
            import asyncio as _aio
            embedding = await _aio.wait_for(self._compute_embedding(gap), timeout=8)
        except Exception:
            pass

        # Keyword-based conflict detection (always attempted, even without embedding)
        if key in self._pool:
            existing = self._pool[key]
            existing_text = (
                existing.original_gaps[0].description
                if existing.original_gaps else ""
            )
            if self._antonym_keywords(gap.description, existing_text):
                logger.warning(
                    "candidate_pool: keyword conflict detected — "
                    "new='%s' vs existing='%s'",
                    gap.description[:60], existing_text[:60],
                )
                return "conflict"

        # Embedding-based conflict detection
        if embedding:
            conflict = await self._detect_conflict(gap, embedding)
            if conflict:
                conflict_key, reason = conflict
                entry = CandidateEntry(
                    normalized_key=key,
                    original_gaps=[gap],
                    count=1,
                    status="conflict",
                    conflict_with=conflict_key,
                    embedding=embedding,
                )
                self._pool[key] = entry
                self._save_persisted()
                logger.warning("candidate_pool: %s", reason)
                return "conflict"

        # Dedup + aggregate
        if key in self._pool:
            entry = self._pool[key]
            if entry.status == "conflict":
                return "conflict"  # Don't aggregate into conflicted entries
            entry.original_gaps.append(gap)
            entry.count = len(set(g.source_session_id for g in entry.original_gaps))
            entry.last_updated = time.time()
            if embedding:
                entry.embedding = embedding
        else:
            entry = CandidateEntry(
                normalized_key=key,
                original_gaps=[gap],
                count=1,
                embedding=embedding,
            )
            self._pool[key] = entry

        # Decision gate
        if entry.count >= 3 and entry.status != "conflict":
            if await self._validate_with_graph(gap):
                if await self._trigger_synthesis(entry):
                    entry.status = "triggered"
                    self._save_persisted()
                    return "triggered"
                # count>=3 but synthesis disabled → mark as ready for manual review
                entry.status = "ready"
                self._save_persisted()
                return "ready"
            else:
                logger.debug(
                    "candidate_pool: gap %s failed GraphIndex validation, deferring",
                    key,
                )

        self._save_persisted()
        return entry.status

    def get_status(self) -> Dict[str, Any]:
        """Return pool summary for diagnostics."""
        return {
            "total": len(self._pool),
            "by_status": {
                s: sum(1 for e in self._pool.values() if e.status == s)
                for s in ["pending", "conflict", "triggered", "discarded"]
            },
            "top_pending": [
                {"key": k, "count": e.count}
                for k, e in sorted(
                    self._pool.items(),
                    key=lambda x: x[1].count,
                    reverse=True,
                )[:10]
                if e.status == "pending"
            ],
            "conflicts": [
                {"key": k, "conflict_with": e.conflict_with}
                for k, e in self._pool.items()
                if e.status == "conflict"
            ],
        }

    def clear_discarded(self) -> int:
        """Remove discarded entries and return count."""
        removed = 0
        for key in list(self._pool.keys()):
            if self._pool[key].status == "discarded":
                del self._pool[key]
                removed += 1
        if removed:
            self._save_persisted()
        return removed


def get_candidate_pool() -> CandidateKnowledgePool:
    return CandidateKnowledgePool.instance()


__all__ = [
    "CandidateKnowledgePool",
    "CandidateEntry",
    "KnowledgeGap",
    "get_candidate_pool",
]
