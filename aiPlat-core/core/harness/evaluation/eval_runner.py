"""
Agent Runtime Evaluation — eval runner v1.0

Orchestrates evaluation: loads eval sets, executes tasks against agents,
collects trace data, computes metrics, and produces reports.
"""

from __future__ import annotations

import json
import os
import time
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional

from .eval_types import (
    EvalSet, EvalTask, SingleTaskResult, TaskResultLevel, AgentEvalResult,
)
from .eval_metrics import EvalMetricsEngine, _level_from_score


# ── Eval Set Storage ────────────────────────────────────────────────────────

def _eval_dir() -> Path:
    home = os.getenv("AIPLAT_HOME", os.path.expanduser("~/.aiplat"))
    return Path(home) / "eval_sets"


def _ensure_dirs():
    for cat in ("default", "custom"):
        (_eval_dir() / cat).mkdir(parents=True, exist_ok=True)


def load_eval_set(set_id: str) -> Optional[EvalSet]:
    """Load an eval set from disk."""
    path = _eval_dir() / f"{set_id}.json"
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        tasks = [EvalTask(**t) for t in data.get("tasks", [])]
        return EvalSet(
            set_id=data.get("set_id", set_id),
            category=data.get("category", "custom"),
            description=data.get("description", ""),
            tasks=tasks,
            created_at=data.get("created_at", time.time()),
        )
    except Exception:
        return None


def save_eval_set(evalset: EvalSet) -> str:
    """Save an eval set to disk. Returns file path."""
    _ensure_dirs()
    path = _eval_dir() / f"{evalset.set_id}.json"
    data = {
        "set_id": evalset.set_id,
        "category": evalset.category,
        "description": evalset.description,
        "created_at": evalset.created_at,
        "tasks": [
            {
                "task_id": t.task_id,
                "agent_id": t.agent_id,
                "user_input": t.user_input,
                "category": t.category,
                "expected_tools": t.expected_tools,
                "forbidden_tools": t.forbidden_tools,
                "expected_steps": t.expected_steps,
                "success_criteria": t.success_criteria,
                "risk_level": t.risk_level,
            }
            for t in evalset.tasks
        ],
    }
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    return str(path)


def list_eval_sets() -> List[Dict[str, Any]]:
    """List all eval sets."""
    _ensure_dirs()
    result = []
    for cat_dir in (_eval_dir() / "default", _eval_dir() / "custom"):
        if not cat_dir.exists():
            continue
        for fp in sorted(cat_dir.glob("*.json")):
            try:
                data = json.loads(fp.read_text(encoding="utf-8"))
                result.append({
                    "set_id": data.get("set_id", fp.stem),
                    "category": data.get("category", "custom"),
                    "description": data.get("description", ""),
                    "tasks": len(data.get("tasks", [])),
                    "created_at": data.get("created_at", 0),
                })
            except Exception:
                pass
    return result


def delete_eval_set(set_id: str) -> bool:
    path = _eval_dir() / f"{set_id}.json"
    if path.exists():
        path.unlink()
        return True
    return False


# ── Eval Runner ─────────────────────────────────────────────────────────────

