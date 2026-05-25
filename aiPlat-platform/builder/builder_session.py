"""
@deprecated — Builder session service. Replaced by BuilderProjectService.
All API routes now use BuilderProjectService (project-based, per-project state files).
This file is retained for reference only. Not wired to any router.
Use builder_project_service.py for all new development.
"""
from __future__ import annotations

import json
import os
import re
import uuid
from typing import Any, Dict, List, Optional

from core.schemas_builder import (
    BuilderSessionPhase,
    AgentConfidence,
    AgentDecision,
    TestRecommendation,
    PRDArtifact,
    ArchitectureArtifact,
    CodeArtifact,
    TestReport,
    Issue,
    BuilderSessionStateResponse,
    BuilderChatResponse,
    UserStory,
)
from core.api.core_facade import create_pipeline_session, extract_json
from core.api.intents import core_chat, ChatContext


class BuilderSessionService:

    def __init__(self, model: Any = None, execution_store: Any = None):
        self._model = model
        self._sessions: Dict[str, Dict[str, Any]] = {}
        self._pipeline_sessions: Dict[str, Any] = {}
        try:
            from core.api.core_facade import seed_all_registries
            seed_all_registries()
        except Exception:
            pass

    async def _restore_chat_history(self, session_id: str) -> List[Dict[str, str]]:
        """Restore conversation history from MemoryManager (survives restart)."""
        try:
            from core.api.core_facade import get_memory_manager as _mem
            mgr = _mem()
            ctx = await mgr.build_context(current_query="", system_prompt="")
            if ctx and isinstance(ctx, dict):
                return ctx.get("messages") or ctx.get("history") or []
        except Exception:
            pass
        return []

    def _get_or_create_session(self, session_id: str, max_tokens: int = 100000,
                                stages_override: Optional[List[Any]] = None):
        if session_id not in self._pipeline_sessions:
            from core.schemas_builder import PipelineConfig, PipelineStageConfig
            if stages_override:
                stages = stages_override
            else:
                raise ValueError("No team stages configured. Use /workspace/teams to create a team first.")
            config = PipelineConfig(stages=stages, max_tokens_per_run=max_tokens,
                                    max_retry_attempts=int(os.getenv("AIPLAT_BUILDER_MAX_RETRY", "3")))
            session = create_pipeline_session(config, self._model)
            self._pipeline_sessions[session_id] = session
        return self._pipeline_sessions[session_id]

    def _update_session_from_state(self, session_id: str, state: Dict[str, Any]) -> None:
        session = self._sessions.get(session_id)
        if not session:
            return
        session["phase"] = state.get("phase", session["phase"])
        for k in state:
            if k.startswith("_"):
                continue
            v = state.get(k)
            if isinstance(v, dict) and v:
                session[k] = v
        session["iteration"] = state.get("iteration", 0)
        session["error"] = state.get("error", "")
        session["output_dir"] = state.get("output_dir", "")
        session["tokens_used"] = state.get("tokens_used", 0)
        session["tokens_budget"] = state.get("tokens_budget", 0)
        session["_pipeline_state"] = state

    async def create_session(self, requirement: str = "", tenant_id: str = "", user_id: str = "") -> str:
        session_id = f"bs_{uuid.uuid4().hex[:12]}"
        self._sessions[session_id] = {
            "session_id": session_id,
            "phase": BuilderSessionPhase.dialogue.value,
            "requirement": requirement,
            "artifacts": {},
            "messages": [], "iteration": 0, "error": "",
            "tokens_used": 0, "tokens_budget": 0,
            "tenant_id": tenant_id, "user_id": user_id,
        }
        return session_id

    async def chat(self, session_id: str, message: str) -> BuilderChatResponse:
        session = self._sessions.get(session_id)
        if not session:
            raise ValueError(f"Session {session_id} not found")
        if not isinstance(session, dict):
            raise ValueError("not in dialogue phase")
        if session.get("phase") != BuilderSessionPhase.dialogue.value:
            raise ValueError("not in dialogue phase")

        # Restore conversation history from MemoryManager on first access (survives restart)
        if not session.get("messages") and not session.get("_history_restored"):
            restored = await self._restore_chat_history(session_id)
            if restored:
                session["messages"] = list(restored)
            session["_history_restored"] = True

        session["messages"].append({"role": "user", "content": message})

        result = await core_chat(ChatContext(
            agent_name="pm_agent",
            session_id=session_id,
            user_input=message,
            model=self._model,
        ))

        reply = result.reply
        session["messages"].append({"role": "assistant", "content": reply})
        prd_ready = "<!-- PRD_READY -->" in str(reply)
        if prd_ready:
            draft = self._extract_prd_from_reply(reply)
            if draft:
                session["prd"] = draft
        return BuilderChatResponse(
            reply=reply,
            session_state=self._build_state(session_id),
            prd_ready=prd_ready,
            trace_id=result.trace_id,
        )

    async def confirm_requirements(self, session_id: str) -> BuilderSessionStateResponse:
        session = self._sessions.get(session_id)
        if not session:
            raise ValueError(f"Session {session_id} not found")
        if not session.get("prd"):
            raise ValueError("No PRD to confirm")
        session["phase"] = BuilderSessionPhase.executing.value
        return self._build_state(session_id)

    async def start_pipeline(self, session_id: str, team_id: str = "") -> BuilderSessionStateResponse:
        session = self._sessions.get(session_id)
        if not session:
            raise ValueError(f"Session {session_id} not found")
        prd_data = session.get("prd")
        if not prd_data:
            raise ValueError("No PRD available")
        prd = PRDArtifact(**prd_data) if isinstance(prd_data, dict) else prd_data
        max_tokens = int(os.getenv("AIPLAT_BUILDER_MAX_TOKENS", "100000"))

        stages_override = None
        if team_id:
            from builder.builder_team_service import BuilderTeamService
            team_svc = BuilderTeamService(model=self._model)
            team = await team_svc.get_team(team_id)
            if team and team.stages:
                from core.schemas_builder import PipelineStageConfig
                stages_override = [
                    PipelineStageConfig(**s.model_dump()) if hasattr(s, 'model_dump') else PipelineStageConfig(**s)
                    for s in team.stages
                ]

        pipeline = self._get_or_create_session(session_id, max_tokens=max_tokens, stages_override=stages_override)
        state = await pipeline.start(
            session_id,
            requirement=session.get("requirement", ""),
            prd_data=prd.model_dump() if hasattr(prd, 'model_dump') else prd_data,
        )
        self._update_session_from_state(session_id, state)
        return self._build_state(session_id)

    async def approve_architecture(self, session_id: str) -> BuilderSessionStateResponse:
        session = self._sessions.get(session_id)
        if not session:
            raise ValueError("session not found")
        state = session.get("_pipeline_state")
        if not state:
            raise ValueError("no pipeline state")
        pipeline = self._get_or_create_session(session_id)
        state = await pipeline.approve(dict(state))
        self._update_session_from_state(session_id, state)
        return self._build_state(session_id)

    async def reject_architecture(self, session_id: str, feedback: str) -> BuilderSessionStateResponse:
        session = self._sessions.get(session_id)
        if not session:
            raise ValueError("session not found")
        state = session.get("_pipeline_state")
        if not state:
            raise ValueError("no pipeline state")
        pipeline = self._get_or_create_session(session_id)
        state = await pipeline.reject(dict(state), feedback)
        self._update_session_from_state(session_id, state)
        return self._build_state(session_id)

    async def approve_test_plan(self, session_id: str) -> BuilderSessionStateResponse:
        session = self._sessions.get(session_id)
        if not session:
            raise ValueError("session not found")
        state = session.get("_pipeline_state")
        if not state:
            raise ValueError("no pipeline state")
        pipeline = self._get_or_create_session(session_id)
        state = await pipeline.approve(dict(state))
        self._update_session_from_state(session_id, state)
        return self._build_state(session_id)

    async def reject_test_plan(self, session_id: str, feedback: str) -> BuilderSessionStateResponse:
        session = self._sessions.get(session_id)
        if not session:
            raise ValueError("session not found")
        state = session.get("_pipeline_state")
        if not state:
            raise ValueError("no pipeline state")
        pipeline = self._get_or_create_session(session_id)
        state = await pipeline.reject(dict(state), feedback)
        self._update_session_from_state(session_id, state)
        return self._build_state(session_id)

    async def get_state(self, session_id: str) -> BuilderSessionStateResponse:
        return self._build_state(session_id)

    def _build_state(self, session_id: str) -> BuilderSessionStateResponse:
        session = self._sessions.get(session_id)
        if not session:
            return BuilderSessionStateResponse(session_id=session_id, phase=BuilderSessionPhase.failed,
                                                error="Session not found")

        def _safe_construct(cls, data):
            try: return cls(**data) if data else None
            except Exception as e:
                import logging
                logging.getLogger("aiplat.builder").warning(
                    "Failed to construct %s from session data: %s", cls.__name__, str(e)[:200])
                return None

        return BuilderSessionStateResponse(
            session_id=session_id,
            phase=BuilderSessionPhase(session["phase"]),
            requirement=session.get("requirement", ""),
            prd=_safe_construct(PRDArtifact, session.get("prd")),
            # @backward-compat (KNOWN_DEBT): architecture/code/test_report are hardcoded artifact
            # keys tied to the standard PM→Arch→FE→BE→QA pipeline. New teams with different
            # output_artifact names will break here. Fix: redesign BuilderSessionStateResponse
            # to use a generic artifacts dict keyed by stage.output_artifact.
            architecture=_safe_construct(ArchitectureArtifact, session.get("architecture")),
            code=_safe_construct(CodeArtifact, session.get("code")),
            test_report=_safe_construct(TestReport, session.get("test_report")),
            messages=session.get("messages", []),
            iteration=session.get("iteration", 0),
            tokens_used=session.get("tokens_used", 0),
            tokens_budget=session.get("tokens_budget", 0),
            stagnation_count=session.get("_pipeline_state", {}).get("_stagnation_count", 0),
            error=session.get("error", ""),
        )

    def _extract_prd_from_reply(self, reply: str) -> Optional[Dict[str, Any]]:
        # Try JSON format first (backward compat)
        try:
            json_str = extract_json(reply)
            if json_str:
                prd = json.loads(json_str)
                missing = [f for f in ("user_stories", "scope") if not prd.get(f)]
                if not missing:
                    return prd
                # Also check for functional_requirements (alternate key)
                if prd.get("functional_requirements") and prd.get("title"):
                    return prd
        except (json.JSONDecodeError, Exception):
            pass

        # Markdown format: parse structured markdown as PRD dict
        if "## 项目名称" in reply or "## 项目背景" in reply:
            return self._parse_markdown_prd(reply)

        return None

    def _parse_markdown_prd(self, reply: str) -> Dict[str, Any]:
        """Parse structured Markdown PRD into a dict."""
        prd: Dict[str, Any] = {}

        # Extract sections by ## headings
        sections: Dict[str, str] = {}
        current_key = ""
        for line in reply.split("\n"):
            m = re.match(r"^## (.+)", line)
            if m:
                current_key = m.group(1).strip()
                sections[current_key] = ""
            elif current_key:
                sections[current_key] += line + "\n"

        # Title
        title_match = re.search(r"^# (.+)", reply, re.MULTILINE)
        if title_match:
            prd["title"] = title_match.group(1).strip()
            if prd["title"].startswith("项目名称："):
                prd["title"] = prd["title"][5:].strip()

        # Background
        bg = sections.get("项目背景", "").strip()
        if bg:
            prd["background"] = bg

        # Goal
        goal = sections.get("项目目标", "").strip()
        if goal:
            prd["goal"] = goal

        # User roles → list
        roles_section = sections.get("用户角色", "")
        user_stories = []
        for role_match in re.finditer(r"-\s*\*\*(.+?)\*\*[：:](.+)", roles_section or ""):
            user_stories.append({"role": role_match.group(1).strip(),
                                 "description": role_match.group(2).strip()})

        # Functional requirements
        func_section = sections.get("功能需求", "")
        fr_items = []
        for fr_match in re.finditer(
            r"###\s*(.+?)\n(.*?)(?=\n###|\n##|\Z)", func_section or "", re.DOTALL
        ):
            fr_name = fr_match.group(1).strip()
            fr_body = fr_match.group(2)
            user_story_match = re.search(r"用户故事[：:]\s*(.+)", fr_body)
            priority_match = re.search(r"优先级[：:]\s*(.+)", fr_body)
            acs = re.findall(r"AC\d+:\s*(.+)", fr_body)
            fr_items.append({
                "id": fr_name.split(":", 1)[0].strip() if ":" in fr_name else fr_name,
                "name": fr_name.split(":", 1)[1].strip() if ":" in fr_name else fr_name,
                "description": user_story_match.group(1).strip() if user_story_match else "",
                "acceptance_criteria": acs,
                "priority": priority_match.group(1).strip() if priority_match else "P0",
                "passes": False,
            })
        if fr_items:
            prd["functional_requirements"] = fr_items

        # Scope
        scope = sections.get("范围", "").strip()
        if scope:
            prd["scope"] = scope

        # Wrap in standard format for downstream compatibility
        if not prd.get("user_stories"):
            prd["user_stories"] = user_stories or fr_items

        return prd if prd.get("title") else None

