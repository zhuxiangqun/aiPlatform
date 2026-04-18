"""
Jobs/Cron scheduler (Roadmap-3).

Design goals:
- Minimal, dependency-free cron scheduler with minute-level resolution.
- Persist jobs/job_runs in ExecutionStore.
- Execute via HarnessIntegration (single kernel entry).
"""

from __future__ import annotations

import asyncio
import time
import uuid
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Set, Tuple

from core.harness.kernel.types import ExecutionRequest
import os


def _parse_cron_field(field: str, *, min_v: int, max_v: int) -> Set[int]:
    """
    Parse a single cron field.

    Supported:
    - "*"
    - "*/n"
    - "a"
    - "a,b,c"
    - "a-b"
    - "a-b/n"
    """
    field = (field or "*").strip()
    if field == "*":
        return set(range(min_v, max_v + 1))

    out: Set[int] = set()
    for part in field.split(","):
        part = part.strip()
        if not part:
            continue
        step = 1
        if "/" in part:
            base, step_s = part.split("/", 1)
            base = base.strip() or "*"
            try:
                step = max(1, int(step_s.strip()))
            except Exception:
                step = 1
        else:
            base = part

        if base == "*":
            start, end = min_v, max_v
        elif "-" in base:
            a, b = base.split("-", 1)
            start, end = int(a.strip()), int(b.strip())
        else:
            start = end = int(base.strip())

        start = max(min_v, start)
        end = min(max_v, end)
        for v in range(start, end + 1, step):
            if min_v <= v <= max_v:
                out.add(v)

    if not out:
        # fail-closed: treat as "*"
        return set(range(min_v, max_v + 1))
    return out


def next_run_from_cron(cron: str, *, from_ts: float) -> float:
    """
    Compute next run time (unix ts) from a 5-field cron spec.

    Resolution: 60 seconds (minute).
    Timezone: treated as local time (Phase-1). The job record stores timezone for future extension.
    """
    cron = (cron or "* * * * *").strip()
    parts = [p for p in cron.split() if p.strip()]
    if len(parts) != 5:
        raise ValueError(f"Invalid cron (expect 5 fields): {cron}")

    mins = _parse_cron_field(parts[0], min_v=0, max_v=59)
    hours = _parse_cron_field(parts[1], min_v=0, max_v=23)
    dom = _parse_cron_field(parts[2], min_v=1, max_v=31)
    months = _parse_cron_field(parts[3], min_v=1, max_v=12)
    dow = _parse_cron_field(parts[4], min_v=0, max_v=6)  # 0=Mon per python? we'll map below

    # Align to next minute boundary
    t = int(from_ts)
    t = t - (t % 60) + 60

    # Search forward up to 366 days
    max_steps = 366 * 24 * 60
    import datetime

    for _ in range(max_steps):
        dt = datetime.datetime.fromtimestamp(t)
        if (
            dt.minute in mins
            and dt.hour in hours
            and dt.day in dom
            and dt.month in months
            and dt.weekday() in dow
        ):
            return float(t)
        t += 60
    raise RuntimeError(f"Unable to find next run within 366 days for cron: {cron}")


@dataclass
class SchedulerConfig:
    poll_interval_seconds: float = 2.0
    batch_size: int = 20
    delivery_timeout_seconds: float = 10.0
    delivery_retries: int = 2
    delivery_backoff_seconds: float = 1.0


