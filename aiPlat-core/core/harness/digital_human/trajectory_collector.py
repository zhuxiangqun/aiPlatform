"""Trajectory Collector — structured conversation data for fine-tuning.

Writes each turn as JSONL to ~/.aiplat/trajectories/.
Format: ShareGPT-compatible, suitable for LoRA / SFT training.
"""
from __future__ import annotations

import json
import logging
import os
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger("aiplat.trajectory")

_TRAJ_DIR = Path(os.getenv("AIPLAT_TRAJECTORY_DIR",
    os.path.expanduser("~/.aiplat/trajectories")))


def ensure_dir() -> None:
    _TRAJ_DIR.mkdir(parents=True, exist_ok=True)


def collect_turn(
    session_id: str,
    role: str,
    content: str,
    *,
    tool_name: Optional[str] = None,
    tool_action: Optional[str] = None,
    tool_result: Optional[Any] = None,
) -> None:
    """Record one conversation turn.

    Args:
        session_id: Unique session identifier.
        role: "user" | "assistant" | "tool"
        content: Text content (user query / assistant response).
        tool_name: Tool name (only for role="tool").
        tool_action: Tool action (e.g. "goto", "extract").
        tool_result: Tool result (JSON-serializable).
    """
    try:
        ensure_dir()
        entry: Dict[str, Any] = {
            "id": session_id,
            "role": role,
            "content": content,
            "timestamp": int(time.time()),
        }
        if role == "tool" and tool_name:
            entry["name"] = tool_name
            entry["action"] = tool_action or ""
            entry["result"] = tool_result

        file_path = _TRAJ_DIR / f"{session_id}.jsonl"
        with open(file_path, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")
    except Exception as e:
        logger.debug("Trajectory save failed: %s", e)


def get_recent_trajectories(limit: int = 10) -> List[Dict[str, Any]]:
    """Get recent trajectories for few-shot injection."""
    try:
        ensure_dir()
        files = sorted(_TRAJ_DIR.glob("*.jsonl"), key=lambda f: f.stat().st_mtime, reverse=True)
        entries: List[Dict[str, Any]] = []
        for f in files[:limit]:
            with open(f) as fh:
                for line in fh:
                    if line.strip():
                        entries.append(json.loads(line))
                        if len(entries) >= limit * 5:
                            return entries
        return entries
    except Exception:
        return []


# ═══════════════════════════════════════════════════════════
# P1-2 闭环: 数字人轨迹 → SFT 训练数据集
# ═══════════════════════════════════════════════════════════

def export_sharegpt_dataset(
    *,
    output_dir: str = "",
    min_turns: int = 2,
    session_filter: str = "",
) -> Dict[str, Any]:
    """把 ~/.aiplat/trajectories/ 的对话轮次聚合为 ShareGPT 格式数据集，
    输出到训练侧目录（~/.aiplat/training/sft_digital_human_*.jsonl），
    与 auto_trigger._convert_to_sharegpt 的格式完全一致 —— 数字人对话由此进入 SFT 训练闭环。

    ShareGPT 结构: {"conversations": [{"from": "human", "value": ...}, {"from": "gpt", "value": ...}]}

    Args:
        output_dir: 输出目录，默认 ~/.aiplat/training（训练侧 dataset_dir）
        min_turns: 至少 N 轮才导出（过滤单轮噪音）
        session_filter: 只导出指定 session 前缀（空=全部）

    Returns:
        {"samples": n, "output_path": str, "skipped_sessions": [...]}
    """
    try:
        ensure_dir()
        out_dir = output_dir or os.path.expanduser("~/.aiplat/training")
        os.makedirs(out_dir, exist_ok=True)

        # 按 session 聚合对话
        sessions: Dict[str, List[Dict[str, Any]]] = {}
        for f in sorted(_TRAJ_DIR.glob("*.jsonl")):
            session_id = f.stem
            if session_filter and not session_id.startswith(session_filter):
                continue
            try:
                with open(f, encoding="utf-8") as fh:
                    turns = [json.loads(line) for line in fh if line.strip()]
                sessions[session_id] = turns
            except Exception:
                logger.debug("Skipping unreadable trajectory %s", f, exc_info=True)

        samples: List[Dict[str, Any]] = []
        skipped: List[str] = []
        for session_id, turns in sessions.items():
            # 配对 user/assistant 轮次 → 多轮 conversations
            pairs: List[Dict[str, str]] = []
            for t in turns:
                role = str(t.get("role") or "")
                content = str(t.get("content") or "").strip()
                if not content:
                    continue
                if role == "user":
                    pairs.append({"from": "human", "value": content})
                elif role == "assistant" and pairs and pairs[-1]["from"] == "human":
                    pairs.append({"from": "gpt", "value": content})
            if len(pairs) < min_turns:
                skipped.append(session_id)
                continue
            samples.append({"conversations": pairs})

        if not samples:
            return {"samples": 0, "output_path": "", "skipped_sessions": skipped}

        timestamp = time.strftime("%Y%m%d_%H%M%S")
        out_path = os.path.join(out_dir, f"sft_digital_human_{timestamp}.jsonl")
        with open(out_path, "w", encoding="utf-8") as f:
            for item in samples:
                f.write(json.dumps(item, ensure_ascii=False) + "\n")

        logger.info("Exported %d digital-human conversations → %s", len(samples), out_path)
        return {"samples": len(samples), "output_path": out_path, "skipped_sessions": skipped}
    except Exception as e:
        logger.warning("Trajectory export failed: %s", e)
        return {"samples": 0, "output_path": "", "error": str(e)}
