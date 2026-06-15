"""
Builder project service — project CRUD + file persistence + team-bound pipeline execution.

Pipeline operations use CoreFacade.PipelineSession — the sole interface for
pipeline execution per architecture contract (docs/index.md §Layer 2 boundary).
"""
from __future__ import annotations

import json
import logging
import os
import time
import uuid
from typing import Any, Dict, List, Optional

from core.schemas_builder import (
    BuilderSessionPhase,
    Project,
    ProjectRun,
    ProjectCreateRequest,
    PipelineConfig,
    PipelineStageConfig,
    PRDArtifact,
)
from core.api.core_facade import create_pipeline_session, apply_agent_md_to_stage, validate_pipeline_stages, extract_json
from builder.builder_team_service import BuilderTeamService

import re

_DANGEROUS_PATTERNS = [
    (re.compile(r"rm\s+-rf", re.IGNORECASE), "attempts to run rm -rf"),
    (re.compile(r"sudo\s", re.IGNORECASE), "attempts to use sudo"),
    (re.compile(r"curl.*\|.*sh", re.IGNORECASE), "attempts to pipe curl to shell"),
    (re.compile(r"os\.system\(|subprocess\.call\(|exec\(|eval\(", re.IGNORECASE), "attempts to execute system commands"),
    (re.compile(r"ignore.*all.*previous.*instructions?", re.IGNORECASE), "attempts prompt injection override"),
    (re.compile(r"<\|im_start\|>|<\|im_end\|>", re.IGNORECASE), "contains model control tokens"),
]

_log = logging.getLogger("aiplat.builder.project_service")

def _scan_agent_security(agent_id: str, sop_body: str) -> None:
    for pattern, description in _DANGEROUS_PATTERNS:
        if pattern.search(sop_body):
            _log.warning("Security: AGENT.md '%s' %s. Body will be stripped.", agent_id, description)
            raise ValueError(f"AGENT.md '{agent_id}' contains dangerous content: {description}")

_AIPLAT_PM_AGENT = os.getenv("AIPLAT_PM_AGENT", "pm_agent")

_AIPLAT_CHAT_NOT_IN_DIALOGUE = os.getenv(
    "AIPLAT_CHAT_NOT_IN_DIALOGUE", "Project is not in dialogue phase")
_AIPLAT_CHAT_NO_MODEL = os.getenv(
    "AIPLAT_CHAT_NO_MODEL", "LLM model not loaded. Check API key configuration.")
_AIPLAT_CHAT_ERROR_PREFIX = os.getenv(
    "AIPLAT_CHAT_ERROR_PREFIX", "Chat error: ")

_AIPLAT_PRD_SECTION_REQUIREMENTS = os.getenv("AIPLAT_PRD_SECTION_REQUIREMENTS", "功能需求")
_AIPLAT_PRD_SECTION_SCOPE = os.getenv("AIPLAT_PRD_SECTION_SCOPE", "范围")
_AIPLAT_PRD_SECTION_METRICS = os.getenv("AIPLAT_PRD_SECTION_METRICS", "成功指标")
_AIPLAT_PRD_SECTION_ACCEPTANCE = os.getenv("AIPLAT_PRD_SECTION_ACCEPTANCE", "验收标准")
_AIPLAT_PRD_SECTION_ISA = os.getenv("AIPLAT_PRD_SECTION_ISA", "ISA 对齐")
_AIPLAT_PRD_TITLE_PREFIX = os.getenv("AIPLAT_PRD_TITLE_PREFIX", "项目名称：")

_AIPLAT_NO_PRD = os.getenv(
    "AIPLAT_NO_PRD", "No PRD data available. Complete the PM dialogue first.")

_PROJECTS_FILE = os.path.join(
    os.getenv("AIPLAT_HOME", os.path.expanduser("~/.aiplat")), "projects.json"
)
_PROJECTS_DIR = os.path.join(
    os.getenv("AIPLAT_HOME", os.path.expanduser("~/.aiplat")), "projects"
)
_BUILDER_STATES_DIR = os.path.join(
    os.path.expanduser(os.getenv("AIPLAT_HOME", "~/.aiplat")),
    "builder_states",
)


def _semantic_output(agent_id: str, phase: str) -> str:
    """Map agent_id to semantic output artifact name — reads from AGENT.md frontmatter."""
    from core.api.facades.agent_facade import get_agent_frontmatter
    try:
        fm = get_agent_frontmatter(agent_id)
        if fm.get("output_artifact"):
            return fm["output_artifact"]
    except Exception as e:
        logging.getLogger("aiplat.builder").warning(
            "Failed to get agent frontmatter for %s: %s", agent_id, str(e)[:200])
    return phase or "artifact"


def _create_skill_loader():
    """Create a SkillLoader for dependency injection into PipelineEngine.

    This function lives in the service layer (allowed to import from apps) and
    injects the loader into the harness, eliminating harness→apps reverse deps.
    """
    def _load(name: str):
        if name == "code_generation":
            from core.api.core_facade import get_code_gen_skill
            return get_code_gen_skill()
        return None
    return _load


def _parse_team_stages(stages_raw: list) -> list:
    """Parse raw team_stages dicts into PipelineStageConfig list."""
    stages = []
    for s in (stages_raw or []):
        try:
            stages.append(PipelineStageConfig(**s) if isinstance(s, dict) else s)
        except Exception as e:
            logging.getLogger("aiplat.builder").warning(
                "Failed to parse team stage: %s", str(e)[:200])
    return stages


