"""
Builder project service — project CRUD + file persistence + team-bound pipeline execution.
"""
from __future__ import annotations

import json
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
from core.harness.execution.pipeline_engine import PipelineEngine
from core.services.builder_team_service import BuilderTeamService

_PROJECTS_FILE = os.path.join(
    os.path.expanduser(os.getenv("AIPLAT_HOME", "~/.aiplat")),
    "projects.json",
)


def _semantic_output(agent_id: str, phase: str) -> str:
    """Map agent_id + phase to semantic output artifact name — reads from AGENT.md first."""
    # Read output_artifact from AGENT.md
    try:
        import yaml, os
        agent_md = os.path.join(os.path.expanduser("~/.aiplat"), "agents", agent_id, "AGENT.md")
        if os.path.exists(agent_md):
            with open(agent_md, "r") as f:
                raw = f.read()
            if raw.startswith("---"):
                parts = raw.split("---", 2)
                if len(parts) >= 3:
                    fm = yaml.safe_load(parts[1]) or {}
                    if fm.get("output_artifact"):
                        return fm["output_artifact"]
    except Exception:
        pass
    # fallback: legacy auto-detection by agent_id/phase
    # Remove this block once all agents define output_artifact in AGENT.md
    aid = (agent_id or '').lower()
    if 'backend' in aid: return 'backend_code'
    if 'frontend' in aid: return 'frontend_code'
    if 'architect' in aid or phase == 'design': return 'architecture'
    if 'pm' in aid or 'product' in aid or phase == 'planning': return 'prd'
    if 'qa' in aid or 'test' in aid or phase == 'testing': return 'test_report'
    if 'programmer' in aid or 'dev' in aid or phase == 'development': return 'code'
    return phase or 'artifact'


def _create_skill_loader():
    """Create a SkillLoader for dependency injection into PipelineEngine.

    This function lives in the service layer (allowed to import from apps) and
    injects the loader into the harness, eliminating harness→apps reverse deps.
    """
    def _load(name: str):
        if name == "code_generation":
            from core.apps.skills.base import CodeGenerationSkill  # noqa
            return CodeGenerationSkill()
        return None
    return _load


def _parse_team_stages(stages_raw: list) -> list:
    """Parse raw team_stages dicts into PipelineStageConfig list."""
    stages = []
    for s in (stages_raw or []):
        try:
            stages.append(PipelineStageConfig(**s) if isinstance(s, dict) else s)
        except Exception:
            pass
    return stages


