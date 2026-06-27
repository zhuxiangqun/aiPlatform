"""
Builder role agents — factory for PM / Architect / Programmer / QA agents.

Each role's system prompt and agent type is loaded from its AGENT.md file
(workspace_seeds/agents/<role>/AGENT.md). No application-specific prompt text
is hardcoded in this module per CLAUDE.md §5.29.
"""

from __future__ import annotations
import logging

import os
import yaml
from typing import Any, Dict, List, Optional

from core.api.core_facade import create_agent


_AGENT_MD_CACHE: Dict[str, Dict[str, Any]] = {}


def _role_agent_md_path(agent_name: str) -> str:
    base = os.getenv("AIPLAT_WORKSPACE_SEEDS",
        os.path.join(os.getenv("AIPLAT_HOME", os.path.expanduser("~/.aiplat")), "workspace_seeds"))
    return os.path.join(base, "agents", agent_name, "AGENT.md")


def _load_agent_md(agent_name: str) -> Dict[str, Any]:
    if agent_name in _AGENT_MD_CACHE:
        return _AGENT_MD_CACHE[agent_name]
    path = _role_agent_md_path(agent_name)
    result: Dict[str, Any] = {"agent_type": "conversational", "system_prompt": "", "metadata": {}}
    try:
        with open(path, "r", encoding="utf-8") as f:
            content = f.read()
        if content.startswith("---"):
            parts = content.split("---", 2)
            if len(parts) >= 3:
                fm = yaml.safe_load(parts[1]) or {}
                sop = parts[2].strip()
                result["agent_type"] = str(fm.get("agent_type", "conversational"))
                result["system_prompt"] = sop
                result["metadata"] = {k: fm[k] for k in fm if k not in ("agent_type",)}
    except Exception as e:
        logging.debug(str(e), exc_info=True)
    _AGENT_MD_CACHE[agent_name] = result
    return result


def get_role_system_prompt(agent_name: str) -> str:
    return str(_load_agent_md(agent_name).get("system_prompt", "") or "")


def get_role_agent_type(agent_name: str) -> str:
    return str(_load_agent_md(agent_name).get("agent_type", "conversational") or "conversational")