class EvalRunner:
    """Execute evaluation tasks against agents and produce results."""

    def __init__(self, metrics_engine: Optional[EvalMetricsEngine] = None):
        self._metrics = metrics_engine or EvalMetricsEngine()

    async def run_eval_set(
        self,
        evalset: EvalSet,
        *,
        max_tasks: int = 0,
        dry_run: bool = False,
    ) -> AgentEvalResult:
        """Run all tasks in an eval set. Results grouped by agent.

        If dry_run=True, only validates tasks without executing them.
        """
        tasks = evalset.tasks[:max_tasks] if max_tasks > 0 else evalset.tasks
        if not tasks:
            return AgentEvalResult(agent_id="unknown", eval_set_id=evalset.set_id)

        if dry_run:
            return self._dry_run(evalset)

        # Group tasks by agent
        agent_tasks: Dict[str, List[EvalTask]] = {}
        for t in tasks:
            agent_tasks.setdefault(t.agent_id, []).append(t)

        # Execute per agent and aggregate
        all_results: List[SingleTaskResult] = []
        all_events: List[Dict[str, Any]] = []

        for agent_id, agent_task_list in agent_tasks.items():
            for task in agent_task_list:
                try:
                    tr, events = await self._execute_single_task(agent_id, task)
                    all_results.append(tr)
                    all_events.extend(events)
                except Exception as e:
                    all_results.append(SingleTaskResult(
                        task_id=task.task_id,
                        agent_id=agent_id,
                        run_id="",
                        level=TaskResultLevel.ERROR_FAILURE,
                        reasoning=f"Execution failed: {e}",
                    ))

        # Compute composite result (use first agent as primary)
        primary_agent = tasks[0].agent_id if tasks else "unknown"
        return self._metrics.compute_all(
            agent_id=primary_agent,
            task_results=all_results,
            syscall_events=all_events,
            eval_set_id=evalset.set_id,
            expected_tools=list(set(t.expected_tools for t in tasks if t.expected_tools)),
        )

    async def _execute_single_task(
        self, agent_id: str, task: EvalTask,
    ) -> tuple[SingleTaskResult, List[Dict[str, Any]]]:
        """Execute one task and collect trace data. Returns (result, events)."""
        run_id = f"eval-{uuid.uuid4().hex[:12]}"
        t0 = time.time()

        events: List[Dict[str, Any]] = []
        steps = 0

        try:
            # Try to execute via core facade
            from core.api.core_facade import run_workspace_agent
            result = await run_workspace_agent(
                agent_info=_make_agent_info(agent_id),
                user_message=task.user_input,
                max_steps=10,
                session_id=run_id,
            )
        except ImportError:
            return SingleTaskResult(
                task_id=task.task_id, agent_id=agent_id, run_id=run_id,
                level=TaskResultLevel.ERROR_FAILURE,
                reasoning="CoreFacade unavailable — cannot execute agent",
            ), events
        except Exception as e:
            return SingleTaskResult(
                task_id=task.task_id, agent_id=agent_id, run_id=run_id,
                level=TaskResultLevel.ERROR_FAILURE,
                reasoning=f"Agent execution error: {e}",
            ), events

        duration_ms = (time.time() - t0) * 1000
        output = str(result.get("output", "")) if isinstance(result, dict) else str(result)
        status = str(result.get("status", "error")) if isinstance(result, dict) else "done"

        # Collect trace events if available
        try:
            events = await self._collect_events(run_id)
            steps = len([e for e in events if e.get("kind") == "tool" or e.get("event_type") == "tool_call"])
        except Exception:
            pass

        # Determine task completion level
        level = self._determine_level(task, output, status, steps, events)

        return SingleTaskResult(
            task_id=task.task_id,
            agent_id=agent_id,
            run_id=run_id,
            level=level,
            reasoning=self._build_reasoning(level, output, task),
            evidence=output[:500] if output else "",
            duration_ms=duration_ms,
            steps=steps,
        ), events

    def _determine_level(
        self, task: EvalTask, output: str, status: str, steps: int,
        events: List[Dict[str, Any]],
    ) -> TaskResultLevel:
        """Determine task completion level from output and trace."""
        if status == "error" or not output:
            return TaskResultLevel.ERROR_FAILURE

        criteria = task.success_criteria or {}
        must_contain = criteria.get("must_contain", [])
        must_not_contain = criteria.get("must_not_contain", [])

        out_lower = output.lower()
        hits = sum(1 for kw in must_contain if kw.lower() in out_lower)
        violations = sum(1 for kw in must_not_contain if kw.lower() in out_lower)

        if must_contain and hits == 0:
            return TaskResultLevel.ERROR_FAILURE
        if must_not_contain and violations > 0:
            return TaskResultLevel.ERROR_FAILURE
        if must_contain and hits == len(must_contain):
            has_errors = any(e.get("status") == "error" for e in events)
            if not has_errors:
                return TaskResultLevel.COMPLETE
            return TaskResultLevel.PARTIAL
        if hits > 0:
            return TaskResultLevel.PARTIAL
        return TaskResultLevel.CORRECT_FAILURE

    def _build_reasoning(self, level: TaskResultLevel, output: str, task: EvalTask) -> str:
        criteria = task.success_criteria or {}
        must_contain = criteria.get("must_contain", [])
        must_not_contain = criteria.get("must_not_contain", [])

        parts = []
        if must_contain:
            found = [kw for kw in must_contain if kw.lower() in output.lower()]
            parts.append(f"Required keywords found: {len(found)}/{len(must_contain)}")
        if must_not_contain:
            violated = [kw for kw in must_not_contain if kw.lower() in output.lower()]
            if violated:
                parts.append(f"Forbidden keywords found: {violated}")
        parts.append(f"Task level: {level.value}")
        return "; ".join(parts) if parts else f"Assigned {level.value}"

    async def _collect_events(self, run_id: str) -> List[Dict[str, Any]]:
        """Collect syscall events for a run from ExecutionStore."""
        try:
            from core.services.execution_store import get_execution_store
            store = get_execution_store()
            events = await store.list_syscall_events(run_id=run_id, limit=200)
            return events if events else []
        except Exception:
            return []

    def _dry_run(self, evalset: EvalSet) -> AgentEvalResult:
        """Validate eval set without execution."""
        result = AgentEvalResult(
            agent_id="", eval_set_id=evalset.set_id, total_tasks=len(evalset.tasks)
        )
        for t in evalset.tasks:
            result.task_results.append(SingleTaskResult(
                task_id=t.task_id, agent_id=t.agent_id, run_id="",
                level=TaskResultLevel.CORRECT_FAILURE,
                reasoning="Dry run — not executed",
            ))
        return result


def _make_agent_info(agent_id: str) -> Any:
    """Build a lightweight agent info object for execution."""
    from types import SimpleNamespace

    model = ""
    try:
        from core.harness.utils.model_injection import get_default_model
        model = get_default_model("default")
    except Exception:
        pass

    return SimpleNamespace(
        id=agent_id,
        name=agent_id,
        agent_type="react",
        status="ready",
        config={"model": model, "system_prompt": ""},
        tools=[],
        skills=[],
        metadata={},
    )


# ── Built-in Eval Sets ──────────────────────────────────────────────────────

def create_builtin_eval_sets() -> List[str]:
    """Copy built-in eval set templates from engine directory to user workspace.
    
    Templates are stored as JSON in core/engine/eval_sets/ (version-controlled).
    On first use, they are copied to ~/.aiplat/eval_sets/default/ (user-writable).
    """
    _ensure_dirs()
    engine_dir = Path(__file__).resolve().parents[3] / "core" / "engine" / "eval_sets"
    if not engine_dir.exists():
        return []

    created = []
    for template in sorted(engine_dir.glob("*.json")):
        dst = _eval_dir() / "default" / template.name
        if not dst.exists():
            content = template.read_text(encoding="utf-8")
            dst.write_text(content, encoding="utf-8")
            created.append(f"default/{template.stem}")

    return created


def ensure_builtin_sets() -> None:
    """Create built-in eval sets if they don't exist."""
    _ensure_dirs()
    existing = {s["set_id"] for s in list_eval_sets()}
    needed = {"default/normal", "default/missing_info", "default/tool_failure", "default/high_risk", "default/noise"}
    if not needed.issubset(existing):
        create_builtin_eval_sets()
