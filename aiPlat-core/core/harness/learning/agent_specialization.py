"""
AgentSpecialization — Agent 专长计算引擎 (EvoMap 自组织对齐)

从 agent 的行动记录中自动计算专长分布，而非预设角色标签。
专长从执行历史中"长出来":

  1. 从 action_audit + syscall_events 提取历史数据
  2. 计算各领域的成功率、偏好度
  3. 长期不用自动衰减 (decay_inactive_domains)
  4. 互补性评分: 向量余弦相似度的倒数

调用者: PartnerSelector / AgentNetworkPanel / MemoryManager
"""

from __future__ import annotations

import json as _json
import logging
import math
import time as _time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)


# ── Data Models ────────────────────────────────────────────────────────────

@dataclass
class DomainScore:
    """单个领域的专长评分."""
    domain: str
    task_type: str = ""
    success_count: int = 0
    total_count: int = 0
    accuracy: float = 0.0        # 成功率 0-1
    avg_latency_ms: float = 0.0  # 平均延迟
    last_used_at: float = 0.0    # 最后使用时间
    preference: float = 0.0      # 偏好度 (频次 + 成功率加权)

    @property
    def is_active(self, decay_threshold_days: float = 30.0) -> bool:
        """是否仍活跃 (未超过衰减阈值)."""
        if self.last_used_at <= 0:
            return True
        days_inactive = (_time.time() - self.last_used_at) / 86400
        return days_inactive <= decay_threshold_days


@dataclass
class SpecializationVector:
    """Agent 的专长向量."""
    agent_id: str
    domains: Dict[str, DomainScore] = field(default_factory=dict)  # domain → score
    computed_at: float = 0.0
    total_actions: int = 0
    primary_domain: str = ""     # 最强领域
    secondary_domains: List[str] = field(default_factory=list)  # 次强领域 (top 3)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "agent_id": self.agent_id,
            "domains": {k: {
                "domain": v.domain,
                "task_type": v.task_type,
                "success_count": v.success_count,
                "total_count": v.total_count,
                "accuracy": round(v.accuracy, 3),
                "avg_latency_ms": round(v.avg_latency_ms, 1),
                "preference": round(v.preference, 3),
                "last_used_at": v.last_used_at,
            } for k, v in self.domains.items()},
            "total_actions": self.total_actions,
            "primary_domain": self.primary_domain,
            "secondary_domains": self.secondary_domains,
        }

    def to_vector(self, domain_list: Optional[List[str]] = None) -> List[float]:
        """转换为向量 (用于余弦相似度计算)."""
        keys = domain_list or sorted(self.domains.keys())
        return [self.domains.get(k, DomainScore(domain=k)).accuracy for k in keys]


# ── AgentSpecialization ────────────────────────────────────────────────────

