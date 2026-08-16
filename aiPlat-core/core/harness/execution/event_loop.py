"""
Event Loop — autonomous pipeline trigger system (Loop Engineering).

Three trigger modes:
  1. cron: scheduled tasks (daily dependency scan, weekly cleanup)
  2. webhook: external event → pipeline (GitHub PR → review, Jira ticket → analyze)
  3. goal: condition-based loop (continue until target met)

Triggers are registered as JSON configs and checked by a background task.
Matches incoming events to OntologyScene templates and auto-starts pipelines.

Design from Gas Town / Stripe Minions: Loop is what gives Harness autonomous life.
"""

from __future__ import annotations

import asyncio
import json as _json
import logging
import os as _os
import time as _time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

from core.utils.paths import get_aiplat_data_dir

_TRIGGERS_PATH = get_aiplat_data_dir("loop/triggers.json")
_RUNNING: List[asyncio.Task] = []


@dataclass
class Trigger:
    trigger_id: str
    mode: str                         # "cron" | "webhook" | "goal"
    scene_id: str                     # which OntologyScene to instantiate
    params: Dict[str, Any] = field(default_factory=dict)

    # cron mode
    cron_expression: str = ""         # "0 6 * * *" (daily 6am)
    last_run: float = 0.0

    # webhook mode
    webhook_pattern: str = ""         # "github_pr" | "jira_ticket" | "*"
    allowed_sources: List[str] = field(default_factory=list)

    # goal mode
    goal_condition: str = ""          # "ci_all_green" | "error_rate_below_1pct"
    max_iterations: int = 10

    enabled: bool = True
    created_at: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "trigger_id": self.trigger_id,
            "mode": self.mode,
            "scene_id": self.scene_id,
            "params": self.params,
            "cron_expression": self.cron_expression,
            "last_run": self.last_run,
            "webhook_pattern": self.webhook_pattern,
            "allowed_sources": self.allowed_sources,
            "goal_condition": self.goal_condition,
            "max_iterations": self.max_iterations,
            "enabled": self.enabled,
            "created_at": self.created_at,
        }

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "Trigger":
        return cls(
            trigger_id=d.get("trigger_id", ""),
            mode=d.get("mode", "cron"),
            scene_id=d.get("scene_id", ""),
            params=d.get("params", {}),
            cron_expression=d.get("cron_expression", ""),
            last_run=d.get("last_run", 0.0),
            webhook_pattern=d.get("webhook_pattern", ""),
            allowed_sources=d.get("allowed_sources", []),
            goal_condition=d.get("goal_condition", ""),
            max_iterations=d.get("max_iterations", 10),
            enabled=d.get("enabled", True),
            created_at=d.get("created_at", ""),
        )


# ── Trigger Storage ──────────────────────────────────────────────

def load_triggers() -> List[Trigger]:
    if not _os.path.exists(_TRIGGERS_PATH):
        return []
    try:
        data = _json.load(open(_TRIGGERS_PATH, "r", encoding="utf-8"))
        return [Trigger.from_dict(t) for t in data.get("triggers", [])]
    except Exception:
        return []


def save_triggers(triggers: List[Trigger]) -> None:
    _os.makedirs(_os.path.dirname(_TRIGGERS_PATH), exist_ok=True)
    with open(_TRIGGERS_PATH, "w", encoding="utf-8") as f:
        _json.dump({
            "version": 1,
            "updated_at": _time.time(),
            "triggers": [t.to_dict() for t in triggers],
        }, f, indent=2, ensure_ascii=False)


def register_trigger(trigger: Trigger) -> Trigger:
    triggers = load_triggers()
    for i, t in enumerate(triggers):
        if t.trigger_id == trigger.trigger_id:
            triggers[i] = trigger
            save_triggers(triggers)
            return trigger
    trigger.created_at = datetime.now(timezone.utc).isoformat()
    triggers.append(trigger)
    save_triggers(triggers)
    return trigger


def remove_trigger(trigger_id: str) -> bool:
    triggers = load_triggers()
    before = len(triggers)
    triggers = [t for t in triggers if t.trigger_id != trigger_id]
    save_triggers(triggers)
    return len(triggers) < before


# ── Cron Scheduler ───────────────────────────────────────────────

def _parse_cron(expr: str) -> Optional[int]:
    u"""Parse cron expr to next run seconds. Minimal impl: "minute hour * * *"."""
    try:
        parts = expr.strip().split()
        if len(parts) < 2:
            return None
        minute = int(parts[0])
        hour = int(parts[1])
        now = datetime.now()
        target = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
        if target <= now:
            # Next occurrence is tomorrow
            from datetime import timedelta
            target += timedelta(days=1)
        return (target - now).total_seconds()
    except (ValueError, IndexError):
        return None


def _should_trigger_cron(trigger: Trigger) -> bool:
    if not trigger.cron_expression:
        return False
    now = _time.time()
    # Don't trigger more than once per cron window
    if now - trigger.last_run < 300:  # 5 min cooldown
        return False
    delay = _parse_cron(trigger.cron_expression)
    if delay is not None and delay < 60:  # within next minute
        return True
    return False


