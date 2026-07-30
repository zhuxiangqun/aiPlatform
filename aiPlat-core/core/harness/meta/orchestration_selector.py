"""OrchestrationSelector — 根据任务复杂度自动选择编排模式。

Design:
  - 读 ControlProfile.orchestration_mode
  - mode="auto" → 根据 expected_tool_steps + has_branching 自动选择
  - mode 显式指定 → 直接使用
  - 表驱动选择，无 LLM 开销
"""

from __future__ import annotations

from typing import Optional


# (max_tool_steps, has_branching) → orchestration_mode
# 表按 max_steps 升序排列，第一次命中即返回
_SELECTION_TABLE = [
    ((1, False), "single"),
    ((2, False), "chain"),
    ((2, True),  "tree"),
    ((3, False), "chain"),
    ((3, True),  "tree"),
    ((5, False), "reflexion"),
    ((5, True),  "reflexion"),
]


class OrchestrationSelector:
    """根据任务特征自动选择编排模式。

    Usage:
        selector = OrchestrationSelector()
        mode = selector.select(expected_tool_steps=3, has_branching=True)
        # mode = "tree"
    """

    def select(
        self,
        expected_tool_steps: int = 1,
        has_branching: bool = False,
        profile_mode: str = "auto",
    ) -> str:
        """选择编排模式。

        Args:
            expected_tool_steps: 预估的工具调用步数（由 ComplexityRouter 或任务分析提供）。
            has_branching: 是否有条件分支（如 if/else、多方案选择）。
            profile_mode: ControlProfile.orchestration_mode。若为非 auto，直接返回。

        Returns:
            编排模式: single | chain | tree | reflexion
        """
        if profile_mode not in ("auto", "", None):
            return profile_mode

        for (max_steps, branch), mode in _SELECTION_TABLE:
            if expected_tool_steps <= max_steps and has_branching == branch:
                return mode

        return "reflexion"  # 兜底：复杂任务 → 带自省

    def select_for_pipeline(
        self,
        stage_count: int = 1,
        has_parallel: bool = False,
        profile_mode: str = "auto",
    ) -> str:
        """Pipeline 级别的编排选择。

        与 select() 的区别：stage_count 用于流水线阶段数，
        has_parallel 用于判断是否需要 tree 模式。

        Args:
            stage_count: 流水线阶段数。
            has_parallel: 是否允许并行执行。
            profile_mode: ControlProfile.orchestration_mode。

        Returns:
            编排模式。
        """
        if profile_mode not in ("auto", "", None):
            return profile_mode

        if stage_count <= 1:
            return "single"
        if stage_count <= 3:
            return "tree" if has_parallel else "chain"
        return "reflexion"
