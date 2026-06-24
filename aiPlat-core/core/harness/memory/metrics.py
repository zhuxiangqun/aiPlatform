"""
Memory subsystem observability metrics.

Prometheus counters and histograms for the 7 hardening plans.
Imported lazily to avoid hard dependency on prometheus_client at module load.
"""

from __future__ import annotations
from typing import Optional

_metrics = None


def _ensure() -> bool:
    """Lazy-init prometheus_client metrics. Returns True if available."""
    global _metrics
    if _metrics is not None:
        return _metrics is not False
    try:
        from prometheus_client import Counter, Histogram

        _metrics = {
            # ── 方案一：工具输出预算帽 ──
            "tool_truncated": Counter(
                "memory_tool_truncated_total",
                "工具输出触发截断/摘要的次数",
                ["tool"],
            ),
            "tool_summary_latency": Histogram(
                "memory_tool_summary_latency_seconds",
                "后台工具摘要耗时(秒)",
                ["tool"],
                buckets=[0.1, 0.5, 1.0, 2.0, 3.0, 5.0, 10.0],
            ),
            # ── 方案二：语义记忆过期 ──
            "semantic_expired": Counter(
                "memory_semantic_expired_total",
                "语义记忆软删除计数",
                [],
            ),
            "semantic_renewed": Counter(
                "memory_semantic_renewed_total",
                "语义记忆命中续期计数",
                [],
            ),
            # ── 方案三：Episodic 预评分 ──
            "critical_promoted": Counter(
                "memory_critical_promoted_total",
                "提升为 critical_episode 的计数",
                [],
            ),
            # ── 方案四：RRF + Early Exit ──
            "rrf_latency": Histogram(
                "retrieval_rrf_latency_seconds",
                "RRF融合耗时(秒)",
                buckets=[0.01, 0.05, 0.1, 0.3, 0.5, 1.0, 2.0],
            ),
            "early_exit": Counter(
                "retrieval_early_exit_total",
                "Graph Early Exit 触发计数",
                ["source"],
            ),
            # ── 方案五：Skill 衰减 ──
            "skill_downgraded": Counter(
                "skill_decay_downgraded_total",
                "Skill 被降权计数",
                ["skill"],
            ),
            "skill_alert": Counter(
                "skill_decay_alert_total",
                "Skill 衰减告警计数",
                ["skill"],
            ),
            # ── 方案六：缓存版本 ──
            "cache_version": Counter(
                "cache_version_change_total",
                "缓存版本号递增计数",
                ["collection"],
            ),
        }
        return True
    except ImportError:
        _metrics = False
        return False


def inc_tool_truncated(tool: str) -> None:
    if _ensure():
        _metrics["tool_truncated"].labels(tool=tool).inc()


def observe_tool_summary(tool: str, seconds: float) -> None:
    if _ensure():
        _metrics["tool_summary_latency"].labels(tool=tool).observe(seconds)


def inc_semantic_expired() -> None:
    if _ensure():
        _metrics["semantic_expired"].inc()


def inc_semantic_renewed() -> None:
    if _ensure():
        _metrics["semantic_renewed"].inc()


def inc_critical_promoted() -> None:
    if _ensure():
        _metrics["critical_promoted"].inc()


def observe_rrf_latency(seconds: float) -> None:
    if _ensure():
        _metrics["rrf_latency"].observe(seconds)


def inc_early_exit(source: str = "graph") -> None:
    if _ensure():
        _metrics["early_exit"].labels(source=source).inc()


def inc_skill_downgraded(skill: str) -> None:
    if _ensure():
        _metrics["skill_downgraded"].labels(skill=skill).inc()


def inc_skill_alert(skill: str) -> None:
    if _ensure():
        _metrics["skill_alert"].labels(skill=skill).inc()


def inc_cache_version(collection: str) -> None:
    if _ensure():
        _metrics["cache_version"].labels(collection=collection).inc()


__all__ = [
    "inc_tool_truncated", "observe_tool_summary",
    "inc_semantic_expired", "inc_semantic_renewed",
    "inc_critical_promoted", "observe_rrf_latency", "inc_early_exit",
    "inc_skill_downgraded", "inc_skill_alert", "inc_cache_version",
]
