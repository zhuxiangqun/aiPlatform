"""eval_code_generator handler — unique path via apps.eval.agent_eval.

Interactive eval_engineer ReAct and automation (上架 / HTTP) all land here.
"""
from __future__ import annotations

import re
from typing import Any, Dict

_TARGET_RE = re.compile(r"target_agent_id\s*[:=]\s*([A-Za-z0-9_\-]+)", re.I)


def _extract_target(p: Dict[str, Any]) -> str:
    target = str(
        p.get("target_agent_id") or p.get("agent_id") or p.get("target") or ""
    ).strip()
    msg = p.get("message")
    if not target and isinstance(msg, dict):
        target = str(msg.get("target_agent_id") or msg.get("agent_id") or "").strip()
    if not target:
        blob = " ".join(
            str(p.get(k) or "") for k in ("message", "input", "task", "query")
        )
        m = _TARGET_RE.search(blob)
        if m:
            target = m.group(1).strip()
    return target


async def execute(params: Dict[str, Any]) -> Dict[str, Any]:
    """Generate scoring_dimensions + eval_metric/eval_runner for target_agent_id."""
    p = params if isinstance(params, dict) else {}
    target = _extract_target(p)
    if not target:
        return {
            "success": False,
            "error": "missing_target_agent_id",
            "message": "需要 target_agent_id（要评估的已上架 Agent ID）",
        }

    force = bool(p.get("force") or False)
    try:
        max_traces = int(p.get("max_traces") or 50)
    except (TypeError, ValueError):
        max_traces = 50
    run_runner = p.get("run_runner")
    if run_runner is None:
        run_runner = True

    from core.apps.eval.agent_eval import generate_agent_eval

    out = await generate_agent_eval(
        target,
        force=force,
        max_traces=max_traces,
        run_runner=bool(run_runner),
        use_llm=bool(p.get("use_llm", True)),
    )
    action = str(out.get("action") or "")
    return {
        "success": action in ("generated", "skip"),
        "skipped": action == "skip",
        **out,
    }
