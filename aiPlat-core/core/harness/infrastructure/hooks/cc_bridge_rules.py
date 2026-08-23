"""
CC/Codex hooks.json 事件映射表（数据驱动）。

对齐 DSH hooks-claude-code / hooks-codex：仅支持事件子集映射，
其余事件显式 unmapped（fail-open，不静默执行）。

设计依据：docs/research/plan-g6-hooks-bridge.md §3.2
"""

from __future__ import annotations

from typing import Dict, Optional

from .hook_manager import HookPhase

# Claude Code 事件全集（hooks.json 支持的事件名，2026-08 参考 CC 文档）
CC_EVENTS: tuple = (
    "PreToolUse", "PostToolUse", "Notification",
    "UserPromptSubmit", "Stop", "SubagentStop", "PreCompact",
    "SessionStart", "SessionEnd", "SubagentStart",
    "PermissionsUpdate",
    "PostToolUseOutput",
)

# Codex 事件全集（hooks.json 支持的事件名，2026-08 参考 Codex 文档）
CODEX_EVENTS: tuple = (
    "SessionStart", "PreToolUse", "PostToolUse",
    "Notification", "SessionEnd",
)

# CC 事件 → aiPlat HookPhase 映射（子集，§3.2）
CC_TO_PHASE: Dict[str, HookPhase] = {
    "SessionStart": HookPhase.SESSION_START,
    "UserPromptSubmit": HookPhase.PRE_LOOP,
    "PreToolUse": HookPhase.PRE_TOOL_USE,
    "PostToolUse": HookPhase.POST_TOOL_USE,
    "Stop": HookPhase.STOP,
    "SubagentStart": HookPhase.PRE_LOOP,   # 子代理启动映射 PRE_LOOP 子代理态
    "SubagentStop": HookPhase.POST_LOOP,   # 子代理结束映射 POST_LOOP 子代理态
}

# Codex 事件 → aiPlat HookPhase 映射（子集，与 CC 共用语义）
CODEX_TO_PHASE: Dict[str, HookPhase] = {
    "SessionStart": HookPhase.SESSION_START,
    "PreToolUse": HookPhase.PRE_TOOL_USE,
    "PostToolUse": HookPhase.POST_TOOL_USE,
    "SessionEnd": HookPhase.SESSION_END,
}


def resolve_phase(event: str, source: str = "cc") -> Optional[HookPhase]:
    """事件名 → HookPhase；unmapped 返回 None（调用方记录 WARNING，fail-open）。"""
    table = CODEX_TO_PHASE if source == "codex" else CC_TO_PHASE
    return table.get(event)


def mapped_event_count(source: str = "cc") -> int:
    """当前 source 的可映射事件数（供测试断言覆盖度）。"""
    table = CODEX_TO_PHASE if source == "codex" else CC_TO_PHASE
    return len(table)
