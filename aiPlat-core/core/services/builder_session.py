"""
Builder session service — manages requirement-driven development sessions.

Handles:
  - PM multi-turn dialogue
  - PRD confirmation / locking
  - Pipeline execution with HITL approval phases
  - State retrieval for frontend polling
"""

from __future__ import annotations

import json
import os
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
from core.harness.execution.pipeline_engine import PipelineEngine
from core.apps.agents.builder_roles import get_role_system_prompt


class BuilderSessionService:

    def __init__(self, model: Any = None, execution_store: Any = None):
        self._model = model
        self._sessions: Dict[str, Dict[str, Any]] = {}
        self._engines: Dict[str, PipelineEngine] = {}

    def _get_or_create_engine(self, session_id: str, max_tokens: int = 100000,
                               stages_override: Optional[List[Any]] = None) -> PipelineEngine:
        if session_id not in self._engines:
            from core.schemas_builder import PipelineConfig, PipelineStageConfig
            if stages_override:
                stages = stages_override
            else:
                raise ValueError("No team stages configured. Use /workspace/teams to create a team first.")
            config = PipelineConfig(stages=stages, max_tokens_per_run=max_tokens)
            engine = PipelineEngine(config, self._model)
            self._engines[session_id] = engine
        return self._engines[session_id]

    def _update_session_from_state(self, session_id: str, state: Dict[str, Any]) -> None:
        session = self._sessions.get(session_id)
        if not session:
            return
        session["phase"] = state.get("phase", session["phase"])
        session["architecture"] = state.get("architecture")
        session["code"] = state.get("code")
        session["test_plan"] = state.get("test_plan")
        session["test_report"] = state.get("test_report")
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
            "prd": None, "architecture": None, "code": None,
            "test_plan": None, "test_report": None,
            "messages": [], "iteration": 0, "error": "",
            "tokens_used": 0, "tokens_budget": 0,
            "tenant_id": tenant_id, "user_id": user_id,
        }
        return session_id

    async def chat(self, session_id: str, message: str) -> BuilderChatResponse:
        session = self._sessions.get(session_id)
        if not session:
            raise ValueError(f"Session {session_id} not found")
        if session["phase"] != BuilderSessionPhase.dialogue.value:
            raise ValueError("not in dialogue phase")
        session["messages"].append({"role": "user", "content": message})
        pm_prompt = get_role_system_prompt("pm_agent")
        conversation = session["messages"][-10:]
        full_prompt = f"""{pm_prompt}

## 会话历史
{json.dumps(conversation, ensure_ascii=False, indent=2)}

## 原始需求
{session.get("requirement", "")}

请基于以上对话继续。如果信息已充分，输出 PRD 草稿并附带 <!-- PRD_READY --> 标记。
"""
        reply = ""
        if self._model:
            from core.harness.syscalls.llm import sys_llm_generate
            try:
                response = await sys_llm_generate(self._model, [{"role": "user", "content": full_prompt}])
                if isinstance(response, str):
                    reply = response
                elif isinstance(response, dict):
                    reply = response.get("content", "") or response.get("message", "") or str(response)
                else:
                    reply = getattr(response, "content", "") or getattr(response, "message", "") or str(response)
            except Exception as e:
                import traceback
                print(f"[builder_session] LLM error: {e}")
                traceback.print_exc()
                reply = f"LLM调用失败：{e}"
        session["messages"].append({"role": "assistant", "content": reply})
        prd_ready = "<!-- PRD_READY -->" in str(reply)
        if prd_ready:
            draft = self._extract_prd_from_reply(reply)
            if draft:
                session["prd"] = draft
        return BuilderChatResponse(reply=reply, session_state=self._build_state(session_id), prd_ready=prd_ready)

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
            from core.services.builder_team_service import BuilderTeamService
            team_svc = BuilderTeamService(model=self._model)
            team = await team_svc.get_team(team_id)
            if team and team.stages:
                from core.schemas_builder import PipelineStageConfig
                stages_override = [
                    PipelineStageConfig(**s.model_dump()) if hasattr(s, 'model_dump') else PipelineStageConfig(**s)
                    for s in team.stages
                ]

        engine = self._get_or_create_engine(session_id, max_tokens=max_tokens, stages_override=stages_override)
        state = await engine.initialize(
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
        engine = self._get_or_create_engine(session_id)
        state = await engine.approve(dict(state))
        self._update_session_from_state(session_id, state)
        return self._build_state(session_id)

    async def reject_architecture(self, session_id: str, feedback: str) -> BuilderSessionStateResponse:
        session = self._sessions.get(session_id)
        if not session:
            raise ValueError("session not found")
        state = session.get("_pipeline_state")
        if not state:
            raise ValueError("no pipeline state")
        engine = self._get_or_create_engine(session_id)
        state = await engine.reject(dict(state), feedback)
        self._update_session_from_state(session_id, state)
        return self._build_state(session_id)

    async def approve_test_plan(self, session_id: str) -> BuilderSessionStateResponse:
        session = self._sessions.get(session_id)
        if not session:
            raise ValueError("session not found")
        state = session.get("_pipeline_state")
        if not state:
            raise ValueError("no pipeline state")
        engine = self._get_or_create_engine(session_id)
        state = await engine.approve(dict(state))
        self._update_session_from_state(session_id, state)
        return self._build_state(session_id)

    async def reject_test_plan(self, session_id: str, feedback: str) -> BuilderSessionStateResponse:
        session = self._sessions.get(session_id)
        if not session:
            raise ValueError("session not found")
        state = session.get("_pipeline_state")
        if not state:
            raise ValueError("no pipeline state")
        engine = self._get_or_create_engine(session_id)
        state = await engine.reject(dict(state), feedback)
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
            except Exception: return None

        return BuilderSessionStateResponse(
            session_id=session_id,
            phase=BuilderSessionPhase(session["phase"]),
            requirement=session.get("requirement", ""),
            prd=_safe_construct(PRDArtifact, session.get("prd")),
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

    @staticmethod
    def _extract_json(s: str) -> str:
        start = s.find("{")
        if start < 0:
            return "{}"
        depth, in_str, esc = 0, False, False
        for i in range(start, len(s)):
            ch = s[i]
            if in_str:
                if esc: esc = False
                elif ch == '\\': esc = True
                elif ch == '"': in_str = False
            else:
                if ch == '"': in_str = True
                elif ch == '{': depth += 1
                elif ch == '}':
                    depth -= 1
                    if depth == 0:
                        return s[start:i + 1]
        return "{}"

    def _extract_prd_from_reply(self, reply: str) -> Optional[Dict[str, Any]]:
        try:
            return json.loads(self._extract_json(reply))
        except (json.JSONDecodeError, Exception):
            return {"title": reply.split("\n")[0] if "\n" in reply else reply[:100],
                    "overview": reply[:500], "user_stories": [], "constraints": [], "scope": "组合"}

