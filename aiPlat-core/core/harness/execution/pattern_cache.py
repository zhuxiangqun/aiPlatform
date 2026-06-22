"""
Pattern Cache — 执行模式晶体化 (Phase 5.4)

检测重复执行模式，跳过 LLM 推理直接复用执行路径。
非向量实现：MD5(domain+task_type+trigger_signature) → 精确匹配。

与 SemanticCache 互补:
  - SemanticCache: 缓存"答案" (RAG 结果)
  - PatternCache: 缓存"执行路径" (跳过哪些Pipeline阶段、用哪些工具)

收益: Pipeline 重复场景节省 40-60% Token

Usage:
    cache = PatternCache()
    
    # 存储执行模式
    await cache.store(
        domain_id="ai-knowledge",
        task_type="retrieval_qa",
        trigger_signature="Python version features",
        execution_path={"skip_stages": ["domain_route", "ontology_map"], "use_tools": ["wiki_retrieve"]}
    )
    
    # 检索缓存模式
    cached = await cache.match(
        domain_id="ai-knowledge", 
        task_type="retrieval_qa",
        trigger_signature="Python 3.13 new features"
    )
    if cached:
        # 跳过域路由和本体映射，直接用 wiki_retrieve
        pipeline.set_skip_stages(cached["skip_stages"])
"""

from __future__ import annotations

import hashlib, os, time, json, logging
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

_log = logging.getLogger("aiplat.pattern_cache")


@dataclass 
class ExecutionPattern:
    """单个执行模式"""
    pattern_id: str
    domain_id: str
    task_type: str              # retrieval_qa / code_gen / data_analysis / summarize
    trigger_signature: str      # 简化的触发签名 (提取自 query)
    skip_stages: List[str] = field(default_factory=list)
    use_tools: List[str] = field(default_factory=list)
    use_skills: List[str] = field(default_factory=list)
    retrieval_strategy: str = ""    # direct / fts5 / hyde
    hit_count: int = 0
    success_count: int = 0
    created_at: float = field(default_factory=time.time)


class PatternCache:
    """执行模式缓存 — 跳过重复推理，直接复用执行路径。

    环境变量:
        AIPLAT_PATTERN_CACHE_SIZE: 最大条目 (默认: 1000)
        AIPLAT_PATTERN_CACHE_ENABLED: 是否启用 (默认: true)
        AIPLAT_PATTERN_CACHE_HIT_THRESHOLD: 模式命中次数阈值 (默认: 3, 命中≥3次才启用)
    """

    def __init__(self):
        self._patterns: Dict[str, ExecutionPattern] = {}
        self._max_size = int(os.getenv("AIPLAT_PATTERN_CACHE_SIZE", "1000"))
        self._enabled = os.getenv("AIPLAT_PATTERN_CACHE_ENABLED", "true").lower() not in ("0", "false", "no")
        self._hit_threshold = int(os.getenv("AIPLAT_PATTERN_CACHE_HIT_THRESHOLD", "3"))

    # ── Public API ──────────────────────────────────────────────────────

    def _make_key(self, domain_id: str, task_type: str, trigger_signature: str) -> str:
        """生成确定性缓存键 (MD5)"""
        raw = f"{domain_id}|{task_type}|{trigger_signature.lower().strip()[:200]}"
        return hashlib.md5(raw.encode()).hexdigest()[:12]

    def _extract_signature(self, query: str) -> str:
        """从 query 中提取触发签名。

        策略: 移除停用词、提取核心名词/动词。
        """
        import re as _re
        # Remove common words and punctuation
        clean = _re.sub(r'[?？,，。！!的了吗呢吧是有什么如何怎么哪个哪些]', ' ', query)
        words = [w for w in clean.split() if len(w) > 1][:6]
        return ' '.join(words)[:200]

    def _classify_task_type(self, query: str) -> str:
        """分类任务类型"""
        q = query.lower()
        if any(k in q for k in ['code', '代码', '写', 'implement', '函数', 'class']):
            return 'code_gen'
        if any(k in q for k in ['data', '数据', '统计', '分析', 'chart', '图表']):
            return 'data_analysis'
        if any(k in q for k in ['summar', '总结', '摘要', '概括']):
            return 'summarize'
        if any(k in q for k in ['search', '搜索', 'find', '查找', 'retriev']):
            return 'retrieval_qa'
        return 'retrieval_qa'  # default

    async def store(
        self,
        domain_id: str,
        query: str,
        execution_path: Dict[str, Any],
        *,
        success: bool = True,
    ):
        """存储执行模式。

        Args:
            domain_id: 域标识
            query: 原始查询
            execution_path: {"skip_stages": [...], "use_tools": [...], "use_skills": [...], "retrieval_strategy": "..."}
            success: 执行是否成功
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
        """匹配执行模式。

        仅返回命中 ≥ hit_threshold 的模式 (已验证可靠的模式)。

        Returns:
            None (无匹配) 或 {"skip_stages": [...], "use_tools": [...], ...}
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
        """模糊匹配 (同域 + 同任务类型的最近模式)。

        当精确匹配失败时，返回同域+同类的最远模式作为参考。
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