class AgentSpecialization:
    """Agent 专长计算引擎.

    使用方式:
        spec = AgentSpecialization()
        vector = await spec.compute("agent_1", lookback_hours=24)
    """

    def __init__(self, *, decay_days: float = 30.0):
        self._decay_days = decay_days
        self._cache: Dict[str, SpecializationVector] = {}
        self._cache_ttl = 300  # 5分钟缓存

    async def compute(
        self,
        agent_id: str,
        *,
        lookback_hours: float = 168.0,  # 默认7天
        domain_list: Optional[List[str]] = None,
    ) -> SpecializationVector:
        """从执行历史计算 Agent 的专长分布.

        Args:
            agent_id: Agent ID
            lookback_hours: 回顾时间窗口 (小时)
            domain_list: 可选的领域列表 (用于向量对齐)

        Returns:
            SpecializationVector
        """
        # Check cache
        cache_key = f"{agent_id}:{lookback_hours}"
        if cache_key in self._cache:
            cached = self._cache[cache_key]
            if _time.time() - cached.computed_at < self._cache_ttl:
                return cached

        # Fetch from execution store
        actions = await self._fetch_agent_actions(agent_id, lookback_hours)

        # Compute domain scores
        domain_scores: Dict[str, DomainScore] = {}
        total_actions = len(actions)

        for action in actions:
            domain = action.get("domain", "general")
            task_type = action.get("task_type", action.get("decision_type", ""))
            success = action.get("outcome_status") == "success"

            key = f"{domain}:{task_type}" if task_type else domain

            if key not in domain_scores:
                domain_scores[key] = DomainScore(domain=domain, task_type=task_type)

            score = domain_scores[key]
            score.total_count += 1
            if success:
                score.success_count += 1
            score.last_used_at = max(score.last_used_at, action.get("created_at", _time.time()))
            score.avg_latency_ms = (
                (score.avg_latency_ms * (score.total_count - 1) + action.get("duration_ms", 0))
                / score.total_count
            )

        # Calculate accuracy and preference
        for key, score in domain_scores.items():
            score.accuracy = score.success_count / max(score.total_count, 1)
            score.preference = score.accuracy * math.log(max(score.total_count, 1) + 1)

        # Apply decay
        self._decay_inactive(domain_scores)

        # Determine primary/secondary
        sorted_domains = sorted(
            domain_scores.items(),
            key=lambda x: x[1].preference,
            reverse=True,
        )

        vector = SpecializationVector(
            agent_id=agent_id,
            domains=domain_scores,
            computed_at=_time.time(),
            total_actions=total_actions,
            primary_domain=sorted_domains[0][0] if sorted_domains else "",
            secondary_domains=[d[0] for d in sorted_domains[1:4]],
        )

        # Update cache
        self._cache[cache_key] = vector
        return vector

    async def _fetch_agent_actions(
        self,
        agent_id: str,
        lookback_hours: float,
    ) -> List[Dict[str, Any]]:
        """从 execution_store 获取 Agent 的历史行动记录."""
        try:
            import sqlite3

            db_path = ""
            try:
                from core.harness.integration import _get_platform_db_path
                db_path = _get_platform_db_path()
            except Exception:
                import os
                db_path = os.path.expanduser("~/.aiplat/data/aiplat_platform.sqlite3")

            if not db_path or not __import__("os").path.exists(db_path):
                return []

            conn = sqlite3.connect(db_path)
            conn.row_factory = sqlite3.Row

            cutoff = _time.time() - lookback_hours * 3600

            # Query from action_audit (Action Registry) and syscall_events
            rows = conn.execute("""
                SELECT 'action' as source, action_id as task_type, result_status as outcome_status,
                       domain_id as domain, created_at, entity_id
                FROM action_audit
                WHERE actor = ? AND created_at > ?
                UNION ALL
                SELECT 'syscall' as source, kind as task_type, status as outcome_status,
                       name as domain, created_at, trace_id as entity_id
                FROM syscall_events
                WHERE user_id = ? OR agent_id = ? AND created_at > ?
                ORDER BY created_at DESC
                LIMIT 500
            """, (agent_id, cutoff, agent_id, agent_id, cutoff)).fetchall()

            conn.close()
            return [dict(r) for r in rows]

        except Exception as e:
            logger.debug("Agent action fetch skipped: %s", e)
            return []

    def _decay_inactive(self, domain_scores: Dict[str, DomainScore]) -> None:
        """对长期不活跃的领域进行衰减."""
        for key, score in domain_scores.items():
            if score.last_used_at > 0:
                days_inactive = (_time.time() - score.last_used_at) / 86400
                if days_inactive > self._decay_days:
                    decay_factor = 0.5 ** (days_inactive / self._decay_days)
                    score.preference *= decay_factor
                    score.accuracy *= decay_factor

    def complementarity_score(
        self,
        vec_a: SpecializationVector,
        vec_b: SpecializationVector,
        domain_list: Optional[List[str]] = None,
    ) -> float:
        """计算两个 Agent 的专业互补性.

        高相似度 = 竞争/同行 (complementarity → 0)
        低相似度但相关 = 互补 (complementarity → 1)

        使用: 1 - cosine_similarity(vec_a, vec_b)
        """
        a = vec_a.to_vector(domain_list)
        b = vec_b.to_vector(domain_list)

        if not a or not b or len(a) != len(b):
            return 0.0

        # Cosine similarity
        dot = sum(x * y for x, y in zip(a, b))
        norm_a = math.sqrt(sum(x * x for x in a))
        norm_b = math.sqrt(sum(x * x for x in b))

        if norm_a == 0 or norm_b == 0:
            return 0.0

        similarity = dot / (norm_a * norm_b)

        # Complementarity = 1 - similarity (if they have non-zero overlap)
        # But only if both have some skill; pure zeros shouldn't be complementary
        has_skill = any(x > 0 for x in a) and any(x > 0 for x in b)
        if not has_skill:
            return 0.0

        return max(0.0, 1.0 - similarity)
