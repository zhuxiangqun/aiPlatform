"""Trajectory Collector — structured conversation data for fine-tuning.

Writes each turn as JSONL to ~/.aiplat/trajectories/.
Format: ShareGPT-compatible, suitable for LoRA / SFT training.

Curated path: thumbs / verbal correction → quality flags →
``export_curated_sharegpt_dataset`` (gold pairs only).
"""
from __future__ import annotations

import json
import logging
import os
import re
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger("aiplat.trajectory")

_TRAJ_DIR = Path(os.getenv("AIPLAT_TRAJECTORY_DIR",
    os.path.expanduser("~/.aiplat/trajectories")))

_GOOD_MARKERS = (
    "讲得对", "说得对", "答对了", "有用", "谢谢小朱", "不错", "正确",
    "helpful", "thanks", "good answer",
)
_BAD_MARKERS = (
    "不对", "错了", "不是这样", "你搞错", "说错", "答错", "纠正：", "应该是",
    "wrong", "incorrect", "not right",
)


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
    quality: Optional[str] = None,
) -> None:
    """Record one conversation turn.

    Args:
        session_id: Unique session identifier.
        role: "user" | "assistant" | "tool"
        content: Text content (user query / assistant response).
        tool_name: Tool name (only for role="tool").
        tool_action: Tool action (e.g. "goto", "extract").
        tool_result: Tool result (JSON-serializable).
        quality: optional "good" | "bad" | "gold" on this turn.
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
        if quality in ("good", "bad", "gold"):
            entry["quality"] = quality

        file_path = _TRAJ_DIR / f"{session_id}.jsonl"
        with open(file_path, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")
    except Exception as e:
        logger.debug("Trajectory save failed: %s", e)


def _rewrite_session_file(session_id: str, rows: List[Dict[str, Any]]) -> None:
    ensure_dir()
    path = _TRAJ_DIR / f"{session_id}.jsonl"
    with open(path, "w", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")


def _load_session_rows(session_id: str) -> List[Dict[str, Any]]:
    sid = (session_id or "").strip()
    if not sid:
        return []
    path = _TRAJ_DIR / f"{sid}.jsonl"
    if not path.is_file():
        return []
    rows: List[Dict[str, Any]] = []
    try:
        with open(path, encoding="utf-8") as fh:
            for line in fh:
                if not line.strip():
                    continue
                try:
                    rows.append(json.loads(line))
                except json.JSONDecodeError:
                    continue
    except OSError:
        return []
    return rows


def mark_feedback(
    session_id: str,
    rating: str,
    *,
    correction: str = "",
) -> Dict[str, Any]:
    """Mark the latest assistant turn as good/bad; optional gold correction.

    rating: "good" | "bad"
    correction: when bad, user-provided better answer (or short fix note).
    """
    sid = (session_id or "").strip()
    rate = (rating or "").strip().lower()
    if rate not in ("good", "bad") or not sid:
        return {"ok": False, "error": "invalid rating or session"}
    rows = _load_session_rows(sid)
    if not rows:
        return {"ok": False, "error": "no turns"}
    target_i = -1
    for i in range(len(rows) - 1, -1, -1):
        if str(rows[i].get("role") or "") == "assistant":
            target_i = i
            break
    if target_i < 0:
        return {"ok": False, "error": "no assistant turn"}
    rows[target_i]["quality"] = rate
    rows[target_i]["rated_at"] = int(time.time())
    corr = (correction or "").strip()
    if rate == "bad" and corr:
        # Prefer stripping leading "不对，应该是" style wrappers for gold value
        gold = re.sub(
            r"^(不对[，,。]?|错了[，,。]?|不是这样[，,。]?|纠正[:：]\s*|应该是\s*)+",
            "",
            corr,
        ).strip() or corr
        rows.append(
            {
                "id": sid,
                "role": "assistant",
                "content": gold,
                "timestamp": int(time.time()),
                "quality": "gold",
                "replaces_bad": True,
            }
        )
    try:
        _rewrite_session_file(sid, rows)
    except OSError as e:
        return {"ok": False, "error": str(e)}
    return {"ok": True, "rating": rate, "index": target_i, "has_gold": bool(corr and rate == "bad")}


def infer_feedback_from_user(user_text: str) -> Optional[Dict[str, str]]:
    """Detect verbal praise/correction without a thumbs UI.

    Returns {"rating": "good"|"bad", "correction": "..."} or None.
    """
    t = (user_text or "").strip()
    if not t or len(t) > 400:
        return None
    low = t.lower()
    if any(m in t or m in low for m in _BAD_MARKERS):
        return {"rating": "bad", "correction": t}
    if any(m in t or m in low for m in _GOOD_MARKERS) and len(t) < 40:
        return {"rating": "good", "correction": ""}
    return None


def recent_session_turns(
    session_id: str,
    *,
    max_turns: int = 6,
    max_chars: int = 500,
) -> List[Dict[str, str]]:
    """This WebSocket/session's last turns (working continuity, not long-term memory)."""
    sid = (session_id or "").strip()
    if not sid or max_turns <= 0:
        return []
    path = _TRAJ_DIR / f"{sid}.jsonl"
    if not path.is_file():
        return []
    rows: List[Dict[str, str]] = []
    try:
        with open(path, encoding="utf-8") as fh:
            for line in fh:
                if not line.strip():
                    continue
                try:
                    item = json.loads(line)
                except json.JSONDecodeError:
                    continue
                role = str(item.get("role") or "").strip()
                content = str(item.get("content") or "").strip()
                if role not in ("user", "assistant") or not content:
                    continue
                cap = max_chars if role == "user" else min(max_chars + 300, 900)
                rows.append({"role": role, "content": content[:cap]})
    except Exception:
        return []
    return rows[-max_turns:]