# ── Background Loop ───────────────────────────────────────────────

async def _start_pipeline_from_scene(scene_id: str, params: Dict[str, Any]) -> None:
    u"""Instantiate a scene and start a pipeline run."""
    try:
        from core.harness.knowledge.scene_model import instantiate_scene, get_scene
        scene = get_scene(scene_id)
        if not scene:
            logger.warning("Trigger for unknown scene: %s", scene_id)
            return

        config = instantiate_scene(scene_id, params=params)
        if not config:
            return

        from core.harness.execution.pipeline_engine import PipelineEngine
        engine = PipelineEngine(config=config)
        # Fire and forget — don't block the scheduler
        asyncio.create_task(engine.initialize(project_id=f"auto_{scene_id}_{int(_time.time())}",
                                                requirement=f"Auto-triggered: {scene_id}"))
        logger.info("Auto-triggered pipeline: scene=%s params=%s", scene_id, str(params)[:100])
    except Exception as e:
        logger.warning("Failed to auto-start pipeline for %s: %s", scene_id, str(e)[:200])


async def _check_webhook_match(source: str, payload: Dict[str, Any], trigger: Trigger) -> bool:
    u"""Check if a webhook event matches the trigger pattern."""
    pattern = trigger.webhook_pattern
    if pattern == "*" or pattern == source:
        return True
    if trigger.allowed_sources and source not in trigger.allowed_sources:
        return False
    return pattern == source


async def dispatch_webhook(source: str, payload: Dict[str, Any]) -> int:
    u"""Dispatch a webhook event to matching triggers. Returns count of triggered pipelines."""
    triggers = load_triggers()
    count = 0
    for t in triggers:
        if not t.enabled or t.mode != "webhook":
            continue
        if await _check_webhook_match(source, payload, t):
            merged_params = {**t.params, **payload.get("params", {})}
            await _start_pipeline_from_scene(t.scene_id, merged_params)
            t.last_run = _time.time()
            count += 1
    if count > 0:
        save_triggers(triggers)
    return count


async def _run_script_trigger(trigger: "Trigger") -> None:
    """P2-A7 (Hermes no_agent): cron trigger with mode=script runs a plain
    shell/python script — zero LLM calls. fail-closed: if the script entry is
    missing or the command is not allowed, log and skip (never fall back to an
    agent silently).

    Script spec is carried in trigger.params:
      {"script": "bash /path/to/script.sh"}      # shell command
      {"script": "python3 -m my.module"}          # python entry
      {"workdir": "/path"}                        # optional cwd
      {"timeout_seconds": 120}                    # optional (default 60)
      {"result_channel": "file|session|none"}     # delivery (default file)
    """
    import asyncio as _aio
    import subprocess as _sp

    script = str((trigger.params or {}).get("script") or "").strip()
    if not script:
        logger.warning("script trigger %s: no 'script' param — skipping (fail-closed)", trigger.trigger_id)
        return
    # fail-closed: reject obvious escapes; allow only concrete shell/python3 invocations
    first = script.split()[0] if script.split() else ""
    if first not in {"bash", "sh", "python3", "python"}:
        logger.warning(
            "script trigger %s: entry '%s' not in {bash,sh,python3,python} — refusing (fail-closed)",
            trigger.trigger_id, first)
        return

    workdir = str((trigger.params or {}).get("workdir") or "")
    timeout_s = float((trigger.params or {}).get("timeout_seconds") or 60)
    result_channel = str((trigger.params or {}).get("result_channel") or "file")

    proc = await _aio.create_subprocess_shell(
        script,
        cwd=workdir or None,
        stdout=_aio.subprocess.PIPE,
        stderr=_aio.subprocess.PIPE,
    )
    try:
        stdout_b, stderr_b = await _aio.wait_for(proc.communicate(), timeout=timeout_s)
    except _aio.TimeoutError:
        proc.kill()
        logger.warning("script trigger %s: timed out after %ss", trigger.trigger_id, timeout_s)
        return

    stdout = (stdout_b or b"").decode("utf-8", errors="replace")
    stderr = (stderr_b or b"").decode("utf-8", errors="replace")
    if proc.returncode != 0:
        logger.warning(
            "script trigger %s: exited %s — stderr: %s", trigger.trigger_id, proc.returncode, stderr[:500])
        return

    logger.info("script trigger %s: OK (exit 0, %d chars out)", trigger.trigger_id, len(stdout))
    if result_channel == "session":
        # Deliver to the scene's session if resolvable (best-effort), else file.
        try:
            from core.harness.knowledge.scene_model import get_scene
            scene = get_scene(trigger.scene_id)
            if scene is not None and getattr(scene, "session_id", None):
                from core.harness.knowledge.wiki_engine import write_page  # noqa: F401  # delivery channel
        except Exception as e:  # noqa: BLE001
            logger.debug("script trigger session delivery skipped: %s", e)


