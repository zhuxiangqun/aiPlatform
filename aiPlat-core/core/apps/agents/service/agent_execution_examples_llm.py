"""LLM-assisted execution test-case generation for workspace Agents (optional).

Heuristic role/skill samples remain the default path; this module is opt-in via UI.
"""

from __future__ import annotations

import json
import logging
from typing import Any, Dict, List, Optional


async def generate_agent_execution_examples_llm(
    *,
    agent_id: str,
    agent_name: str = "",
    description: str = "",
    skill_ids: Optional[List[str]] = None,
    tool_ids: Optional[List[str]] = None,
    input_schema: Optional[Dict[str, Any]] = None,
    refine_hint: str = "",
) -> Dict[str, Any]:
    """Generate 2–4 realistic smoke test cases for an Agent via LLM.

    Returns:
      {examples: [{title, content}], model: str, source: "llm"|heuristic_fallback, warning?}
    """
    agent_id = str(agent_id or "").strip()
    if not agent_id:
        raise ValueError("agent_id is required")

    try:
        from core.apps.agents.prompts import register_agents_prompts

        register_agents_prompts()
    except Exception:
        logging.warning("agent execution-examples prompts not registered", exc_info=True)

    label = (agent_name or agent_id).strip()
    skills = [str(s) for s in (skill_ids or []) if str(s).strip()]
    tools = [str(t) for t in (tool_ids or []) if str(t).strip()]
    schema = input_schema if isinstance(input_schema, dict) else {}
    schema_json = json.dumps(schema, ensure_ascii=False, indent=2)[:4000]
    hint = str(refine_hint or "").strip()

    from core.api.core_facade import (  # P0-A2: via CoreFacade
        _async_prompt_resolve,
        best_model_for_purpose,
        create_selected_adapter,
        sys_llm_generate,
    )
    from core.apps.skills.service.skill_execution_examples_llm import _extract_json_array

    prompt = await _async_prompt_resolve(
        "agent-execution-examples",
        agent_id=agent_id,
        agent_name=label,
        description=(description or "")[:1500] or "(无描述)",
        skills=", ".join(skills) if skills else "(无)",
        tools=", ".join(tools) if tools else "(无)",
        input_schema_json=schema_json or "{}",
        refine_hint=hint or "(无)",
    )
    model_name = best_model_for_purpose("clarify")
    model = create_selected_adapter(model_name=model_name)
    messages = [
        {
            "role": "system",
            "content": await _async_prompt_resolve("agent-execution-examples-system-role"),
        },
        {"role": "user", "content": prompt},
    ]
    resp = await sys_llm_generate(
        model,
        messages,
        trace_context={"skip_claude_md": True, "source": "agent_execution_examples"},
    )
    text = str(resp.content if hasattr(resp, "content") else resp)
    examples = _extract_json_array(text)
    if not examples:
        from core.management.execution_examples import build_agent_task_examples

        examples = build_agent_task_examples(
            display_name=label,
            description=description or "",
            skill_ids=skills,
            tool_ids=tools,
        )
        return {
            "examples": examples,
            "model": model_name,
            "source": "heuristic_fallback",
            "warning": "LLM 未返回可用 JSON，已回退到角色/技能启发式样例",
        }
    return {"examples": examples, "model": model_name, "source": "llm"}