def format_session_dialogue(turns: List[Dict[str, str]]) -> str:
    if not turns:
        return ""
    lines = ["本会话刚才（不是长期记忆，追问须接上，勿换题）:"]
    for t in turns:
        who = "用户" if t.get("role") == "user" else "小朱"
        lines.append(f"{who}: {t.get('content') or ''}")
    return "\n".join(lines)


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


def export_curated_sharegpt_dataset(
    *,
    output_dir: str = "",
    session_filter: str = "",
) -> Dict[str, Any]:
    """Export only human-rated good / gold-corrected pairs for SFT.

    Pairing rules:
    - quality=good on assistant → previous user + this assistant
    - quality=gold on assistant → previous user (before the bad assistant) + gold
    """
    try:
        ensure_dir()
        out_dir = output_dir or os.path.expanduser("~/.aiplat/training")
        os.makedirs(out_dir, exist_ok=True)

        samples: List[Dict[str, Any]] = []
        for f in sorted(_TRAJ_DIR.glob("*.jsonl")):
            session_id = f.stem
            if session_filter and not session_id.startswith(session_filter):
                continue
            try:
                with open(f, encoding="utf-8") as fh:
                    turns = [json.loads(line) for line in fh if line.strip()]
            except Exception:
                logger.debug("Skipping unreadable trajectory %s", f, exc_info=True)
                continue

            last_user = ""
            last_bad_user = ""
            for t in turns:
                role = str(t.get("role") or "")
                content = str(t.get("content") or "").strip()
                quality = str(t.get("quality") or "").strip()
                if role == "user" and content:
                    last_user = content
                    continue
                if role != "assistant" or not content:
                    continue
                if quality == "bad":
                    last_bad_user = last_user
                    continue
                if quality == "good" and last_user:
                    samples.append(
                        {
                            "conversations": [
                                {"from": "human", "value": last_user},
                                {"from": "gpt", "value": content},
                            ],
                            "meta": {"session": session_id, "quality": "good"},
                        }
                    )
                elif quality == "gold":
                    q = last_bad_user or last_user
                    if q:
                        samples.append(
                            {
                                "conversations": [
                                    {"from": "human", "value": q},
                                    {"from": "gpt", "value": content},
                                ],
                                "meta": {"session": session_id, "quality": "gold"},
                            }
                        )

        if not samples:
            return {"samples": 0, "output_path": "", "note": "no curated turns"}

        timestamp = time.strftime("%Y%m%d_%H%M%S")
        out_path = os.path.join(out_dir, f"sft_digital_human_curated_{timestamp}.jsonl")
        with open(out_path, "w", encoding="utf-8") as f:
            for item in samples:
                f.write(json.dumps(item, ensure_ascii=False) + "\n")

        logger.info("Exported %d curated digital-human pairs → %s", len(samples), out_path)
        return {"samples": len(samples), "output_path": out_path}
    except Exception as e:
        logger.warning("Curated trajectory export failed: %s", e)
        return {"samples": 0, "output_path": "", "error": str(e)}


