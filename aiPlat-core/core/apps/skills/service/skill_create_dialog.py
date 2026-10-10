"""Conversational Skill creation dialog (clarify → draft via auto-fill)."""

from __future__ import annotations

import json
import logging
import re
from typing import Any, Dict, List, Optional

from core.apps.skills.service.skill_autofill import generate_skill_autofill


def _extract_json(text: str) -> Dict[str, Any]:
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


def _build_skill_md_preview(draft: Dict[str, Any]) -> str:
    """Minimal SKILL.md preview for UI (not a full YAML dumper)."""
    import yaml as _yaml

    inv = str(draft.get("invocation_mode") or "user").strip().lower()
    if inv not in ("user", "auto"):
        inv = "user"
    fm = {
        "name": draft.get("name"),
        "display_name": draft.get("display_name"),
        "description": draft.get("description"),
        "category": draft.get("category"),
        "status": "enabled",
        "invocation_mode": inv,
        "auto_trigger_allowed": bool(draft.get("auto_trigger_allowed")) if draft.get("auto_trigger_allowed") is not None else (inv == "auto"),
        "skill_kind": draft.get("skill_kind"),
        "trigger_conditions": draft.get("trigger_conditions") or [],
        "permissions": draft.get("permissions") or [],
        "input_schema": draft.get("input_schema") or {},
        "output_schema": draft.get("output_schema") or {},
    }
    cfg = draft.get("config")
    if isinstance(cfg, dict) and cfg:
        fm["config"] = cfg
    body = str(draft.get("sop") or "").strip() or "# SOP\n\n（待补充）\n"
    try:
        header = _yaml.safe_dump(fm, allow_unicode=True, sort_keys=False).strip()
    except Exception:
        header = "name: unknown"
    return f"---\n{header}\n---\n\n{body}\n"


async def run_skill_create_dialog_turn(
    *,
    text: str,
    history: Optional[List[Dict[str, str]]] = None,
) -> Dict[str, Any]:
    """
    One turn of conversational Skill creation.

    Returns:
      next: "ask" | "draft"
      reply: assistant message
      questions: optional list
      draft: full auto-fill payload when next=draft
      skill_md_preview: SKILL.md text when next=draft
    """
    text = str(text or "").strip()
    if not text:
        return {
            "next": "ask",
            "reply": "请先用一两句话描述这个 Skill 要做什么（输入、输出、是否写文件/联网）。",
            "questions": [
                "这个 Skill 的目标是什么？",
                "用户会提供哪些输入？",
                "期望产出是什么（文本 / 文件路径等）？",
            ],
        }

    hist = history if isinstance(history, list) else []
    # Keep last N turns for prompt size
    trimmed: List[Dict[str, str]] = []
    for m in hist[-16:]:
        if not isinstance(m, dict):
            continue
        role = str(m.get("role") or "").strip()
        content = str(m.get("content") or "").strip()
        if role in ("user", "assistant") and content:
            trimmed.append({"role": role, "content": content[:2000]})

    from core.api.core_facade import (  # P0-A2
        _async_prompt_resolve,
        best_model_for_purpose,
        create_selected_adapter,
        sys_llm_generate,  # noqa: context-assembly-ok
    )

    history_txt = "\n".join(f"{m['role']}: {m['content']}" for m in trimmed) or "(无)"
    user_prompt = await _async_prompt_resolve(
        "skill-create-dialog",
        history=history_txt,
        latest_user=text,
    )
    model_name = best_model_for_purpose("skill_creation")
    model = create_selected_adapter(model_name=model_name)
    messages = [
        {
            "role": "system",
            "content": await _async_prompt_resolve("skill-create-dialog-system-role"),
        },
        {"role": "user", "content": user_prompt},
    ]

    try:
        resp = await sys_llm_generate(model, messages)  # noqa: context-assembly-ok
        raw = str(resp.content if hasattr(resp, "content") else resp)
    except Exception as e:
        logging.warning("skill create dialog LLM failed: %s", e, exc_info=True)
        return {
            "next": "ask",
            "reply": "暂时无法生成回复。请再补充：目标、输入、输出、是否需要写文件。",
            "questions": [
                "Skill 显示名称？",
                "输入是什么？",
                "输出是什么？是否落盘写文件？",
            ],
            "error": str(e)[:200],
        }

    parsed = _extract_json(raw)
    next_state = str(parsed.get("next") or "").strip().lower()
    reply = str(parsed.get("reply") or "").strip()
    questions = parsed.get("questions") if isinstance(parsed.get("questions"), list) else []
    questions = [str(q).strip() for q in questions if str(q).strip()][:5]

    # Heuristic: enough info → draft even if model forgot next=draft
    display_name = str(parsed.get("display_name") or parsed.get("name_cn") or "").strip()
    skill_name = str(parsed.get("name") or parsed.get("skill_id") or "").strip()
    description = str(parsed.get("description") or "").strip()

    ready = next_state == "draft" or (
        bool(description)
        and len(description) >= 40
        and (bool(display_name) or bool(skill_name))
    )

    if not ready:
        if not reply:
            reply = "还需要再确认几项，才能生成可靠的 Skill 草稿。"
        if not questions:
            questions = [
                "输入有哪些必填字段？",
                "输出是文本还是文件（路径/格式）？",
                "有没有禁止事项（如不联网、不编造）？",
            ]
        return {"next": "ask", "reply": reply, "questions": questions}

    # Build name/description for auto-fill
    if not display_name:
        display_name = skill_name or "未命名技能"
    if not skill_name:
        # leave empty — autofill can use display name as seed
        skill_name = display_name
    if not description:
        # fall back to conversation summary
        description = text if len(text) >= 40 else f"{display_name}：{text}"

    try:
        draft = await generate_skill_autofill(name=skill_name, description=description)
    except Exception as e:
        logging.warning("skill create dialog autofill failed: %s", e, exc_info=True)
        return {
            "next": "ask",
            "reply": f"草稿生成失败：{str(e)[:120]}。请再补充描述后重试。",
            "questions": ["请用一段话重述：输入 / 处理 / 输出 / 约束"],
            "error": str(e)[:200],
        }

    # Prefer dialog-provided display name when user-facing Chinese
    if display_name and re.search(r"[\u4e00-\u9fff]", display_name):
        draft["display_name"] = display_name
    # Keep richer description (dialog summary often already has I/O constraints)
    if description and len(description) >= len(str(draft.get("description") or "")):
        draft["description"] = description
        # Re-run enrich-side effects after description override (file-write → executable)
        from core.apps.skills.service.skill_autofill import _enrich_draft

        draft = _enrich_draft(draft, seed_name=str(draft.get("name") or skill_name), seed_desc=description)

    gaps = draft.pop("autofill_gaps", None) if isinstance(draft.get("autofill_gaps"), list) else None
    preview = _build_skill_md_preview(draft)
    final_reply = reply or "已根据对话生成 Skill 草稿，请确认后创建。"
    if gaps:
        final_reply += "\n\n（提醒：以下字段仍偏弱，确认前建议核对：" + "；".join(str(g) for g in gaps[:4]) + "）"

    from core.apps.common.boundary_hints import hints_for_skill_draft

    boundary_hints = hints_for_skill_draft(draft, description=description)
    if boundary_hints:
        final_reply += "\n\n边界提示：\n- " + "\n- ".join(boundary_hints)

    return {
        "next": "draft",
        "reply": final_reply,
        "questions": [],
        "draft": draft,
        "skill_md_preview": preview,
        "autofill_gaps": gaps or [],
        "boundary_hints": boundary_hints,
    }
