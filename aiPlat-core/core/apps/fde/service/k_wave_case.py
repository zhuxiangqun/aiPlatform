"""Phase K4 — cases from OrgRun / consecutive tool failures. Overlay only; no TBox."""

from __future__ import annotations

import logging
from typing import Any, Dict

logger = logging.getLogger(__name__)


def _outcome_from_run(status: str) -> str:
    s = (status or "").lower()
    if s in ("succeeded", "success", "ok", "completed"):
        return "success"
    if s in ("needs_hitl", "completed_partial", "partial"):
        return "partial"
    return "failure"


def record_case_from_org_run(run: Dict[str, Any]) -> Dict[str, Any]:
    """Best-effort OrgRun → OntologyCaseStore. Never raises; never mutates TBox."""
    try:
        from core.harness.knowledge.ontology_case_learning import OntologyCaseStore

        domain_id = str(run.get("domain_id") or "it-ops")
        run_id = str(run.get("run_id") or "")
        status = str(run.get("status") or "")
        outcome = _outcome_from_run(status)
        skill_candidate = outcome == "success" and status.lower() in ("succeeded", "success", "ok")
        exceptions = run.get("exceptions") or []
        reasons = []
        for ex in exceptions:
            if isinstance(ex, dict) and ex.get("reason"):
                reasons.append(str(ex.get("reason")))
        store = OntologyCaseStore(domain_id)
        return store.record(
            title=f"OrgRun {run_id}",
            summary=(
                f"goal={run.get('goal_id')} status={status} "
                f"exceptions={','.join(reasons) or 'none'} "
                f"paths={(run.get('reasoning') or {}).get('path_count') or 0}"
            )[:4000],
            outcome=outcome,
            action_id="org_run_goal",
            entity_id=str(((run.get("reasoning") or {}).get("entities") or [{}])[0].get("entity_id") or ""),
            tags=["org_run", "k4", outcome],
            metadata={
                "trace_id": str(run.get("trace_id") or run_id),
                "trace_origin": str(run.get("trace_origin") or "run"),
                "run_id": run_id,
                "goal_id": str(run.get("goal_id") or ""),
                "week_label": str(run.get("week_label") or ""),
                "skill_candidate": skill_candidate,
                "schema_gap": not skill_candidate,
                "gap_note": "" if skill_candidate else "本体缺口探针；不改活 YAML",
                "exception_reasons": reasons[:8],
                "authority_note": "K4 case overlay only; not TBox; no SKILL.md",
            },
            write_graph=False,
        )
    except Exception:
        logger.debug("K4 record_case_from_org_run failed", exc_info=True)
        return {"status": "error"}


def record_case_from_tool_streak(
    *,
    domain_id: str = "",
    tool_name: str = "",
    error_code: str = "",
    run_id: str = "",
    trace_id: str = "",
    task: str = "",
    detail: str = "",
) -> Dict[str, Any]:
    """Same Run, same tool, same error class, consecutive ≥2 → one failure case."""
    try:
        from core.harness.knowledge.ontology_case_learning import OntologyCaseStore

        did = (domain_id or "").strip() or "default"
        tool = (tool_name or "").strip() or "tool"
        err = (error_code or "").strip() or "error"
        store = OntologyCaseStore(did)
        return store.record(
            title=f"tool_streak {tool}:{err}",
            summary=(
                f"K4 consecutive tool failure tool={tool} error={err} "
                f"task={(task or '')[:200]} detail={(detail or '')[:400]}"
            )[:4000],
            outcome="failure",
            action_id=tool,
            entity_id="",
            tags=["tool_streak", "k4", "failure"],
            metadata={
                "trace_id": (trace_id or run_id or "").strip(),
                "run_id": (run_id or "").strip(),
                "error_code": err,
                "tool_name": tool,
                "skill_candidate": False,
                "schema_gap": True,
                "gap_note": "工具连续失败；本体缺口探针；不改活 YAML",
                "authority_note": "K4 failure case only; reflector hint stays ephemeral",
            },
            write_graph=False,
        )
    except Exception:
        logger.debug("K4 record_case_from_tool_streak failed", exc_info=True)
        return {"status": "error"}
