"""
Claude Code 会话/记忆导入（P0-b，对标 Codex external_agent_config_migration）。

把 Claude Code 会话 JSONL（~/.claude/projects/*.jsonl 或 ~/.claude/transcripts/*.jsonl）
解析为对话轮次，写入 aiPlat MemoryManager（episodic/semantic 记忆）。

设计依据：docs/research/Codex-Harness开源借鉴分析报告.md §2.2 (P0-b)
参考实现：codex-rs/tui/src/external_agent_config_migration（.claude/projects session.jsonl → memories）
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

# 默认搜索路径（Claude Code 会话存储位置）
DEFAULT_PATHS = (
    "~/.claude/projects",
    "~/.claude/transcripts",
)
MAX_SESSION_SIZE = 20 * 1024 * 1024  # 单会话 20MB 上限
MAX_LINES_PER_SESSION = 20000


@dataclass
class ClaudeTurn:
    """Claude Code 会话中的一轮对话（user/assistant 对）。"""
    user_text: str = ""
    assistant_text: str = ""
    timestamp: float = 0.0
    source_file: str = ""
    session_id: str = ""
    metadata: Dict[str, Any] = field(default_factory=dict)


def _extract_text(content: Any) -> str:
    """从 Claude content 字段提取文本（字符串或消息块列表）。"""
    if content is None:
        return ""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = []
        for block in content:
            if not isinstance(block, dict):
                continue
            if block.get("type") == "text":
                parts.append(str(block.get("text", "")))
            elif block.get("type") == "tool_use":
                parts.append(f"[tool: {block.get('name', '')}]")
            elif block.get("type") == "tool_result":
                c = block.get("content")
                if isinstance(c, str):
                    parts.append(f"[tool_result: {c[:500]}]")
        return "\n".join(parts)
    return str(content)


def parse_claude_session(path: Path, limit: int = MAX_LINES_PER_SESSION) -> List[ClaudeTurn]:
    """解析单个 Claude Code 会话 JSONL → 对话轮次列表。

    按 user→assistant 配对；跳过 system-reminder 噪音；source_tag 标记
    为 "claude_import"（区别于 user/system/agent/auto_learned 原生来源）。
    """
    if not path.exists():
        raise FileNotFoundError(f"Claude session not found: {path}")
    if path.stat().st_size > MAX_SESSION_SIZE:
        logger.warning("Claude session %s exceeds %d bytes, skipping", path, MAX_SESSION_SIZE)
        return []

    turns: List[ClaudeTurn] = []
    pending_user: Optional[ClaudeTurn] = None
    session_id = path.stem

    with open(path, encoding="utf-8", errors="ignore") as f:
        for i, line in enumerate(f):
            if i >= limit:
                break
            line = line.strip()
            if not line:
                continue
            try:
                record = json.loads(line)
            except json.JSONDecodeError:
                continue
            rtype = record.get("type")
            text = _extract_text(record.get("content"))
            if not text.strip():
                continue
            # 跳过系统指令噪音（非用户真实输入）
            if "system-reminder" in text[:200] or "[SYSTEM DIRECTIVE" in text[:200]:
                continue
            try:
                ts = record.get("timestamp", "")
                timestamp = float(ts) if isinstance(ts, (int, float)) else 0.0
            except (TypeError, ValueError):
                timestamp = 0.0

            if rtype == "user":
                if pending_user is not None:
                    # 连续 user → 保留前一个（无 assistant 响应）
                    pending_user = None
                pending_user = ClaudeTurn(
                    user_text=text.strip(),
                    timestamp=timestamp,
                    source_file=str(path),
                    session_id=session_id,
                )
            elif rtype == "assistant" and pending_user is not None:
                pending_user.assistant_text = text.strip()
                pending_user.metadata["assistant_timestamp"] = timestamp
                turns.append(pending_user)
                pending_user = None
            elif rtype == "assistant":
                # 无 user 前置的 assistant（如恢复会话）→ 独立记录
                turns.append(ClaudeTurn(
                    assistant_text=text.strip(),
                    timestamp=timestamp,
                    source_file=str(path),
                    session_id=session_id,
                ))

    logger.info("Parsed %d turns from %s", len(turns), path)
    return turns


def find_claude_sessions(base_path: Optional[str] = None) -> List[Path]:
    """查找本地 Claude Code 会话 JSONL 文件。"""
    candidates = [Path(p).expanduser() for p in (DEFAULT_PATHS if base_path is None else (base_path,))]
    found: List[Path] = []
    for cand in candidates:
        if not cand.exists():
            continue
        if cand.is_file() and cand.suffix == ".jsonl":
            found.append(cand)
        elif cand.is_dir():
            found.extend(sorted(cand.rglob("*.jsonl")))
    return found[:200]  # 单次导入上限 200 个会话


async def import_claude_sessions(
    memory_manager: Any,
    base_path: Optional[str] = None,
    session_files: Optional[List[Path]] = None,
    max_sessions: int = 50,
) -> Dict[str, Any]:
    """导入 Claude Code 会话 → MemoryManager（P0-b 主入口）。

    :param memory_manager: 实现 save_interaction(user_message, assistant_message, ...) 的记忆管理器
    :param base_path: Claude 会话目录（默认 ~/.claude/projects + transcripts）
    :param session_files: 显式指定会话文件（用于测试/精确导入）
    :param max_sessions: 单次导入会话数上限
    :return: {imported, sessions, turns, skipped, errors}
    """
    if session_files is None:
        session_files = find_claude_sessions(base_path)
    session_files = session_files[:max_sessions]

    total_turns = 0
    imported_sessions = 0
    skipped = 0
    errors: List[str] = []

    for path in session_files:
        try:
            turns = parse_claude_session(path)
            if not turns:
                skipped += 1
                continue
            for turn in turns:
                user_msg = turn.user_text or ""
                assistant_msg = turn.assistant_text or ""
                if not user_msg and not assistant_msg:
                    continue
                await memory_manager.save_interaction(
                    user_message=user_msg or "[imported]",
                    assistant_message=assistant_msg or "[no response]",
                    stability="medium",
                    session_id=f"claude:{turn.session_id}",
                    metadata={
                        "source": "claude_import",
                        "source_file": turn.source_file,
                        "provenance": f"claude:{turn.session_id}:{path.stem}",
                    },
                )
                total_turns += 1
            imported_sessions += 1
        except Exception as e:  # noqa: BLE001 — 单会话失败不阻断整体
            logger.warning("claude import failed for %s: %s", path, e)
            errors.append(f"{path}: {str(e)[:150]}")

    return {
        "imported": imported_sessions,
        "sessions": len(session_files),
        "turns": total_turns,
        "skipped": skipped,
        "errors": errors,
    }
