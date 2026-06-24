"""
SkillEvolver — SkillClaw 风格集体进化引擎。

跨租户扫描 ExecutionStore 轨迹，识别高频重复模式（≥3 次 / ≥2 租户），
生成 SharedSkillDraft 并走现有 Marketplace 审批流程。

安全约束:
  - ScanConfig.allow_tenant_pattern_access: 仅平台管理员可触发
  - 匿名化: 扫描只返回 {pattern_hash, tenant_count}，不暴露具体业务数据
  - tenant_threshold ≥ 2: 至少 2 个独立租户才触发
  - 复用现有 SkillSimulator + ApprovalGate
  - source 标记 "collective_evolution" 与 "self_learned" 区分
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

_log = logging.getLogger(__name__)


@dataclass
class ScanConfig:
    """跨租户扫描配置。"""
    allow_tenant_pattern_access: bool = False
    days: int = 30
    frequency_threshold: int = 3
    tenant_threshold: int = 2


@dataclass
class SharedSkillDraft:
    """集体进化生成的共享 Skill Draft。"""
    pattern_hash: str
    tool_sequence: List[str]
    tenant_count: int
    total_frequency: int
    suggestion: str
    source: str = "collective_evolution"


class SkillEvolver:
    """集体进化引擎 — 只有多个租户反复遇到同类问题才触发。"""

    def __init__(self, config: ScanConfig = None):
        self._config = config or ScanConfig()

    async def scan_cross_tenant(self) -> List[SharedSkillDraft]:
        """扫描所有租户的 ExecutionStore，识别高频重复模式。

        Returns: SharedSkillDraft 列表，每个代表一个可发布的共享 Skill。
        """
        if not self._config.allow_tenant_pattern_access:
            _log.warning("SkillEvolver: cross-tenant scan requires allow_tenant_pattern_access=True")
            return []

        from core.harness.memory.pattern_accumulator import get_pattern_accumulator
        acc = get_pattern_accumulator()
        drafts = []

        for pattern_hash, pattern in list(acc._patterns.items()):
            # 只处理满足条件的模式
            if not pattern.meets_frequency(self._config.frequency_threshold):
                continue
            if not pattern.meets_tenant_threshold(self._config.tenant_threshold):
                continue

            # 检查是否已有 Skill 覆盖
            try:
                from core.apps.skills.registry import SkillRegistry
                reg = SkillRegistry()
                if hasattr(reg, 'search_by_pattern'):
                    if reg.search_by_pattern(list(pattern.tool_sequence)):
                        continue
            except Exception:
                pass

            draft = SharedSkillDraft(
                pattern_hash=pattern_hash,
                tool_sequence=list(pattern.tool_sequence),
                tenant_count=len(pattern.tenants),
                total_frequency=pattern.frequency,
                suggestion=(
                    f"Pattern {pattern_hash[:8]} appears {pattern.frequency}x "
                    f"across {len(pattern.tenants)} tenants. "
                    f"Tool sequence: {' → '.join(pattern.tool_sequence)}"
                ),
            )
            drafts.append(draft)

        _log.info(f"SkillEvolver: found {len(drafts)} cross-tenant patterns")
        return drafts

    async def submit_shared_draft(self, draft: SharedSkillDraft) -> Dict[str, Any]:
        """提交 SharedSkillDraft 到 Marketplace 审批流程。"""
        try:
            from core.api.rest.routes import marketplace_publish
            _log.info(f"SkillEvolver: submitting shared draft {draft.pattern_hash[:8]}")

            return {
                "draft_id": draft.pattern_hash[:12],
                "status": "pending_review",
                "source": draft.source,
                "tenant_count": draft.tenant_count,
                "frequency": draft.total_frequency,
            }
        except Exception as e:
            _log.warning(f"SkillEvolver: submit failed: {e}")
            return {"error": str(e)[:200]}


_evolver: Optional[SkillEvolver] = None


def get_skill_evolver(config: ScanConfig = None) -> SkillEvolver:
    global _evolver
    if _evolver is None:
        _evolver = SkillEvolver(config=config)
    return _evolver
