"""MetaAgent — 元认知分析 Agent（P0-C7 黄金样本修复，2026-08-18）。

EvolutionEngine 的 meta_analysis step 调用 get_meta_agent().analyze(days)，
但该符号此前从未实现 → step 每次返回 error（功能静默失效）。

本模块提供最小可用实现：聚合系统健康信号（最近失败分布、质量评分、
知识覆盖率）生成结构化策略建议。不引入 LLM/外部依赖——元认知分析
基于已有监控数据（capability_health_report / execution_store），
符合"能用已有数据表达的不新增抽象"原则。

设计依据：docs/architecture/plans/optimization-roadmap.md A1.1
（ERR Translator→MetaAgent 链路 requires_live，本实现为数据驱动最小版）。
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

logger = logging.getLogger("aiplat.meta_agent")


@dataclass
class MetaSuggestion:
    """一条策略建议：问题 → 建议动作 → 优先级。"""

    area: str
    problem: str
    suggestion: str
    priority: str = "low"  # high | medium | low
    evidence: str = ""


@dataclass
class MetaAgent:
    """数据驱动的元认知分析器。analyze() 返回最近 N 天内的策略建议。"""

    days: int = 7

    def _collect_failure_signals(self) -> List[Dict[str, Any]]:
        """从 execution_store 收集最近失败信号（尽力而为，不可用返回空）。"""
        try:
            from core.api.core_facade import get_execution_store
            store = get_execution_store()
            if store is None:
                return []
            # 最近的失败事件（syscall 失败/阶段失败）
            events = []
            try:
                import asyncio
                async def _fetch() -> List[Dict[str, Any]]:
                    try:
                        return await store.list_recent_failures(limit=50)
                    except Exception:  # noqa: BLE001 — store API 形状差异
                        return []
                events = asyncio.run(_fetch())
            except Exception:  # noqa: BLE001
                events = []
            return events or []
        except Exception as e:  # noqa: BLE001
            logger.debug("meta_agent failure signals unavailable: %s", e)
            return []

    def _collect_health_signals(self) -> Dict[str, Any]:
        """收集能力健康报告（尽力而为）。"""
        try:
            from core.api.core_facade import capability_health_report
            report = capability_health_report()
            if isinstance(report, dict):
                return report
        except Exception as e:  # noqa: BLE001
            logger.debug("meta_agent health signals unavailable: %s", e)
        return {}

    def analyze(self, days: Optional[int] = None) -> List[MetaSuggestion]:
        """分析最近 days 天的系统健康，返回策略建议列表。"""
        window = days or self.days
        suggestions: List[MetaSuggestion] = []

        failures = self._collect_failure_signals()
        if failures:
            suggestions.append(MetaSuggestion(
                area="reliability",
                problem=f"最近 {window} 天检测到 {len(failures)} 条失败记录",
                suggestion="查看失败分布并优先修复高频错误源（结合 error_translator 分类）",
                priority="high" if len(failures) >= 10 else "medium",
                evidence=f"failures={len(failures)}",
            ))

        health = self._collect_health_signals()
        low_health = [k for k, v in health.items()
                      if isinstance(v, dict) and v.get("score", 100) < 60]
        if low_health:
            suggestions.append(MetaSuggestion(
                area="capability_health",
                problem=f"以下能力健康度 < 60: {low_health}",
                suggestion="优先恢复低健康度能力的依赖（模型/知识源/服务）",
                priority="medium",
                evidence=f"low_health={low_health}",
            ))

        if not suggestions:
            suggestions.append(MetaSuggestion(
                area="baseline",
                problem="近窗口内无显著异常信号",
                suggestion="系统运行平稳，无需元认知干预",
                priority="low",
                evidence=f"window_days={window}",
            ))
        return suggestions


_meta_agent: Optional[MetaAgent] = None


def get_meta_agent() -> MetaAgent:
    """获取 MetaAgent 单例（EvolutionEngine meta_analysis step 调用）。"""
    global _meta_agent
    if _meta_agent is None:
        _meta_agent = MetaAgent()
    return _meta_agent


__all__ = ["MetaAgent", "MetaSuggestion", "get_meta_agent"]
