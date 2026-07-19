u"""
Field Assessment Handler (v2.7) — 5-step reasoning via ontology_agent.

Replaces the giant LLM prompt with a structured reasoning pipeline:
  1. Task Understanding → 2. Path Planning → 3. Graph Query
  4. Rule Scoring → 5. NL Output

Produces auditable reasoning_trace alongside the diagnosis.
"""
from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

logger = logging.getLogger("field_assessment")


async def execute(params: Dict[str, Any]) -> Dict[str, Any]:
    u"""Main handler: run ontology_agent 5-step reasoning pipeline.

    Input: { domain_id, session_id, customer_profile, pain_points, context }
    Output: { diagnosis, reasoning_trace, quality_indicators }
    """
    domain_id = params.get("domain_id", "")
    session_id = params.get("session_id", "")
    profile = params.get("customer_profile", {})
    pain_points = profile.get("pain_points", "") or params.get("pain_points", "")
    industry = profile.get("industry", "")

    # ── Build task description ──
    task_parts = []
    if industry:
        task_parts.append(f"{industry}行业客户")
    if pain_points:
        task_parts.append(f"痛点: {pain_points}")
    task = " ".join(task_parts) if task_parts else f"分析 domain={domain_id} 的业务问题"

    # ── Run Ontology Agent 5-step reasoning ──
    reasoning_result = {}
    try:
        from core.harness.syscalls.ontology_reason import sys_ontology_reason
        reasoning_result = await sys_ontology_reason(
            task=task,
            domain_id=domain_id,
        )
        logger.info("OntologyAgent completed: mode=%s, path=%s",
                     reasoning_result.get("mode", "?"),
                     reasoning_result.get("selected_path", "?"))
    except Exception as e:
        logger.warning("OntologyAgent reasoning failed: %s", e)
        reasoning_result = {"error": str(e), "mode": "react_fallback"}

    # ── Extract diagnosis from reasoning output ──
    scoring_results = reasoning_result.get("scoring_results", [])
    path_result = reasoning_result.get("path_result", {})
    reasoning_trace = reasoning_result.get("reasoning_trace", [])

    diagnosis = {
        "domain_id": domain_id,
        "session_id": session_id,
        "mode": reasoning_result.get("mode", "unknown"),
        "selected_path": reasoning_result.get("selected_path", ""),
        "nl_summary": reasoning_result.get("nl_output", ""),
        "issues_found": len(scoring_results),
        "high_priority_issues": len([r for r in scoring_results
                                      if isinstance(r, dict) and r.get("level") == "high"]),
        "terminal_entities": (
            path_result.get("terminal_entities", [])
            if isinstance(path_result, dict) else []
        ),
    }

    # ── Quality indicators ──
    quality = {
        "reasoning_trace_complete": len(reasoning_trace) >= 3,
        "scoring_applied": len(scoring_results) > 0,
        "path_completed": (
            path_result.get("completed", False)
            if isinstance(path_result, dict) else False
        ),
        "confidence": _estimate_confidence(reasoning_result),
    }

    return {
        "diagnosis": diagnosis,
        "reasoning_trace": reasoning_trace,
        "quality_indicators": quality,
    }


def _estimate_confidence(result: Dict) -> float:
    u"""Estimate confidence from reasoning trace completeness."""
    trace = result.get("reasoning_trace", [])
    if not trace:
        return 0.3
    successful = sum(1 for t in trace if isinstance(t, dict) and t.get("success", True))
    return round(min(0.95, successful / max(len(trace), 1)), 2)
