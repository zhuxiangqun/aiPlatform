"""Conversational Team assembly: clarify → stage draft from agent catalog."""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from core.apps.common.create_dialog_utils import (
    extract_json_object,
    history_as_text,
    is_draft_ready,
    parse_clarify_payload,
    trim_history,
)


def _catalog_text(agents: List[Dict[str, Any]], limit: int = 80) -> str:
    lines = []
    for a in agents[:limit]:
        aid = str(a.get("agent_id") or a.get("id") or a.get("name") or "").strip()
        if not aid:
            continue
        name = str(a.get("display_name") or a.get("name") or aid)
        cat = str(a.get("category") or "")
        desc = str(a.get("description") or "")[:60]
        phase = str(a.get("phase") or "")
        lines.append(f"- {aid}: {name} [{cat}/{phase}] — {desc}")
    return "\n".join(lines) or "(无可用 Agent)"


def _resolve_stages(
    suggested: List[Any],
    agents: List[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    by_id: Dict[str, Dict[str, Any]] = {}
    for a in agents:
        aid = str(a.get("agent_id") or a.get("id") or a.get("name") or "").strip()
        if aid:
            by_id[aid] = a
            by_id[aid.lower()] = a
            dn = str(a.get("display_name") or "").strip()
            if dn:
                by_id[dn] = a
                by_id[dn.lower()] = a

    stages: List[Dict[str, Any]] = []
    for i, item in enumerate(suggested if isinstance(suggested, list) else []):
        if isinstance(item, str):
            agent_id = item.strip()
            phase = ""
            hitl = False
        elif isinstance(item, dict):
            agent_id = str(item.get("agent_id") or item.get("id") or "").strip()
            phase = str(item.get("phase") or "").strip()
            hitl = bool(item.get("hitl"))
        else:
            continue
        if not agent_id:
            continue
        meta = by_id.get(agent_id) or by_id.get(agent_id.lower())
        if not meta:
            # soft skip unknown ids
            continue
        resolved_id = str(meta.get("agent_id") or meta.get("id") or agent_id)
        name = str(meta.get("display_name") or meta.get("name") or resolved_id)
        category = str(meta.get("category") or "")
        tags = meta.get("tags") if isinstance(meta.get("tags"), list) else []
        out = str(meta.get("output_artifact") or f"stage_{i}_output")
        stages.append(
            {
                "id": f"stage_{i}_{resolved_id}",
                "agent_id": resolved_id,
                "agent_name": name,
                "category": category,
                "tags": tags,
                "phase": phase or str(meta.get("phase") or ""),
                "order": i,
                "hitl": hitl,
                "hitl_phase": str(meta.get("hitl_phase") or ""),
                "retry_target_id": "",
                "input_artifacts": [],
                "output_artifact": out,
                "phase_description": str(meta.get("description") or "")[:200],
            }
        )
    # wire input_artifacts sequentially
    for i, st in enumerate(stages):
        if i == 0:
            st["input_artifacts"] = []
        else:
            prev = stages[i - 1].get("output_artifact")
            st["input_artifacts"] = [prev] if prev else []
    return stages


async def run_team_create_dialog_turn(
    *,
    text: str,
    history: Optional[List[Dict[str, str]]] = None,
    agents: Optional[List[Dict[str, Any]]] = None,
) -> Dict[str, Any]:
    """
    Clarify team goal → draft stages from available agents.
    Does not persist; UI applies draft into canvas then user saves.
    """
    text = str(text or "").strip()
    agent_list = [a for a in (agents or []) if isinstance(a, dict)]
    if not text:
        return {
            "next": "ask",
            "reply": "请描述这个团队要完成什么流水线（阶段顺序、关键角色、是否需要人工审批）。",
            "questions": [
                "团队目标是什么？",
                "大概几步？先后顺序？",
                "哪些环节需要人工确认（HITL）？",
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
        "team-create-dialog",
        history=history_as_text(trimmed),
        latest_user=text,
        agent_catalog=_catalog_text(agent_list),
    )
    model = create_selected_adapter(model_name=best_model_for_purpose("skill_creation"))
    messages = [
        {
            "role": "system",
            "content": await _async_prompt_resolve("team-create-dialog-system-role"),
        },
        {"role": "user", "content": user_prompt},
    ]

    try:
        resp = await sys_llm_generate(model, messages)
        raw = str(resp.content if hasattr(resp, "content") else resp)
    except Exception as e:
        logging.warning("team create dialog LLM failed: %s", e, exc_info=True)
        return {
            "next": "ask",
            "reply": "暂时无法生成回复。请再补充：目标、阶段、角色。",
            "questions": ["团队名称？", "需要哪些阶段？", "是否 HITL？"],
            "error": str(e)[:200],
        }

    parsed = extract_json_object(raw)
    info = parse_clarify_payload(parsed)
    reply = info["reply"]
    questions = info["questions"]
    display_name = info["display_name"] or str(parsed.get("team_name") or "").strip()
    description = info["description"]
    suggested = parsed.get("stages") if isinstance(parsed.get("stages"), list) else []

    ready = is_draft_ready(
        next_state=info["next"],
        description=description,
        display_name=display_name,
        name=display_name,
        min_desc=20,
    ) and (info["next"] == "draft" or len(suggested) > 0)

    if not ready:
        return {
            "next": "ask",
            "reply": reply or "还需要再确认几项，才能生成团队阶段草稿。",
            "questions": questions
            or [
                "需要哪些角色（按顺序）？",
                "是否有人工审批节点？",
                "最终产出物是什么？",
            ],
        }

    if not display_name:
        display_name = "未命名团队"
    if not description:
        description = text if len(text) >= 20 else f"{display_name}：{text}"

    stages = _resolve_stages(suggested, agent_list)
    if not stages and agent_list:
        # fallback: take first 3 catalog agents if model returned unmatched ids
        stages = _resolve_stages(
            [
                {
                    "agent_id": str(a.get("agent_id") or a.get("id") or ""),
                    "phase": str(a.get("phase") or ""),
                }
                for a in agent_list[:3]
            ],
            agent_list,
        )

    if not stages:
        return {
            "next": "ask",
            "reply": "未能匹配到可用 Agent。请点名已有 Agent（见目录），或先去应用库创建 Agent。",
            "questions": ["希望用哪些已有 Agent（按顺序说 id 或显示名）？"],
        }

    draft = {
        "name": display_name,
        "display_name": display_name,
        "description": description,
        "stages": stages,
    }
    preview = "\n".join(
        [
            f"# {display_name}",
            "",
            f"> {description}",
            "",
            "## 阶段",
            "",
            *[
                f"{i + 1}. `{s['agent_name']}` ({s['agent_id']})"
                + (f" · phase={s['phase']}" if s.get("phase") else "")
                + (" · HITL" if s.get("hitl") else "")
                for i, s in enumerate(stages)
            ],
            "",
        ]
    )
    return {
        "next": "draft",
        "reply": reply or "已生成团队阶段草稿。确认后将写入画布，你仍可拖拽调整后再保存。",
        "questions": [],
        "draft": draft,
        "team_preview": preview,
    }