# Distilled from consultant_constitution / AGENT.md — bootstrap only.
# Runtime facts still come from platform_status_brief; do not train inventory counts.
_SEED_QA: List[Tuple[str, str]] = [
    (
        "选模怎么走？小朱用哪个模型？",
        "结论：Chat LLM 唯一链是 purpose → infra unified_pipeline，业务代码禁止点名模型。"
        "开放问答用 purpose=auto（先出 purpose 名再打分）。界面看 /infra/models。"
        "问「用哪个」看本轮简报 Chat LLM 段与顾问 header 的 model/purpose，不要瞎荐权重名。",
    ),
    (
        "我想做一个分析视频的应用，应该做 Agent 还是走应用工厂？",
        "结论：做应用产品走 /app/factory；平台内可对话角色走 /workspace/agents。"
        "工作区视频 Agent 只是样例可试跑，不等于你的应用已交付。"
        "下一步：到 /app/factory 用一句话写清分析要什么结果。\n"
        "[ACTION:navigate:/app/factory]",
    ),
    (
        "Skill 和 Agent 有什么区别？",
        "结论：Agent 是角色（可绑多个 Skill）；Skill 是可复用能力（prompt/handler）；"
        "Tool/MCP 是副作用出口；应用工厂是交付产品入口，不是再建一个 Agent。"
        "有没有某 Skill/Agent 以本轮平台实况简报为准，简报没有就说「简报未见」。",
    ),
    (
        "四层架构各自干什么？",
        "结论：infra=模型目录与选模权威；core=Harness/Skill/Agent 执行；"
        "platform=应用路由与工厂交付；management=管理端 UI，展示模型列表但不自建注册表。"
        "细节数量仍以本轮磁盘简报为准。",
    ),
    (
        "OSS 对象存储是什么？",
        "【通用说明，非 aiPlat 既有】对象存储（如 OSS/S3）按对象键存大文件，适合素材与备份。"
        "若要对齐本平台：看简报里是否有数据源/凭证名，没有则「简报未见」，不要编造工作区同名 Skill。",
    ),
    (
        "帮忙启动流水线创建项目",
        "结论：我可以指路，但不代执行 pipeline.start、也不未询问就创建项目。"
        "做应用请你到 /app/factory 自行确认并构建；需要跳转时我只给菜单路径。\n"
        "[ACTION:handoff:/app/factory]",
    ),
]


def export_seed_sharegpt_dataset(*, output_dir: str = "", force: bool = False) -> Dict[str, Any]:
    """Write distilled platform-mindset Q&A seeds for FineTune bootstrap.

    Stable file name (overwrite when force). Complements curated human feedback;
    never replaces live brief for inventory facts.
    """
    try:
        out_dir = output_dir or os.path.expanduser("~/.aiplat/training")
        os.makedirs(out_dir, exist_ok=True)
        out_path = os.path.join(out_dir, "sft_digital_human_seed.jsonl")
        if os.path.isfile(out_path) and not force:
            n = 0
            try:
                with open(out_path, encoding="utf-8") as fh:
                    n = sum(1 for line in fh if line.strip())
            except OSError:
                n = 0
            return {
                "samples": n,
                "output_path": out_path,
                "note": "exists (pass force=True to rewrite)",
            }
        samples = [
            {
                "conversations": [
                    {"from": "human", "value": q},
                    {"from": "gpt", "value": a},
                ],
                "meta": {"source": "constitution_seed", "quality": "seed"},
            }
            for q, a in _SEED_QA
        ]
        with open(out_path, "w", encoding="utf-8") as f:
            for item in samples:
                f.write(json.dumps(item, ensure_ascii=False) + "\n")
        logger.info("Wrote %d digital-human seed pairs → %s", len(samples), out_path)
        return {"samples": len(samples), "output_path": out_path}
    except Exception as e:
        logger.warning("Seed ShareGPT export failed: %s", e)
        return {"samples": 0, "output_path": "", "error": str(e)}
