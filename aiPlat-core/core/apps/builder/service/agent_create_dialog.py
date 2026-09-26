"""Conversational Agent creation dialog (clarify → draft via auto-fill)."""

from __future__ import annotations

import json
import logging
import re
from typing import Any, Dict, List, Optional


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


def _build_agent_md_preview(draft: Dict[str, Any]) -> str:
    """Minimal AGENT.md-style preview for UI."""
    name = str(draft.get("name") or draft.get("display_name") or "agent").strip()
    desc = str(draft.get("description") or "").strip()
    agent_type = str(draft.get("agent_type") or "react").strip()
    skills = draft.get("skills") if isinstance(draft.get("skills"), list) else []
    tools = draft.get("tools") if isinstance(draft.get("tools"), list) else []
    mcps = draft.get("mcp_ids") if isinstance(draft.get("mcp_ids"), list) else []
    triggers = draft.get("trigger_conditions") if isinstance(draft.get("trigger_conditions"), list) else []
    perms = draft.get("permissions") if isinstance(draft.get("permissions"), list) else []
    sop = str(draft.get("sop_text") or draft.get("sop") or "").strip() or "（待补充）"
    lines = [
        f"# {name}",
        "",
        f"> {desc}" if desc else "> （无描述）",
        "",
        f"- type: `{agent_type}`",
        f"- skills: {', '.join(str(s) for s in skills) or '（无）'}",
        f"- tools: {', '.join(str(t) for t in tools) or '（无）'}",
        f"- mcp: {', '.join(str(m) for m in mcps) or '（无）'}",
        f"- permissions: {', '.join(str(p) for p in perms) or '（无）'}",
        f"- triggers: {', '.join(str(t) for t in triggers) or '（无）'}",
        "",
        "## SOP",
        "",
        sop,
        "",
    ]
    return "\n".join(lines)


def _heuristic_agent_draft(*, description: str, display_name: str) -> Dict[str, Any]:
    """No-LLM draft when autofill times out — enough for user to confirm/edit."""
    blob = f"{display_name}\n{description}".lower()
    is_ppt = any(k in blob for k in ("ppt", "pptx", "演示文稿", "幻灯片"))
    skills = ["ppt_generation", "summarize", "knowledge_ingest_doc", "requirement_analysis"] if is_ppt else ["summarize", "requirement_analysis"]
    tools = ["file_operations"]
    if "code" in blob or is_ppt:
        tools.append("code")
    sop = (
        "1. 接收用户要点与素材，确认可访问路径；缺信息则暂停追问。\n"
        "2. 模版：优先用户上传 pptx；否则查内置模版库；皆无则暂停询问，禁止臆造。\n"
        "3. 仅基于用户信息建立要点↔素材映射，不联网、不编造。\n"
        "4. 调用 `ppt_generation` 生成 pptx。\n"
        "5. 用 `file_operations` 保存到指定目录/项目空间，并提供下载。\n"
        "6. 回报路径、页数与模版来源。"
        if is_ppt
        else "1. 澄清目标与输入。\n2. 按绑定 Skill/Tool 执行。\n3. 产出并验收。\n4. 回报结果。"
    )
    triggers = (
        ["帮我做个PPT", "生成pptx", "根据这些要点做PPT", "用这个模版生成PPT"]
        if is_ppt
        else ["开始执行", "帮我处理"]
    )
    system_prompt = (
        f"你是“{display_name or '数字员工'}”。严格按 SOP 执行；只用用户提供的信息；"
        "不联网检索、不编造；只使用已绑定的 Skill/Tool/MCP。"
    )
    return {
        "agent_type": "react",
        "config": {"system_prompt": system_prompt, "temperature": 0.2},
        "skills": skills,
        "tools": tools,
        "mcp_ids": [],
        "missing_skills": [],
        "missing_tools": [],
        "missing_mcps": [],
        "agent_ids": [],
        "memory_config": {"type": "conversation", "max_turns": 20, "persist": True},
        "sop_text": sop,
        "reasoning": "autofill timeout → heuristic draft",
        "workflow_ids": [],
        "trigger_conditions": triggers,
        "permissions": [],
    }


