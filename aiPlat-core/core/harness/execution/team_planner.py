"""
Team Planner — Agent discovery and LLM-based team recommendation.

General AI capability (boundary-standard.md §决策树).
Callers: platform/builder, CLI, API, any application that needs team planning.

Architecture:
  - list_available_agents() → scans AGENT.md files, builds catalog
  - recommend_team_stages() → LLM analyzes requirement + catalog → TeamRecommendation
"""
from __future__ import annotations

import glob
import logging
import os
import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from core.schemas_builder import PipelineStageConfig

logger = logging.getLogger("aiplat.team_planner")


@dataclass
# disposition: internal helper — used by recommend_team_stages() in same module
class AgentCatalogEntry:
    agent_id: str
    display_name: str
    agent_type: str
    phase: str
    skills: List[str]
    description: str


@dataclass
# disposition: internal helper — used by recommend_team_stages() in same module
class TeamRecommendation:
    team_name: str
    reasoning: str
    stages: List[Dict[str, Any]] = field(default_factory=list)
    raw_reply: str = ""


# disposition: internal helper — used by recommend_team_stages() in same module
def list_available_agents() -> List[AgentCatalogEntry]:
    """Scan all agent directories for AGENT.md files and return their frontmatter.

    Searches:
      1. ~/.aiplat/agents/ (user workspace)
      2. AIPLAT_WORKSPACE_SEEDS/agents/ (engine seeds)

    Returns a list of AgentCatalogEntry sorted by agent_id.
    """
    from core.api.facades.agent_facade import get_agent_frontmatter

    entries: List[AgentCatalogEntry] = []
    seen: set = set()

    for base in [
        os.path.expanduser("~/.aiplat/agents"),
        os.path.join(
            os.getenv("AIPLAT_HOME", os.path.expanduser("~/.aiplat")),
            "workspace_seeds", "agents",
        ),
    ]:
        for agent_dir in sorted(glob.glob(os.path.join(base, "*/"))):
            agent_id = os.path.basename(agent_dir.rstrip("/"))
            if agent_id in seen:
                continue
            seen.add(agent_id)

            fm = get_agent_frontmatter(agent_id) or {}
            if not fm:
                continue

            entries.append(AgentCatalogEntry(
                agent_id=agent_id,
                display_name=str(fm.get("display_name") or fm.get("name") or agent_id),
                agent_type=str(fm.get("agent_type") or "react"),
                phase=str(fm.get("phase") or fm.get("phase_description") or "-"),
                skills=[s for s in (fm.get("required_skills") or []) if isinstance(s, str)],
                description=re.sub(r"\s+", " ", str(fm.get("description") or "")[:200]),
            ))

    entries.sort(key=lambda e: e.agent_id)
    return entries


# disposition: internal helper — used by recommend_team_stages() in same module
def build_agent_catalog_markdown(agents: Optional[List[AgentCatalogEntry]] = None) -> str:
    """Format agent catalog as a markdown table for LLM prompts.

    Args:
        agents: Agents to include (uses all available agents if None)

    Returns:
        Markdown table with columns: Agent ID, Name, Type, Phase, Skills, Description
    """
    if agents is None:
        agents = list_available_agents()

    lines = [
        "| Agent ID | Name | Type | Phase | Skills | Description |",
        "|----------|------|------|-------|--------|-------------|",
    ]
    for entry in agents:
        skills = ", ".join(entry.skills) or "-"
        lines.append(
            f"| {entry.agent_id} | {entry.display_name} | {entry.agent_type} "
            f"| {entry.phase} | {skills} | {entry.description} |"
        )
    return "\n".join(lines)


