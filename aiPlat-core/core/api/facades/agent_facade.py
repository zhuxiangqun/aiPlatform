"""Agent Facade — agent configuration (no core_facade dependency)."""
from __future__ import annotations
from typing import Any, Dict


def get_agent_frontmatter(agent_id: str) -> Dict[str, Any]:
    """Load AGENT.md frontmatter for an agent. Looks in:
    1. ~/.aiplat/agents/{agent_id}/AGENT.md
    2. AIPLAT_WORKSPACE_SEEDS/agents/{agent_id}/AGENT.md
    Returns dict with all frontmatter fields + '_sop_body' (the SOP text after ---)."""
    import os
    import yaml

    agent_home = os.path.join(os.path.expanduser("~/.aiplat"), "agents", agent_id, "AGENT.md")
    seeds = os.getenv("AIPLAT_WORKSPACE_SEEDS",
        os.path.join(os.getenv("AIPLAT_HOME", os.path.expanduser("~/.aiplat")), "workspace_seeds"))
    seeds_path = os.path.join(seeds, "agents", agent_id, "AGENT.md")

    found_path = None
    if os.path.exists(agent_home):
        found_path = agent_home
    elif os.path.exists(seeds_path):
        found_path = seeds_path

    if not found_path:
        return {"agent_type": "conversational", "name": agent_id}
    with open(found_path, "r", encoding="utf-8") as f:
        raw = f.read()
    parts = raw.split("---", 2)
    if len(parts) >= 3:
        fm = yaml.safe_load(parts[1]) or {}
        fm["_sop_body"] = parts[2].strip()
        return fm
    return {"agent_type": "conversational", "name": agent_id}
