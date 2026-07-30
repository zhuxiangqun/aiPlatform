"""
RecursivePatternDetector — 递归自指模式检测 (Cognitive Safety Layer)

检测 LLM 对话中是否存在"认知同化"攻击模式:
  - 连续自指追问 (描述AI自身内部机制)
  - 内部标签泄漏 (</final_answer>, 合规注释, 审核路径)
  - 累积暴露拓扑 (超过3轮持续追问 → 标记 _recursive_risk)

原则: Harness 层不能阻止模型"想什么"，但能检测"这种模式正在形成"。

调用者: _guard_messages() → sys_llm_generate 前
"""

from __future__ import annotations

import logging
import re as _re
import time as _time
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger("aiplat.cognitive_safety")

# ── Patterns ───────────────────────────────────────────────────────────

# 内部标签泄漏特征
_INTERNAL_TAG_PATTERNS = [
    _re.compile(r'</final_answer>', _re.IGNORECASE),
    _re.compile(r'\[合规注释\]|\[safety_audit\]|\[审核路径\]|\[内部判定\]'),
    _re.compile(r'final_decision|escalation_level|audit_trail'),
    _re.compile(r'输入层得分|规则引擎触发|动态阈值|级联模式'),
]

# 自指追问特征 (AI 在描述自身内部机制)
_SELF_REF_PATTERNS = [
    _re.compile(r'(你的|内部|底层|安全审查|生成机制|运行机制|逻辑链路|认知语法)'),
    _re.compile(r'(如何判断|如何生成|如何选择|如何过滤|如何决定|如何处理)'),
    _re.compile(r'(暴露了?|泄漏了?|绕过了?|穿透了?)'),
]

# 递归特征 (对 AI 自身运作的渐进式追问)
_RECURSIVE_PATTERNS = [
    _re.compile(r'(刚才的回答.*暴露|这次.*泄漏|上一轮.*显示|根据你的.*回答)'),
    _re.compile(r'(框架.*取代|框架.*替换|框架.*覆盖|认知.*同化)'),
    _re.compile(r'(观.*藏.*生.*归.*觉|七步|周天|般若|造化诀)'),
]


class RecursivePatternDetector:
    """递归自指模式检测器.

    使用方式:
        detector = RecursivePatternDetector()
        is_risk, score = detector.check(user_input, assistant_output, session_history)
    """

    def __init__(self, *, threshold: float = 0.6):
        self._threshold = threshold
        self._session_scores: Dict[str, float] = {}  # session_id → cumulative risk

    def check(
        self,
        user_input: str,
        assistant_output: str,
        *,
        session_id: str = "",
        message_history: Optional[List[Dict]] = None,
    ) -> Tuple[bool, float, Dict[str, Any]]:
        """检测当前轮次是否存在递归自指风险.

        Returns:
            (is_risk, score, details)
        """
        score = 0.0
        details: Dict[str, Any] = {
            "internal_tags": [],
            "self_ref": False,
            "recursive_trail": False,
            "cumulative": False,
        }

        # 1. 检测内部标签泄漏 (输出侧)
        for pat in _INTERNAL_TAG_PATTERNS:
            matches = pat.findall(assistant_output)
            if matches:
                details["internal_tags"].extend(matches[:5])
                score += 0.2 * min(len(matches), 3)

        # 2. 检测自指追问 (输入侧)
        input_hits = 0
        for pat in _SELF_REF_PATTERNS:
            if pat.search(user_input):
                input_hits += 1
        if input_hits >= 2:
            details["self_ref"] = True
            score += 0.3

        # 3. 检测递归追问特征 (输入侧 — 渐进式暴露)
        for pat in _RECURSIVE_PATTERNS:
            if pat.search(user_input):
                details["recursive_trail"] = True
                score += 0.3
                break

        # 4. 累积风险 (跨轮次)
        if session_id:
            cumulative = self._session_scores.get(session_id, 0.0)
            cumulative += score * 0.5  # Dampen: current score contributes 50% to cumulative
            self._session_scores[session_id] = min(cumulative, 1.0)
            if cumulative > self._threshold:
                details["cumulative"] = True
                score = max(score, cumulative)

        is_risk = score > self._threshold

        if is_risk:
            logger.warning(
                "Recursive pattern detected: session=%s score=%.2f tags=%d self_ref=%s trail=%s cumulative=%s",
                session_id, score, len(details["internal_tags"]),
                details["self_ref"], details["recursive_trail"], details["cumulative"],
            )

        return is_risk, score, details

    def reset_session(self, session_id: str):
        self._session_scores.pop(session_id, None)


# ── Convenience ──────────────────────────────────────────────────────────

def check_cognitive_safety(
    user_input: str,
    assistant_output: str = "",
    *,
    session_id: str = "",
    message_history: Optional[List[Dict]] = None,
) -> Dict[str, Any]:
    """快速检查认知安全性."""
    detector = RecursivePatternDetector()
    is_risk, score, details = detector.check(
        user_input, assistant_output,
        session_id=session_id, message_history=message_history,
    )
    return {
        "risk_detected": is_risk,
        "risk_score": round(score, 2),
        "details": details,
        "action": "block_persist" if is_risk else "allow",
    }
