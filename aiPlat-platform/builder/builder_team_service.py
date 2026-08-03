"""
Builder team service — team CRUD + file persistence + execution via CoreFacade PipelineSession.
"""

from __future__ import annotations
import logging

import json
import os
import time
import uuid
from typing import Any, Dict, List, Optional

from core.schemas_builder import (
    BuilderSessionPhase,
    PipelineStageConfig,
    TeamConfig,
    TeamAssembleRequest,
)
from core.api.core_facade import create_pipeline_session  # changed from create_pipeline_engine

_TEAMS_FILE = os.path.join(
    os.path.expanduser(os.getenv("AIPLAT_HOME", "~/.aiplat")),
    "teams.json",
)


class BuilderTeamService:

    def __init__(self, model: Any = None):
        self._model = model
        self._teams: Dict[str, TeamConfig] = {}
        self._sessions: Dict[str, Any] = {}
        self._runs: Dict[str, Dict[str, Any]] = {}
        self._load_teams()

    # ── Persistence ──────────────────────────────────────────────────

    def _load_teams(self) -> None:
        try:
            if os.path.exists(_TEAMS_FILE):
                with open(_TEAMS_FILE, "r", encoding="utf-8") as f:
                    data = json.load(f)
                for item in data.get("teams", []):
                    team = TeamConfig(**item)
                    self._teams[team.team_id] = team
        except Exception as e:
            logging.debug(str(e), exc_info=True)

    def _save_teams(self) -> None:
        try:
            os.makedirs(os.path.dirname(_TEAMS_FILE), exist_ok=True)
            data = {
                "teams": [t.model_dump() if hasattr(t, "model_dump") else t for t in self._teams.values()],
                "updated_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
            }
            tmp = _TEAMS_FILE + ".tmp"
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            os.replace(tmp, _TEAMS_FILE)
        except Exception as e:
            logging.debug(str(e), exc_info=True)

    # ── CRUD ─────────────────────────────────────────────────────────

    async def create_team(self, req: TeamAssembleRequest) -> TeamConfig:
        team_id = f"team_{uuid.uuid4().hex[:8]}"
        stages_raw = [s.model_dump() if hasattr(s, 'model_dump') else s for s in req.stages]
        team = TeamConfig(
            team_id=team_id,
            name=req.name or f"团队 {team_id}",
            description=req.description,
            stages=stages_raw,
            max_tokens_per_run=req.max_tokens_per_run,
        )
        self._teams[team_id] = team
        self._save_teams()
        return team

    async def list_teams(self) -> List[TeamConfig]:
        return list(self._teams.values())

    def reload_teams(self) -> None:
        """Reload team configs from disk. Called when YAML configs change (e.g., new stages added to default.yaml)."""
        self._load_teams()

    async def get_team(self, team_id: str) -> Optional[TeamConfig]:
        return self._teams.get(team_id)

    async def update_team(self, team_id: str, req: TeamAssembleRequest) -> Optional[TeamConfig]:
        if team_id not in self._teams:
            return None
        existing = self._teams[team_id]
        self._teams[team_id] = TeamConfig(
            team_id=team_id,
            name=req.name or existing.name,
            description=req.description or existing.description,
            stages=req.stages,
            max_tokens_per_run=req.max_tokens_per_run or existing.max_tokens_per_run,
            created_at=existing.created_at,
            updated_at=time.strftime("%Y-%m-%dT%H:%M:%S"),
        )
        self._save_teams()
        return self._teams[team_id]

    async def delete_team(self, team_id: str) -> bool:
        if team_id in self._teams:
            del self._teams[team_id]
            self._save_teams()
            return True
        return False

    async def run_team(self, team_id: str, description: str = "",
                       prd_data: Optional[Dict] = None) -> Dict[str, Any]:
        team = self._teams.get(team_id)
        if not team:
            raise ValueError(f"Team {team_id} not found")

        from core.schemas_builder import PipelineConfig
        config = PipelineConfig(
            stages=team.stages,
            max_iterations=team.max_iterations,
            max_tokens_per_run=team.max_tokens_per_run,
            max_stagnation=team.max_stagnation,
        )
        session = create_pipeline_session(config=config, model=self._model)
        self._sessions[team_id] = session

        state = await session.start(team_id, description, prd_data)
        self._runs[team_id] = state
        return {"team_id": team_id, "phase": state.get("phase"), "state": state}

    async def approve_stage(self, team_id: str) -> Dict[str, Any]:
        session = self._sessions.get(team_id)
        if not session:
            raise ValueError("no session")
        state = self._runs.get(team_id, {})
        state = await session.approve(dict(state))
        self._runs[team_id] = state
        return {"team_id": team_id, "phase": state.get("phase"), "state": state}

    async def reject_stage(self, team_id: str, feedback: str) -> Dict[str, Any]:
        session = self._sessions.get(team_id)
        if not session:
            raise ValueError("no session")
        state = self._runs.get(team_id, {})
        state = await session.reject(dict(state), feedback)
        self._runs[team_id] = state
        return {"team_id": team_id, "phase": state.get("phase"), "state": state}

    async def get_team_state(self, team_id: str) -> Dict[str, Any]:
        return self._runs.get(team_id, {"team_id": team_id, "phase": "unknown"})
