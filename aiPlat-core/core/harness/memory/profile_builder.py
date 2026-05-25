"""
ProfileBuilder — background memory review that extracts user/team preferences.

Design principle (Hermes Agent architecture, run_agent.py:2423-2456):
  After the agent loop completes, a background task reviews the conversation
  and extracts facts about the user, team, or project. The profile is persisted
  in SemanticMemory and injected into future context builds.

Threshold: _iters_since_memory >= _MEMORY_NUDGE_INTERVAL (default 10).
"""

from __future__ import annotations

import asyncio
import json
import logging
import re
import os
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

_log = logging.getLogger("pipeline_engine.profile_builder")

_MEMORY_REVIEW_PROMPT = (
    "Review the conversation above and extract facts about the user, team, or project.\n\n"
    "Extract ONLY clear, explicit information — do not guess or infer.\n"
    "Output JSON with these keys:\n"
    "- preferences: technical choices they prefer or avoid (list of strings)\n"
    "- constraints: team size, budget, timeline restrictions (list of strings)\n"
    "- decisions: things they explicitly approved or rejected (list of strings)\n"
    "- work_style: brief description of how they work (string)\n\n"
    'Example: {"preferences":["React","TypeScript"],"constraints":["team of 3"],"decisions":["rejected microservices"],"work_style":"iterate fast, refine later"}\n\n'
    "If nothing new is learned beyond what's already known, output empty lists:\n"
    '{"preferences":[],"constraints":[],"decisions":[],"work_style":""}'
)

_MEMORY_NUDGE_INTERVAL = 10

MEMORY_PROFILE_TAG = "user_profile"


@dataclass
class UserProfile:
    preferences: List[str] = field(default_factory=list)
    constraints: List[str] = field(default_factory=list)
    decisions: List[str] = field(default_factory=list)
    work_style: str = ""
    updated_at: float = 0.0

    def is_empty(self) -> bool:
        return not any([self.preferences, self.constraints, self.decisions, self.work_style])

    def to_system_message(self) -> str:
        if self.is_empty():
            return ""
        parts = ["## User Profile (auto-extracted)"]
        if self.preferences:
            parts.append("- Preferences: " + ", ".join(self.preferences))
        if self.constraints:
            parts.append("- Constraints: " + ", ".join(self.constraints))
        if self.decisions:
            parts.append("- Prior Decisions: " + ", ".join(self.decisions))
        if self.work_style:
            parts.append(f"- Work Style: {self.work_style}")
        return "\n".join(parts)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "UserProfile":
        return cls(
            preferences=[str(x) for x in data.get("preferences", []) if x],
            constraints=[str(x) for x in data.get("constraints", []) if x],
            decisions=[str(x) for x in data.get("decisions", []) if x],
            work_style=str(data.get("work_style", "") or "").strip(),
            updated_at=float(data.get("updated_at", 0) or 0),
        )

    def to_dict(self) -> Dict[str, Any]:
        return {
            "preferences": self.preferences,
            "constraints": self.constraints,
            "decisions": self.decisions,
            "work_style": self.work_style,
            "updated_at": self.updated_at,
        }


def get_nudge_interval() -> int:
    v = os.getenv("AIPLAT_MEMORY_NUDGE_INTERVAL", "")
    return int(v) if v.isdigit() and int(v) > 0 else _MEMORY_NUDGE_INTERVAL


def _extract_json(text: str) -> Optional[Dict[str, Any]]:
    m = re.search(r'\{[^{}]*"preferences"[^{}]*\}', text, re.DOTALL)
    if not m:
        m = re.search(r'\{[^{}]*\}', text, re.DOTALL)
    if m:
        try:
            return json.loads(m.group(0))
        except json.JSONDecodeError:
            pass
    return None


