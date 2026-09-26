"""Shared helpers for conversational create-dialogs (Skill/Agent/Tool/MCP/Team)."""

from __future__ import annotations

import json
import re
from typing import Any, Dict, List, Optional


def extract_json_object(text: str) -> Dict[str, Any]:
    raw = str(text or "").strip()
    if not raw:
        return {}
    try:
        obj = json.loads(raw)
        return obj if isinstance(obj, dict) else {}
    except Exception:  # noqa: cleanup-best-effort
        pass
    m = re.search(r"\{[\s\S]*\}", raw)
    if not m:
        return {}
    try:
        obj = json.loads(m.group(0))
        return obj if isinstance(obj, dict) else {}
    except Exception:
        return {}


def trim_history(
    history: Optional[List[Dict[str, str]]],
    *,
    limit: int = 16,
    max_chars: int = 2000,
) -> List[Dict[str, str]]:
    hist = history if isinstance(history, list) else []
    trimmed: List[Dict[str, str]] = []
    for m in hist[-limit:]:
        if not isinstance(m, dict):
            continue
        role = str(m.get("role") or "").strip()
        content = str(m.get("content") or "").strip()
        if role in ("user", "assistant") and content:
            trimmed.append({"role": role, "content": content[:max_chars]})
    return trimmed


def history_as_text(trimmed: List[Dict[str, str]]) -> str:
    return "\n".join(f"{m['role']}: {m['content']}" for m in trimmed) or "(无)"


def parse_clarify_payload(parsed: Dict[str, Any]) -> Dict[str, Any]:
    """Normalize clarify LLM JSON into next/reply/questions/name fields."""
    next_state = str(parsed.get("next") or "").strip().lower()
    reply = str(parsed.get("reply") or "").strip()
    questions = parsed.get("questions") if isinstance(parsed.get("questions"), list) else []
    questions = [str(q).strip() for q in questions if str(q).strip()][:5]
    display_name = str(
        parsed.get("display_name") or parsed.get("name_cn") or parsed.get("name") or ""
    ).strip()
    asset_id = str(
        parsed.get("name")
        or parsed.get("skill_id")
        or parsed.get("agent_id")
        or parsed.get("tool_id")
        or parsed.get("server_name")
        or ""
    ).strip()
    description = str(parsed.get("description") or "").strip()
    return {
        "next": next_state,
        "reply": reply,
        "questions": questions,
        "display_name": display_name,
        "name": asset_id or display_name,
        "description": description,
    }


def is_draft_ready(
    *,
    next_state: str,
    description: str,
    display_name: str,
    name: str,
    min_desc: int = 40,
) -> bool:
    return next_state == "draft" or (
        bool(description)
        and len(description) >= min_desc
        and (bool(display_name) or bool(name))
    )


def join_user_corpus(latest: str, history: Optional[List[Dict[str, str]]] = None) -> str:
    """Concatenate user turns + latest for readiness heuristics."""
    parts: List[str] = []
    for m in trim_history(history):
        if m.get("role") == "user":
            parts.append(m["content"])
    latest = str(latest or "").strip()
    if latest:
        parts.append(latest)
    return "\n".join(parts).strip()


def agent_create_corpus_ready(corpus: str) -> bool:
    """True when user text already has goal + I/O + enough execution policy to draft.

    Prevents clarify LLM from re-asking questions already answered in the same
    message or prior turns (e.g. 停下来问用户 / 保存下载 / 自动判断).
    """
    text = str(corpus or "").strip()
    if len(text) < 40:
        return False
    low = text.lower()

    has_goal = any(k in text for k in ("数字员工", "Agent", "agent", "制作", "生成", "助手"))
    has_ppt = "ppt" in low or "演示文稿" in text or "幻灯片" in text
    has_input = any(k in text for k in ("要点", "素材", "模版", "模板", "输入", "文档", "图片"))
    has_output = "pptx" in low or "ppt" in low or "输出" in text or "下载" in text
    has_constraint = any(
        k in text for k in ("不编造", "不联网", "只用用户", "严格只用", "不补充外部")
    )

    # Execution policies commonly clarified — treat as answered if present.
    has_template_policy = any(
        k in text
        for k in (
            "停下来",
            "询问用户",
            "问用户",
            "向用户询问",
            "默认模版",
            "无可用模版",
            "没有可用模版",
        )
    )
    has_save_policy = any(
        k in text for k in ("保存", "下载", "项目空间", "指定目录", "落盘", "写盘")
    )
    has_mapping_policy = any(
        k in text for k in ("自动判断", "对应关系", "用户确认", "素材对应")
    )

    if not (has_goal and (has_ppt or (has_input and has_output))):
        return False

    # Explicit answers to the usual 3 clarify questions (can be short follow-up turn)
    if has_template_policy and has_save_policy and has_mapping_policy:
        return True
    # Rich single-shot with constraints + save path → draft
    if has_constraint and has_save_policy and len(text) >= 120:
        return True
    # Long enough + I/O + constraint even without all three labels
    if has_constraint and has_input and has_output and len(text) >= 200:
        return True
    return False


def guess_agent_display_name(corpus: str) -> str:
    text = str(corpus or "")
    if any(k in text.lower() for k in ("ppt", "pptx")) or "演示文稿" in text:
        if "数字员工" in text or "制作" in text:
            return "PPT制作数字员工"
        return "PPT生成助手"
    return ""