class JobScheduler:
    def __init__(self, *, execution_store: Any, harness: Any, config: Optional[SchedulerConfig] = None) -> None:
        self._store = execution_store
        self._harness = harness
        self._cfg = config or SchedulerConfig()
        self._stop = asyncio.Event()
        self._task: Optional[asyncio.Task] = None

    async def start(self) -> None:
        if self._task and not self._task.done():
            return
        self._stop.clear()
        self._task = asyncio.create_task(self._run_loop(), name="aiplat.job_scheduler")

    async def stop(self) -> None:
        self._stop.set()
        if self._task:
            try:
                await asyncio.wait_for(self._task, timeout=5)
            except Exception:
                pass

    async def run_job_once(self, job_id: str) -> Dict[str, Any]:
        job = await self._store.get_job(job_id)
        if not job:
            raise ValueError(f"Job not found: {job_id}")
        res = await self._execute_job(job, scheduled_for=time.time(), force=True)
        if isinstance(res, dict) and res.get("skipped") and res.get("reason") == "locked":
            raise RuntimeError("Job is locked by another scheduler instance")
        return res

    async def _run_loop(self) -> None:
        while not self._stop.is_set():
            try:
                now = time.time()
                due = await self._store.list_due_jobs(now_ts=now, limit=int(self._cfg.batch_size))
                for job in due:
                    # fire-and-forget; each run persists status
                    asyncio.create_task(self._execute_job(job, scheduled_for=job.get("next_run_at") or now), name=f"job:{job.get('id')}")
            except Exception:
                # keep scheduler alive
                pass
            try:
                await asyncio.wait_for(self._stop.wait(), timeout=float(self._cfg.poll_interval_seconds))
            except asyncio.TimeoutError:
                continue

    async def _execute_job(self, job: Dict[str, Any], *, scheduled_for: float, force: bool = False) -> Dict[str, Any]:
        job_id = str(job.get("id"))
        kind = str(job.get("kind") or "agent")
        target_id = str(job.get("target_id") or "")
        user_id = str(job.get("user_id") or "system")
        session_id = str(job.get("session_id") or "default")

        now = time.time()
        run_id = f"jobrun-{uuid.uuid4().hex[:12]}"

        # Acquire lock to prevent duplicate runs (best-effort, leaderless).
        lock_owner = run_id
        try:
            ttl = float(os.getenv("AIPLAT_JOBS_LOCK_TTL_SECONDS", "300") or "300")
        except Exception:
            ttl = 300.0
        try:
            ok_lock = await self._store.acquire_job_lock(job_id, owner=lock_owner, ttl_seconds=ttl)
            if not ok_lock:
                # Another scheduler instance owns it.
                return {"skipped": True, "reason": "locked", "job_id": job_id}
        except Exception:
            # If locking fails unexpectedly, fail-open to preserve functionality.
            ok_lock = True
        # advance next_run_at early to avoid duplicate pickup
        try:
            next_run = None
            if not force:
                next_run = next_run_from_cron(str(job.get("cron") or "* * * * *"), from_ts=now)
            patch = {"last_run_at": now, "next_run_at": next_run}
            await self._store.update_job(job_id, patch)
        except Exception:
            # If cron invalid, disable job to avoid hot loop
            try:
                await self._store.update_job(job_id, {"enabled": False})
            except Exception:
                pass

        job_run = await self._store.create_job_run(
            {
                "id": run_id,
                "job_id": job_id,
                "scheduled_for": float(scheduled_for),
                "started_at": now,
                "status": "running",
                "run_id": run_id,
            }
        )


        payload = dict(job.get("payload") or {})
        options = dict(job.get("options") or {})
        if options:
            payload.setdefault("options", options)

        # Inject execution context for traceability (best-effort).
        # This is safe for all kinds:
        # - agent: loop reads payload["context"]
        # - skill: server wrapper already uses separate context; but scheduler runs kernel directly
        # - tool: ignored by tool itself but consumed by gating/tracing hooks
        try:
            ctx = payload.get("context") if isinstance(payload.get("context"), dict) else {}
            ctx = dict(ctx) if isinstance(ctx, dict) else {}
            ctx.setdefault("source", "job")
            ctx.setdefault("job_id", job_id)
            ctx.setdefault("job_run_id", run_id)
            payload["context"] = ctx
        except Exception:
            pass

        exec_req = ExecutionRequest(
            kind=kind,  # type: ignore[arg-type]
            target_id=target_id,
            payload=payload,
            user_id=user_id,
            session_id=session_id,
            request_id=run_id,
        )

        final_payload: Dict[str, Any] = {}
        final_ok = False
        final_error: Optional[str] = None
        trace_id: Optional[str] = None

        try:
            result = await self._harness.execute(exec_req)
            finished = time.time()
            if not getattr(result, "ok", False):
                final_ok = False
                final_error = getattr(result, "error", None) or "Execution failed"
                trace_id = getattr(result, "trace_id", None)
                final_payload = {"ok": False, "error": getattr(result, "error", None), "payload": getattr(result, "payload", {})}
                await self._store.finish_job_run(
                    run_id,
                    {
                        "finished_at": finished,
                        "status": "failed",
                        "error": final_error,
                        "trace_id": trace_id,
                        "result": final_payload,
                    },
                )
            else:
                payload_out = getattr(result, "payload", {}) or {}
                status = str(payload_out.get("status") or "completed")
                final_ok = True
                final_error = payload_out.get("error")
                trace_id = getattr(result, "trace_id", None) or payload_out.get("trace_id")
                final_payload = {"ok": True, "payload": payload_out}
                await self._store.finish_job_run(
                    run_id,
                    {
                        "finished_at": finished,
                        "status": "completed" if status in ("completed", "success") else status,
                        "error": final_error,
                        "trace_id": trace_id,
                        "result": final_payload,
                    },
                )
        except Exception as e:
            finished = time.time()
            final_ok = False
            final_error = str(e)
            final_payload = {"ok": False, "error": final_error}
            await self._store.finish_job_run(
                run_id,
                {
                    "finished_at": finished,
                    "status": "failed",
                    "error": final_error,
                    "result": final_payload,
                },
            )

        # Delivery (best-effort): webhook POST for completion/failure.
        try:
            delivery = job.get("delivery") if isinstance(job, dict) else None
            delivery_result = await self._deliver_webhook(
                delivery if isinstance(delivery, dict) else {},
                job=job,
                run={
                    "id": run_id,
                    "job_id": job_id,
                    "scheduled_for": float(scheduled_for),
                    "status": "completed" if final_ok else "failed",
                    "error": final_error,
                    "trace_id": trace_id,
                    "run_id": run_id,
                },
                result=final_payload,
            )
            if delivery_result is not None:
                # merge into job_run result for auditability
                try:
                    await self._store.finish_job_run(
                        run_id,
                        {
                            "result": {
                                **(final_payload or {}),
                                "delivery": delivery_result,
                            }
                        },
                    )
                except Exception:
                    pass
        except Exception:
            pass

        # Return the run record (stable id)
        try:
            return await self._store.get_job_run(run_id) or {"id": run_id, "job_id": job_id}
        finally:
            # Always release lock when done (best-effort).
            try:
                await self._store.release_job_lock(job_id, owner=lock_owner)
            except Exception:
                pass

    async def _deliver_webhook(
        self,
        delivery: Dict[str, Any],
        *,
        job: Dict[str, Any],
        run: Dict[str, Any],
        result: Dict[str, Any],
    ) -> Optional[Dict[str, Any]]:
        """
        Webhook delivery (best-effort).

        delivery format:
        {
          "type": "webhook",
          "url": "http://...",
          "headers": {"Authorization": "..."},
          "include": ["job","run","result"]   # optional
        }
        """
        if not isinstance(delivery, dict) or not delivery:
            return None
        if str(delivery.get("type") or "webhook") != "webhook":
            return None
        url = delivery.get("url")
        if not isinstance(url, str) or not url.strip():
            return None

        headers = delivery.get("headers") if isinstance(delivery.get("headers"), dict) else {}
        include = delivery.get("include")
        if not isinstance(include, list) or not include:
            include = ["job", "run", "result"]

        body: Dict[str, Any] = {"type": "job_run"}
        if "job" in include:
            body["job"] = job
        if "run" in include:
            body["run"] = run
        if "result" in include:
            body["result"] = result

        # env overrides
        retries = int(os.getenv("AIPLAT_JOBS_DELIVERY_RETRIES", str(self._cfg.delivery_retries)) or "2")
        timeout_s = float(os.getenv("AIPLAT_JOBS_DELIVERY_TIMEOUT_SECONDS", str(self._cfg.delivery_timeout_seconds)) or "10")
        backoff = float(os.getenv("AIPLAT_JOBS_DELIVERY_BACKOFF_SECONDS", str(self._cfg.delivery_backoff_seconds)) or "1")

        # Lazy import (aiohttp is already a dependency in this repo)
        import aiohttp

        last_err: Optional[str] = None
        for attempt in range(retries + 1):
            try:
                async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=timeout_s)) as sess:
                    async with sess.post(url, json=body, headers=headers) as resp:
                        text = await resp.text()
                        if 200 <= resp.status < 300:
                            return {"ok": True, "status": resp.status, "response_text": text[:2000]}
                        last_err = f"HTTP {resp.status}: {text[:2000]}"
            except Exception as e:
                last_err = str(e)
            if attempt < retries:
                await asyncio.sleep(backoff * (attempt + 1))
        return {"ok": False, "error": last_err or "delivery_failed"} 