async def run_agent_create_dialog_turn(
    *,
    text: str,
    history: Optional[List[Dict[str, str]]] = None,
) -> Dict[str, Any]:
    """
    One turn of conversational Agent creation.

    Returns:
      next: "ask" | "draft"
      reply: assistant message
      questions: optional list
      draft: autofill payload + name/description when next=draft
      agent_md_preview: preview text when next=draft
    """
    text = str(text or "").strip()
    if not text:
        return {
            "next": "ask",
            "reply": "请先用一两句话描述这个数字员工要做什么（目标、输入、输出、是否用模版/写文件）。",
            "questions": [
                "这个 Agent 的目标是什么？",
                "用户会提供哪些输入（要点、模版、文件）？",
                "期望产出是什么（如 pptx 路径、幻灯片）？",
            ],
        }

    hist = history if isinstance(history, list) else []
    trimmed: List[Dict[str, str]] = []
    for m in hist[-16:]:
        if not isinstance(m, dict):
            continue
        role = str(m.get("role") or "").strip()
        content = str(m.get("content") or "").strip()
        if role in ("user", "assistant") and content:
            trimmed.append({"role": role, "content": content[:2000]})

    from core.apps.common.create_dialog_utils import (
        agent_create_corpus_ready,
        guess_agent_display_name,
        join_user_corpus,
    )

    corpus = join_user_corpus(text, trimmed)
    corpus_ready = agent_create_corpus_ready(corpus)

    parsed: Dict[str, Any] = {}
    if corpus_ready:
        # Skip clarify LLM when user already answered the usual gaps — avoids double LLM wait.
        guessed = guess_agent_display_name(corpus) or "未命名数字员工"
        name_hint = "ppt_maker" if "ppt" in guessed.lower() or "ppt" in corpus.lower() else guessed
        parsed = {
            "next": "draft",
            "reply": "已收集足够信息，正在生成草稿",
            "display_name": guessed,
            "name": name_hint,
            "description": corpus[:1500],
        }
    else:
        from core.api.core_facade import (  # P0-A2
            _async_prompt_resolve,
            best_model_for_purpose,
            create_selected_adapter,
            sys_llm_generate,
        )

        history_txt = "\n".join(f"{m['role']}: {m['content']}" for m in trimmed) or "(无)"
        user_prompt = await _async_prompt_resolve(
            "agent-create-dialog",
            history=history_txt,
            latest_user=text,
        )
        model_name = best_model_for_purpose("skill_creation")
        model = create_selected_adapter(model_name=model_name)
        messages = [
            {
                "role": "system",
                "content": await _async_prompt_resolve("agent-create-dialog-system-role"),
            },
            {"role": "user", "content": user_prompt},
        ]

        try:
            resp = await sys_llm_generate(model, messages)
            raw = str(resp.content if hasattr(resp, "content") else resp)
            parsed = _extract_json(raw)
        except Exception as e:
            logging.warning("agent create dialog LLM failed: %s", e, exc_info=True)
            return {
                "next": "ask",
                "reply": "暂时无法生成回复。请再补充：目标、输入、输出、约束。",
                "questions": [
                    "Agent 显示名称？",
                    "输入是什么？",
                    "输出是什么？是否需要现成模版？",
                ],
                "error": str(e)[:200],
            }

    next_state = str(parsed.get("next") or "").strip().lower()
    reply = str(parsed.get("reply") or "").strip()
    questions = parsed.get("questions") if isinstance(parsed.get("questions"), list) else []
    questions = [str(q).strip() for q in questions if str(q).strip()][:5]

    display_name = str(parsed.get("display_name") or parsed.get("name_cn") or "").strip()
    agent_name = str(parsed.get("name") or parsed.get("agent_id") or "").strip()
    description = str(parsed.get("description") or "").strip()

    # Corpus already answers the usual clarify gaps → force draft even if model re-asks.
    if corpus_ready and next_state != "draft":
        next_state = "draft"
        if not reply or "确认" in reply or "还差" in reply:
            reply = "已收集足够信息，正在生成草稿"
        questions = []
        if not description or len(description) < 40:
            description = corpus[:1500]
        if not display_name:
            display_name = guess_agent_display_name(corpus)
        if not agent_name:
            agent_name = display_name or "agent"

    ready = next_state == "draft" or (
        bool(description)
        and len(description) >= 40
        and (bool(display_name) or bool(agent_name))
    )

    if not ready:
        if not reply:
            reply = "还需要再确认几项，才能生成可靠的 Agent 草稿。"
        if not questions:
            questions = [
                "输入有哪些（要点、模版、附件）？",
                "输出形态（pptx / 幻灯片 / 路径）？",
                "有没有禁止事项（如不联网、不编造）？",
            ]
        return {"next": "ask", "reply": reply, "questions": questions}

    # Prefer full user corpus for autofill when model description is thin.
    if (not description or len(description) < 80) and len(corpus) >= 80:
        description = corpus[:1500]
    if not display_name:
        display_name = guess_agent_display_name(corpus) or agent_name or "未命名数字员工"
    if not agent_name:
        agent_name = display_name
    if not description:
        description = text if len(text) >= 40 else f"{display_name}：{text}"

    try:
        import asyncio

        from core.api.routers.workspace_agents import _do_auto_fill
        from core.schemas_agents import AgentAutoFillRequest

        fill = await asyncio.wait_for(
            _do_auto_fill(AgentAutoFillRequest(name=agent_name, description=description)),
            timeout=75.0,
        )
        draft = fill.model_dump() if hasattr(fill, "model_dump") else dict(fill)
    except Exception as e:
        logging.warning("agent create dialog autofill failed/timeout: %s", e, exc_info=True)
        # Deterministic fallback so UI is not stuck on 「思考中」forever.
        draft = _heuristic_agent_draft(description=description, display_name=display_name)
        reply = (reply or "已收集足够信息，正在生成草稿") + "（智能填充较慢，已用规则草稿，确认前请核对绑定与 SOP）"

    draft["name"] = agent_name
    draft["display_name"] = display_name
    draft["description"] = description
    if not draft.get("sop_text") and draft.get("sop"):
        draft["sop_text"] = draft.get("sop")
    if not isinstance(draft.get("permissions"), list) or not draft.get("permissions"):
        from core.api.routers.workspace_agents import _derive_agent_permissions

        draft["permissions"] = _derive_agent_permissions(
            tools=draft.get("tools") if isinstance(draft.get("tools"), list) else [],
            skills=draft.get("skills") if isinstance(draft.get("skills"), list) else [],
            mcp_ids=draft.get("mcp_ids") if isinstance(draft.get("mcp_ids"), list) else [],
            description=description,
            sop_text=str(draft.get("sop_text") or ""),
        )

    preview = _build_agent_md_preview(draft)
    final_reply = reply or "已根据对话生成 Agent 草稿，请确认绑定与 SOP 后创建。"
    missing = []
    for key, label in (
        ("missing_skills", "技能缺口"),
        ("missing_tools", "工具缺口"),
        ("missing_mcps", "MCP 缺口"),
    ):
        items = draft.get(key) if isinstance(draft.get(key), list) else []
        if items:
            missing.append(f"{label} {len(items)} 项")
    if missing:
        final_reply += "\n\n（提醒：" + "；".join(missing) + "，确认前建议核对）"

    from core.apps.common.boundary_hints import hints_for_agent_draft

    boundary_hints = hints_for_agent_draft(draft, description=description)
    if boundary_hints:
        final_reply += "\n\n边界提示：\n- " + "\n- ".join(boundary_hints)

    return {
        "next": "draft",
        "reply": final_reply,
        "questions": [],
        "draft": draft,
        "agent_md_preview": preview,
        "boundary_hints": boundary_hints,
    }
