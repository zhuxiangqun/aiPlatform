"""LLM-assisted execution test-case generation for workspace Skills (optional).

Heuristic Schema samples remain the default path; this module is opt-in via UI.
"""

from __future__ import annotations

import json
import logging
import re
from typing import Any, Dict, List, Optional


def _extract_json_array(text: str) -> List[Dict[str, str]]:
    raw = str(text or "").strip()
    if not raw:
        return []
    fence = re.search(r"```(?:json)?\s*([\s\S]*?)```", raw, re.I)
    if fence:
        raw = fence.group(1).strip()
    # Prefer first JSON array
    start = raw.find("[")
    end = raw.rfind("]")
    if start < 0 or end <= start:
        return []
    try:
        data = json.loads(raw[start : end + 1])
    except Exception as e:
        logging.warning("execution examples LLM JSON parse failed: %s", e, exc_info=True)
        return []
    if not isinstance(data, list):
        return []
    out: List[Dict[str, str]] = []
    for item in data:
        if not isinstance(item, dict):
            continue
        title = str(item.get("title") or "").strip()
        content = item.get("content")
        if content is None:
            continue
        if isinstance(content, (dict, list)):
            content = json.dumps(content, ensure_ascii=False, indent=2)
        else:
            content = str(content).strip()
        if not title or not content:
            continue
        # Reject legacy one-liner placeholders
        if "请按本能力说明完成一次冒烟测试" in content and len(content) < 80:
            continue
        out.append({"title": title[:80], "content": content[:8000]})
        if len(out) >= 5:
            break
    return out


async def generate_skill_execution_examples_llm(
    *,
    skill_id: str,
    skill_name: str = "",
    description: str = "",
    input_schema: Optional[Dict[str, Any]] = None,
    refine_hint: str = "",
) -> Dict[str, Any]:
    """Generate 2–4 realistic smoke test cases for a Skill via LLM.

    Returns:
      {examples: [{title, content}], model: str, source: "llm"}
    """
    skill_id = str(skill_id or "").strip()
    if not skill_id:
        raise ValueError("skill_id is required")

    label = (skill_name or skill_id).strip()
    schema = input_schema if isinstance(input_schema, dict) else {}
    schema_json = json.dumps(schema, ensure_ascii=False, indent=2)[:4000]
    hint = str(refine_hint or "").strip()

    from core.api.core_facade import (  # P0-A2: via CoreFacade
        _async_prompt_resolve,
        best_model_for_purpose,
        create_selected_adapter,
        sys_llm_generate,
    )

    prompt = await _async_prompt_resolve(
        "skill-execution-examples",
        skill_id=skill_id,
        skill_name=label,
        description=(description or "")[:1500] or "(无描述)",
        input_schema_json=schema_json or "{}",
        refine_hint=hint or "(无)",
    )
    model_name = best_model_for_purpose("clarify")  # lighter than skill_creation
    model = create_selected_adapter(model_name=model_name)
    messages = [
        {
            "role": "system",
            "content": await _async_prompt_resolve("skill-execution-examples-system-role"),
        },
        {"role": "user", "content": prompt},
    ]
    resp = await sys_llm_generate(
        model,
        messages,
        trace_context={"skip_claude_md": True, "source": "skill_execution_examples"},
    )
    text = str(resp.content if hasattr(resp, "content") else resp)
    examples = _extract_json_array(text)
    if not examples:
        # Fallback: keep schema heuristics rather than empty
        from core.management.execution_examples import build_examples_from_input_schema

        examples = build_examples_from_input_schema(
            schema,
            skill_id=skill_id,
            skill_name=label,
        )
        return {
            "examples": examples,
            "model": model_name,
            "source": "heuristic_fallback",
            "warning": "LLM 未返回可用 JSON，已回退到 Schema 启发式样例",
        }
    return {"examples": examples, "model": model_name, "source": "llm"}
