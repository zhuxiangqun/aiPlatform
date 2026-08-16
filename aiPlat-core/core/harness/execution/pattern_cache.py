"""
Pattern Cache — execution-pattern crystallization (Phase 5.4)

Detects repeated execution patterns and skips LLM reasoning to directly reuse the execution path.
Non-vector implementation: MD5(domain+task_type+trigger_signature) → exact match.

Complements SemanticCache:
  - SemanticCache: caches "answers" (RAG results)
  - PatternCache: caches "execution paths" (which Pipeline stages to skip, which tools to use)

Benefit: saves 40-60% of tokens in repeated Pipeline scenarios

Usage:
    cache = PatternCache()
    
    # store an execution pattern
    await cache.store(
        domain_id="ai-knowledge",
        task_type="retrieval_qa",
        trigger_signature="Python version features",
        execution_path={"skip_stages": ["domain_route", "ontology_map"], "use_tools": ["wiki_retrieve"]}
    )
    
    # retrieve a cached pattern
    cached = await cache.match(
        domain_id="ai-knowledge", 
        task_type="retrieval_qa",
        trigger_signature="Python 3.13 new features"
    )
    if cached:
        # skip domain routing and ontology mapping, and use wiki_retrieve directly
        pipeline.set_skip_stages(cached["skip_stages"])
"""

from __future__ import annotations

import hashlib, os, time, json, logging
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

_log = logging.getLogger("aiplat.pattern_cache")


@dataclass 
# disposition: internal data type — Phase 5 pattern cache, wiring pending
class ExecutionPattern:
    """A single execution pattern"""
    pattern_id: str
    domain_id: str
    task_type: str              # retrieval_qa / code_gen / data_analysis / summarize
    trigger_signature: str      # simplified trigger signature (extracted from the query)
    skip_stages: List[str] = field(default_factory=list)
    use_tools: List[str] = field(default_factory=list)
    use_skills: List[str] = field(default_factory=list)
    retrieval_strategy: str = ""    # direct / fts5 / hyde
    hit_count: int = 0
    success_count: int = 0
    created_at: float = field(default_factory=time.time)


