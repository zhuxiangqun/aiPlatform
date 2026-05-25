"""Chain Planner — structured intent → thinking chain (stage sequence with dependencies).

All chain templates are config-driven via AIPLAT_CHAIN_TEMPLATES env var (JSON).
Only loaded when AGENT.md scanning cannot produce a chain. Per CLAUDE.md §5.29:
no hardcoded business role names, phase strings, or domain-specific chains in core.
"""
from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from .intent_analyzer import StructuredIntent


@dataclass
class ChainStep:
    """A single step in the execution chain."""
    id: str
    role: str
    depends_on: List[str] = field(default_factory=list)


def _load_chain_templates() -> Dict[str, List[Dict[str, Any]]]:
    raw = os.getenv("AIPLAT_CHAIN_TEMPLATES", "")
    if raw:
        try:
            return json.loads(raw)
        except (json.JSONDecodeError, TypeError):
            pass
    return {}


_DEFAULT_CHAINS: Dict[str, List[ChainStep]] = {}


async def plan_chain(intent: StructuredIntent, model: Any = None) -> List[ChainStep]:
    """Generate execution chain from structured intent.

    Priority:
    1. LLM-generated chain (when model is available)
    2. Config-driven templates (AIPLAT_CHAIN_TEMPLATES env var)
    3. Empty chain (caller must provide chain via AGENT.md or team config)
    """

    # Load config-driven templates
    templates = _load_chain_templates()
    if templates:
        for name, steps_data in templates.items():
            if not isinstance(steps_data, list):
                continue
            _DEFAULT_CHAINS[name] = [
                ChainStep(id=s.get("id", ""), role=s.get("role", ""),
                          depends_on=s.get("depends_on", []))
                for s in steps_data if isinstance(s, dict)
            ]

    matched = _DEFAULT_CHAINS.get(intent.app_type, [])
    if not matched:
        matched = _DEFAULT_CHAINS.get("general", [])

    if model and (not matched or os.getenv("AIPLAT_CHAIN_USE_LLM", "true").lower() in ("1", "true", "yes")):
        try:
            llm_chain = await _llm_plan_chain(intent, model)
            if llm_chain:
                return llm_chain
        except Exception:
            pass
    return matched


async def _llm_plan_chain(intent: StructuredIntent, model: Any) -> List[ChainStep]:
    """Use LLM to generate execution chain from intent."""
    from core.api.intents import core_chat, ChatContext
    prompt = (
        f"Given the following user intent for a {intent.app_type or 'software'} project, "
        f"produce an execution chain as a JSON array of steps. "
        f"Each step has: id (string), role (string), depends_on (list of step ids).\n\n"
        f"Intent: {intent.summary or intent.raw_text or 'build a software application'}\n"
        f"Output ONLY JSON array."
    )
    result = await core_chat(ChatContext(
        agent_name="chain_planner",
        session_id="chain_plan",
        user_input=prompt, model=model,
    ))
    import json as _json
    try:
        data = _json.loads(result.reply)
        if isinstance(data, list):
            return [ChainStep(id=s.get("id", ""), role=s.get("role", ""),
                             depends_on=s.get("depends_on", [])) for s in data if isinstance(s, dict)]
    except Exception:
        pass
    return []


__all__ = ["ChainStep", "plan_chain"]
