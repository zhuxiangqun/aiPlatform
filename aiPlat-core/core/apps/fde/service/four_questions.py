"""FDE 立项四问评估（P2-L0，六层框架 L0 战略罗盘工具化）。

立项四问（见 docs/research/企业级AI可信落地全景图-aiPlat对照.md §L0）：
  1. 决策反复发生（recurrence）      —— 该决策是高频反复，还是一次性？
  2. 跨 3+ 系统（cross_system）      —— 是否横跨 3 个以上业务系统？
  3. 有 Owner + 量化指标（owner+metrics）—— 是否有人负责且有可度量结果？
  4. 可写回 Action（action_writeback）—— 决策结果能否闭环成系统 Action？

输出：0-100 总分 + 立项结论（go / conditional / sandbox）+ MVP 本体建议 tier
（复用 P2-L1 分层语义：edge=沙盘验证，logic=MVP 起步，core=承重墙需架构评审）。
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

# ── 四问定义 ──

FOUR_QUESTIONS: List[Dict[str, Any]] = [
    {
        "key": "recurrence",
        "question": "决策是否反复发生？",
        "weight": 0.25,
        "hint": "高频反复（每天/每周）才值得系统化；一次性决策用流程文档即可",
    },
    {
        "key": "cross_system",
        "question": "是否跨 3+ 业务系统？",
        "weight": 0.25,
        "hint": "跨系统决策才能体现本体统一语义的价值；单系统内部逻辑用普通代码",
    },
    {
        "key": "owner_metrics",
        "question": "是否有 Owner 和量化指标？",
        "weight": 0.25,
        "hint": "无人负责、无法度量 → 无法验收，AI 系统会沦为玩具",
    },
    {
        "key": "action_writeback",
        "question": "决策结果能否写回 Action 闭环？",
        "weight": 0.25,
        "hint": "结论必须能落成系统可执行的动作（审批/通知/状态变更），否则只是报告",
    },
]

GO_THRESHOLD = 75          # ≥75 → 立项（go）
CONDITIONAL_THRESHOLD = 50  # 50-74 → 有条件立项（conditional）；<50 → 沙盘（sandbox）


def _score_recurrence(value: Any) -> int:
    """频率映射：daily=100 / weekly=75 / monthly=50 / rare=25 / 未知=40。"""
    v = str(value or "").strip().lower()
    table = {"daily": 100, "weekly": 75, "monthly": 50, "quarterly": 35, "rare": 25, "once": 25}
    return table.get(v, 40)


def _score_cross_system(count: Any) -> int:
    """系统数：≥3 → 100；2 → 60；1 → 30；0 → 0。"""
    try:
        n = int(count or 0)
    except (TypeError, ValueError):
        n = 0
    if n >= 3:
        return 100
    if n == 2:
        return 60
    if n == 1:
        return 30
    return 0


def _score_owner_metrics(has_owner: Any, metrics: Any) -> int:
    owner = bool(has_owner)
    has_metrics = bool(metrics)
    if owner and has_metrics:
        return 100
    if owner or has_metrics:
        return 60
    return 0


def _score_action_writeback(action: Any) -> int:
    return 100 if action else 0


def evaluate_four_questions(inputs: Dict[str, Any]) -> Dict[str, Any]:
    """评估立项四问。返回逐问得分 + 总分 + 结论 + MVP 本体建议 tier。

    Args:
        inputs: {
            title, recurrence(str), systems_count(int), has_owner(bool),
            metrics(list[str]), action_writeback(str|None), notes(str)
        }
    """
    title = str(inputs.get("title") or "未命名决策")

    answers = [
        {
            "key": q["key"],
            "question": q["question"],
            "hint": q["hint"],
            "score": _score_recurrence(inputs.get("recurrence")),
            "weight": q["weight"],
        }
        for q in FOUR_QUESTIONS
        if q["key"] == "recurrence"
    ]
    answers += [
        {
            "key": "cross_system",
            "question": next(q["question"] for q in FOUR_QUESTIONS if q["key"] == "cross_system"),
            "hint": next(q["hint"] for q in FOUR_QUESTIONS if q["key"] == "cross_system"),
            "score": _score_cross_system(inputs.get("systems_count")),
            "weight": 0.25,
        },
        {
            "key": "owner_metrics",
            "question": next(q["question"] for q in FOUR_QUESTIONS if q["key"] == "owner_metrics"),
            "hint": next(q["hint"] for q in FOUR_QUESTIONS if q["key"] == "owner_metrics"),
            "score": _score_owner_metrics(inputs.get("has_owner"), inputs.get("metrics")),
            "weight": 0.25,
        },
        {
            "key": "action_writeback",
            "question": next(q["question"] for q in FOUR_QUESTIONS if q["key"] == "action_writeback"),
            "hint": next(q["hint"] for q in FOUR_QUESTIONS if q["key"] == "action_writeback"),
            "score": _score_action_writeback(inputs.get("action_writeback")),
            "weight": 0.25,
        },
    ]

    total = round(sum(a["score"] * a["weight"] for a in answers))

    # 结论判定
    if total >= GO_THRESHOLD:
        verdict = "go"
        verdict_label = "立项（建议实施）"
    elif total >= CONDITIONAL_THRESHOLD:
        verdict = "conditional"
        verdict_label = "有条件立项（补齐短板后实施）"
    else:
        verdict = "sandbox"
        verdict_label = "暂缓 / 沙盘验证"

    # MVP 本体建议 tier（复用 P2-L1 分层语义）
    if verdict == "sandbox":
        suggested_tier = "edge"
        tier_reason = "得分 <50：先按实验边缘（edge）建沙盘验证，绝不自动升格"
    else:
        suggested_tier = "logic"
        tier_reason = "MVP 本体按可变逻辑（logic）起步；核心语义类（身份/血缘/权限）后续经架构评审升 core"
    if verdict == "go" and int(inputs.get("systems_count") or 0) >= 3:
        suggested_tier = "logic"
        tier_reason += "（跨 3+ 系统，建议立项时同步规划 core 类清单）"

    # 短板提示（得分 < 60 的项）
    gaps = [
        {"key": a["key"], "question": a["question"], "score": a["score"]}
        for a in answers
        if a["score"] < 60
    ]

    return {
        "title": title,
        "total_score": total,
        "verdict": verdict,
        "verdict_label": verdict_label,
        "answers": answers,
        "gaps": gaps,
        "suggested_tier": suggested_tier,
        "tier_reason": tier_reason,
        "evaluated_at": datetime.now(timezone.utc).isoformat(),
    }
