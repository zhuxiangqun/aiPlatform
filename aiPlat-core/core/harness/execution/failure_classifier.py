"""
FailureClassifier — maps runtime errors to failure types and constraint actions.

Design principle (harness/CLAUDE.md §5.17, control theory Rule #2):
  Each failure mode requires at least one dedicated constraint mechanism.
  Generic skip_stage / fail_pipeline don't address WHY the stage failed,
  so the same failure recurs across retries.

Classification is based on error message patterns (no LLM call needed).
The constraint map is configurable per-stage via PipelineStageConfig.failure_mode_constraints.
"""

from __future__ import annotations

import logging
import re
from typing import Any, Dict, List, Optional

FEATURE_FLAG = "AIPLAT_ENABLE_FAILURE_CLASSIFICATION"

DEFAULT_FAILURE_MODE_CONSTRAINTS: List[Dict[str, Any]] = [
    {
        "failure_type": "rate_limit",
        "constraint_action": "retry_with_backoff",
        "max_escalation": 3,
        "description": "LLM rate-limited (429)",
    },
    {
        "failure_type": "timeout",
        "constraint_action": "reduce_context_retry",
        "max_escalation": 2,
        "description": "LLM call timed out",
    },
    {
        "failure_type": "context_overflow",
        "constraint_action": "emergency_compress_retry",
        "max_escalation": 1,
        "description": "Context too long for model",
    },
    {
        "failure_type": "model_unavailable",
        "constraint_action": "switch_fallback_model",
        "max_escalation": 2,
        "description": "LLM service unavailable (503/502)",
    },
    {
        "failure_type": "format_error",
        "constraint_action": "strict_format_retry",
        "max_escalation": 2,
        "description": "Output doesn't match expected format",
    },
    {
        "failure_type": "policy_denied",
        "constraint_action": "escalate_to_hitl",
        "max_escalation": 0,
        "description": "Safety/content policy blocked the call",
    },
    {
        "failure_type": "needs_clarification",
        "constraint_action": "escalate_to_hitl",
        "max_escalation": 0,
        "description": "Agent requires more information to proceed",
    },
]

_log = logging.getLogger("pipeline_engine.failure_classifier")


class FailureClassifier:
    _RATE_LIMIT = re.compile(r'rate.limit|429|too many request|quota.*exceed', re.IGNORECASE)
    _TIMEOUT = re.compile(r'time.?out|timed.?out|deadline.*exceed|read.?timeout', re.IGNORECASE)
    _CONTEXT_OVERFLOW = re.compile(r'context.?length|too long|reduce (the )?length|token limit|max token|context window|too many token|truncat', re.IGNORECASE)
    _MODEL_UNAVAILABLE = re.compile(r'503|502|service.?unavailable|bad gateway|model.*not.*available|overloaded', re.IGNORECASE)
    _FORMAT_ERROR = re.compile(r'json.*decode|schema.*valid|format.*error|malform|unexpected token|not valid', re.IGNORECASE)
    _POLICY_DENIED = re.compile(r'policy.*denied|safety|content.*filter|blocked|refus|guard|injection', re.IGNORECASE)
    _NEEDS_CLARIFICATION = re.compile(r'need.*clari|insufficient.*info|ambiguous|unclear', re.IGNORECASE)

    @classmethod
    def classify(cls, error_message: str, exception_type: str = "") -> str:
        if not error_message and not exception_type:
            return "unknown"
        msg = str(error_message or "") + " " + str(exception_type or "")
        if cls._RATE_LIMIT.search(msg):
            return "rate_limit"
        if cls._CONTEXT_OVERFLOW.search(msg):
            return "context_overflow"
        if cls._TIMEOUT.search(msg):
            return "timeout"
        if cls._MODEL_UNAVAILABLE.search(msg):
            return "model_unavailable"
        if cls._POLICY_DENIED.search(msg):
            return "policy_denied"
        if cls._FORMAT_ERROR.search(msg):
            return "format_error"
        if cls._NEEDS_CLARIFICATION.search(msg):
            return "needs_clarification"
        return "unknown"

    @classmethod
    def get_constraint(cls, failure_type: str, stage_constraints: Optional[List[Dict]] = None) -> Optional[Dict]:
        constraints = stage_constraints if stage_constraints else DEFAULT_FAILURE_MODE_CONSTRAINTS
        for c in constraints:
            if c.get("failure_type") == failure_type:
                return dict(c)
        for c in DEFAULT_FAILURE_MODE_CONSTRAINTS:
            if c.get("failure_type") == failure_type:
                return dict(c)
        return None

    @classmethod
    def get_escalation_count(cls, state: Dict[str, Any], failure_type: str) -> int:
        key = f"_escalation_{failure_type}"
        return state.get(key, 0)

    @classmethod
    def record_escalation(cls, state: Dict[str, Any], failure_type: str) -> None:
        key = f"_escalation_{failure_type}"
        state[key] = state.get(key, 0) + 1

    @classmethod
    def get_auto_rule(cls, failure_type: str) -> Optional[str]:
        _RULES: Dict[str, str] = {
            "rate_limit": "如果 LLM 返回 429 限流错误，等待 5 秒后重试，不要连续重试。",
            "timeout": "如果单次 LLM 调用超过 60 秒无响应，输出当前已分析的内容而非重试。",
            "context_overflow": "当上下文过长时优先压缩历史对话而非删减系统提示词。",
            "format_error": "输出必须严格符合 JSON 格式，JSON 内不得包含 Markdown 代码块标记。",
            "policy_denied": "不要生成任何可能触发内容安全策略的输出。",
            "needs_clarification": "当输入信息不足以完成任务时，直接标注 uncertainty 字段而非猜测填充。",
        }
        return _RULES.get(failure_type)
