"""人机反馈阈值告警 — 历史基线 + 动态阈值判定。

从 AdoptionTracker 读取 HITL 拒绝率、审批率等关键指标，
与 7 天/30 天历史基线对比，计算移动平均值 + 标准差。

判定规则：
  - 当前值超出 3σ → FAIL（显著异常）
  - 当前值超出 2σ → WARN（需关注）
"""

import statistics
from typing import Any, Dict, List


async def check_human_feedback() -> Dict[str, Any]:
    try:
        from core.harness.evaluation.adoption_metrics import AdoptionTracker
        tracker = AdoptionTracker()
        report = tracker.compute_metrics()
    except Exception as e:
        return {"status": "warn", "reason": f"AdoptionTracker unavailable: {str(e)[:100]}"}

    historical = tracker.get_historical(days=30)
    rejection_rates = [
        h["hitl_rejection_rate"]
        for h in historical
        if h.get("hitl_rejection_rate") is not None
    ]

    if len(rejection_rates) < 7:
        return {
            "status": "pass",
            "note": f"insufficient history ({len(rejection_rates)} days, need ≥7)",
            "current_rejection_rate": report.hitl_rejection_rate,
        }

    mean = statistics.mean(rejection_rates)
    stdev = statistics.stdev(rejection_rates) if len(rejection_rates) > 1 else 0.01
    current = report.hitl_rejection_rate

    sigma = round((current - mean) / stdev, 1) if stdev > 0 else 0

    if current > mean + 3 * stdev:
        return {
            "status": "fail",
            "metric": "hitl_rejection_rate",
            "current": current,
            "mean_30d": round(mean, 4),
            "sigma": sigma,
            "threshold": "3σ",
        }
    if current > mean + 2 * stdev:
        return {
            "status": "warn",
            "metric": "hitl_rejection_rate",
            "current": current,
            "mean_30d": round(mean, 4),
            "sigma": sigma,
            "threshold": "2σ",
        }
    return {
        "status": "pass",
        "current_rejection_rate": round(current, 4),
        "mean_30d": round(mean, 4),
        "sigma": sigma,
    }