class BuilderProjectService:

    def __init__(self, model: Any = None, team_service: Optional[BuilderTeamService] = None):
        self._model = model
        self._team_service = team_service or BuilderTeamService(model)
        self._projects: Dict[str, Dict[str, Any]] = {}
        self._engines: Dict[str, PipelineEngine] = {}
        self._runs: Dict[str, Dict[str, Any]] = {}
        self._load_projects()

    # ── Persistence ──────────────────────────────────────────────────

    def _load_projects(self) -> None:
        try:
            if os.path.exists(_PROJECTS_FILE):
                with open(_PROJECTS_FILE, "r", encoding="utf-8") as f:
                    data = json.load(f)
                for item in data.get("projects", []):
                    pid = item.get("project_id", "")
                    if pid:
                        self._projects[pid] = item
        except Exception:
            pass

    def _save_projects(self) -> None:
        try:
            os.makedirs(os.path.dirname(_PROJECTS_FILE), exist_ok=True)
            data = {
                "projects": list(self._projects.values()),
                "updated_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
            }
            with open(_PROJECTS_FILE, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2, default=str)
        except Exception:
            pass

    # ── CRUD ─────────────────────────────────────────────────────────

    async def create_project(self, req: ProjectCreateRequest) -> Project:
        project_id = f"prj_{uuid.uuid4().hex[:8]}"
        now = time.strftime("%Y-%m-%dT%H:%M:%S")

        stages: List[PipelineStageConfig] = []
        if req.team_id:
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
            project_id=project_data["project_id"],
            name=project_data["name"],
            description=project_data.get("description", ""),
            team_id=project_data.get("team_id", ""),
            team_name=team_name,
            team_stages=_parse_team_stages(project_data.get("team_stages", [])),
            runs=[],
            created_at=project_data.get("created_at", ""),
            updated_at=project_data.get("updated_at", ""),
        )

    async def list_projects(self) -> List[Project]:
        projects = []
        for pid, data in self._projects.items():
            runs_data = data.get("runs", [])
            latest = runs_data[-1] if runs_data else None
            team_name = ""
            team_id = data.get("team_id", "")
            if team_id:
                team = await self._team_service.get_team(team_id)
                if team:
                    team_name = team.name
            projects.append(Project(
                project_id=data["project_id"],
                name=data["name"],
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
        if project_id in self._projects:
            del self._projects[project_id]
            self._save_projects()
            return True
        return False

    async def chat(self, project_id: str, message: str) -> Dict[str, Any]:
        """PM dialogue — delegates to BuilderSessionService internally."""
        from core.services.builder_session import BuilderSessionService

        if not hasattr(self, '_chat_svc'):
            self._chat_svc: Dict[str, BuilderSessionService] = {}

        if project_id not in self._chat_svc:
            svc = BuilderSessionService(model=self._model)
            proj = self._projects.get(project_id, {})
            await svc.create_session(
                requirement=proj.get("description", ""),
                tenant_id="default", user_id="system",
            )
            keys = list(svc._sessions.keys())
            if keys:
                svc._sessions[project_id] = svc._sessions.pop(keys[0])
                svc._sessions[project_id]["session_id"] = project_id
            self._chat_svc[project_id] = svc

        svc = self._chat_svc[project_id]
        if not self._model:
            return {"reply": "LLM 模型未加载，请检查服务器配置（api_key / 环境变量 DEEPSEEK_API_KEY）", "prd_ready": False, "session_state": {}}
        try:
            resp = await svc.chat(project_id, message)
            return {"reply": resp.reply, "prd_ready": resp.prd_ready, "session_state": resp.session_state.model_dump() if hasattr(resp.session_state, 'model_dump') else {}}
        except Exception as e:
            import traceback
            print(f"[builder_project] chat error: {e}")
            traceback.print_exc()
            return {"reply": f"对话出错：{str(e)[:200]}", "prd_ready": False, "session_state": {}}

    async def confirm_prd(self, project_id: str, prd_data: Any = None) -> Dict[str, Any]:
        if not prd_data:
            chat_svc = getattr(self, '_chat_svc', {}).get(project_id)
            if chat_svc:
                chat_session = chat_svc._sessions.get(project_id, {})
                prd_data = chat_session.get("prd")

        proj = self._projects.get(project_id, {})
        if prd_data:
            proj["confirmed_prd"] = prd_data
            self._save_projects()

        from core.services.builder_session import BuilderSessionService
        svc = BuilderSessionService(model=self._model)
        try:
            await svc.confirm_requirements(project_id)
        except Exception:
            pass
        return {"phase": BuilderSessionPhase.executing.value, "prd": prd_data}

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
                    if not s.model or not s.hitl_after_execute or not hasattr(s, '_auto_hitl_loaded') or not s.phase_description:
                        try:
                            agent_md = os.path.join(os.path.expanduser("~/.aiplat"), "agents", s.agent_id, "AGENT.md")
                            if os.path.exists(agent_md):
                                import yaml
                                with open(agent_md, "r") as f:
                                    raw = f.read()
                                if raw.startswith("---"):
                                    parts = raw.split("---", 2)
                                    if len(parts) >= 3:
                                        fm = yaml.safe_load(parts[1]) or {}
                                        cfg = fm.get("config") or {}
                                        if cfg.get("model") and not s.model:
                                            s.model = cfg["model"]
                                        if not s.hitl_after_execute and fm.get("hitl_after_execute"):
                                            s.hitl_after_execute = fm["hitl_after_execute"]
                                            s.hitl_after_phase = fm.get("hitl_after_phase") or ""
                                        if fm.get("auto_hitl") and not hasattr(s, '_auto_hitl_loaded'):
                                            s.hitl = True
                                            s.hitl_phase = s.hitl_phase or ("awaiting_architecture_approval" if fm.get("phase") == "design" else "awaiting_test_plan_approval")
                                            s._auto_hitl_loaded = True
                                        elif not fm.get("auto_hitl") and not hasattr(s, '_auto_hitl_loaded'):
                                            s.hitl = False
                                            s.hitl_phase = ""
                                            s._auto_hitl_loaded = True
                                        if not hasattr(s, 'generate_test_plan') or not s.generate_test_plan:
                                            s.generate_test_plan = fm.get("generate_test_plan", False)
                                        if not hasattr(s, 'test_result_key') or not s.test_result_key:
                                            s.test_result_key = fm.get("test_result_key") or "test_report"
                                        if not hasattr(s, 'uses_code_skill') or not s.uses_code_skill:
                                            s.uses_code_skill = fm.get("uses_code_skill", False)
                                        if not getattr(s, 'code_target', None):
                                            s.code_target = fm.get("code_target") or "backend"
                                        if not getattr(s, 'prompt_extra', None):
                                            s.prompt_extra = fm.get("prompt_extra") or ""
                                        if not s.phase_description:
                                            s.phase_description = fm.get("phase_description", "") or ""
                                        if not getattr(s, 'failure_strategy', None):
                                            s.failure_strategy = fm.get("failure_strategy") or "fail_pipeline"
                                        if not getattr(s, 'fallback_result_key', None):
                                            s.fallback_result_key = fm.get("fallback_result_key") or ""
                                        if not getattr(s, 'retry_llm_on_rate_limit', None) and fm.get("retry_llm_on_rate_limit") is not None:
                                            s.retry_llm_on_rate_limit = bool(fm["retry_llm_on_rate_limit"])
                                        if not getattr(s, 'max_consecutive_llm_failures', None):
                                            s.max_consecutive_llm_failures = int(fm.get("max_consecutive_llm_failures") or 3)
                        except Exception:
                            pass

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
            raise ValueError("No team stages configured. Please create a team first.")

        max_tokens = int(os.getenv("AIPLAT_BUILDER_MAX_TOKENS", "100000"))
        max_retry = int(os.getenv("AIPLAT_BUILDER_MAX_RETRY", "3"))
        config = PipelineConfig(stages=stages, max_tokens_per_run=max_tokens, max_retry_attempts=max_retry)
        engine = PipelineEngine(config, self._model, skill_loader=_create_skill_loader())
        self._engines[project_id] = engine

        prd_data = proj.get("confirmed_prd")
        if not prd_data:
            chat_svc = getattr(self, '_chat_svc', {}).get(project_id)
            if chat_svc:
                chat_session = chat_svc._sessions.get(project_id, {})
                prd_data = chat_session.get("prd")

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
            state = await engine.initialize(project_id, requirement, prd_data=prd_data)
            tr = state.get("test_report") or {}
            run_record = proj["runs"][-1]
            run_record["phase"] = state.get("phase", "done")
            run_record["pass_rate"] = tr.get("pass_rate", 0)
            run_record["tokens_used"] = state.get("tokens_used", 0)
            run_record["iteration"] = state.get("iteration", 0)
            run_record["error"] = state.get("error", "")
            self._runs[project_id] = state
            # Persist pipeline state so approve works after restart
            self._save_pipeline_state(project_id, state)
        except Exception as e:
            run_record = proj["runs"][-1]
            run_record["error"] = str(e)[:200]
            run_record["phase"] = "failed"
            self._runs[project_id] = {"phase": "failed", "error": str(e)[:200]}
        finally:
            proj["updated_at"] = time.strftime("%Y-%m-%dT%H:%M:%S")
            self._save_projects()

        return {"project_id": project_id, "phase": state.get("phase", "executing"), "run_id": run_id,
                "state": state}

    async def _save_state(self, project_id: str, state: dict):
        """Save pipeline state and trigger deploy assembly if completed."""
        self._runs[project_id] = state
        self._save_pipeline_state(project_id, state)
        tr = state.get("test_report") or {}
        if state.get("phase") == "done" or tr.get("recommendation") == "APPROVED":
            engine = self._engines.get(project_id)
            if engine:
                deploy_dir = engine.assemble_deploy(state)
                if deploy_dir:
                    self._projects.setdefault(project_id, {})["deploy_dir"] = deploy_dir
                    self._save_projects()

    async def approve_stage(self, project_id: str) -> Dict[str, Any]:
        engine = self._engines.get(project_id)
        if not engine:
            engine = self._rebuild_engine(project_id)
            if not engine:
                raise ValueError("no engine")
        state = self._runs.get(project_id)
        if not state:
            state = self._load_pipeline_state(project_id)
            if not state:
                raise ValueError("no pipeline state")
        state = await engine.approve(dict(state))
        await self._save_state(project_id, state)
        return {"project_id": project_id, "phase": state.get("phase", "executing")}

    async def start_fix(self, project_id: str) -> Dict[str, Any]:
        engine = self._engines.get(project_id)
        if not engine:
            engine = self._rebuild_engine(project_id)
            if not engine:
                raise ValueError("no engine")
        state = self._runs.get(project_id)
        if not state:
            state = self._load_pipeline_state(project_id)
            if not state:
                raise ValueError("no pipeline state")
        state = dict(state)
        state["phase"] = "executing"
        state = await engine.approve(state)
        await self._save_state(project_id, state)
        return {"project_id": project_id, "phase": state.get("phase", "executing")}

    async def reject_stage(self, project_id: str, feedback: str) -> Dict[str, Any]:
        engine = self._engines.get(project_id)
        if not engine:
            engine = self._rebuild_engine(project_id)
            if not engine:
                raise ValueError("no engine")
        state = self._runs.get(project_id)
        if not state:
            state = self._load_pipeline_state(project_id)
            if not state:
                raise ValueError("no pipeline state")
        state = await engine.reject(dict(state), feedback)
        await self._save_state(project_id, state)
        return {"project_id": project_id, "phase": state.get("phase", "executing")}

    async def rollback_stage(self, project_id: str, stage_id: str) -> Dict[str, Any]:
        engine = self._engines.get(project_id)
        if not engine:
            engine = self._rebuild_engine(project_id)
            if not engine:
                raise ValueError("no engine")
        state = self._runs.get(project_id)
        if not state:
            state = self._load_pipeline_state(project_id)
            if not state:
                raise ValueError("no pipeline state")
        target_id = stage_id
        for s in engine._config.stages:
            if s.output_artifact == stage_id or s.agent_id == stage_id:
                target_id = s.id
                break
        state = await engine.rollback(dict(state), target_id)
        await self._save_state(project_id, state)
        return {"project_id": project_id, "phase": state.get("phase", "executing")}

    async def rollback_prd(self, project_id: str) -> Dict[str, Any]:
        """Roll back to PRD editing phase"""
        proj = self._projects.get(project_id, {})
        proj["confirmed_prd"] = None
        self._save_projects()
        self._runs[project_id] = {}
        self._engines.pop(project_id, None)
        return {"project_id": project_id, "phase": "dialogue"}

    async def get_deploy_dir(self, project_id: str) -> Optional[str]:
        """Get deploy directory path for a project."""
        proj = self._projects.get(project_id, {})
        return proj.get("deploy_dir") or None

    async def get_project_state(self, project_id: str) -> Dict[str, Any]:
        state = self._runs.get(project_id)
        if not state or state.get("phase") == "failed":
            persisted = self._load_pipeline_state(project_id)
            if persisted:
                self._runs[project_id] = persisted  # recovery
                state = persisted
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

    # ── Pipeline state persistence ─────────────────────────────────

    def _save_pipeline_state(self, project_id: str, state: Dict[str, Any]) -> None:
        proj = self._projects.get(project_id, {})
        if proj:
            proj["pipeline_state"] = dict(state)
            self._save_projects()

    def _load_pipeline_state(self, project_id: str) -> Optional[Dict[str, Any]]:
        proj = self._projects.get(project_id, {})
        return proj.get("pipeline_state")

    def _rebuild_engine(self, project_id: str) -> Optional[Any]:
        """Rebuild PipelineEngine and state from persisted project data (for crash recovery)."""
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

        # Read config from AGENT.md for each stage
        for s in stages:
            try:
                agent_md = os.path.join(os.path.expanduser("~/.aiplat"), "agents", s.agent_id, "AGENT.md")
                if not os.path.exists(agent_md):
                    continue
                import yaml
                with open(agent_md, "r") as f:
                    raw = f.read()
                if not raw.startswith("---"):
                    continue
                parts = raw.split("---", 2)
                if len(parts) < 3:
                    continue
                fm = yaml.safe_load(parts[1]) or {}
                if fm.get("auto_hitl"):
                    s.hitl = True
                    s.hitl_phase = s.hitl_phase or ("awaiting_architecture_approval" if fm.get("phase") == "design" else "awaiting_test_plan_approval")
                elif not fm.get("auto_hitl"):
                    s.hitl = False
                    s.hitl_phase = ""
                if fm.get("hitl_after_execute"):
                    s.hitl_after_execute = fm["hitl_after_execute"]
                    s.hitl_after_phase = fm.get("hitl_after_phase") or ""
                s.generate_test_plan = fm.get("generate_test_plan", s.generate_test_plan if hasattr(s, 'generate_test_plan') else False)
                if not getattr(s, 'test_result_key', None):
                    s.test_result_key = fm.get("test_result_key") or "test_report"
                if not getattr(s, 'uses_code_skill', None):
                    s.uses_code_skill = fm.get("uses_code_skill", s.uses_code_skill if hasattr(s, 'uses_code_skill') else False)
                if not getattr(s, 'code_target', None):
                    s.code_target = fm.get("code_target") or "backend"
                if not getattr(s, 'prompt_extra', None):
                    s.prompt_extra = fm.get("prompt_extra") or ""
                if not s.phase_description:
                    s.phase_description = fm.get("phase_description", "") or ""
                if not getattr(s, 'failure_strategy', None):
                    s.failure_strategy = fm.get("failure_strategy") or "fail_pipeline"
                if not getattr(s, 'fallback_result_key', None):
                    s.fallback_result_key = fm.get("fallback_result_key") or ""
                if not getattr(s, 'retry_llm_on_rate_limit', None) and fm.get("retry_llm_on_rate_limit") is not None:
                    s.retry_llm_on_rate_limit = bool(fm["retry_llm_on_rate_limit"])
                if not getattr(s, 'max_consecutive_llm_failures', None):
                    s.max_consecutive_llm_failures = int(fm.get("max_consecutive_llm_failures") or 3)
            except Exception:
                pass

        if not stages:
            return None

        max_tokens = int(os.getenv("AIPLAT_BUILDER_MAX_TOKENS", "100000"))
        max_retry = int(os.getenv("AIPLAT_BUILDER_MAX_RETRY", "3"))
        config = PipelineConfig(stages=stages, max_tokens_per_run=max_tokens, max_retry_attempts=max_retry)
        engine = PipelineEngine(config, self._model, skill_loader=_create_skill_loader())
        self._engines[project_id] = engine
        return engine
