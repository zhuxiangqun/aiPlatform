"""
Skills 渐进式披露策略（P0：统一入口）

目标：
- 用一个小而稳定的策略层，统一控制：
  1) skills_desc（技能索引）的展示预算
  2) skill_load（SOP 正文）的默认加载预算（建议值）
- 策略依据主要来自“上下文压力”（used_tokens / max_tokens）
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class SkillsDisclosureBudget:
    per_skill_desc_max_chars: int
    skills_desc_total_max_chars: int
    skill_sop_recommended_max_chars: int
    policy: str  # normal | pressured | critical


def compute_skills_disclosure_budget(
    *,
    context_pressure: float,
    default_per_skill_desc_max_chars: int,
    default_skills_desc_total_max_chars: int,
    default_skill_sop_max_chars: int,
) -> SkillsDisclosureBudget:
    """
    根据上下文压力计算预算：
    - normal: 使用默认预算
    - pressured: 中度收缩，避免 desc 过长，同时建议 SOP 降到 4k
    - critical: 强收缩，建议 SOP 降到 2k
    """
    p = float(context_pressure or 0.0)

    if p >= 0.9:
        return SkillsDisclosureBudget(
            per_skill_desc_max_chars=max(40, min(default_per_skill_desc_max_chars, 60)),
            skills_desc_total_max_chars=max(300, min(default_skills_desc_total_max_chars, 600)),
            skill_sop_recommended_max_chars=max(512, min(default_skill_sop_max_chars, 2000)),
            policy="critical",
        )

    if p >= 0.8:
        return SkillsDisclosureBudget(
            per_skill_desc_max_chars=max(60, min(default_per_skill_desc_max_chars, 90)),
            skills_desc_total_max_chars=max(500, min(default_skills_desc_total_max_chars, 900)),
            skill_sop_recommended_max_chars=max(1024, min(default_skill_sop_max_chars, 4000)),
            policy="pressured",
        )

    return SkillsDisclosureBudget(
        per_skill_desc_max_chars=default_per_skill_desc_max_chars,
        skills_desc_total_max_chars=default_skills_desc_total_max_chars,
        skill_sop_recommended_max_chars=default_skill_sop_max_chars,
        policy="normal",
    )