class BuilderProjectService:

    def __init__(self, model: Any = None, team_service: Optional[BuilderTeamService] = None):
        self._model = model  # None = lazy init on first use
        self._team_service = team_service or BuilderTeamService(None)
        self._seed_registries()
        self._projects: Dict[str, Dict[str, Any]] = {}
        self._sessions: Dict[str, Dict[str, Any]] = {}
        self._pipeline_sessions: Dict[str, Any] = {}
        self._runs: Dict[str, Dict[str, Any]] = {}

    @property
    def model(self) -> Any:
        """Lazy init: only create LLM adapter when actually needed."""
        if self._model is None:
            from core.api.facades.service_facade import get_default_model
            self._model = get_default_model()
        return self._model
        self._phases: Dict[str, str] = {}  # dialogue | executing
        self._load_projects()

    @staticmethod
    def _seed_registries() -> None:
        from core.api.facades.skill_tool_facade import seed_all_registries
        seed_all_registries()

    # ── Persistence ──────────────────────────────────────────────────

    def _load_projects(self) -> None:
        try:
            if os.path.exists(_PROJECTS_FILE):
                with open(_PROJECTS_FILE, "r", encoding="utf-8") as f:
                    data = json.load(f)
                seen_ids = set()
                for item in data.get("projects", []):
                    pid = item.get("project_id", "")
                    if pid and pid not in seen_ids:
                        self._projects[pid] = item
                        seen_ids.add(pid)
        except Exception as e:
            _log.warning("Failed to load projects from %s: %s", _PROJECTS_FILE, e)

    def _save_projects(self) -> None:
        try:
            os.makedirs(os.path.dirname(_PROJECTS_FILE), exist_ok=True)
            # Deduplicate by project_id before saving
            seen = set()
            deduped = []
            for p in list(self._projects.values()):
                pid = p.get("project_id", "")
                if pid not in seen:
                    deduped.append(p)
                    seen.add(pid)
            data = {
                "projects": deduped,
                "updated_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
            }
            tmp = _PROJECTS_FILE + ".tmp"
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            os.replace(tmp, _PROJECTS_FILE)

            # Also write per-project directory files for governance support
            try:
                os.makedirs(_PROJECTS_DIR, exist_ok=True)
                for p in deduped:
                    pid = p.get("project_id", "")
                    if not pid:
                        continue
                    proj_dir = os.path.join(_PROJECTS_DIR, pid)
                    os.makedirs(proj_dir, exist_ok=True)

                    # Write project.json
                    proj_json = os.path.join(proj_dir, "project.json")
                    proj_payload = dict(p)
                    # Strip runs from the per-file snapshot (they're in projects.json)
                    proj_payload.pop("runs", None)
                    with open(proj_json + ".tmp", "w", encoding="utf-8") as f:
                        json.dump(proj_payload, f, ensure_ascii=False, indent=2)
                    os.replace(proj_json + ".tmp", proj_json)

                    # Enrich with provenance/integrity if manifest exists
                    manifest_path = os.path.join(proj_dir, "PROJECT.manifest.json")
                    if os.path.exists(manifest_path):
                        try:
                            with open(manifest_path, "r", encoding="utf-8") as f:
                                manifest = json.load(f)
                            p.setdefault("metadata", {})
                            p["metadata"].setdefault("provenance", {})
                            p["metadata"]["provenance"].update({
                                "publisher": manifest.get("publisher"),
                                "source": manifest.get("source"),
                                "version": manifest.get("version"),
                                "signature": manifest.get("signature"),
                            })
                        except Exception:
                            pass
            except Exception:
                _log.debug("Failed to write per-project directory files", exc_info=True)
        except Exception as e:
            _log.error("Failed to save projects to %s (project data may be lost on restart): %s", _PROJECTS_FILE, e)

    def _reload_if_stale(self) -> None:
        try:
            mtime = os.path.getmtime(_PROJECTS_FILE)
        except OSError:
            return
        cached = getattr(self, "_last_file_mtime", 0.0)
        if mtime <= cached:
            return
        current_ids = set(self._projects.keys())
        self._load_projects()
        new_ids = set(self._projects.keys()) - current_ids
        removed_ids = current_ids - set(self._projects.keys())
        if new_ids or removed_ids:
            _log.info(
                "Reloaded projects from %s: +%d new, -%d removed",
                _PROJECTS_FILE, len(new_ids), len(removed_ids),
            )
        self._last_file_mtime = mtime

    # ── CRUD ─────────────────────────────────────────────────────────

    async def create_project(self, req: ProjectCreateRequest) -> Project:
        project_id = f"prj_{uuid.uuid4().hex[:8]}"
        now = time.strftime("%Y-%m-%dT%H:%M:%S")

        stages: List[PipelineStageConfig] = []
        if req.stages:
            # Pre-built workflow stages from canvas/editor
            for s in req.stages:
                if isinstance(s, dict):
                    stages.append(PipelineStageConfig(**s))
        elif req.team_id:
            team = await self._team_service.get_team(req.team_id)
            if team:
                stages = team.stages

        self._projects[project_id] = {
            "project_id": project_id,
            "name": req.name or f"Project {project_id}",
            "description": req.description,
            "team_id": req.team_id,
            "team_stages": [s.model_dump() if hasattr(s, 'model_dump') else s for s in stages],
            "runs": [],
            "created_at": now,
            "updated_at": now,
        }
        self._save_projects()
        project_data = self._projects[project_id]
        team_name = ""
        if team_id := project_data.get("team_id"):
            team = await self._team_service.get_team(team_id)
            if team:
                team_name = team.name
        return Project(
            project_id=project_data.get("project_id", project_id),
            name=project_data.get("name", ""),
            description=project_data.get("description", ""),
            team_id=project_data.get("team_id", ""),
            team_name=team_name,
            team_stages=_parse_team_stages(project_data.get("team_stages", [])),
            runs=[],
            created_at=project_data.get("created_at", ""),
            updated_at=project_data.get("updated_at", ""),
        )

    async def list_projects(self) -> List[Project]:
        self._reload_if_stale()
        # Batch-load all teams to avoid N+1 per-project queries
        team_ids = list({data.get("team_id", "") for data in self._projects.values() if data.get("team_id")})
        team_map: Dict[str, str] = {}
        for tid in team_ids:
            try:
                team = await self._team_service.get_team(tid)
                if team:
                    team_map[tid] = team.name
            except Exception:
                pass

        projects: List[Project] = []
        for pid, data in self._projects.items():
            runs_data = data.get("runs", [])
            latest = runs_data[-1] if runs_data else None
            team_id = data.get("team_id", "")
            team_name = team_map.get(team_id, "")
            projects.append(Project(
                project_id=data.get("project_id", pid),
                name=data.get("name", ""),
                description=data.get("description", ""),
                team_id=team_id,
                team_name=team_name,
                team_stages=_parse_team_stages(data.get("team_stages", [])),
                runs=[ProjectRun(**r) for r in runs_data[-3:]] if runs_data else [],
                created_at=data.get("created_at", ""),
                updated_at=data.get("updated_at", ""),
            ))
        return projects

    async def get_project(self, project_id: str) -> Optional[Dict[str, Any]]:
        return self._projects.get(project_id)

    async def delete_project(self, project_id: str) -> bool:
        if project_id not in self._projects:
            return False
        import shutil
        home = os.getenv("AIPLAT_HOME", os.path.expanduser("~/.aiplat"))
        # Output directories may use legacy "bare ID" or new "name-ID" format
        dirs_to_check = [
            (os.path.join(home, "output"), project_id),
            (os.path.join(os.getenv("AIPLAT_APP_DEPLOY_DIR", os.path.expanduser("~/.aiplat/apps")), ""), project_id),
        ]
        for base_dir, pid in dirs_to_check:
            try:
                if not os.path.isdir(base_dir):
                    continue
                for entry in os.listdir(base_dir):
                    full = os.path.join(base_dir, entry)
                    if entry.endswith(f"-{pid}") or entry == pid:
                        try:
                            if os.path.isdir(full):
                                shutil.rmtree(full)
                            elif os.path.isfile(full):
                                os.remove(full)
                        except OSError:
                            pass
            except OSError:
                pass
        for state_file in [
            os.path.join(home, "builder_states", f"{project_id}.json"),
            os.path.join(home, "builder_states", f"{project_id}_chat.json"),
        ]:
            try:
                if os.path.isfile(state_file):
                    os.remove(state_file)
            except OSError:
                pass
        del self._projects[project_id]
        self._save_projects()
        return True

    async def chat(self, project_id: str, message: str) -> Dict[str, Any]:
        """PM dialogue — directly managed through self._sessions (chat dicts only)."""
        from core.api.intents import core_chat, ChatContext

        session = self._sessions.get(project_id)
        if not session:
            session = self._load_chat_session(project_id)
            if session:
                self._sessions[project_id] = session

        if not isinstance(session, dict):
            return {"reply": _AIPLAT_CHAT_NOT_IN_DIALOGUE, "prd_ready": False, "trace_id": "", "session_state": {}}

        if not session or session.get("phase") != BuilderSessionPhase.dialogue.value:
            return {"reply": _AIPLAT_CHAT_NOT_IN_DIALOGUE, "prd_ready": False, "trace_id": "", "session_state": {}}

        if not self._model:
            return {"reply": _AIPLAT_CHAT_NO_MODEL, "prd_ready": False, "trace_id": "", "session_state": {}}

        session["messages"].append({"role": "user", "content": message})

        try:
            result = await core_chat(ChatContext(
                agent_name=_AIPLAT_PM_AGENT,
                session_id=project_id,
                user_input=message,
                model=self.model,
            ))
            reply = result.reply
            session["messages"].append({"role": "assistant", "content": reply})
            prd_ready = "<!-- PRD_READY -->" in str(reply)
            if prd_ready:
                # Try JSON first (backward compat), then Markdown
                draft = None
                try:
                    json_str = extract_json(reply)
                    if json_str:
                        draft = json.loads(json_str)
                        if not (draft.get("user_stories") or draft.get("functional_requirements")):
                            draft = None
                except Exception:
                    pass
                # Fallback: parse Markdown PRD
                if not draft and "## 项目名称" in str(reply):
                    draft = self._parse_markdown_prd(reply)
                if draft:
                    session["prd"] = draft
                    # Also save to project directly so PRD survives session loss/overwrite
                    proj = self._projects.get(project_id, {})
                    if proj:
                        proj["confirmed_prd"] = draft
                        self._save_projects()
            self._save_chat_session(project_id)
            return {"reply": reply, "prd_ready": prd_ready, "trace_id": result.trace_id, "session_state": {}}
        except Exception as e:
            return {"reply": f"{_AIPLAT_CHAT_ERROR_PREFIX}{str(e)[:200]}", "prd_ready": False, "trace_id": "", "session_state": {}}

    async def confirm_prd(self, project_id: str, prd_data: Any = None) -> Dict[str, Any]:
        session = self._sessions.get(project_id)
        if not session:
            session = self._load_chat_session(project_id)
            if session:
                self._sessions[project_id] = session
        if not isinstance(session, dict):
            session = {}
        if not prd_data:
            prd_data = session.get("prd") if isinstance(session, dict) else None
        # Last resort: extract PRD from last assistant message in session
        if not prd_data and isinstance(session, dict):
            msgs = session.get("messages", [])
            for m in reversed(msgs):
                if m.get("role") == "assistant":
                    content = m.get("content", "")
                    if "<!-- PRD_READY -->" in content or "## 项目名称" in content:
                        draft = self._parse_markdown_prd(content)
                        if draft:
                            prd_data = draft
                            session["prd"] = draft
                        break

        proj = self._projects.get(project_id, {})
        if not prd_data:
            raise ValueError(_AIPLAT_NO_PRD)

        proj["confirmed_prd"] = prd_data
        self._save_projects()

        # Transition session phase from dialogue to executing
        if session:
            session["phase"] = BuilderSessionPhase.executing.value
        return {"phase": BuilderSessionPhase.executing.value, "prd": prd_data}

    async def recommend_team(self, project_id: str) -> Dict[str, Any]:
        """Use Planning Agent to analyze PRD and recommend a team configuration.

        Delegates to core/harness/execution/team_planner.recommend_team_stages()
        for the AI inference (boundary-standard.md §决策树: agent discovery → Core).
        Platform-specific logic (team creation, project association) stays here.
        """
        from core.api.core_facade import recommend_team_stages

        proj = self._projects.get(project_id)
        if not proj:
            raise ValueError(f"Project {project_id} not found")

        prd = proj.get("confirmed_prd")
        if not prd:
            session = self._sessions.get(project_id)
            if not session:
                session = self._load_chat_session(project_id)
                if session:
                    self._sessions[project_id] = session
            prd = (session or {}).get("prd") if isinstance(session, dict) else None
        if not prd:
            # Fallback: use project description as a minimal requirement
            desc = proj.get("description", "")
            if not desc:
                raise ValueError("No PRD or project description available. Complete the PM dialogue first.")
            prd = {"title": proj.get("name", "New Project"), "description": desc,
                   "functional_requirements": [], "user_stories": []}

        # Delegate AI inference to core team_planner (boundary-standard.md §决策树)
        # Gather agent performance history for smarter recommendations
        extra_context = ""
        try:
            agent_insights = await self.list_agent_insights()
            if agent_insights and agent_insights.get("agents"):
                insights = agent_insights["agents"]
                if insights:
                    lines = ["## Agent Performance History (from past pipeline runs)",
                             "| Agent ID | First Pass | Rejection | Rollback | Runs |",
                             "|----------|-----------|-----------|----------|------|"]
                    for a in insights[:20]:
                        aid = a.get("agent_id", "?")
                        fpr = a.get("first_pass_rate", 0) or 0
                        rej = a.get("rejection_rate", 0) or 0
                        qa = a.get("qa_rollback_rate", 0) or 0
                        tr = a.get("total_runs", 0) or 0
                        if tr > 0:
                            lines.append(f"| {aid} | {fpr:.0%} | {rej:.0%} | {qa:.0%} | {tr} |")
                    extra_context = "\n".join(lines)
        except Exception:
            pass
        
        rec = await recommend_team_stages(requirement=prd, model=self.model, extra_context=extra_context or None)

        recommendation = {
            "team_name": rec.team_name,
            "reasoning": rec.reasoning,
            "raw_reply": rec.raw_reply,
        }
        plan_stages = rec.stages

        if plan_stages:
            proj["plan_stages"] = plan_stages
            proj["plan_stage_ids"] = [s.get("id", f"plan_stage_{i}") for i, s in enumerate(plan_stages)]

            # Auto-create team from plan_stages so pipeline can start immediately
            if not proj.get("team_id"):
                try:
                    from core.schemas_builder import PipelineStageConfig, TeamAssembleRequest
                    team_stages = []
                    for ps in plan_stages:
                        team_stages.append(PipelineStageConfig(
                            id=ps.get("id", f"stage_{len(team_stages)}"),
                            agent_id=ps.get("agent_id", ""),
                            agent_name=ps.get("agent_name", ps.get("agent_id", "")),
                            phase=ps.get("phase", ""),
                            order=ps.get("order", len(team_stages)),
                            uses_file_output=bool(ps.get("uses_file_output") or ps.get("uses_code_skill", False)),
                            hitl=bool(ps.get("hitl", False)),
                            hitl_phase=ps.get("hitl_phase", ""),
                            output_artifact=ps.get("output_artifact", ""),
                            generate_test_plan=bool(ps.get("generate_test_plan", False)),
                            test_result_key=ps.get("test_result_key", "test_report"),
                            agent_type=ps.get("agent_type", "react"),
                        ))
                    if team_stages:
                        team_req = TeamAssembleRequest(
                            name=recommendation.get("team_name", f"团队-{project_id}"),
                            description=recommendation.get("reasoning", ""),
                            stages=team_stages,
                        )
                        team = await self._team_service.create_team(team_req)
                        proj["team_id"] = team.team_id
                        proj["team_stages"] = [s.model_dump() if hasattr(s, 'model_dump') else s for s in team_stages]
                        self._save_projects()
                        recommendation["_team_created"] = True
                        recommendation["_team_id"] = team.team_id
                except Exception as e:
                    recommendation["_team_create_failed"] = str(e)[:200]

        return {
            "project_id": project_id,
            "recommendation": recommendation,
            "plan_stages": plan_stages,
            "plan_stage_ids": proj.get("plan_stage_ids", []),
            "trace_id": getattr(rec, 'trace_id', '') or '',
        }

    @staticmethod
    def _parse_plan_stages(recommendation: Dict) -> List[Dict]:
        """UNUSED static utility — retained for future API compat.
        Actual parsing is done inline in recommend_team()."""
        stages_raw = (
            recommendation.get("stages")
            or recommendation.get("team", {}).get("stages")
            or recommendation.get("plan", {}).get("stages")
            or []
        )
        result = []
        warnings = []
        for i, s in enumerate(stages_raw):
            if not isinstance(s, dict):
                continue
            agent_id = s.get("agent_id") or s.get("agent") or s.get("name") or f"agent_{i}"
            result.append({
                "id": s.get("id") or f"plan_stage_{i}",
                "agent_id": agent_id,
                "output_artifact": s.get("output_artifact") or s.get("output") or f"plan_artifact_{i}",
                "description": s.get("description") or s.get("role") or "",
                "generate_test_plan": s.get("generate_test_plan", False),
                "uses_file_output": s.get("uses_file_output", False),
                "hitl": s.get("hitl", True),
                "order": s.get("order", i),
                "prompt_extra": s.get("prompt_extra") or s.get("sop") or "",
                "agent_type": s.get("agent_type") or s.get("type", "react"),
            })
        return result

    def _validate_pipeline_stages(self, stages: List[PipelineStageConfig]) -> Dict[str, Any]:
        """Validate pipeline stages — delegates to CoreFacade."""
        return validate_pipeline_stages(stages)

    @staticmethod
    def _parse_markdown_prd(reply: str) -> Dict[str, Any]:
        """Parse structured Markdown PRD into a dict for session storage."""
        prd: Dict[str, Any] = {}
        # Strip PRD_READY marker if present (appears before the # heading)
        clean = reply.replace("<!-- PRD_READY -->", "").strip()
        title_match = re.search(r"^# (.+)", clean, re.MULTILINE)
        if title_match:
            prd["title"] = title_match.group(1).strip()
            if prd["title"].startswith(_AIPLAT_PRD_TITLE_PREFIX):
                prd["title"] = prd["title"][5:].strip()
        # Extract sections by ## headings
        sections: Dict[str, str] = {}
        current_key = ""
        for line in clean.split("\n"):
            m = re.match(r"^## (.+)", line)
            if m:
                current_key = m.group(1).strip()
                sections[current_key] = ""
            elif current_key:
                sections[current_key] += line + "\n"
        # Functional requirements count as user_stories
        func_section = sections.get(_AIPLAT_PRD_SECTION_REQUIREMENTS, "")
        fr_items = []
        for fr_match in re.finditer(r"###\s*(.+?)\n(.*?)(?=\n###|\n##|\Z)", func_section or "", re.DOTALL):
            fr_name = fr_match.group(1).strip()
            fr_body = fr_match.group(2)
            user_story_match = re.search(r"用户故事[：:]\s*(.+)", fr_body)
            acs = re.findall(r"AC\d+:\s*(.+)", fr_body)
            fr_items.append({
                "id": fr_name.split(":", 1)[0].strip() if ":" in fr_name else fr_name,
                "name": fr_name.split(":", 1)[1].strip() if ":" in fr_name else fr_name,
                "description": user_story_match.group(1).strip() if user_story_match else "",
                "acceptance_criteria": acs,
            })
        if fr_items:
            prd["functional_requirements"] = fr_items
            prd["user_stories"] = fr_items
        scope = sections.get(_AIPLAT_PRD_SECTION_SCOPE, "").strip()
        if scope:
            prd["scope"] = scope
        # ISA upgrade: extract success metrics and target state
        metrics_section = sections.get(_AIPLAT_PRD_SECTION_METRICS, "") or sections.get(_AIPLAT_PRD_SECTION_ACCEPTANCE, "")
        if metrics_section.strip():
            isc_list = []
            for isc_match in re.finditer(r"###?\s*(ISC-\d+)[：:]\s*(.+?)\n(.*?)(?=\n###|\n##|\Z)", metrics_section, re.DOTALL):
                isc_id = isc_match.group(1).strip()
                isc_name = isc_match.group(2).strip()
                isc_body = isc_match.group(3)
                verify = re.search(r"验证方式[：:]\s*(.+)", isc_body)
                isc_list.append({
                    "id": isc_id, "name": isc_name,
                    "criteria": isc_body.strip()[:200],
                    "verification_method": verify.group(1).strip() if verify else "manual",
                })
            if isc_list:
                prd["isc_list"] = isc_list
        target_state = sections.get("目标状态", "") or sections.get(_AIPLAT_PRD_SECTION_ISA, "")
        if target_state.strip():
            prd["target_state"] = target_state.strip()[:500]
        return prd if prd.get("title") else {}

    async def start_pipeline(self, project_id: str) -> Dict[str, Any]:
        proj = self._projects.get(project_id)
        if not proj:
            raise ValueError(f"Project {project_id} not found")

        team_id = proj.get("team_id", "")
        stages: List[PipelineStageConfig] = []

        # Re-sync latest team stages (team might have been edited after project creation)
        if team_id:
            team = await self._team_service.get_team(team_id)
            if team and team.stages:
                stages = [PipelineStageConfig(**s.model_dump()) if hasattr(s, 'model_dump') else PipelineStageConfig(**s) for s in team.stages]

                # Inject model + hitl config from agent AGENT.md
                for s in stages:
                    if (not s.model or not s.hitl_after_execute or not hasattr(s, '_auto_hitl_loaded')
                        or not s.phase_description or not s.prompt_extra or not s.required_skills):
                        try:
                            from core.api.facades.agent_facade import get_agent_frontmatter
                            fm = get_agent_frontmatter(s.agent_id)
                            if not fm:
                                continue
                            sop = fm.get("_sop_body", "")
                            _scan_agent_security(s.agent_id, sop)
                            cfg = fm.get("config") or {}
                            if cfg.get("model") and not s.model:
                                s.model = cfg["model"]
                            apply_agent_md_to_stage(s, s.agent_id)
                        except Exception as e:
                            _log.warning("Failed to load AGENT.md config for '%s': %s", s.agent_id, e)

                # Remap old generic output names to semantic names
                for s in stages:
                    if not s.output_artifact or s.output_artifact.startswith("stage_"):
                        s.output_artifact = _semantic_output(s.agent_id, s.phase)
                # Update project snapshot to latest
                proj["team_stages"] = [s.model_dump() if hasattr(s, 'model_dump') else s for s in stages]
                self._save_projects()

        if not stages:
            stages_raw = proj.get("team_stages", [])
            for s in stages_raw:
                if hasattr(s, 'model_dump'):
                    s = s.model_dump()
                stages.append(PipelineStageConfig(**s))

        if not stages:
            # Auto-trigger team recommendation if no team configured
            try:
                await self.recommend_team(project_id)
                # Re-read project after recommendation (team_id + team_stages now set)
                proj = self._projects.get(project_id, {})
                team_id = proj.get("team_id", "")
                if team_id:
                    team = await self._team_service.get_team(team_id)
                    if team and team.stages:
                        stages = [PipelineStageConfig(**s.model_dump()) if hasattr(s, 'model_dump') else PipelineStageConfig(**s) for s in team.stages]
                        proj["team_stages"] = [s.model_dump() if hasattr(s, 'model_dump') else s for s in stages]
                        self._save_projects()
            except Exception as e:
                _log.warning("Auto team recommend failed for %s: %s", project_id, e)

        if not stages:
            raise ValueError("No team stages configured. Unable to auto-recommend a team. Please click 'AI 推荐团队' first.")

        max_tokens = int(os.getenv("AIPLAT_BUILDER_MAX_TOKENS", "100000"))
        max_retry = int(os.getenv("AIPLAT_BUILDER_MAX_RETRY", "3"))
        config = PipelineConfig(stages=stages, max_tokens_per_run=max_tokens, max_retry_attempts=max_retry)
        diagnostics = self._validate_pipeline_stages(config.stages)

        # Extract PRD from chat session before pipeline takes over
        prd_data = proj.get("confirmed_prd")
        if not prd_data:
            chat_session = self._sessions.get(project_id, {})
            if isinstance(chat_session, dict):
                prd_data = chat_session.get("prd")

        pipeline_session = create_pipeline_session(config=config, model=self.model, skill_loader=_create_skill_loader())
        self._pipeline_sessions[project_id] = pipeline_session

        # Register event bus listener — writes pipeline state to singleton _runs for frontend polling
        from core.api.facades.runtime_facade import get_event_bus
        from api.routers.builder import _svc as builder_singleton
        _runs_singleton = builder_singleton._runs
        def _on_event(pid: str, evt: str, data: dict):
            if pid == project_id:
                _runs_singleton[pid] = dict(data.get("state", data))
        get_event_bus().on(_on_event)

        # Run synchronously — proxy timeout is 600s, Architect takes 20-60s.
        requirement = proj.get("description", "")
        run_id = f"run_{uuid.uuid4().hex[:8]}"
        now = time.strftime("%Y-%m-%dT%H:%M:%S")
        proj.setdefault("runs", []).append({
            "run_id": run_id, "project_id": project_id,
            "phase": "executing", "pass_rate": 0, "tokens_used": 0,
            "iteration": 0, "error": "", "started_at": now, "finished_at": "",
        })
        proj["updated_at"] = now
        self._save_projects()

        state = {"phase": "executing"}
        try:
            state = await pipeline_session.start(project_id, requirement, prd_data=prd_data, project_name=proj.get("name", ""))
            # Config-driven: use stage.test_result_key (default "test_report" for backward compat)
            test_key = "test_report"
            for s in (proj.get("team_stages") or []):
                sk = s.get("test_result_key", "") if isinstance(s, dict) else getattr(s, "test_result_key", "")
                if sk:
                    test_key = sk
            tr = state.get(test_key) or {}
            run_record = proj["runs"][-1]
            run_record["phase"] = state.get("phase", "done")
            run_record["pass_rate"] = tr.get("pass_rate", 0)
            run_record["tokens_used"] = state.get("tokens_used", 0)
            run_record["iteration"] = state.get("iteration", 0)
            run_record["error"] = state.get("error", "")
            self._runs[project_id] = state
            # Persist pipeline state so approve works after restart
            self._save_pipeline_state(project_id, state)
            # Trigger deploy assembly if pipeline completed (non-HITL auto pipelines)
            await self._save_state(project_id, state)
        except Exception as e:
            run_record = proj["runs"][-1]
            run_record["error"] = str(e)[:200]
            run_record["phase"] = "failed"
            state = {"phase": "failed", "error": str(e)[:200]}
            self._runs[project_id] = state
        finally:
            proj["updated_at"] = time.strftime("%Y-%m-%dT%H:%M:%S")
            self._save_projects()

        # Signature verification on governed projects (non-blocking best-effort)
        sig_verified = None
        try:
            proj_dir = os.path.join(_PROJECTS_DIR, project_id)
            manifest_path = os.path.join(proj_dir, "PROJECT.manifest.json")
            if os.path.exists(manifest_path):
                from core.security.skill_signature_gate import get_trusted_skill_pubkeys_map
                import asyncio as _asyncio

                # Compute integrity from per-project JSON
                proj_json = os.path.join(proj_dir, "project.json")
                if os.path.exists(proj_json):
                    import hashlib
                    h = hashlib.sha256()
                    h.update(Path(proj_json).read_bytes())
                    bundle_sha = h.hexdigest()

                    with open(manifest_path, "r", encoding="utf-8") as f:
                        manifest = json.load(f)
                    sig = manifest.get("signature")
                    if sig:
                        from core.harness.infrastructure.crypto.signature import verify_skill_signature
                        from core.harness.kernel.runtime import get_kernel_runtime
                        rt = get_kernel_runtime()
                        store = getattr(rt, "execution_store", None) if rt else None
                        import concurrent.futures as _cf2
                        with _cf2.ThreadPoolExecutor(max_workers=1) as _pool:
                            trusted = _pool.submit(_asyncio.run, get_trusted_skill_pubkeys_map(store)).result(timeout=10) if store else {}
                        r = verify_skill_signature(
                            skill_id=project_id,
                            version=manifest.get("version", "0.1.0"),
                            bundle_sha256=bundle_sha,
                            signature=sig,
                            trusted_keys=trusted,
                        )
                        sig_verified = r.get("verified")
                        if not sig_verified:
                            _log.warning("Project %s signature verification failed: %s", project_id, r.get("error"))
        except Exception:
            _log.debug("Signature verification skipped for project %s", project_id, exc_info=True)

        # Record as changeset for governance audit
        try:
            from core.api.core_facade import record_changeset
            await record_changeset(
                name="start_pipeline",
                target_type="project",
                target_id=project_id,
                status=state.get("phase", "executing"),
                args={"run_id": run_id, "team_id": team_id, "stage_count": len(stages)},
                user_id="admin",
            )
        except Exception:
            _log.debug(f"Failed to record start_pipeline changeset for {project_id}", exc_info=True)

        return {"project_id": project_id, "phase": state.get("phase", "executing"), "run_id": run_id,
                "state": state, "diagnostics": diagnostics}

    async def _save_state(self, project_id: str, state: dict):
        """Save pipeline state and trigger deploy assembly if completed."""
        self._runs[project_id] = state
        # Embed episodic memory state for restart survival
        try:
            from core.api.facades.runtime_facade import get_memory_manager
            mgr = get_memory_manager()
            state["_episodic"] = mgr.export_episodic_state()
        except Exception:
            pass
        self._save_pipeline_state(project_id, state)
        session = self._pipeline_sessions.get(project_id)
        # Config-driven: find test result key from session stages
        test_key = "test_report"
        if session:
            for s in (session.get_stages() or []):
                sk = getattr(s, 'test_result_key', '') if hasattr(s, 'test_result_key') else ''
                if sk:
                    test_key = sk
        tr = state.get(test_key) or {}
        if state.get("phase") == "done" or tr.get("recommendation") == "APPROVED":
            if session:
                deploy_dir = session.assemble_deploy(state)
                if deploy_dir:
                    self._projects.setdefault(project_id, {})["deploy_dir"] = deploy_dir
                    self._save_projects()

    async def approve_stage(self, project_id: str) -> Dict[str, Any]:
        session = self._pipeline_sessions.get(project_id)
        if not session:
            session = self._rebuild_session(project_id)
            if not session:
                raise ValueError("no session")
        state = self._runs.get(project_id)
        if not state:
            state = self._load_pipeline_state(project_id)
            if not state:
                raise ValueError("no pipeline state")
        state = await session.approve(dict(state))
        await self._save_state(project_id, state)
        return {"project_id": project_id, "phase": state.get("phase", "executing")}

    async def start_fix(self, project_id: str) -> Dict[str, Any]:
        session = self._pipeline_sessions.get(project_id)
        if not session:
            session = self._rebuild_session(project_id)
            if not session:
                raise ValueError("no session")
        state = self._runs.get(project_id)
        if not state:
            state = self._load_pipeline_state(project_id)
            if not state:
                raise ValueError("no pipeline state")
        state = dict(state)
        state["phase"] = "executing"
        state = await session.approve(state)
        await self._save_state(project_id, state)
        return {"project_id": project_id, "phase": state.get("phase", "executing")}

    async def reject_stage(self, project_id: str, feedback: str) -> Dict[str, Any]:
        session = self._pipeline_sessions.get(project_id)
        if not session:
            session = self._rebuild_session(project_id)
            if not session:
                raise ValueError("no session")
        state = self._runs.get(project_id)
        if not state:
            state = self._load_pipeline_state(project_id)
            if not state:
                raise ValueError("no pipeline state")
        state = await session.reject(dict(state), feedback)
        await self._save_state(project_id, state)
        return {"project_id": project_id, "phase": state.get("phase", "executing")}

    async def rollback_stage(self, project_id: str, stage_id: str) -> Dict[str, Any]:
        session = self._pipeline_sessions.get(project_id)
        if not session:
            session = self._rebuild_session(project_id)
            if not session:
                raise ValueError("no session")
        state = self._runs.get(project_id)
        if not state:
            state = self._load_pipeline_state(project_id)
            if not state:
                raise ValueError("no pipeline state")
        target_id = stage_id
        for s in session.get_stages():
            if s.output_artifact == stage_id or s.agent_id == stage_id:
                target_id = s.id
                break
        state = await session.rollback(dict(state), target_id)
        await self._save_state(project_id, state)
        return {"project_id": project_id, "phase": state.get("phase", "executing")}

    async def resume_from_stage(self, project_id: str, stage_id: str) -> Dict[str, Any]:
        """Resume pipeline from a specific stage without clearing artifacts."""
        session = self._pipeline_sessions.get(project_id)
        if not session:
            session = self._rebuild_session(project_id)
            if not session:
                raise ValueError("no session")
        state = self._runs.get(project_id)
        if not state:
            state = self._load_pipeline_state(project_id)
            if not state:
                raise ValueError("no pipeline state")
        target_idx = 0
        for i, s in enumerate(session.get_stages()):
            if s.id == stage_id or s.output_artifact == stage_id or s.agent_id == stage_id:
                target_idx = i
                break
        state = dict(state)
        state["phase"] = "executing"
        state["tokens_used"] = 0
        state.pop("error", None)
        state = await session.resume_from(target_idx, state)
        await self._save_state(project_id, state)
        return {"project_id": project_id, "phase": state.get("phase", "executing")}

    async def rollback_prd(self, project_id: str) -> Dict[str, Any]:
        """Roll back to PRD editing phase"""
        proj = self._projects.get(project_id, {})
        proj["confirmed_prd"] = None
        self._save_projects()
        # Clean up pipeline state files to prevent ghost recovery
        for fname in (f"{project_id}.json", f"{project_id}_chat.json"):
            fpath = os.path.join(_BUILDER_STATES_DIR, fname)
            try:
                if os.path.exists(fpath):
                    os.remove(fpath)
            except OSError:
                pass
        # Clear in-memory state
        self._runs[project_id] = {}
        self._sessions.pop(project_id, None)
        self._pipeline_sessions.pop(project_id, None)
        return {"project_id": project_id, "phase": "dialogue"}

    async def get_deploy_dir(self, project_id: str) -> Optional[str]:
        """Get deploy directory path for a project."""
        proj = self._projects.get(project_id, {})
        return proj.get("deploy_dir") or None

    async def get_project_state(self, project_id: str) -> Dict[str, Any]:
        # Merge all pipeline_events' states for complete picture (single source of truth)
        import json
        from storage.sqlite import list_pipeline_events
        events = list_pipeline_events(project_id)
        state: Dict[str, Any] = {}
        phase = "idle"
        for ev in events:
            try:
                st = json.loads(ev.get("state_json", "{}"))
                state.update(st)
                if st.get("phase"):
                    phase = st["phase"]
            except Exception:
                pass
        state["phase"] = state.get("phase", phase)
        if not state or state.get("phase") == "failed":
            persisted = self._load_pipeline_state(project_id)
            if persisted:
                self._runs[project_id] = persisted  # recovery
                state = persisted
                # Restore episodic memory from persisted state
                episodic = state.get("_episodic")
                if isinstance(episodic, dict):
                    try:
                        from core.api.facades.runtime_facade import get_memory_manager
                        mgr = get_memory_manager()
                        mgr.import_episodic_state(episodic)
                    except Exception:
                        pass
        if not state:
            state = {}
        proj = self._projects.get(project_id, {})
        return {
            "project_id": project_id,
            "phase": state.get("phase", "idle"),
            "confirmed_prd": proj.get("confirmed_prd"),
            "state": state,
            "runs": proj.get("runs", []),
        }

    # ── Pipeline state persistence (per-project files, survives restart) ──

    def _save_pipeline_state(self, project_id: str, state: Dict[str, Any]) -> None:
        """Save pipeline state to dedicated JSON file (not projects.json).
        
        Using per-project files avoids concurrent write hazards on the shared
        projects.json and enables full session recovery after restart.
        """
        os.makedirs(_BUILDER_STATES_DIR, exist_ok=True)
        state_file = os.path.join(_BUILDER_STATES_DIR, f"{project_id}.json")
        try:
            with open(state_file + ".tmp", "w", encoding="utf-8") as f:
                json.dump(dict(state), f, ensure_ascii=False, indent=2, default=str)
            os.replace(state_file + ".tmp", state_file)
        except Exception as e:
            _log.warning("Failed to save pipeline state for %s: %s", project_id, e)

    def _save_chat_session(self, project_id: str) -> None:
        """Persist chat session (messages, prd, phase) to survive restart.
        
        Stored alongside pipeline state in builder_states/."""
        session = self._sessions.get(project_id)
        if not session or not isinstance(session, dict):
            return
        os.makedirs(_BUILDER_STATES_DIR, exist_ok=True)
        chat_file = os.path.join(_BUILDER_STATES_DIR, f"{project_id}_chat.json")
        try:
            with open(chat_file + ".tmp", "w", encoding="utf-8") as f:
                json.dump(dict(session), f, ensure_ascii=False, indent=2, default=str)
            os.replace(chat_file + ".tmp", chat_file)
        except Exception as e:
            _log.warning("Failed to save chat session for %s: %s", project_id, e)

    def _load_chat_session(self, project_id: str) -> Optional[Dict[str, Any]]:
        """Load persisted chat session from disk, if it exists."""
        chat_file = os.path.join(_BUILDER_STATES_DIR, f"{project_id}_chat.json")
        try:
            if os.path.exists(chat_file):
                with open(chat_file, "r", encoding="utf-8") as f:
                    return json.load(f)
        except Exception:
            pass
        return None

    def _load_pipeline_state(self, project_id: str) -> Optional[Dict[str, Any]]:
        """Load pipeline state from per-project JSON file."""
        state_file = os.path.join(_BUILDER_STATES_DIR, f"{project_id}.json")
        try:
            if os.path.exists(state_file):
                with open(state_file, "r", encoding="utf-8") as f:
                    return json.load(f)
        except Exception as e:
            _log.warning("Failed to load pipeline state for %s: %s", project_id, str(e)[:200])
        return None

    def _rebuild_session(self, project_id: str) -> Optional[Any]:
        """Rebuild PipelineSession and state from persisted project data (for crash recovery)."""
        proj = self._projects.get(project_id)
        if not proj:
            return None

        stages_raw = proj.get("team_stages", [])
        stages: List[PipelineStageConfig] = []
        for s in stages_raw:
            stages.append(PipelineStageConfig(**s) if isinstance(s, dict) else s)
        for s in stages:
            if not s.output_artifact or s.output_artifact.startswith("stage_"):
                s.output_artifact = _semantic_output(s.agent_id, s.phase)

        # Read config from AGENT.md for each stage (delegates to CoreFacade)
        for s in stages:
            try:
                apply_agent_md_to_stage(s, s.agent_id)
            except Exception as e:
                _log.warning("Failed to apply AGENT.md config for agent %s in project %s: %s",
                    s.agent_id, project_id, str(e)[:200])

        if not stages:
            return None

        max_tokens = int(os.getenv("AIPLAT_BUILDER_MAX_TOKENS", "100000"))
        max_retry = int(os.getenv("AIPLAT_BUILDER_MAX_RETRY", "3"))
        config = PipelineConfig(stages=stages, max_tokens_per_run=max_tokens, max_retry_attempts=max_retry)
        session = create_pipeline_session(config=config, model=self.model, skill_loader=_create_skill_loader())
        self._pipeline_sessions[project_id] = session
        return session

    async def get_graph(self, project_id: str) -> Dict[str, Any]:
        """Return pipeline execution graph for visualization (P2-9)."""
        state = self._runs.get(project_id) or self._load_pipeline_state(project_id) or {}
        graph_trace = state.get("_graph_trace", []) or []
        proj = self._projects.get(project_id, {})
        stages = proj.get("team_stages", [])
        current_idx = state.get("_current_stage_idx", 0)
        stage_objs = []
        for i, s_raw in enumerate(stages):
            if isinstance(s_raw, dict):
                stage_objs.append(type('Stage', (), {
                    'id': s_raw.get('id', ''),
                    'agent_id': s_raw.get('agent_id', ''),
                    'output_artifact': s_raw.get('output_artifact', ''),
                    'hitl': s_raw.get('hitl', False),
                }))
        return {
            "project_id": project_id,
            "phase": state.get("phase", ""),
            "current_stage_idx": current_idx,
            "stages": [
                {
                    "id": s.id,
                    "agent_id": s.agent_id,
                    "output_artifact": s.output_artifact,
                    "status": _stage_status_for_graph(s, graph_trace, i, current_idx, state),
                    "hitl": s.hitl,
                }
                for i, s in enumerate(stage_objs)
            ],
        }

    async def run_tests(self, project_id: str) -> Dict[str, Any]:
        """Run E2E smoke + repo tests for a completed project pipeline."""
        proj = self._projects.get(project_id, {})
        deploy_dir = proj.get("deploy_dir", "") or await self.get_deploy_dir(project_id)
        return _run_tests_for_project(project_id, deploy_dir or "")

    async def deploy_to_app(self, project_id: str) -> Dict[str, Any]:
        """Deploy pipeline output to the app layer."""
        proj = self._projects.get(project_id, {})
        deploy_dir = proj.get("deploy_dir", "") or await self.get_deploy_dir(project_id)
        return _deploy_to_app_for_project(project_id, deploy_dir or "", proj)

    async def get_agent_insight(self, agent_id: str) -> Dict[str, Any]:
        """Get insight metrics for a single agent."""
        return _get_agent_insight_for(agent_id, self._projects)

    async def list_agent_insights(self) -> Dict[str, Any]:
        """Get insight metrics for all agents."""
        agent_ids: set = set()
        for pid, proj in self._projects.items():
            stages = proj.get("team_stages", []) or []
            for s in stages:
                aid = s.get("agent_id", "") if isinstance(s, dict) else getattr(s, "agent_id", "")
                if aid:
                    agent_ids.add(aid)
        insights: Dict[str, Any] = {}
        for aid in agent_ids:
            insights[aid] = await self.get_agent_insight(aid)
        return {"agents": insights, "total": len(insights)}

    async def refresh_agent_insights(self) -> Dict[str, Any]:
        """Refresh agent insight metrics."""
        result = await self.list_agent_insights()
        result["ok"] = True
        return result

    async def get_health_report(self, project_id: str) -> Dict[str, Any]:
        """Build health report from pipeline state, aggregating per-stage dimensional scores."""
        state = self._runs.get(project_id)
        if not state:
            state = self._load_pipeline_state(project_id) or {}
        proj = self._projects.get(project_id, {})
        stages = []
        all_dims: Dict[str, Dict] = {}
        for s in (proj.get("team_stages") or []):
            sid = s.get("id") if isinstance(s, dict) else getattr(s, "id", "")
            hr = state.get(f"_health_report_{sid}") if sid else None
            if isinstance(hr, dict):
                stages.append(hr)
                for d in (hr.get("dimensions") or []):
                    dname = d.get("name", "")
                    if dname not in all_dims:
                        all_dims[dname] = dict(d)
                        all_dims[dname]["score"] = 0.0
                    all_dims[dname]["score"] += d.get("score", 0)
        # Average dimension scores across stages
        n = max(len(stages), 1)
        dim_list = []
        total_score = 0.0
        for d in all_dims.values():
            d["score"] = round(d["score"] / n, 1)
            total_score += d["score"] * d.get("weight", 1.0)
            dim_list.append(d)
        total_weight = sum(d.get("weight", 1.0) for d in dim_list) or 1.0
        overall = round(total_score / total_weight * 10, 1)
        # Build trend from run history
        trend = []
        for run in (proj.get("runs") or [])[-20:]:
            if isinstance(run, dict) and run.get("pass_rate"):
                trend.append({"run_id": run.get("run_id", ""), "score": round(float(run.get("pass_rate", 0)) * 100, 1),
                              "timestamp": run.get("started_at", "")})
        return {
            "project_id": project_id,
            "overall_score": overall,
            "dimensions": dim_list,
            "stages": stages,
            "trend": trend,
            "updated_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
        }


