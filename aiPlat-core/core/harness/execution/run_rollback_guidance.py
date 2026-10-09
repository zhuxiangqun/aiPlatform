"""Explainable rollback for runs — no fake universal undo.

Enterprise Agents sell results with accountability: when a run has already
side-effected, say clearly what can still be restored (file checkpoints)
and what cannot (completed pipeline semantics).
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional


def build_run_rollback_guidance(
    *,
    run_id: str,
    run_status: str = "",
    session_id: str = "",
    checkpoint_count: Optional[int] = None,
    checkpoint_preview: Optional[List[Dict[str, Any]]] = None,
) -> Dict[str, Any]:
    """Structured guidance returned when ``POST /runs/{id}/undo`` cannot undo."""
    status = str(run_status or "").strip().lower()
    alternatives: List[Dict[str, Any]] = []

    if status in ("queued", "pending"):
        alternatives.append(
            {
                "action": "undo_queued",
                "endpoint": f"/api/core/runs/{run_id}/undo",
                "effect": "cancel queued run (no side effects yet)",
            }
        )
    if status in ("running", "paused", "waiting", "hitl"):
        alternatives.append(
            {
                "action": "cancel",
                "endpoint": f"/api/core/runs/{run_id}/cancel",
                "effect": "request cooperative cancel; in-flight side effects may remain",
            }
        )

    alternatives.append(
        {
            "action": "file_checkpoints",
            "endpoint": "/api/platform/execution/file-checkpoints",
            "ui": "/core/checkpoints",
            "session_id": session_id or "",
            "effect": "restore files written via sys_file_write (code_generation / edits)",
            "checkpoint_count": checkpoint_count,
        }
    )
    alternatives.append(
        {
            "action": "domain_rollback",
            "effect": (
                "use stage/project rollback (Factory), agent version rollback, "
                "or ontology proposal rollback — there is no universal completed-run undo"
            ),
        }
    )

    return {
        "status": "undo_not_supported",
        "run_id": str(run_id),
        "run_status": status or "unknown",
        "message": (
            "Completed or active runs have no universal undo. "
            "Use cancel (if still running) or file/domain rollback paths below."
        ),
        "alternatives": alternatives,
        "file_checkpoints": {
            "count": int(checkpoint_count or 0),
            "items": list(checkpoint_preview or [])[:12],
            "ui": "/core/checkpoints",
        },
    }
