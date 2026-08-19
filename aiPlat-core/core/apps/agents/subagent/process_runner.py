"""Process provider runner (P3-2, DSH fork 借鉴) — executes in a forked subprocess.

Wired by ``ProcessProvider`` (``providers.py``): the provider spawns
``python -m core.apps.agents.subagent.process_runner`` with a JSON payload on
stdin and reads a ProviderResult-shaped JSON object from stdout. True process
isolation for subagent execution (aligns with DSH's fork provider semantics).

Usage:
    echo '{"name": "pm_agent", "task": "...", "context": []}' \\
      | python -m core.apps.agents.subagent.process_runner
"""
from __future__ import annotations

import asyncio
import json
import sys
from typing import Any, Dict, List, Optional


def _execute(name: str, task: str,
             context: Optional[List[Dict[str, Any]]] = None) -> Dict[str, Any]:
    """Run one subagent via SubagentCoordinator and normalize to ProviderResult shape.

    Imported lazily inside the subprocess so the module is importable without
    pulling the whole agent stack (parent process only imports this module by
    module name, never executes it).
    """
    from core.apps.agents.subagent.coordinator import SubagentCoordinator
    from core.apps.agents.subagent.registry import initialize_registry

    async def _run() -> Dict[str, Any]:
        coordinator = SubagentCoordinator()
        await initialize_registry()
        result = await coordinator.execute_single(task, name, context=context or [])
        return {
            "ok": bool(result.success),
            "output": str(result.output or ""),
            "error": str(result.error or ""),
            "instance_id": f"process:{name}",
            "can_continue": False,
            "metadata": {
                "tokens_used": result.tokens_used,
                "duration_ms": result.duration_ms,
            },
        }

    return asyncio.run(_run())


def main() -> None:
    """Read JSON {name, task, context} from stdin, emit JSON result to stdout."""
    try:
        payload = json.loads(sys.stdin.read() or "{}")
        name = str(payload.get("name") or "")
        task = str(payload.get("task") or "")
        context = payload.get("context") or []
        res = _execute(name, task, context)
        json.dump(res, sys.stdout, ensure_ascii=False)
    except Exception as e:  # noqa: BLE001 — runner must always emit JSON
        json.dump({"ok": False, "error": f"process_runner: {e}"[:300],
                   "output": "", "instance_id": "", "can_continue": False},
                  sys.stdout, ensure_ascii=False)
    sys.stdout.write("\n")


if __name__ == "__main__":
    main()