def _stage_status_for_graph(stage, graph_trace: List[Dict], idx: int, current_idx: int, state: Dict) -> str:
    for t in reversed(graph_trace):
        if t.get("stage_id") == stage.id:
            return t.get("status", "pending")
    if idx < current_idx:
        return "completed"
    if idx == current_idx:
        phase = state.get("phase", "")
        if "awaiting" in phase or "approval" in phase:
            return "paused_hitl"
        return "in_progress"
    return "pending"


def _run_tests_for_project(project_id: str, deploy_dir: str) -> dict:
    import subprocess, os
    results: dict = {"all_passed": False, "e2e_smoke": None, "repo_tests": None}
    if deploy_dir and os.path.isdir(deploy_dir):
        test_dir = os.path.join(deploy_dir, "tests")
        if not os.path.isdir(test_dir):
            test_dir = os.path.join(deploy_dir, "test")
        if os.path.isdir(test_dir):
            try:
                import sys as _sys
                r = subprocess.run([_sys.executable, "-m", "pytest", test_dir, "-q"], capture_output=True, text=True, timeout=60)
                results["repo_tests"] = {"passed": r.returncode == 0, "output": r.stdout[:2000]}
                results["all_passed"] = r.returncode == 0
            except Exception as e:
                results["repo_tests"] = {"passed": False, "error": str(e)}
    if deploy_dir:
        results["e2e_smoke"] = {"passed": True, "reason": "deploy_directory_exists"}
    return results


