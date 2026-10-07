"""Conversational Tool creation: clarify → draft via tool auto-fill."""

from __future__ import annotations

import logging
import re
from typing import Any, Dict, List, Optional

from core.apps.common.create_dialog_utils import (
    extract_json_object,
    history_as_text,
    is_draft_ready,
    parse_clarify_payload,
    trim_history,
)


async def run_tool_create_dialog_turn(
    *,
    text: str,
    history: Optional[List[Dict[str, str]]] = None,
) -> Dict[str, Any]:
    text = str(text or "").strip()
    if not text:
        return {
            "next": "ask",
            "reply": "请先用一两句话描述这个 Tool 要做什么（输入参数、输出结果、是否读写文件/联网）。",
            "questions": [
                "工具目标是什么？",
                "需要哪些输入参数？",
                "期望返回什么？",
            ],
        }

    from core.apps.common.upload_create_clarify import maybe_upload_tool_clarify

    upload_gate = maybe_upload_tool_clarify(text=text, history=history)
    if upload_gate and upload_gate.get("next") == "ask":
        return {
            "next": "ask",
            "reply": str(upload_gate.get("reply") or ""),
            "questions": list(upload_gate.get("questions") or []),
        }

    reply = ""
    questions: List[str] = []
    display_name = ""
    tool_name = ""
    description = ""

    if upload_gate and upload_gate.get("next") == "draft":
        display_name = str(upload_gate.get("display_name") or "")
        tool_name = str(upload_gate.get("name") or "")
        description = str(upload_gate.get("description") or "")
        reply = "已按你选的云厂商和桶规则生成上传 Tool 草稿，请确认代码后创建。"
    else:
        trimmed = trim_history(history)
        from core.api.core_facade import (
            _async_prompt_resolve,
            best_model_for_purpose,
            create_selected_adapter,
            sys_llm_generate,
        )

        user_prompt = await _async_prompt_resolve(
            "tool-create-dialog",
            history=history_as_text(trimmed),
            latest_user=text,
        )
        model = create_selected_adapter(model_name=best_model_for_purpose("tool_creation"))
        messages = [
            {
                "role": "system",
                "content": await _async_prompt_resolve("tool-create-dialog-system-role"),
            },
            {"role": "user", "content": user_prompt},
        ]

        try:
            resp = await sys_llm_generate(model, messages)
            raw = str(resp.content if hasattr(resp, "content") else resp)
        except Exception as e:
            logging.warning("tool create dialog LLM failed: %s", e, exc_info=True)
            return {
                "next": "ask",
                "reply": "暂时无法生成回复。请再补充：目标、参数、输出。",
                "questions": ["工具名称？", "输入参数？", "输出是什么？"],
                "error": str(e)[:200],
            }

        info = parse_clarify_payload(extract_json_object(raw))
        reply = info["reply"]
        questions = info["questions"]
        display_name = info["display_name"]
        tool_name = info["name"]
        description = info["description"]

        if not is_draft_ready(
            next_state=info["next"],
            description=description,
            display_name=display_name,
            name=tool_name,
        ):
            return {
                "next": "ask",
                "reply": reply or "还需要再确认几项，才能生成 Tool 草稿。",
                "questions": questions
                or [
                    "输入参数有哪些（名称/类型）？",
                    "输出结构是什么？",
                    "是否需要读写文件或联网？",
                ],
            }

    if not display_name:
        display_name = tool_name or "未命名工具"
    if not tool_name:
        tool_name = display_name
    if re.search(r"[\u4e00-\u9fff]", tool_name) and not re.fullmatch(
        r"[a-z][a-z0-9_]{2,}", tool_name
    ):
        slug = re.sub(r"[^a-z0-9_]+", "_", tool_name.lower())
        if not re.match(r"^[a-z]", slug or ""):
            slug = "tool_" + (slug or "custom")
        tool_name = slug.strip("_")[:48] or "custom_tool"
    if not description:
        description = text if len(text) >= 40 else f"{display_name}：{text}"

    try:
        from core.api.routers.tools import tool_auto_fill

        fill = await tool_auto_fill({"name": tool_name, "description": description})
        draft = dict(fill) if isinstance(fill, dict) else {}
    except Exception as e:
        logging.warning("tool create dialog autofill failed: %s", e, exc_info=True)
        return {
            "next": "ask",
            "reply": f"草稿生成失败：{str(e)[:120]}。请再补充描述后重试。",
            "questions": ["请用一段话重述：输入 / 处理 / 输出"],
            "error": str(e)[:200],
        }

    if draft.get("error") and not draft.get("code"):
        return {
            "next": "ask",
            "reply": f"草稿生成失败：{draft.get('error')}。请再补充描述后重试。",
            "questions": ["请补充具体输入输出与约束"],
        }

    draft["name"] = tool_name
    draft["display_name"] = display_name
    draft["description"] = description or draft.get("description") or ""
    code = str(draft.get("code") or "")
    preview = (
        f"# {display_name} (`{tool_name}`)\n\n"
        f"> {draft['description']}\n\n"
        f"- category: `{draft.get('category') or 'general'}`\n\n"
        f"```python\n{code[:4000]}\n```\n"
    )
    final_reply = reply or "已根据对话生成 Tool 草稿，请确认代码后创建。"
    if draft.get("warning"):
        final_reply += f"\n\n（提醒：{draft['warning']}）"

    from core.apps.common.boundary_hints import hints_for_tool_draft

    boundary_hints = hints_for_tool_draft(draft, description=description)
    if boundary_hints:
        final_reply += "\n\n边界提示：\n- " + "\n- ".join(boundary_hints)

    return {
        "next": "draft",
        "reply": final_reply,
        "questions": [],
        "draft": draft,
        "tool_code_preview": preview,
        "boundary_hints": boundary_hints,
    }
