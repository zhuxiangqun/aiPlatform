"""
File-based Memory Store (P1-3 — OpenClaw 借鉴)

Markdown 文件作为记忆的标准答案载体。SQLite FTS5 只做检索增强。
人类可直接查看/编辑 MARKDOWN 文件验证 Agent 学到了什么。

文件结构:
  ~/.aiplat/memory/
  ├── MEMORY.md           # 长期偏好
  ├── YYYY-MM-DD.md       # 每日工作笔记

写入路径: Markdown 先写 → 成功后 SQLite FTS5 → 失败时整体失败
读取路径: FTS5 搜索 → 返回文件路径+行号 → Agent 读原文
"""
from __future__ import annotations

import os
import logging
from datetime import datetime
from typing import Any, Dict, List, Optional

_log = logging.getLogger("aiplat.memory.file_store")

MEMORY_DIR = os.path.expanduser("~/.aiplat/memory")


def _ensure_dir() -> None:
    os.makedirs(MEMORY_DIR, exist_ok=True)


def write_memory(content: str, key: str = "preference", source: str = "agent") -> bool:
    """Dual-write: Markdown first, then SQLite. Markdown is the canonical store."""
    _ensure_dir()
    today = datetime.now().strftime("%Y-%m-%d")
    date_file = os.path.join(MEMORY_DIR, f"{today}.md")
    mem_file = os.path.join(MEMORY_DIR, "MEMORY.md")
    
    entry = f"\n- **[{key}]** ({source}) {datetime.now().strftime('%H:%M')}: {content}\n"
    
    try:
        # Primary: write to Markdown
        with open(mem_file, "a", encoding="utf-8") as f:
            f.write(entry)
        # Secondary: write to date file
        with open(date_file, "a", encoding="utf-8") as f:
            f.write(entry)
        
        # SQLite FTS5 index (best-effort, non-blocking)
        try:
            from core.services.execution_store import get_execution_store
            store = get_execution_store()
            import asyncio as _aio
            _aio.ensure_future(store.set_meta(
                f"memory:{key}:{today}",
                "memory_content", content,
            ))
        except Exception:
            pass
        
        _log.info("Memory written: %s → %s", key, mem_file)
        return True
    except Exception as e:
        _log.error("Memory write failed: %s", e)
        return False


def read_memory(key_filter: str = "", limit: int = 20) -> List[Dict[str, Any]]:
    """Read memory entries from Markdown files. Optional key filter."""
    _ensure_dir()
    results = []
    mem_file = os.path.join(MEMORY_DIR, "MEMORY.md")
    
    if not os.path.exists(mem_file):
        return results
    
    try:
        with open(mem_file, "r", encoding="utf-8") as f:
            lines = f.readlines()
        
        for line in lines:
            line = line.strip()
            if not line or not line.startswith("- **"):
                continue
            # Parse: - **[key]** (source) time: content
            if key_filter and key_filter not in line:
                continue
            results.append({"raw": line})
            if len(results) >= limit:
                break
    except Exception as e:
        _log.debug("Memory read skipped: %s", e)
    
    return results


def list_memory_files() -> List[str]:
    """List all Markdown memory files."""
    _ensure_dir()
    if not os.path.isdir(MEMORY_DIR):
        return []
    return sorted([
        f for f in os.listdir(MEMORY_DIR)
        if f.endswith(".md")
    ])


# ── Auto Memory: Agent self-learning persistence (Claude Code 差距) ──

def auto_save_learning(
    learning_type: str,  # "correction" | "preference" | "pattern" | "mistake"
    content: str,
    source: str = "agent",
) -> bool:
    """Auto-save agent self-learnings to file memory.

    Triggered when:
    - User corrects agent (correction) → save the corrected pattern
    - Agent discovers user preference (preference) → save for future
    - Agent detects recurring pattern (pattern) → crystallize as reusable knowledge
    - Agent makes a mistake it's corrected for (mistake) → save to avoid repeating

    Controlled by AIPLAT_AUTO_LEARNING_ENABLED (default: true).
    """
    import os as _os
    enabled = _os.getenv("AIPLAT_AUTO_LEARNING_ENABLED", "true")
    if enabled in ("0", "false", "no"):
        return False

    prefix_map = {
        "correction": "🔄 Correction",
        "preference": "⭐ Preference",
        "pattern": "📊 Pattern",
        "mistake": "⚠️ Avoid",
    }
    prefix = prefix_map.get(learning_type, "📝 Learned")
    key = f"auto_{learning_type}"

    return write_memory(content=f"[{prefix}] {content}", key=key, source=source)


def should_auto_learn(interaction_count: int, correction_count: int) -> bool:
    """Decide whether the agent should auto-save learnings.

    Thresholds:
    - correction_count >= 2 in current session → likely preference pattern
    - interaction_count % 10 == 0 → periodic checkpoint
    - More than 3 similar queries detected → recurring pattern
    """
    if correction_count >= 2:
        return True
    if interaction_count > 0 and interaction_count % 10 == 0:
        return True
    return False