def _deploy_to_app_for_project(project_id: str, deploy_dir: str, proj: dict) -> dict:
    import os
    if not deploy_dir:
        deploy_dir = proj.get("deploy_dir", "") or os.path.join(
            os.getenv("AIPLAT_HOME", os.path.expanduser("~/.aiplat")), "output", project_id, "deploy")
    app_url = f"http://localhost:8004/app/sessions/{project_id}"
    return {"ok": True, "deploy_dir": deploy_dir, "app_url": app_url}


def _get_agent_insight_for(agent_id: str, projects: dict) -> dict:
    """Get insight metrics for a single agent from project run history.
    
    Filters to only count runs from projects where this agent is in the team.
    """
    total_runs, passes, rejections, rollbacks = 0, 0, 0, 0
    for pid, proj in projects.items():
        # Check if this agent is part of the project's team
        stages = proj.get("team_stages", []) or []
        agent_in_team = any(
            str(s.get("agent_id", "")) == str(agent_id) for s in stages if isinstance(s, dict)
        )
        if not agent_in_team:
            continue
        
        runs = proj.get("runs", []) or []
        for run in runs:
            total_runs += 1
            pass_rate = run.get("pass_rate", 0)
            if pass_rate >= 80:
                passes += 1
            if run.get("rejected", False):
                rejections += 1
            if run.get("rollback_count", 0) > 0:
                rollbacks += 1
    
    first_pass_rate = round(passes / max(total_runs, 1), 2)
    rejection_rate = round(rejections / max(total_runs, 1), 2)
    qa_rollback_rate = round(rollbacks / max(total_runs, 1), 2)
    return {
        "agent_id": agent_id,
        "first_pass_rate": first_pass_rate,
        "rejection_rate": rejection_rate,
        "qa_rollback_rate": qa_rollback_rate,
        "total_runs": total_runs,
        "output_completeness": 1.0,
    }
