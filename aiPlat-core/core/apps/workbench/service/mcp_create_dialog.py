"""Conversational MCP creation: clarify → draft via mcp auto-fill."""

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


async def run_mcp_create_dialog_turn(
    *,
    text: str,
    history: Optional[List[Dict[str, str]]] = None,
) -> Dict[str, Any]:
    text = str(text or "").strip()
    if not text:
        return {
            "next": "ask",
            "reply": "请先描述要接入的 MCP：目标能力、传输方式（stdio/sse/http）、服务地址或启动命令。",
            "questions": [
                "这个 MCP 提供什么能力？",
                "用 stdio、sse 还是 http？",
                "URL 或启动命令是什么？",
            ],
        }

    trimmed = trim_history(history)
    from core.api.core_facade import (
        _async_prompt_resolve,
        best_model_for_purpose,
        create_selected_adapter,
        sys_llm_generate,
    )

    user_prompt = await _async_prompt_resolve(
        "mcp-create-dialog",
        history=history_as_text(trimmed),
        latest_user=text,
    )
    model = create_selected_adapter(model_name=best_model_for_purpose("tool_creation"))
    messages = [
        {
            "role": "system",
            "content": await _async_prompt_resolve("mcp-create-dialog-system-role"),
        },
        {"role": "user", "content": user_prompt},
    ]

    try:
        resp = await sys_llm_generate(model, messages)
        raw = str(resp.content if hasattr(resp, "content") else resp)
    except Exception as e:
        logging.warning("mcp create dialog LLM failed: %s", e, exc_info=True)
        return {
            "next": "ask",
            "reply": "暂时无法生成回复。请再补充：能力、传输、地址/命令。",
            "questions": ["MCP 名称？", "transport？", "url 或 command？"],
            "error": str(e)[:200],
        }

    info = parse_clarify_payload(extract_json_object(raw))
    reply = info["reply"]
    questions = info["questions"]
    display_name = info["display_name"]
    server_name = info["name"]
    description = info["description"]

    if not is_draft_ready(
        next_state=info["next"],
        description=description,
        display_name=display_name,
        name=server_name,
    ):
        return {
            "next": "ask",
            "reply": reply or "还需要再确认几项，才能生成 MCP 草稿。",
            "questions": questions
            or [
                "传输方式（stdio / sse / http）？",
                "服务 URL 或启动 command？",
                "需要限制哪些 allowed_tools？",
            ],
        }

    if not display_name:
        display_name = server_name or "未命名 MCP"
    if not server_name:
        server_name = display_name
    if re.search(r"[\u4e00-\u9fff]", server_name) and not re.fullmatch(
        r"[a-zA-Z][a-zA-Z0-9_-]{1,}", server_name
    ):
        slug = re.sub(r"[^a-zA-Z0-9_-]+", "-", server_name)
        if not re.match(r"^[a-zA-Z]", slug or ""):
            slug = "mcp-" + (slug or "server")
        server_name = slug.strip("-_")[:48] or "mcp-server"
    if not description:
        description = text if len(text) >= 40 else f"{display_name}：{text}"

    try:
        from core.api.routers.mcp_admin import mcp_auto_fill

        fill = await mcp_auto_fill({"name": server_name, "description": description})
        draft = dict(fill) if isinstance(fill, dict) else {}
    except Exception as e:
        logging.warning("mcp create dialog autofill failed: %s", e, exc_info=True)
        return {
            "next": "ask",
            "reply": f"草稿生成失败：{str(e)[:120]}。请再补充描述后重试。",
            "questions": ["请重述：能力 / transport / 地址或命令"],
            "error": str(e)[:200],
        }

    if draft.get("error"):
        return {
            "next": "ask",
            "reply": f"草稿生成失败：{draft.get('error')}。请再补充描述后重试。",
            "questions": ["请补充 transport 与连接信息"],
        }

    draft["name"] = server_name
    draft["display_name"] = display_name
    draft["description"] = description
    meta = draft.get("metadata") if isinstance(draft.get("metadata"), dict) else {}
    if description and not meta.get("description"):
        meta = {**meta, "description": description}
        draft["metadata"] = meta

    preview_lines = [
        f"# {display_name} (`{server_name}`)",
        "",
        f"> {description}",
        "",
        f"- transport: `{draft.get('transport') or '-'}`",
        f"- url: `{draft.get('url') or '-'}`",
        f"- command: `{draft.get('command') or '-'}`",
        f"- allowed_tools: {', '.join(str(t) for t in (draft.get('allowed_tools') or [])[:12]) or '（空）'}",
        "",
    ]
    final_reply = reply or "已根据对话生成 MCP 草稿，请确认连接配置后创建。"

    from core.apps.common.boundary_hints import hints_for_mcp_draft

    boundary_hints = hints_for_mcp_draft(draft, description=description)
    if boundary_hints:
        final_reply += "\n\n边界提示：\n- " + "\n- ".join(boundary_hints)

    return {
        "next": "draft",
        "reply": final_reply,
        "questions": [],
        "draft": draft,
        "mcp_preview": "\n".join(preview_lines),
        "boundary_hints": boundary_hints,
    }