async def _judge_goal_condition(trigger: "Trigger") -> bool:
    """P2-A6 (Hermes judge_goal): evaluate a goal trigger's condition each
    round and decide whether the goal is met. Deterministic built-ins first;
    LLM judge is opt-in via params.judge='llm'. Returns True when met.

    Built-in conditions (goal_condition):
      - "ci_all_green"       → recent CI runs (from execution_store) all success
      - "error_rate_below_1pct" → recent syscall events error ratio < 1%
      - "always"             → always met (test/debug)
      - "never"              → never met (loop until iteration budget)
    Custom: params.get("judge_expr") = "key op value" evaluated against the
    execution_store summary (e.g. "artifacts_count >= 3").
    """
    cond = str(trigger.goal_condition or "").strip()
    if not cond:
        logger.debug("goal trigger %s: no goal_condition — treated as not met", trigger.trigger_id)
        return False
    if cond == "always":
        return True
    if cond == "never":
        return False

    try:
        from core.services.execution_store import get_execution_store
        store = get_execution_store()

        if cond == "ci_all_green":
            items = await store.list_syscall_events(limit=50) if hasattr(store, "list_syscall_events") else None
            if not items:
                return False
            evs = items if isinstance(items, list) else (items.get("items") or [])
            if not evs:
                return False
            statuses = [str(e.get("status") or "") for e in evs if isinstance(e, dict)]
            return all(s in {"success", "completed", "ok"} for s in statuses if s)

        if cond == "error_rate_below_1pct":
            items = await store.list_syscall_events(limit=500) if hasattr(store, "list_syscall_events") else None
            if not items:
                return False
            evs = items if isinstance(items, list) else (items.get("items") or [])
            if not evs:
                return False
            errors = sum(1 for e in evs if isinstance(e, dict) and str(e.get("status") or "").startswith("error"))
            return (errors / max(len(evs), 1)) < 0.01

        # Custom judge_expr: "key op value" on the store summary dict
        expr = str((trigger.params or {}).get("judge_expr") or "").strip()
        if expr:
            summary = {}
            for meth in ("get_artifact_stats", "get_overview", "get_stats"):
                if hasattr(store, meth):
                    try:
                        r = await getattr(store, meth)()
                        if isinstance(r, dict):
                            summary.update(r)
                    except Exception:  # noqa: BLE001
                        continue
            parts = expr.split()
            if len(parts) == 3:
                key, op, val = parts
                cur = summary.get(key)
                try:
                    cur_f = float(cur)
                    val_f = float(val)
                    if op == ">=": return cur_f >= val_f
                    if op == ">":  return cur_f > val_f
                    if op == "<=": return cur_f <= val_f
                    if op == "<":  return cur_f < val_f
                    if op == "==": return cur_f == val_f
                except (TypeError, ValueError):
                    return False
        return False
    except Exception as e:  # noqa: BLE001
        logger.warning("goal judge for %s failed: %s", trigger.trigger_id, str(e)[:200])
        return False


async def run_loop_scheduler(interval: int = 60) -> None:
    u"""Background loop: check triggers every N seconds.

    Start with `asyncio.create_task(run_loop_scheduler())` in server startup.
    """
    logger.info("Loop scheduler started (interval=%ds)", interval)
    while True:
        try:
            triggers = load_triggers()
            for t in triggers:
                if not t.enabled:
                    continue
                if t.mode == "cron" and _should_trigger_cron(t):
                    if str((t.params or {}).get("mode") or "") == "script":
                        # P2-A7: no-agent script mode — zero LLM, fail-closed
                        await _run_script_trigger(t)
                    else:
                        await _start_pipeline_from_scene(t.scene_id, t.params)
                    t.last_run = _time.time()

                elif t.mode == "goal":
                    # P2-A6: judge each round — met → done; not met → re-run
                    # (within the trigger's iteration budget)
                    met = await _judge_goal_condition(t)
                    t.params = dict(t.params or {})
                    budget = int(t.params.get("iterations_left", t.max_iterations))
                    if met:
                        logger.info("goal trigger %s: goal_judge: met", t.trigger_id)
                        t.params["iterations_left"] = 0
                    elif budget > 0:
                        logger.info("goal trigger %s: goal_judge: not_met (budget %d) — re-running",
                                    t.trigger_id, budget)
                        t.params["iterations_left"] = budget - 1
                        await _start_pipeline_from_scene(t.scene_id, t.params)
                    else:
                        logger.info("goal trigger %s: goal_judge: not_met — budget exhausted, stop", t.trigger_id)
                        t.params["iterations_left"] = 0

            save_triggers(triggers)
        except Exception as e:
            logging.warning(str(e), exc_info=True)
        await asyncio.sleep(interval)


def start_loop_scheduler(interval: int = 60) -> None:
    u"""Start the loop scheduler in the background. Safe to call multiple times."""
    try:
        loop = asyncio.get_running_loop()
        task = loop.create_task(run_loop_scheduler(interval))
        _RUNNING.append(task)
    except RuntimeError:
        pass  # noqa: cleanup-best-effort

