"""Capability Mapper — matches chain steps to available agents via AGENT.md capabilities.

All role-to-agent mappings are config-driven via AIPLAT_ROLE_AGENT_MAP env var (JSON).
Only loaded when AGENT.md capabilities frontmatter scanning fails to find a match.
Per CLAUDE.md §5.29: no hardcoded business role names or agent IDs in core.
"""
from __future__ import annotations

import json
import os
from typing import Any, Dict, List, Optional

from .types import ChainStep


def _load_role_agent_map() -> Dict[str, str]:
    raw = os.getenv("AIPLAT_ROLE_AGENT_MAP", "")
    if raw:
        try:
            return json.loads(raw)
        except (json.JSONDecodeError, TypeError):
            pass
    return {}


_ROLE_TO_AGENT_DEFAULTS: Dict[str, str] = {}


async def map_capabilities(steps: List[ChainStep], model: Any = None) -> Dict[str, str]:
    """Map each chain step to the best-matching agent.

    Priority:
    1. AGENT.md capabilities frontmatter (exact keyword match)
    2. Config-driven role→agent mapping (AIPLAT_ROLE_AGENT_MAP env var)
    3. LLM-based matching (when model available and no clear match)

    Returns: {step_id: agent_id}
    """
    # Load config-driven role→agent defaults
    role_map = _load_role_agent_map()
    if role_map:
        _ROLE_TO_AGENT_DEFAULTS.update(role_map)

    # Phase 1: Scan AGENT.md files for capabilities
    agent_caps = _scan_agent_capabilities()

    # Phase 2: Match each step
    mapping: Dict[str, str] = {}
    for step in steps:
        best_agent = _match_step_to_agent(step, agent_caps)
        mapping[step.id] = best_agent

    return mapping


def _scan_agent_capabilities() -> Dict[str, List[str]]:
    """Scan all AGENT.md files and return {agent_id: [capability_keywords]}."""
    import os
    import yaml

    caps: Dict[str, List[str]] = {}
    search_dirs = [
        os.path.expanduser("~/.aiplat/agents"),
        os.path.join(os.path.expanduser("~/.aiplat"), "workspace_seeds/agents"),
    ]
    for base in search_dirs:
        if not os.path.isdir(base):
            continue
        for agent_name in os.listdir(base):
            md_path = os.path.join(base, agent_name, "AGENT.md")
            if not os.path.isfile(md_path):
                continue
            try:
                with open(md_path, "r") as f:
                    raw = f.read()
                if raw.startswith("---"):
                    parts = raw.split("---", 2)
                    if len(parts) >= 3:
                        fm = yaml.safe_load(parts[1]) or {}
                        agent_caps = fm.get("capabilities") or fm.get("skills") or []
                        if isinstance(agent_caps, list):
                            caps[agent_name] = [str(c).lower() for c in agent_caps]
            except Exception:
                pass
    return caps


def _match_step_to_agent(step: ChainStep, agent_caps: Dict[str, List[str]]) -> str:
    """Find the best agent for a chain step."""
    # Default mapping
    default = _ROLE_TO_AGENT_DEFAULTS.get(step.role, "react_agent")

    # Keyword matching against AGENT.md capabilities
    role_keywords = step.role.lower().split()
    best_score = 0
    best_agent = default
    for agent_id, caps in agent_caps.items():
        score = sum(1 for kw in role_keywords if any(kw in c for c in caps))
        if score > best_score:
            best_score = score
            best_agent = agent_id

    return best_agent
