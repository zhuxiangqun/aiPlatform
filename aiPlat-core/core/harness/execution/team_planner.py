"""
Team Planner — Agent discovery, team template loading, and LLM-based team recommendation.

General AI capability (boundary-standard.md §决策树).
Callers: platform/builder, CLI, API, any application that needs team planning.

Architecture:
  - list_available_agents() → scans AGENT.md files, builds catalog
  - list_team_templates() → scans ~/.aiplat/teams/*.yaml
  - load_team_template(name) → loads a specific team YAML
  - recommend_team_stages() → LLM analyzes requirement + catalog → TeamRecommendation

Team templates are external YAML files — engine carries zero business assumptions.
New domain? New team YAML. No code change required.
"""
from __future__ import annotations

import glob
import logging
import os
import re
from collections import defaultdict, deque
from dataclasses import dataclass, field
from functools import lru_cache
from typing import Any, Dict, List, Optional

from core.schemas_builder import PipelineStageConfig

logger = logging.getLogger("aiplat.team_planner")


@dataclass
class AgentCatalogEntry:
    agent_id: str
    display_name: str
    agent_type: str
    phase: str
    skills: List[str]
    description: str
    depends_on: List[str] = field(default_factory=list)
    output_artifact: str = ""
    execution_backend: str = "llm"


@dataclass
class TeamRecommendation:
    team_name: str
    reasoning: str
    stages: List[Dict[str, Any]] = field(default_factory=list)
    raw_reply: str = ""


@dataclass
class TeamTemplate:
    """A named team configuration loaded from YAML file."""
    name: str
    file_path: str
    team_name: str
    description: str
    stages: List[Dict[str, Any]]


# ── Team template discovery ──────────────────────────────────────

def list_team_templates() -> List[TeamTemplate]:
    """Scan ~/.aiplat/teams/*.yaml and return all available team templates.

    Each YAML file defines a pre-configured team with stages.
    Users can add custom teams without changing engine code.
    """
    templates: List[TeamTemplate] = []
    teams_dir = os.path.expanduser("~/.aiplat/teams")
    if not os.path.isdir(teams_dir):
        return templates

    import yaml as _yaml
    for yaml_path in sorted(glob.glob(os.path.join(teams_dir, "*.yaml"))):
        try:
            with open(yaml_path, "r", encoding="utf-8") as f:
                data = _yaml.safe_load(f)
            if not isinstance(data, dict):
                continue
            name = os.path.splitext(os.path.basename(yaml_path))[0]
            stages = data.get("stages", [])
            templates.append(TeamTemplate(
                name=name,
                file_path=yaml_path,
                team_name=str(data.get("team_name", name)),
                description=str(data.get("description", "")),
                stages=stages if isinstance(stages, list) else [],
            ))
        except Exception:
            logger.debug("Failed to load team template: %s", yaml_path, exc_info=True)
    return templates


def load_team_template(name: str) -> Optional[TeamTemplate]:
    """Load a specific team template by name (without .yaml extension).

    Returns None if the template file doesn't exist.
    """
    yaml_path = os.path.expanduser(f"~/.aiplat/teams/{name}.yaml")
    if not os.path.isfile(yaml_path):
        return None

    import yaml as _yaml
    try:
        with open(yaml_path, "r", encoding="utf-8") as f:
            data = _yaml.safe_load(f)
        if not isinstance(data, dict):
            return None
        stages = data.get("stages", [])
        return TeamTemplate(
            name=name,
            file_path=yaml_path,
            team_name=str(data.get("team_name", name)),
            description=str(data.get("description", "")),
            stages=stages if isinstance(stages, list) else [],
        )
    except Exception:
        logger.debug("Failed to load team template: %s", yaml_path, exc_info=True)
        return None


# ── Agent discovery ──────────────────────────────────────────────

