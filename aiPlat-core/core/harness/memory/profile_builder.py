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


def _get_memory_review_prompt() -> str:
    from core.harness.utils.prompt_loader import _sync_resolve
    return _sync_resolve("memory-review")


def _get_skill_review_prompt() -> str:
    from core.harness.utils.prompt_loader import _sync_resolve
    return _sync_resolve("memory-skill-review",
        stage_name="", agent_id="", output_summary="",
    ).split("\n\n", 1)[0]  # Get the prompt text without pre-filled variables

_MEMORY_NUDGE_INTERVAL = 10

MEMORY_PROFILE_TAG = "user_profile"


@dataclass
class UserProfile:
    preferences: List[str] = field(default_factory=list)
    constraints: List[str] = field(default_factory=list)
    decisions: List[str] = field(default_factory=list)
    work_style: str = ""
    updated_at: float = 0.0
    evidence_ids: List[str] = field(default_factory=list)
    prior_versions: List[Dict[str, Any]] = field(default_factory=list)

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

    def to_durable_message(self) -> str:
        """Stable prefs and constraints only. One-task decisions stay out of every turn."""
        from core.harness.memory.file_store import memory_content_is_fact

        prefs = [p for p in self.preferences if memory_content_is_fact(p)]
        constraints = [c for c in self.constraints if memory_content_is_fact(c)]
        style = self.work_style if memory_content_is_fact(self.work_style) else ""
        if not prefs and not constraints and not style:
            return ""
        parts = ["## User Profile (auto-extracted)"]
        if prefs:
            parts.append("- Preferences: " + ", ".join(prefs))
        if constraints:
            parts.append("- Constraints: " + ", ".join(constraints))
        if style:
            parts.append(f"- Work Style: {style}")
        if self.evidence_ids:
            parts.append("- Evidence: " + ", ".join(self.evidence_ids[:8]))
        return "\n".join(parts)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "UserProfile":
        return cls(
            preferences=[str(x) for x in data.get("preferences", []) if x],
            constraints=[str(x) for x in data.get("constraints", []) if x],
            decisions=[str(x) for x in data.get("decisions", []) if x],
            work_style=str(data.get("work_style", "") or "").strip(),
            updated_at=float(data.get("updated_at", 0) or 0),
            evidence_ids=[str(x) for x in (data.get("evidence_ids") or []) if str(x).strip()],
            prior_versions=[
                row for row in (data.get("prior_versions") or []) if isinstance(row, dict)
            ][:5],
        )

    def to_dict(self) -> Dict[str, Any]:
        return {
            "preferences": self.preferences,
            "constraints": self.constraints,
            "decisions": self.decisions,
            "work_style": self.work_style,
            "updated_at": self.updated_at,
            "evidence_ids": list(self.evidence_ids),
            "prior_versions": list(self.prior_versions)[-5:],
        }