async def recommend_team_stages(
    *,
    requirement: Dict[str, Any],
    available_agents: Optional[List[AgentCatalogEntry]] = None,
    model: Any = None,
    extra_context: str = "",
) -> TeamRecommendation:
    """Use LLM to analyze a requirement and recommend a team configuration.

    Args:
        requirement: Dict with at minimum 'functional_requirements' or 'description'
        available_agents: Agent catalog (uses all available if None)
        model: LLM adapter for inference
        extra_context: Additional text to include in the prompt (e.g., industry context)

    Returns:
        TeamRecommendation with team_name, reasoning, and stages
    """
    from core.api.intents import core_chat, ChatContext
    from core.utils.json_utils import extract_json

    if available_agents is None:
        available_agents = list_available_agents()

    catalog_md = build_agent_catalog_markdown(available_agents)
    req_json = json_dumps_safe(requirement, max_len=5000)

    prompt = (
        f"## Available Agent Types (from system registry)\n\n{catalog_md}\n\n"
        f"## Requirement\n\n{req_json}\n\n"
    )
    if extra_context:
        prompt += f"## Additional Context\n\n{extra_context}\n\n"
    prompt += (
        "## Task\n"
        "1. Select the best agents from the available types above for each stage\n"
        "2. Assign agent_id matching exactly the names listed in the catalog\n"
        "3. Order stages by logical dependency (upstream stages before downstream)\n"
        "4. Set uses_file_output=True for agents that generate source files\n"
        "5. Set generate_test_plan=True for agents that validate/verify output\n"
        "6. Set hitl=True for stages that require human approval\n"
        "7. Output JSON with team_name, reasoning, and stages array\n"
        "8. If Agent Performance History is provided, prefer agents with higher first_pass_rate and lower rejection_rate when multiple agents could fulfill the same role. Include a brief note in reasoning about why you preferred certain agents."
    )

    result = await core_chat(ChatContext(
        agent_name="planning_agent",
        session_id=f"team_plan_{id(requirement)}",
        user_input=prompt,
        model=model,
    ))

    recommendation = TeamRecommendation(team_name="", reasoning="", raw_reply=result.reply or "")

    try:
        json_str = extract_json(result.reply or "")
        if json_str:
            import json as _json
            data = _json.loads(json_str)
            recommendation.team_name = str(data.get("team_name", ""))
            recommendation.reasoning = str(data.get("reasoning", ""))
            stages_raw = (
                data.get("stages")
                or data.get("team", {}).get("stages")
                or data.get("plan", {}).get("stages")
                or []
            )
            for s in stages_raw:
                if isinstance(s, dict):
                    recommendation.stages.append({
                        "agent_id": s.get("agent_id") or s.get("agent") or s.get("name") or "",
                        "agent_name": s.get("agent_name") or s.get("name", ""),
                        "agent_type": s.get("agent_type") or s.get("type", "react"),
                        "phase": s.get("phase", ""),
                        "order": s.get("order", len(recommendation.stages)),
                        "uses_file_output": bool(s.get("uses_file_output") or s.get("uses_code_skill", False)),
                        "hitl": bool(s.get("hitl", False)),
                        "hitl_phase": s.get("hitl_phase", ""),
                        "output_artifact": s.get("output_artifact", ""),
                        "generate_test_plan": bool(s.get("generate_test_plan", False)),
                        "test_result_key": s.get("test_result_key", ""),
                        "id": s.get("id", f"stage_{len(recommendation.stages)}"),
                    })
    except Exception as e:
        logging.warning(str(e), exc_info=True)

    # Validate recommended agents
    unknown = []
    for s in recommendation.stages:
        aid = s.get("agent_id", "")
        if aid:
            from core.api.facades.agent_facade import get_agent_frontmatter
            if not get_agent_frontmatter(aid):
                unknown.append(aid)
    if unknown:
        recommendation.reasoning += f" [WARNING: Unknown agents: {unknown}]"

    return recommendation


# disposition: internal helper — json serialization for prompt injection
def json_dumps_safe(obj: Any, max_len: int = 8000) -> str:
    """Safe JSON dump with length limit."""
    import json as _json
    try:
        if isinstance(obj, dict):
            return _json.dumps(obj, ensure_ascii=False, indent=2)[:max_len]
        return str(obj)[:max_len]
    except Exception:
        return str(obj)[:max_len]


__all__ = [
    "AgentCatalogEntry",
    "TeamRecommendation",
    "list_available_agents",
    "build_agent_catalog_markdown",
    "recommend_team_stages",
]