def list_available_agents() -> List[AgentCatalogEntry]:
    """Scan all agent directories for AGENT.md files and return their frontmatter.

    Searches:
      1. ~/.aiplat/agents/ (user workspace)
      2. AIPLAT_WORKSPACE_SEEDS/agents/ (engine seeds)
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
                depends_on=[d for d in (fm.get("depends_on") or []) if isinstance(d, str)],
                output_artifact=str(fm.get("output_artifact") or ""),
                execution_backend=str(fm.get("execution_backend") or "llm"),
            ))

    entries.sort(key=lambda e: e.agent_id)
    return entries


@lru_cache(maxsize=1)
def _list_agents_cached() -> tuple:
    """Scanned & cached agent catalog. I/O once, reuse until server restart."""
    return tuple(list_available_agents())


def _topological_order(stages: List[Dict]) -> List[Dict]:
    """Kahn's algorithm: assign `order` from depends_on DAG. Same order = parallel-safe.

    Each stage dict must have `id` and optionally `depends_on` (list of stage ids).
    Returns stages with `order` assigned (sorted). Isolated nodes get order=0.
    Circular dependencies get order=-1 with warning.
    """
    if not stages:
        return stages
    # Ensure each stage has an id
    for i, s in enumerate(stages):
        if not s.get("id"):
            s["id"] = s.get("agent_id", f"stage_{i}")
    stage_map = {s["id"]: s for s in stages}
    graph: dict = defaultdict(list)
    in_degree: dict = {s["id"]: 0 for s in stages}

    # Build graph from depends_on
    for s in stages:
        for dep_ref in s.get("depends_on", []) or []:
            # dep_ref can be agent_id or output_artifact name
            # First try direct id match; then try matching by output_artifact
            dep_id = dep_ref if dep_ref in stage_map else None
            if not dep_id:
                for sid, sm in stage_map.items():
                    if sm.get("output_artifact") == dep_ref:
                        dep_id = sid
                        break
            if dep_id and dep_id != s["id"]:
                graph[dep_id].append(s["id"])
                in_degree[s["id"]] += 1

    # BFS by layer (same layer = same order = parallel-safe)
    queue = deque([sid for sid, deg in in_degree.items() if deg == 0])
    order_map: dict = {}
    current_order = 0

    while queue:
        level_size = len(queue)
        for _ in range(level_size):
            node = queue.popleft()
            order_map[node] = current_order
            for neighbor in graph[node]:
                in_degree[neighbor] -= 1
                if in_degree[neighbor] == 0:
                    queue.append(neighbor)
        current_order += 1

    # Assign order; remaining in_degree > 0 = circular dependency
    for s in stages:
        s["order"] = order_map.get(s["id"], -1)
        if s["order"] == -1:
            logger.warning("Circular or broken dependency: stage %s cannot be ordered", s["id"])

    return sorted(stages, key=lambda x: x["order"])


def build_agent_catalog_markdown(agents: Optional[List[AgentCatalogEntry]] = None) -> str:
    """Format agent catalog as a markdown table for LLM prompts."""
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


def _enrich_stage_from_agent(stage: Dict[str, Any]) -> Dict[str, Any]:
    """Auto-populate pipeline fields from AGENT.md frontmatter.

    AGENT.md is the single source of truth for agent configuration.
    Fields already present in the stage (set by YAML or LLM) are preserved —
    only empty/missing fields get auto-populated from AGENT.md.

    This eliminates the need to duplicate agent config in every team YAML.
    """
    aid = stage.get("agent_id", "")
    if not aid:
        return stage

    from core.api.facades.agent_facade import get_agent_frontmatter
    fm = get_agent_frontmatter(aid) or {}

    # ── Display fields ──
    if not stage.get("agent_name"):
        stage["agent_name"] = str(fm.get("display_name") or fm.get("name") or aid)
    if not stage.get("agent_type"):
        stage["agent_type"] = str(fm.get("agent_type") or "react")
    if not stage.get("phase"):
        stage["phase"] = str(fm.get("phase") or fm.get("phase_description") or "")

    # ── Model routing ──
    if not stage.get("skill_model_purpose"):
        phase = stage.get("phase", "").lower()
        if "design" in phase or "architect" in phase or "review" in phase:
            stage["skill_model_purpose"] = "reasoning"
        elif "dev" in phase or "code" in phase or "program" in phase:
            stage["skill_model_purpose"] = "code_gen"
        elif "test" in phase or "qa" in phase:
            stage["skill_model_purpose"] = "code_gen"
        else:
            stage["skill_model_purpose"] = "chat"

    # Pre-resolve model name so frontend can preview without running pipeline
    if not stage.get("resolved_model"):
        try:
            from core.harness.utils.model_injection import best_model_for_purpose
            stage["resolved_model"] = best_model_for_purpose(stage.get("skill_model_purpose", "chat"))
        except Exception:
            stage["resolved_model"] = "auto"

    # ── Pipeline execution fields (from AGENT.md, not hardcoded in team YAML) ──
    _pipe_fields = [
        # (stage_key, fm_key, default, coerce_type)
        ("skill_name",         "skill_name",         "",     str),
        ("output_artifact",    "output_artifact",    "",     str),
        ("required_skills",    "required_skills",    [],     lambda v: v if isinstance(v, list) else []),
        ("execution_backend",  "execution_backend",  "llm",  str),
        ("test_execution_mode","test_execution_mode","",      str),
        ("generate_test_plan", "generate_test_plan",  False,  bool),
        ("deploy_files_to_disk","deploy_files_to_disk",False, bool),
        ("chain_skill_after",  "chain_skill_after",  "",     str),
        ("depends_on",         "depends_on",         [],     lambda v: v if isinstance(v, list) else []),
        ("hitl",               "hitl",               False,  bool),
        ("hitl_phase",         "hitl_phase",         "",     str),
        ("uses_file_output",   "uses_file_output",   False,  bool),
    ]
    for stage_key, fm_key, default, coerce in _pipe_fields:
        if not stage.get(stage_key):
            val = fm.get(fm_key, default)
            if val != default or not stage.get(stage_key):
                try:
                    stage[stage_key] = coerce(val) if callable(coerce) else val
                except Exception:
                    stage[stage_key] = default

    # ── Capability profile: guarantee all core capabilities are wired ──
    _ensure_capability_profile(stage)

    return stage


def _ensure_capability_profile(stage: dict) -> None:
    """Post-generation injection: every generated app gets all core capability defaults.

    Runs after _enrich_stage_from_agent() — regardless of what the LLM or
    YAML config produced, this step guarantees the output has every required
    capability field with sensible defaults.
    """
    _defaults = {
        # Execution
        "execution_backend": "llm",
        # Quality
        "scoring_dimensions": [
            {"name": "completeness", "weight": 0.4},
            {"name": "accuracy", "weight": 0.3},
            {"name": "efficiency", "weight": 0.3},
        ],
        "quality_gate": {"min_output_length": 100},
        # Context
        "context_profile": "code",
        # Resilience
        "retry_policy": {"max_retries": 2, "backoff": "exponential"},
        "failure_strategy": "skip_stage",
        # Safety
        "sandbox": False,
    }
    for key, value in _defaults.items():
        if key not in stage:
            stage[key] = value


def _load_fallback_team() -> List[Dict[str, Any]]:
    """Load fallback team from ~/.aiplat/default_team.yaml.

    Returns the stages list if the file exists and is valid, otherwise [].
    Engine carries zero business assumptions — team is entirely user-configured.
    """
    template = load_team_template("default")
    if template and template.stages:
        return template.stages
    return []


def _match_stage_from_templates(stage: Dict[str, Any]) -> Dict[str, Any]:
    """Fill skill_name + orchestration fields from registered YAML team templates.

    Scans all ~/.aiplat/teams/*.yaml for stages matching stage['agent_id'].
    When found, copies config fields (skill_name, output_artifact, hitl, etc.)
    into the stage dict. Does NOT overwrite fields already set by LLM or user.

    This bridges the gap between LLM-recommended stages (which don't know
    about skill mapping) and YAML-configured stages (which do).
    """
    aid = stage.get("agent_id", "")
    if not aid:
        return stage

    for tmpl in list_team_templates():
        for ts in tmpl.stages:
            if ts.get("agent_id") == aid:
                # Copy orchestration fields from template if not already set
                _config_fields = [
                    "skill_name", "output_artifact", "test_result_key",
                    "hitl", "hitl_phase", "uses_file_output", "generate_test_plan",
                    "failure_strategy", "skill_model_purpose",
                ]
                for f in _config_fields:
                    if not stage.get(f) and ts.get(f):
                        stage[f] = ts[f]
                return stage  # First match wins

    return stage


# ── Team recommendation ─────────────────────────────────────────

async def recommend_team_stages(
    *,
    requirement: Dict[str, Any],
    available_agents: Optional[List[AgentCatalogEntry]] = None,
    model: Any = None,
    extra_context: str = "",
    team_template: str = "",
) -> TeamRecommendation:
    """Use LLM to analyze a requirement and recommend a team configuration.

    Args:
        requirement: Dict with at minimum 'functional_requirements' or 'description'
        available_agents: Agent catalog (uses all available if None)
        model: LLM adapter for inference
        extra_context: Additional text to include in the prompt (e.g., industry context)
        team_template: Name of a team template from ~/.aiplat/teams/ to use instead
                       of LLM recommendation (e.g., 'default', 'data-science')

    Returns:
        TeamRecommendation with team_name, reasoning, and stages
    """
    from core.api.intents import core_chat, ChatContext
    from core.utils.json_utils import extract_json

    recommendation = TeamRecommendation(team_name="", reasoning="", raw_reply="")

    # ── Path 1: User explicitly selected a team template ──
    if team_template:
        tmpl = load_team_template(team_template)
        if tmpl and tmpl.stages:
            recommendation.team_name = tmpl.team_name
            recommendation.reasoning = f"使用团队模板: {tmpl.team_name} ({team_template}.yaml)"
            for i, s in enumerate(tmpl.stages):
                stage = dict(s)
                stage.setdefault("id", f"stage_{i}")
                stage = _enrich_stage_from_agent(stage)
                recommendation.stages.append(stage)
            # Auto-assign order from depends_on DAG (overrides sequential defaults)
            recommendation.stages = _topological_order(recommendation.stages)
            return recommendation

    # ── Path 2: LLM-based team recommendation ──
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

    recommendation.raw_reply = result.reply or ""

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
                    _stage = {
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
                    }
                    # Match against YAML templates for skill_name + orchestration
                    _stage = _match_stage_from_templates(_stage)
                    recommendation.stages.append(_stage)
    except Exception as e:
        logging.warning(str(e), exc_info=True)

    # ── Fallback: LLM returned 0 stages → load from default_team.yaml ──
    if not recommendation.stages:
        fallback = _load_fallback_team()
        if fallback:
            for i, fs in enumerate(fallback):
                stage = _enrich_stage_from_agent(dict(fs))
                stage.setdefault("id", f"stage_{i}")
                stage.setdefault("order", i)
                recommendation.stages.append(stage)
            if fallback:
                tmpl = load_team_template("default")
                recommendation.team_name = recommendation.team_name or (tmpl.team_name if tmpl else "default-team")
            recommendation.reasoning = recommendation.reasoning or "LLM recommendation returned no stages. Using default team from ~/.aiplat/default_team.yaml."

    # ── Validate recommended agents ──
    unknown = []
    for s in recommendation.stages:
        aid = s.get("agent_id", "")
        if aid:
            from core.api.facades.agent_facade import get_agent_frontmatter
            if not get_agent_frontmatter(aid):
                unknown.append(aid)
    if unknown:
        recommendation.reasoning += f" [WARNING: Unknown agents: {unknown}]"

    # Auto-assign order from depends_on DAG (for both LLM-recommended and fallback paths)
    recommendation.stages = _topological_order(recommendation.stages)

    return recommendation


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
    "TeamTemplate",
    "list_available_agents",
    "build_agent_catalog_markdown",
    "list_team_templates",
    "load_team_template",
    "recommend_team_stages",
]
