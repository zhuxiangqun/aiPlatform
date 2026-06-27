"""
CMM Graduation — 3 准则毕业机制。

从 PatternAccumulator 获取累积的跨会话模式，满足条件后
生成 SkillDraft → SkillSimulator 预检 → ApprovalGate 审批 → SkillRegistry 注册。

3 准则:
  1. 跨会话频次 ≥ 3
  2. 检索验证（已有 Skill 覆盖则跳过）
  3. 人工审批（复用现有 ApprovalGate）
"""

from __future__ import annotations

import logging
from typing import Dict, Any, Optional

_log = logging.getLogger(__name__)


class CMMGraduation:
    """CMM 3 准则毕业 — 连接 PatternAccumulator 和 AutoLearner 流水线。"""

    def __init__(self, frequency_threshold: int = 3):
        self._freq_threshold = frequency_threshold

    async def graduate(self, pattern_hash: str, error_context: Dict = None) -> Optional[str]:
        """执行 3 准则毕业流程。

        Returns:
            Skill ID if graduated, None if not ready.
        """
        from core.harness.memory.pattern_accumulator import get_pattern_accumulator

        acc = get_pattern_accumulator()
        pattern = acc._patterns.get(pattern_hash)
        if not pattern:
            return None

        # 准则 1: 频次检查
        if not pattern.meets_frequency(self._freq_threshold):
            _log.debug(f"CMM: pattern {pattern_hash[:8]} freq={pattern.frequency} < {self._freq_threshold}")
            return None

        # 准则 2: 检索去重
        try:
            from core.harness.integration import get_skill_registry
            reg = get_skill_registry()
            similar = reg.search_by_pattern(list(pattern.tool_sequence)) if hasattr(reg, 'search_by_pattern') else None
            if similar:
                _log.info(f"CMM: pattern {pattern_hash[:8]} already covered by {similar}, skipping")
                return None
        except Exception as e:
            logging.debug(str(e), exc_info=True)

        # 准则 3: 生成 Draft → SkillSimulator → ApprovalGate
        draft_id = await self._generate_and_submit(pattern, error_context or {})
        return draft_id

    async def _generate_and_submit(self, pattern, error_context: Dict) -> Optional[str]:
        """通过 AutoLearner 生成 Draft，走现有流水线。"""
        try:
            from core.harness.learning import get_auto_learner
            learner = get_auto_learner()
            draft = await learner.create_draft(
                failure_context={
                    "pattern": list(pattern.tool_sequence),
                    "frequency": pattern.frequency,
                    "sessions": list(pattern.sessions)[:5],
                },
                source="cmm_graduation",
            )
            _log.info(f"CMM: graduated pattern {pattern.hash[:8]} → draft {draft.get('id', '?')}")
            return draft.get("id")
        except Exception as e:
            _log.warning(f"CMM: graduation failed for {pattern.hash[:8]}: {e}")
            return None


_cmm: Optional[CMMGraduation] = None


def get_cmm_graduation() -> CMMGraduation:
    global _cmm
    if _cmm is None:
        _cmm = CMMGraduation()
    return _cmm
