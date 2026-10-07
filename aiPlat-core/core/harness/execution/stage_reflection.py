"""Per-stage reflection for Pipeline self-improvement loop.

Deterministic capture from health report / errors / artifacts (zero LLM cost).
Optional LLM enrichment when AIPLAT_STAGE_REFLECTION_LLM=true.

callers: pipeline_engine._capture_stage_reflection
"""

from __future__ import annotations

import logging
import os
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

_log = logging.getLogger("aiplat.stage_reflection")


def _normalize_verdict(raw: str) -> str:
    v = (raw or "").strip().lower()
    if v in ("passed", "pass", "ok", "good", "success"):
        return "passed"
    if v in ("failed", "fail", "poor", "error"):
        return "failed"
    if v in ("partial", "needs_improvement", "adequate", "warn", "warning"):
        return "partial" if v != "needs_improvement" else "needs_improvement"
    return "partial"


def build_stage_reflection(stage: Any, state: Dict[str, Any]) -> Dict[str, Any]:
    """Build structured reflection dict expected by crystallize / quality signals.

    Shape: verdict, strengths, problems, lesson, timestamp, agent_id, source
    """
    stage_id = getattr(stage, "id", "") or "unknown"
    agent_id = getattr(stage, "agent_id", "") or stage_id
    health = state.get(f"_health_report_{stage_id}") or {}
    error = state.get("error") or state.get(f"_stage_error_{stage_id}") or ""
    artifact_key = getattr(stage, "output_artifact", "") or ""
    artifact = state.get(artifact_key) if artifact_key else None

    strengths: List[str] = []
    problems: List[str] = []
    verdict = "partial"

    if isinstance(health, dict) and health:
        verdict = _normalize_verdict(str(health.get("verdict") or "partial"))
        overall = health.get("overall_score")
        if overall is not None:
            strengths.append(f"overall_score={overall}")
        for dim in health.get("dimensions") or []:
            if not isinstance(dim, dict):
                continue
            score = float(dim.get("score") or 0)
            name = dim.get("name") or dim.get("display_name") or "?"
            if score >= 7:
                strengths.append(f"{name}={score}")
            elif score < 5:
                problems.append(f"{name}={score}")
    elif error:
        verdict = "failed"
        problems.append(str(error)[:200])
    elif artifact not in (None, "", {}, []):
        verdict = "passed"
        strengths.append("artifact_present")
    else:
        problems.append("no_health_report_no_artifact")

    if error and verdict == "passed":
        verdict = "failed"
        problems.append(str(error)[:200])

    if problems:
        lesson = f"Stage {stage_id} ({agent_id}): " + "; ".join(problems[:3])
    elif strengths:
        lesson = f"Stage {stage_id} succeeded: " + "; ".join(strengths[:2])
    else:
        lesson = f"Stage {stage_id}: no strong signals"

    return {
        "verdict": verdict,
        "strengths": strengths[:5],
        "problems": problems[:5],
        "lesson": lesson,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "agent_id": agent_id,
        "source": "deterministic",
    }


async def enrich_reflection_with_llm(
    stage: Any,
    state: Dict[str, Any],
    reflection: Dict[str, Any],
) -> Optional[Dict[str, Any]]:
    """Optional LLM polish of lesson/problems. Opt-in via env."""
    if os.getenv("AIPLAT_STAGE_REFLECTION_LLM", "").lower() not in ("1", "true", "yes", "y"):
        return None
    try:
        from core.harness.utils.prompt_loader import _sync_resolve
        from core.harness.syscalls.llm import sys_llm_generate
        from core.harness.utils.model_injection import best_model_for_purpose
        import json
        import re

        stage_id = getattr(stage, "id", "") or ""
        artifact_key = getattr(stage, "output_artifact", "") or ""
        artifact_preview = str(state.get(artifact_key) or "")[:800] if artifact_key else ""
        prompt = _sync_resolve(
            "pipeline-stage-reflection",
            stage_id=stage_id,
            agent_id=str(reflection.get("agent_id") or ""),
            verdict=str(reflection.get("verdict") or ""),
            strengths="; ".join(reflection.get("strengths") or []) or "(none)",
            problems="; ".join(reflection.get("problems") or []) or "(none)",
            artifact_preview=artifact_preview or "(empty)",
            error=str(state.get("error") or "")[:300] or "(none)",
        )
        model = best_model_for_purpose("clarify", messages=[{"role": "user", "content": prompt}])
        raw = await sys_llm_generate(
            [{"role": "user", "content": prompt}],
            model_name=model,
            temperature=0.1,
            max_tokens=400,
            inject_agent_config=False,
            trace_context={"skip_claude_md": True, "purpose": "clarify"},
        )
        text = raw if isinstance(raw, str) else str(getattr(raw, "content", raw) or "")
        m = re.search(r"\{.*\}", text.replace("\n", " "), re.DOTALL)
        if not m:
            return None
        data = json.loads(m.group(0))
        if not isinstance(data, dict):
            return None
        out: Dict[str, Any] = {"source": "llm"}
        if data.get("lesson"):
            out["lesson"] = str(data["lesson"])[:500]
        if isinstance(data.get("problems"), list):
            out["problems"] = [str(p)[:200] for p in data["problems"][:5]]
        if isinstance(data.get("strengths"), list):
            out["strengths"] = [str(s)[:200] for s in data["strengths"][:5]]
        if data.get("verdict"):
            out["verdict"] = _normalize_verdict(str(data["verdict"]))
        return out
    except Exception:
        _log.debug("LLM stage reflection enrichment skipped", exc_info=True)
        return None


async def capture_stage_reflection(stage: Any, state: Dict[str, Any]) -> Dict[str, Any]:
    """Public entry: deterministic reflection + optional LLM enrichment."""
    reflection = build_stage_reflection(stage, state)
    enriched = await enrich_reflection_with_llm(stage, state, reflection)
    if enriched:
        reflection.update(enriched)
    return reflection
