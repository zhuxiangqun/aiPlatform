"""
CostsMixin — extracted from ExecutionStore global_mixin.py.
"""
from typing import Any, Dict, List, Optional, Tuple
import json, time, sqlite3, logging
from ._base import _json_dumps, _json_loads


class CostsMixin:
    """Extracted from ExecutionStore."""
    async def get_run_cost_summary(self, *, run_id: str, tenant_id: Optional[str] = None, limit_syscalls: int = 5000) -> Dict[str, Any]:
        """
        Aggregate a lightweight cost summary for one run_id.
        Metrics:
          - duration_ms (from run record)
          - llm_calls, llm_total_tokens/prompt_tokens/completion_tokens (from syscall_events kind=llm, result.usage)
          - tool_calls (kind=tool)
          - skill_calls (kind=skill)
        """
        run = await self.get_run_summary(run_id=str(run_id))
        if not run:
            return {"run_id": str(run_id), "ok": False, "error": "run_not_found"}

        # Pull syscalls (best-effort). We intentionally do a single scan to avoid heavy SQL changes.
        ev = await self.list_syscall_events(limit=int(limit_syscalls), offset=0, tenant_id=tenant_id, run_id=str(run_id))
        items = ev.get("items") if isinstance(ev, dict) else None
        items = items if isinstance(items, list) else []

        llm_calls = 0
        tool_calls = 0
        skill_calls = 0
        pt = ct = tt = 0.0
        for it in items:
            if not isinstance(it, dict):
                continue
            k = str(it.get("kind") or "")
            if k == "tool":
                tool_calls += 1
            elif k == "skill":
                skill_calls += 1
            elif k == "llm" and str(it.get("name") or "") == "generate":
                llm_calls += 1
                res = it.get("result") if isinstance(it.get("result"), dict) else {}
                usage = res.get("usage") if isinstance(res.get("usage"), dict) else {}
                try:
                    pt += float(usage.get("prompt_tokens") or 0)
                except Exception as e:
                    logging.debug(str(e), exc_info=True)
                try:
                    ct += float(usage.get("completion_tokens") or 0)
                except Exception as e:
                    logging.debug(str(e), exc_info=True)
                try:
                    v = usage.get("total_tokens")
                    if v is None:
                        v = (usage.get("prompt_tokens") or 0) + (usage.get("completion_tokens") or 0)
                    tt += float(v or 0)
                except Exception as e:
                    logging.debug(str(e), exc_info=True)

        duration_ms = run.get("duration_ms")
        if duration_ms is None:
            try:
                started = float(run.get("start_time") or 0)
                ended = float(run.get("end_time") or 0)
                duration_ms = (ended - started) * 1000.0 if ended and started else None
            except Exception:
                duration_ms = None

        return {
            "run_id": str(run_id),
            "ok": True,
            "duration_ms": duration_ms,
            "counts": {"llm_calls": llm_calls, "tool_calls": tool_calls, "skill_calls": skill_calls},
            "llm_tokens": {"prompt_tokens": pt, "completion_tokens": ct, "total_tokens": tt},
            "limit_syscalls": int(limit_syscalls),
        }

    # ------------------------------------------------------------------
    # Roadmap-4: persistent session memory + cross-session search (FTS)
    # ------------------------------------------------------------------