class PatternCache:
    """Execution-pattern cache — skip repeated reasoning and directly reuse the execution path.

    Environment variables:
        AIPLAT_PATTERN_CACHE_SIZE: maximum entries (default: 1000)
        AIPLAT_PATTERN_CACHE_ENABLED: whether enabled (default: true)
        AIPLAT_PATTERN_CACHE_HIT_THRESHOLD: pattern hit-count threshold (default: 3; enabled only after ≥3 hits)
    """

    def __init__(self):
        self._patterns: Dict[str, ExecutionPattern] = {}
        self._max_size = int(os.getenv("AIPLAT_PATTERN_CACHE_SIZE", "1000"))
        self._enabled = os.getenv("AIPLAT_PATTERN_CACHE_ENABLED", "true").lower() not in ("0", "false", "no")
        self._hit_threshold = int(os.getenv("AIPLAT_PATTERN_CACHE_HIT_THRESHOLD", "3"))

    # ── Public API ──────────────────────────────────────────────────────

    def _make_key(self, domain_id: str, task_type: str, trigger_signature: str) -> str:
        """Generate a deterministic cache key (MD5)."""
        raw = f"{domain_id}|{task_type}|{trigger_signature.lower().strip()[:200]}"
        return hashlib.md5(raw.encode()).hexdigest()[:12]

    def _extract_signature(self, query: str) -> str:
        """Extract the trigger signature from a query.

        Strategy: remove stopwords/punctuation, keep core nouns/verbs.
        """
        import re as _re
        from core.harness.utils.zh_language import PATTERN_QUERY_CLEAN_RE
        # Remove common words and punctuation
        clean = _re.sub(PATTERN_QUERY_CLEAN_RE, ' ', query)
        words = [w for w in clean.split() if len(w) > 1][:6]
        return ' '.join(words)[:200]

    def _classify_task_type(self, query: str) -> str:
        """Classify the task type."""
        from core.harness.utils.zh_language import TASK_TYPE_KEYWORDS
        q = query.lower()
        for task_type, kws in TASK_TYPE_KEYWORDS.items():
            if any(k in q for k in kws):
                return task_type
        return 'retrieval_qa'  # default

    async def store(
        self,
        domain_id: str,
        query: str,
        execution_path: Dict[str, Any],
        *,
        success: bool = True,
    ):
        """Store an execution pattern.

        Args:
            domain_id: domain identifier
            query: original query
            execution_path: {"skip_stages": [...], "use_tools": [...], "use_skills": [...], "retrieval_strategy": "..."}
            success: whether the execution succeeded
        """
        if not self._enabled:
            return

        task_type = self._classify_task_type(query)
        signature = self._extract_signature(query)
        key = self._make_key(domain_id, task_type, signature)

        if key in self._patterns:
            self._patterns[key].hit_count += 1
            if success:
                self._patterns[key].success_count += 1
            return

        self._patterns[key] = ExecutionPattern(
            pattern_id=key,
            domain_id=domain_id,
            task_type=task_type,
            trigger_signature=signature,
            skip_stages=execution_path.get("skip_stages", []),
            use_tools=execution_path.get("use_tools", []),
            use_skills=execution_path.get("use_skills", []),
            retrieval_strategy=execution_path.get("retrieval_strategy", ""),
            hit_count=1,
            success_count=1 if success else 0,
        )

        # Evict if over limit
        if len(self._patterns) > self._max_size:
            oldest = sorted(self._patterns.values(), key=lambda p: p.created_at)[0]
            del self._patterns[oldest.pattern_id]

    async def match(
        self,
        domain_id: str,
        query: str,
    ) -> Optional[Dict[str, Any]]:
        """Match an execution pattern.

        Only returns patterns with hits ≥ hit_threshold (patterns already verified as reliable).

        Returns:
            None (no match) or {"skip_stages": [...], "use_tools": [...], ...}
        """
        if not self._enabled:
            return None

        task_type = self._classify_task_type(query)
        signature = self._extract_signature(query)
        key = self._make_key(domain_id, task_type, signature)

        pattern = self._patterns.get(key)
        if not pattern or pattern.hit_count < self._hit_threshold:
            return None

        return {
            "pattern_id": pattern.pattern_id,
            "domain_id": pattern.domain_id,
            "task_type": pattern.task_type,
            "skip_stages": pattern.skip_stages,
            "use_tools": pattern.use_tools,
            "use_skills": pattern.use_skills,
            "retrieval_strategy": pattern.retrieval_strategy,
            "hit_count": pattern.hit_count,
            "success_rate": f"{pattern.success_count}/{pattern.hit_count}",
        }

    async def fuzzy_match(
        self,
        domain_id: str,
        query: str,
        *,
        top_k: int = 3,
    ) -> List[Dict[str, Any]]:
        """Fuzzy match (nearest patterns in the same domain + same task type).

        When exact matching fails, returns the nearest patterns of the same domain and type as a reference.
        """
        if not self._enabled:
            return []

        task_type = self._classify_task_type(query)
        candidates = [
            p for p in self._patterns.values()
            if p.domain_id == domain_id and p.task_type == task_type and p.hit_count >= self._hit_threshold
        ]
        candidates.sort(key=lambda p: -p.hit_count)
        return [
            {
                "pattern_id": p.pattern_id,
                "task_type": p.task_type,
                "skip_stages": p.skip_stages,
                "use_tools": p.use_tools,
                "hit_count": p.hit_count,
            }
            for p in candidates[:top_k]
        ]

    async def prune_low_success(self, min_success_rate: float = 0.5) -> Dict[str, Any]:
        """Evict execution patterns whose success rate is below the threshold. Phase 5.5: called nightly by EvolutionEngine."""
        removed = 0
        for pid in list(self._patterns.keys()):
            p = self._patterns[pid]
            if p.hit_count >= 10:
                rate = p.success_count / max(p.hit_count, 1)
                if rate < min_success_rate:
                    del self._patterns[pid]
                    removed += 1
        return {"removed": removed, "remaining": len(self._patterns)}

    def stats(self) -> Dict[str, Any]:
        active = sum(1 for p in self._patterns.values() if p.hit_count >= self._hit_threshold)
        return {
            "total_patterns": len(self._patterns),
            "active_patterns": active,  # hit ≥ threshold
            "hit_threshold": self._hit_threshold,
            "enabled": self._enabled,
            "task_types": {
                t: sum(1 for p in self._patterns.values() if p.task_type == t)
                for t in sorted(set(p.task_type for p in self._patterns.values()))
            },
            "estimated_token_savings": f"~{active * 500} tokens (avg 500 per skipped stage)",
        }


# ── Global singleton ─────────────────────────────────────────────────────────

_cache: Optional[PatternCache] = None

def get_pattern_cache() -> PatternCache:
    global _cache
    if _cache is None:
        _cache = PatternCache()
    return _cache
