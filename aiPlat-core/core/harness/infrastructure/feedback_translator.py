"""
FeedbackTranslator — PolicyGate decision → natural language for Agent.

When PolicyGate returns DENY or APPROVAL_REQUIRED, the raw machine enum
is not useful to the Agent's ReAct reasoning loop. FeedbackTranslator
translates these into structured, actionable natural language messages
that the Agent can use to decide: wait for approval, retry, or give up.

Integration point: called from PolicyGate._format_feedback() or directly
from syscall handlers (sys_tool_call, sys_skill_call, sys_agent_call).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, Optional


@dataclass
class AgentFeedback:
    """Structured feedback returned to Agent after a PolicyGate decision."""

    decision: str  # "denied" | "approval_required" | "allowed"
    message: str  # Human-readable NL explanation
    next_action: str  # What the Agent should do next
    approval_id: Optional[str] = None  # Approval ticket ID (if applicable)
    suggested_retry_after: Optional[float] = None  # Seconds (if rate-limited)
    details: Dict[str, Any] = field(default_factory=dict)


def translate_denial(reason: str, tool_name: str = "", user_id: str = "") -> AgentFeedback:
    """
    Translate a PolicyGate DENY decision into Agent-actionable feedback.

    Args:
        reason: Raw reason string from PolicyGate
        tool_name: The tool/skill/agent being denied
        user_id: The user who was denied

    Returns:
        AgentFeedback with NL message + recommended next action
    """
    # ApprovalGate denials
    if "approval_gate:deny" in reason:
        return AgentFeedback(
            decision="denied",
            message=f"操作被安全门禁拦截：{_extract_approval_message(reason)}",
            next_action="放弃此操作，寻找替代方案。不要重试——此操作已被永久阻断。",
            details={"blocker": "approval_gate", "raw_reason": reason},
        )

    # Architecture boundary violations
    if "architecture_violation" in reason or "protected_path" in reason:
        return AgentFeedback(
            decision="denied",
            message=f"操作违反架构边界：{reason}。不允许跨层写入受保护的目录。",
            next_action="停止当前操作，改用被允许的接口。如需写入受保护路径，联系系统管理员。",
            details={"blocker": "arch_boundary", "raw_reason": reason},
        )

    # Permission denials
    if "lacks" in reason or "permission" in reason.lower():
        return AgentFeedback(
            decision="denied",
            message=f"操作被拒绝：权限不足（{reason}）。当前用户 {user_id or 'unknown'} 没有执行此操作所需的权限。",
            next_action="不要重试此操作。告知用户需要申请权限，或在设置中调整权限配置。",
            details={"blocker": "permission", "user_id": user_id, "raw_reason": reason},
        )

    # Generic denial
    return AgentFeedback(
        decision="denied",
        message=f"操作被系统安全策略拒绝：{reason}。",
        next_action="不要重试。检查操作参数是否正确，或联系系统管理员。",
        details={"blocker": "unknown", "raw_reason": reason},
    )


def translate_approval_required(reason: str, tool_name: str = "", approval_id: str = "") -> AgentFeedback:
    """
    Translate a PolicyGate APPROVAL_REQUIRED decision into Agent-actionable feedback.

    The Agent should WAIT for the human approval, not retry immediately.
    """
    # ApprovalGate requirements
    if "approval_gate:ask" in reason:
        return AgentFeedback(
            decision="approval_required",
            message=f"此操作需要人工审批：{_extract_approval_message(reason)}。审批单 #{approval_id or 'pending'} 已生成。",
            next_action="等待管理员审批此操作。不要重试——审批完成后系统会自动通知你。",
            approval_id=approval_id,
            details={"blocker": "approval_gate", "raw_reason": reason},
        )

    # Generic approval
    return AgentFeedback(
        decision="approval_required",
        message=f"此操作需要额外审批：{reason}。",
        next_action="等待审批完成后再继续。不要在审批中重复提交。",
        approval_id=approval_id,
        details={"blocker": "approval_gate", "raw_reason": reason},
    )


def translate_rate_limit(wait_seconds: float, model_name: str = "") -> AgentFeedback:
    """Translate a rate limit into actionable feedback."""
    wait_str = f"{wait_seconds:.0f}秒" if wait_seconds < 60 else f"{wait_seconds / 60:.1f}分钟"
    model_hint = f"（模型: {model_name}）" if model_name else ""
    return AgentFeedback(
        decision="denied",
        message=f"调用频率超限，需等待 {wait_str} 后重试{model_hint}。",
        next_action=f"等待 {wait_str} 后自动恢复。如需继续，可尝试切换模型。",
        suggested_retry_after=wait_seconds,
        details={"blocker": "rate_limit", "model": model_name},
    )


def translate_error(error_type: str, message: str = "") -> AgentFeedback:
    """Translate a generic error into feedback."""
    return AgentFeedback(
        decision="denied",
        message=f"操作执行失败（{error_type}）：{message}",
        next_action="分析错误原因。如为临时错误，可稍后重试。如为永久错误，更换方案。",
        details={"error_type": error_type, "message": message},
    )


def format_for_agent(feedback: AgentFeedback) -> str:
    """
    Format feedback into a single string for injection into the Agent's
    observation stream (ReAct loop context).

    Returns a compact, parseable format that the LLM can understand.
    """
    parts = [f"[{feedback.decision.upper()}] {feedback.message}"]
    if feedback.next_action:
        parts.append(f"下一步: {feedback.next_action}")
    if feedback.approval_id:
        parts.append(f"审批单: #{feedback.approval_id}")
    if feedback.suggested_retry_after is not None:
        parts.append(f"重试等待: {feedback.suggested_retry_after:.0f}s")
    return "\n".join(parts)


def _extract_approval_message(raw_reason: str) -> str:
    """Extract human-readable message from approval gate reason string."""
    # Format: "approval_gate:ask — File deletion detected — this cannot be undone."
    parts = raw_reason.split(" — ")
    if len(parts) >= 2:
        return parts[-1]
    return raw_reason.replace("approval_gate:ask", "").replace("approval_gate:deny", "").strip(" —")