def semantic_context_block(
    memories,
    *,
    limit: Optional[int] = None,
    max_chars: Optional[int] = None,
) -> str:
    """Query-matched semantic lines, cut by char budget (not a fixed top-k).

    ``limit`` is an optional safety cap. Profile rows and command lines stay out.
    """
    from core.harness.memory.file_store import durable_semantic_content, memory_char_budget

    budget = int(max_chars) if max_chars is not None else max(200, memory_char_budget() // 2)
    if budget <= 0:
        return ""
    header = "## Relevant Past Context\n"
    lines = []
    used = len(header)
    cap = int(limit) if limit is not None else 20
    for mem in memories or []:
        if len(lines) >= max(1, cap):
            break
        meta = getattr(mem, "metadata", None) or {}
        if isinstance(meta, dict) and str(meta.get("tag") or "") == MEMORY_PROFILE_TAG:
            continue
        raw = str(getattr(mem, "content", "") or "").strip()
        text = durable_semantic_content(raw[:500])
        if not text:
            continue
        snippet = " ".join(text.split())[:200]
        line = f"- {snippet}..."
        extra = len(line) + (1 if lines else 0)
        if used + extra > budget:
            break
        lines.append(line)
        used += extra
    if not lines:
        return ""
    return header + "\n".join(lines)


def sanitize_episodic_summary_text(summary: str) -> str:
    """Drop command/TODO lines from an episodic summary body (no header)."""
    from core.harness.memory.file_store import memory_content_is_fact

    text = (summary or "").strip()
    if not text:
        return ""
    kept = []
    for raw in text.replace("。", "。\n").splitlines():
        line = raw.strip()
        if not line:
            continue
        low = line.lower()
        if low.startswith("session with ") and "interaction" in low:
            continue
        if not memory_content_is_fact(line):
            continue
        body = line.split(":", 1)[-1].strip().strip(".") if ":" in line else line
        if body != line and not memory_content_is_fact(body):
            continue
        kept.append(line)
    return "\n".join(kept).strip()


def session_summary_block(summary: str) -> str:
    """Current-session summary with command lines removed."""
    body = sanitize_episodic_summary_text(summary)
    if not body:
        return ""
    return "## Session Summary\n" + body


def critical_episodes_block(episodes) -> str:
    """High-importance turns, minus commands and step lists."""
    from core.harness.memory.file_store import memory_content_is_fact

    lines = []
    for ep in episodes or []:
        if not isinstance(ep, dict):
            continue
        user = str(ep.get("user") or "")[:120].strip()
        assistant = str(ep.get("assistant") or "")[:120].strip()
        if user and not memory_content_is_fact(user):
            user = ""
        if assistant and not memory_content_is_fact(assistant):
            assistant = ""
        if not user and not assistant:
            continue
        ts = str(ep.get("timestamp") or "")[:19]
        parts = []
        if user:
            parts.append(f"[{ts}] User: {user}")
        if assistant:
            parts.append(f"[{ts}] Assistant: {assistant}")
        lines.append("\n".join(parts))
        if len(lines) >= 5:
            break
    if not lines:
        return ""
    return "## Critical Decisions (Preserved)\n" + "\n---\n".join(lines)


def get_nudge_interval() -> int:
    v = os.getenv("AIPLAT_MEMORY_NUDGE_INTERVAL", "")
    return int(v) if v.isdigit() and int(v) > 0 else _MEMORY_NUDGE_INTERVAL


def sanitize_user_profile(profile: UserProfile) -> UserProfile:
    """Drop commands/TODOs from durable fields. Decisions stay for audit only."""
    from core.harness.memory.file_store import memory_content_is_fact

    return UserProfile(
        preferences=[p for p in profile.preferences if memory_content_is_fact(p)][:8],
        constraints=[c for c in profile.constraints if memory_content_is_fact(c)][:8],
        decisions=[d for d in profile.decisions if d][:5],
        work_style=profile.work_style if memory_content_is_fact(profile.work_style) else "",
        updated_at=profile.updated_at,
        evidence_ids=list(profile.evidence_ids),
        prior_versions=list(profile.prior_versions)[-5:],
    )


def profile_evidence_ids(state: Optional[Dict[str, Any]]) -> List[str]:
    """Ids the caller already has. Empty means the observation must not be stored."""
    if not isinstance(state, dict):
        return []
    found: List[str] = []
    for key in ("evidence_ids", "_profile_evidence_ids"):
        raw = state.get(key)
        if isinstance(raw, list):
            found.extend(str(item).strip() for item in raw if str(item).strip())
    receipts = state.get("_tool_receipts")
    if isinstance(receipts, list):
        for index, row in enumerate(receipts):
            if isinstance(row, dict) and str(row.get("status") or "") == "ok":
                tool = str(row.get("tool") or "tool").strip() or "tool"
                found.append(f"receipt:{tool}:{index}")
    seen: List[str] = []
    for item in found:
        if item not in seen:
            seen.append(item)
    return seen[:12]


def _belief_body(data: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "preferences": list(data.get("preferences") or []),
        "constraints": list(data.get("constraints") or []),
        "work_style": str(data.get("work_style") or ""),
    }


def _belief_snapshot(data: Dict[str, Any]) -> Dict[str, Any]:
    snap = _belief_body(data)
    snap["evidence_ids"] = list(data.get("evidence_ids") or [])
    snap["updated_at"] = data.get("updated_at") or 0
    return snap


def revise_profile_observation(
    previous_content: Optional[str],
    profile: UserProfile,
    evidence_ids: List[str],
) -> Optional[Dict[str, Any]]:
    """Rewrite the current belief only when new evidence ids are present.

    The previous belief is appended to ``prior_versions`` (last 5). Same belief
    keeps the stored document. No ids → refuse, so a rewrite cannot land bare.
    """
    ids = [str(item).strip() for item in (evidence_ids or []) if str(item).strip()]
    if not ids:
        return None
    previous: Optional[Dict[str, Any]] = None
    if previous_content:
        try:
            parsed = json.loads(previous_content)
        except (json.JSONDecodeError, TypeError, ValueError):
            parsed = None
        if isinstance(parsed, dict):
            previous = parsed
    new_body = _belief_body({
        "preferences": profile.preferences,
        "constraints": profile.constraints,
        "work_style": profile.work_style,
    })
    if previous is not None and _belief_body(previous) == new_body:
        return previous
    prior_versions: List[Dict[str, Any]] = []
    if previous is not None:
        older = previous.get("prior_versions")
        if isinstance(older, list):
            prior_versions.extend(row for row in older if isinstance(row, dict))
        prior_versions.append(_belief_snapshot(previous))
        prior_versions = prior_versions[-5:]
    data = profile.to_dict()
    data["evidence_ids"] = ids[:12]
    data["prior_versions"] = prior_versions
    return data


def promote_durable_profile_facts(profile: UserProfile) -> Dict[str, Any]:
    """Session-end split: durable prefs → MEMORY.md (fact gate). Decisions stay out."""
    from core.harness.memory.file_store import write_memory

    written = 0
    skipped = 0
    for key, items in (
        ("preference", profile.preferences),
        ("constraint", profile.constraints),
    ):
        for text in items:
            if write_memory(str(text), key=key, source="profile"):
                written += 1
            else:
                skipped += 1
    if profile.work_style:
        if write_memory(profile.work_style, key="work_style", source="profile"):
            written += 1
        else:
            skipped += 1
    return {"written": written, "skipped": skipped}


def compose_sticky_memory(
    max_chars: Optional[int] = None, *, tenant_id: str = "default"
) -> Dict[str, Any]:
    """User profile + pinned MEMORY.md under one char budget. Pi sticky payload."""
    from core.harness.memory.file_store import memory_char_budget, pinned_memory_text

    tid = (tenant_id or "default").strip() or "default"
    budget = memory_char_budget() if max_chars is None else max(0, int(max_chars))
    profile_cap = min(600, max(0, budget // 2)) if budget else 0
    profile = (
        user_profile_sticky_text(max_chars=profile_cap, tenant_id=tid)
        if profile_cap
        else ""
    )
    used = len(profile) + (2 if profile else 0)
    pinned_budget = max(0, budget - used)
    pinned = (
        pinned_memory_text(max_chars=pinned_budget, tenant_id=tid)
        if pinned_budget
        else ""
    )
    parts = [p for p in (profile, pinned) if p]
    text = "\n\n".join(parts)
    return {
        "text": text,
        "chars": len(text),
        "budget": budget,
        "available": bool(text),
        "has_profile": bool(profile),
        "has_pinned": bool(pinned),
        "tenant_id": tid,
    }


def user_profile_sticky_text(max_chars: int = 600, *, tenant_id: str = "default") -> str:
    """Char-budgeted user profile for sticky / Pi session start. Empty when none."""
    budget = max(0, int(max_chars or 0))
    if budget <= 0:
        return ""
    try:
        from core.harness.memory.semantic import SemanticMemory
        import json as _json

        store = SemanticMemory(store_type="sqlite", tenant_id=tenant_id or "default")
        item = store.latest_by_tag(MEMORY_PROFILE_TAG)
        if item is None:
            return ""
        data = _json.loads(item.content) if isinstance(item.content, str) else item.content
        if not isinstance(data, dict):
            return ""
        msg = UserProfile.from_dict(data).to_durable_message()
        if not msg:
            return ""
        if len(msg) <= budget:
            return msg
        return msg[: max(0, budget - 1)].rstrip() + "…"
    except Exception:
        _log.debug("user_profile_sticky_text skipped", exc_info=True)
        return ""


def _extract_json(text: str) -> Optional[Dict[str, Any]]:
    m = re.search(r'\{[^{}]*"preferences"[^{}]*\}', text, re.DOTALL)
    if not m:
        m = re.search(r'\{[^{}]*\}', text, re.DOTALL)
    if m:
        try:
            return json.loads(m.group(0))
        except json.JSONDecodeError:
            pass  # noqa: cleanup-best-effort
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
        prompt = f"{_get_memory_review_prompt()}\n\n{conversation_summary}"
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
    profile = sanitize_user_profile(profile)
    if profile.is_empty():
        return None
    evidence = profile_evidence_ids(state)
    if not evidence:
        _log.info("profile_extracted skipped: observation has no evidence ids")
        return None
    profile.updated_at = time.time()
    previous_content = None
    if memory_manager is None:
        try:
            from core.harness.memory.manager import get_memory_manager
            ns = str((state or {}).get("session_id") or (state or {}).get("_session_id") or "default")
            memory_manager = get_memory_manager(namespace=ns)
        except Exception:
            memory_manager = None
    semantic = getattr(memory_manager, "_semantic", None) if memory_manager else None
    latest = getattr(semantic, "latest_by_tag", None)
    if callable(latest):
        try:
            item = latest(MEMORY_PROFILE_TAG)
            previous_content = getattr(item, "content", None) if item is not None else None
        except Exception:
            previous_content = None
    revised = revise_profile_observation(previous_content, profile, evidence)
    if not revised:
        return None
    profile = UserProfile.from_dict(revised)
    pinned = promote_durable_profile_facts(profile)
    if memory_manager and hasattr(memory_manager, "capture_to_semantic"):
        try:
            await memory_manager.capture_to_semantic(
                key=MEMORY_PROFILE_TAG,
                content=json.dumps(revised, ensure_ascii=False),
                metadata={
                    "tag": MEMORY_PROFILE_TAG,
                    "updated_at": profile.updated_at,
                },
            )
        except Exception as e:
            logging.debug(str(e), exc_info=True)
    log_data = {
        "preferences": len(profile.preferences),
        "constraints": len(profile.constraints),
        "decisions": len(profile.decisions),
        "pinned_written": pinned.get("written", 0),
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
        from core.harness.utils.prompt_loader import _sync_resolve
        stage_summary = build_stage_summary(state)
        prompt = _sync_resolve("memory-skill-review",
            stage_name="current_stage",
            agent_id="review",
            output_summary=stage_summary[:2000],
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

