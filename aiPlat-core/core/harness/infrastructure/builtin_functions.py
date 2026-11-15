"""内置 Function handlers — 纯计算，零写库/零写 Wiki。

签名约定：``handler(params: dict, *, actor: str = "") -> dict``
"""
from __future__ import annotations

from typing import Any, Dict


def priority_hint(params: Dict[str, Any], *, actor: str = "") -> Dict[str, Any]:
    """根据 urgency/impact（0–5）计算优先级提示分，无副作用。

    Args:
        params: 须含 urgency / impact（可缺省为 0）。
        actor: 调用方（不参与计算，仅签名对齐）。

    Returns:
        ``{score, reason, urgency, impact}``。
    """
    def _clamp(v: Any) -> float:
        try:
            x = float(v)
        except (TypeError, ValueError):
            x = 0.0
        return max(0.0, min(5.0, x))

    urgency = _clamp(params.get("urgency", 0))
    impact = _clamp(params.get("impact", 0))
    # 简单加权：urgency 0.6 + impact 0.4，归一到 0–100
    score = round((urgency * 0.6 + impact * 0.4) / 5.0 * 100.0, 2)
    reason = f"urgency={urgency}, impact={impact}, actor={actor or '-'}"
    return {
        "score": score,
        "reason": reason,
        "urgency": urgency,
        "impact": impact,
    }
