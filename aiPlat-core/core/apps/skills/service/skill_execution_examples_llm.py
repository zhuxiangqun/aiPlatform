"""LLM-assisted execution test-case generation for workspace Skills (optional).

Heuristic Schema samples remain the default path; this module is opt-in via UI.

Quality gate is skill-agnostic: thin / one-liner payloads are rejected and we
fall back to schema heuristics so「LLM 生成」won't persist false-green chips.
"""

from __future__ import annotations

import json
import logging
import re
from typing import Any, Dict, List, Optional, Tuple

from core.management.execution_examples import (
    accept_llm_execution_examples,
    build_examples_from_input_schema,
)


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
        # Thin chips are dropped after sanitize + schema gate, not here.
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
    sop_excerpt: str = "",
) -> Dict[str, Any]:
    """Generate 2–4 realistic smoke test cases for a Skill via LLM.

    Returns:
      {examples: [{title, content}], model: str, source: "llm"|heuristic_fallback, warning?}
    """
    skill_id = str(skill_id or "").strip()
    if not skill_id:
        raise ValueError("skill_id is required")

    try:
        from core.apps.skills.prompts import register_skills_prompts

        register_skills_prompts()
    except Exception:
        logging.warning("skill execution-examples prompts not registered", exc_info=True)

    label = (skill_name or skill_id).strip()
    schema = input_schema if isinstance(input_schema, dict) else {}
    schema_json = json.dumps(schema, ensure_ascii=False, indent=2)[:4000]
    hint = str(refine_hint or "").strip()
    sop = str(sop_excerpt or "").strip() or "(无 SOP)"

    from core.api.core_facade import (  # P0-A2: via CoreFacade
        _async_prompt_resolve,
        best_model_for_purpose,
        create_selected_adapter,
        sys_llm_generate,  # noqa: context-assembly-ok
    )

    prompt = await _async_prompt_resolve(
        "skill-execution-examples",
        skill_id=skill_id,
        skill_name=label,
        description=(description or "")[:1500] or "(无描述)",
        input_schema_json=schema_json or "{}",
        refine_hint=hint or "(无)",
        sop_excerpt=sop[:2500],
    )
    model_name = best_model_for_purpose("skill_execution")
    model = create_selected_adapter(model_name=model_name)
    messages = [
        {
            "role": "system",
            "content": await _async_prompt_resolve("skill-execution-examples-system-role"),
        },
        {"role": "user", "content": prompt},
    ]
    resp = await sys_llm_generate(  # noqa: context-assembly-ok
        model,
        messages,
        trace_context={"skip_claude_md": True, "source": "skill_execution_examples"},
    )
    text = str(resp.content if hasattr(resp, "content") else resp)
    examples = accept_llm_execution_examples(
        _extract_json_array(text),
        schema if schema else None,
        skill_hint=f"{skill_id} {label}",
    )
    if not examples:
        examples = build_examples_from_input_schema(
            schema,
            skill_id=skill_id,
            skill_name=label,
        )
        return {
            "examples": examples,
            "model": model_name,
            "source": "heuristic_fallback",
            "warning": "LLM 用例未通过 schema 门禁或过薄，已回退到 Schema 启发式样例（未覆盖已有落盘）",
        }
    return {"examples": examples, "model": model_name, "source": "llm"}


def _skill_md_candidates(mgr: Any, skill: Any, skill_id: str) -> List[Any]:
    from pathlib import Path as _P

    sid = str(skill_id or "").strip()
    out: List[Any] = []
    fs = (getattr(skill, "metadata", None) or {})
    fs = fs.get("filesystem") if isinstance(fs, dict) else {}
    if isinstance(fs, dict) and fs.get("skill_md"):
        out.append(_P(str(fs["skill_md"])))
    if mgr is not None and hasattr(mgr, "_find_skill_md"):
        try:
            found = mgr._find_skill_md(sid)
            if found:
                out.append(_P(str(found)))
        except Exception:
            pass  # noqa: cleanup-best-effort
    if sid:
        core_root = _P(__file__).resolve().parents[3]
        out.append(core_root / "engine" / "skills" / sid / "SKILL.md")
        out.append(_P.home() / ".aiplat" / "skills" / sid / "SKILL.md")
    seen = set()
    uniq = []
    for p in out:
        key = str(p)
        if key in seen:
            continue
        seen.add(key)
        uniq.append(p)
    return uniq


def _parse_skill_md_frontmatter(raw: str, mgr: Any = None) -> Dict[str, Any]:
    if mgr is not None and hasattr(mgr, "_split_front_matter"):
        try:
            parsed, _body = mgr._split_front_matter(raw)
            if isinstance(parsed, dict):
                return parsed
        except Exception:
            pass  # noqa: cleanup-best-effort
    parts = str(raw or "").split("---", 2)
    if len(parts) < 3:
        return {}
    try:
        import yaml as _yaml
        fm = _yaml.safe_load(parts[1]) or {}
        return fm if isinstance(fm, dict) else {}
    except Exception:
        return {}


def skill_md_frontmatter_and_excerpt(mgr: Any, skill: Any, skill_id: str) -> Tuple[Dict[str, Any], str]:
    """Load SKILL.md YAML + SOP body excerpt for generate/help."""
    fm: Dict[str, Any] = {}
    excerpt = ""
    try:
        from core.management.execution_examples import sop_excerpt_from_markdown

        for md in _skill_md_candidates(mgr, skill, skill_id):
            try:
                if not md or not getattr(md, "exists", lambda: False)():
                    continue
            except Exception:
                continue
            raw = md.read_text(encoding="utf-8", errors="ignore")
            excerpt = sop_excerpt_from_markdown(raw)
            fm = _parse_skill_md_frontmatter(raw, mgr)
            if excerpt or fm:
                break
    except Exception:
        return fm, excerpt
    return fm, excerpt


async def run_generate_skill_execution_examples(
    *,
    mgr: Any,
    skill: Any,
    skill_id: str,
    persist: bool = False,
    refine_hint: str = "",
) -> Dict[str, Any]:
    """Shared Skill LLM generate + persist gate (workspace and engine)."""
    from core.management.execution_examples import resolve_skill_example_schema

    fm, sop_excerpt = skill_md_frontmatter_and_excerpt(mgr, skill, skill_id)
    input_schema = resolve_skill_example_schema(
        live=getattr(skill, "input_schema", None),
        frontmatter=fm,
    )
    result = await generate_skill_execution_examples_llm(
        skill_id=str(skill_id),
        skill_name=str(getattr(skill, "display_name", None) or getattr(skill, "name", "") or skill_id),
        description=str(getattr(skill, "description", "") or ""),
        input_schema=input_schema,
        refine_hint=refine_hint,
        sop_excerpt=sop_excerpt,
    )
    examples = result.get("examples") if isinstance(result, dict) else None
    if not isinstance(examples, list) or not examples:
        raise ValueError("LLM did not return usable examples")
    saved = False
    if persist and str(result.get("source") or "") == "llm":
        try:
            saved = bool(mgr.persist_execution_examples(str(skill_id), examples))
        except Exception:
            logging.warning("persist execution examples failed skill_id=%s", skill_id, exc_info=True)
            saved = False
    elif persist:
        extra = str(result.get("warning") or "").strip()
        result["warning"] = (extra + "；" if extra else "") + "启发式回退未写入 SKILL.md（避免覆盖已有用例）"
    result["status"] = "ok"
    result["skill_id"] = skill_id
    result["examples"] = examples
    result["persisted"] = saved
    return result
