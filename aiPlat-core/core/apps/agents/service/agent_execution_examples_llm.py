"""LLM-assisted execution test-case generation for workspace Agents (optional).

Heuristic role/skill samples remain the default path; this module is opt-in via UI.
"""

from __future__ import annotations

import json
import logging
import re
from typing import Any, Dict, List, Optional


def _coding_llm_examples_need_fallback(
    examples: List[Dict[str, str]],
    skill_ids: List[str],
    *,
    agent_id: str = "",
    description: str = "",
) -> bool:
    """True when LLM chips would send a coding/scaffold Agent off its SOP."""
    skills = {str(s).strip().lower().replace("-", "_") for s in (skill_ids or [])}
    hint = f"{agent_id} {description}".lower()
    is_coding = bool(skills & {"code_generation", "file_operations"})
    is_scaffold = bool(
        re.search(r"scaffold|脚手架", hint)
        or "code_generation" in skills
        and re.search(r"脚手架|vite\s*\+\s*fastapi|可启动", hint)
    )
    if not is_coding and not is_scaffold:
        return False
    blob = "\n".join(str((e or {}).get("content") or "") for e in examples)
    if re.search(
        r"(?i)"
        r"请先列出你计划创建的文件|"
        r"再(?:用|执行)\s*`?file_operations|"
        r"file_operations`?\s*落盘|"
        r"必须落盘|"
        r"先(?:对|做).{0,12}澄清|"
        r"不要自行假设后直接落盘|"
        r"标注为待确认[，,]?\s*不要自行假设|"
        r"第一步只输出澄清|"
        r"若用户未回答关键问题",
        blob,
    ):
        return True
    if is_scaffold and re.search(
        r"(?i)待办|/api/todos|标记完成|业务 CRUD|增删改查",
        blob,
    ):
        return True
    return False


def _executor_llm_examples_need_fallback(
    examples: List[Dict[str, str]],
    skill_ids: List[str],
    *,
    agent_id: str = "",
    description: str = "",
) -> bool:
    """True when LLM chips ask the runner to write a product brief instead of execute cases."""
    skills = {str(s).strip().lower().replace("-", "_") for s in (skill_ids or [])}
    hint = f"{agent_id} {description}".lower()
    is_executor = bool(
        "test_executor" in skills
        or re.search(r"测试执行器|test_executor", hint)
    )
    if not is_executor:
        return False
    blob = "\n".join(str((e or {}).get("content") or "") for e in examples)
    has_cases = bool(
        re.search(r'"test_cases"\s*:\s*\[', blob)
        or re.search(r'"test_questions"\s*:\s*\[', blob)
        or "SMK-001" in blob
    )
    looks_product_brief = bool(
        re.search(r"复杂冒烟｜", blob)
        or (
            "钉钉" in blob
            and ("不上公网" in blob or "不能传到公网" in blob)
            and "本次不做" in blob
        )
    )
    if looks_product_brief and not has_cases:
        return True
    if not has_cases:
        return True
    return False


async def generate_agent_execution_examples_llm(
    *,
    agent_id: str,
    agent_name: str = "",
    description: str = "",
    skill_ids: Optional[List[str]] = None,
    tool_ids: Optional[List[str]] = None,
    input_schema: Optional[Dict[str, Any]] = None,
    refine_hint: str = "",
    sop_excerpt: str = "",
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
    from core.management.execution_examples import accept_llm_execution_examples

    prompt = await _async_prompt_resolve(
        "agent-execution-examples",
        agent_id=agent_id,
        agent_name=label,
        description=(description or "")[:1500] or "(无描述)",
        skills=", ".join(skills) if skills else "(无)",
        tools=", ".join(tools) if tools else "(无)",
        input_schema_json=schema_json or "{}",
        refine_hint=hint or "(无)",
        sop_excerpt=(str(sop_excerpt or "").strip() or "(无 SOP)")[:2500],
    )
    # Not "clarify": that purpose biases 追问/待确认 and wrecks coding/scaffold smokes.
    model_name = best_model_for_purpose("skill_execution")
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
    examples = accept_llm_execution_examples(
        _extract_json_array(text),
        schema if schema else None,
        skill_hint=f"{agent_id} {label}",
    )
    coding_clash = _coding_llm_examples_need_fallback(
        examples,
        skills,
        agent_id=agent_id,
        description=description or "",
    )
    executor_clash = _executor_llm_examples_need_fallback(
        examples,
        skills,
        agent_id=agent_id,
        description=description or "",
    )
    clash = coding_clash or executor_clash
    if clash or not examples:
        from core.management.execution_examples import build_agent_task_examples

        examples = build_agent_task_examples(
            display_name=label,
            description=description or "",
            skill_ids=skills,
            tool_ids=tools,
        )
        warn = (
            "LLM 用例与编码交付冲突（澄清/先落盘），已回退到角色启发式样例"
            if coding_clash
            else (
                "LLM 用例不是待执行的 test_cases，已回退到测试执行器样例"
                if executor_clash
                else "LLM 用例未通过 schema 门禁或过薄，已回退到角色/技能启发式样例（未覆盖已有落盘）"
            )
        )
        return {
            "examples": examples,
            "model": model_name,
            "source": "heuristic_fallback",
            "warning": warn,
        }
    return {"examples": examples, "model": model_name, "source": "llm"}