async def _run_profile_extraction(conversation_summary: str) -> Optional[UserProfile]:
    try:
        from core.harness.execution.loop import ReActLoop
        from core.harness.interfaces.loop import LoopConfig, LoopState, LoopStateEnum
        loop = ReActLoop(
            config=LoopConfig(max_steps=5, max_tokens=4096, model_name="eval"),
            model=None,
            tools=[],
            skills=[],
        )
        prompt = f"{_MEMORY_REVIEW_PROMPT}\n\n{conversation_summary}"
        loop_state = LoopState(
            current=LoopStateEnum.INIT,
            context={
                "task": prompt,
                "messages": [],
                "_session_id": "profile-review",
                "_user_id": "system",
            },
        )
        result = await loop.run(loop_state, LoopConfig(max_steps=5))
        output = result.final_state.context.get("output", "") or ""
        raw = result.output if hasattr(result, 'output') and result.output else output
        data = _extract_json(str(raw))
        if data:
            profile = UserProfile.from_dict(data)
            if not profile.is_empty():
                return profile
    except Exception as e:
        _log.debug("profile_extraction best-effort skipped: %s", e)
    return None


async def extract_and_persist_profile(
    state: Dict[str, Any], memory_manager: Any = None
) -> Optional[Dict[str, Any]]:
    try:
        summary = build_stage_summary(state)
    except Exception:
        summary = str(state.get("task", ""))[:3000]
    profile = await _run_profile_extraction(summary)
    if not profile:
        return None
    import time
    profile.updated_at = time.time()
    if memory_manager and hasattr(memory_manager, 'capture_to_semantic'):
        try:
            await memory_manager.capture_to_semantic(
                content=json.dumps(profile.to_dict(), ensure_ascii=False),
                metadata={
                    "tag": MEMORY_PROFILE_TAG,
                    "updated_at": profile.updated_at,
                },
            )
        except Exception:
            pass
    log_data = {
        "preferences": len(profile.preferences),
        "constraints": len(profile.constraints),
        "decisions": len(profile.decisions),
    }
    _log.info("profile_extracted: %s", log_data)
    return profile.to_dict()


# ── Shared utilities: stage summary builder + skill review (moved from apps/skills/background_review
#    to fix harness→apps boundary violation per CLAUDE.md §11) ──

def build_stage_summary(state: Dict[str, Any]) -> str:
    parts = []
    task = state.get("task", "")
    if task: parts.append(f"## Task\n{task[:2000]}")
    stage_id = state.get("_agent_id", "")
    if stage_id: parts.append(f"## Agent\n{stage_id}")
    steps = state.get("step_count", 0)
    if steps: parts.append(f"## Steps\n{steps} reasoning steps")
    ctx_asm = state.get("_context_assembly") or {}
    for layer, label in [("working", "Working"), ("episodic", "Episodic"), ("semantic", "Semantic")]:
        txt = ctx_asm.get(layer, "")
        if txt:
            cap = 1500 if layer != "semantic" else 1000
            parts.append(f"### {label}\n{str(txt)[:cap]}")
    errors = state.get("_stage_error", "")
    if errors: parts.append(f"## Errors\n{str(errors)[:500]}")
    return "\n".join(parts)


async def run_skill_review(state: Dict[str, Any]) -> Dict[str, Any]:
    try:
        from core.harness.execution.loop import ReActLoop
        from core.harness.interfaces.loop import LoopConfig, LoopState, LoopStateEnum
        prompt = (
            "Review the stage execution above and consider saving a reusable approach as a skill.\n\n"
            "Focus on:\n"
            "- Was a non-trivial, multi-step approach used?\n"
            "- Did execution require trial-and-error or format corrections?\n"
            "- Would this approach be useful in future similar tasks?\n\n"
            "If a relevant skill already exists, update it. Otherwise create a new one.\n"
            "If nothing is worth saving, respond 'Nothing to save.'"
        )
        loop = ReActLoop(
            config=LoopConfig(max_steps=8, max_tokens=4096, model_name="eval"),
            model=None, tools=[], skills=[],
        )
        loop_state = LoopState(
            current=LoopStateEnum.INIT,
            context={"task": f"{prompt}\n\n{build_stage_summary(state)}", "messages": [], "_session_id": "skill-review", "_user_id": "system"},
        )
        result = await loop.run(loop_state, LoopConfig(max_steps=8))
        output = result.final_state.context.get("output", "") or ""
        saved = "created" if "new skill" in output.lower() else ""
        updated = "updated" if "update" in output.lower() or "patch" in output.lower() else ""
        return {"action": saved or updated or "no_action", "saved": bool(saved), "updated": bool(updated), "output_preview": output[:300]}
    except Exception:
        return {"action": "error"}
