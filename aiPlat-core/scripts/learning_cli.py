"""
Phase 6.1: Offline learning CLI.

This script is intentionally offline and side-effect free with respect to runtime execution.
It only reads/writes learning_artifacts in ExecutionStore.

Examples:
  python3 scripts/learning_cli.py --db /path/to/executions.sqlite3 create-eval-artifact \
    --target-type agent --target-id a1 --version v1 --benchmark-json ./bench.json

  python3 scripts/learning_cli.py --db /path/to/executions.sqlite3 list --target-type agent --target-id a1
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
from typing import Any, Dict, Optional

import anyio

# Ensure repo root is on sys.path so `import core.*` works when running as a script.
REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))


async def _create_eval_artifact(db: str, args: argparse.Namespace) -> int:
    from core.services.execution_store import ExecutionStore, ExecutionStoreConfig
    from core.apps.evaluation.types import BenchmarkResult, TaskResult
    from core.learning.pipeline import artifact_from_benchmark_result

    with open(args.benchmark_json, "r", encoding="utf-8") as f:
        data = json.load(f)

    # Minimal deserialization for BenchmarkResult (task_results optional)
    task_results = []
    for tr in (data.get("task_results") or []):
        if isinstance(tr, dict):
            task_results.append(
                TaskResult(
                    task_id=str(tr.get("task_id") or ""),
                    success=bool(tr.get("success", False)),
                    latency_ms=int(tr.get("latency_ms", 0) or 0),
                    tokens_used=int(tr.get("tokens_used", 0) or 0),
                    tool_calls=tr.get("tool_calls") if isinstance(tr.get("tool_calls"), list) else [],
                    error=tr.get("error"),
                    metadata=tr.get("metadata") if isinstance(tr.get("metadata"), dict) else {},
                )
            )

    result = BenchmarkResult(
        benchmark_name=str(data.get("benchmark_name") or "unknown"),
        total_tasks=int(data.get("total_tasks", len(task_results)) or 0),
        passed_tasks=int(data.get("passed_tasks", 0) or 0),
        pass_at_1=float(data.get("pass_at_1", 0.0) or 0.0),
        pass_at_3=float(data.get("pass_at_3", 0.0) or 0.0),
        pass_at_k=float(data.get("pass_at_k", 0.0) or 0.0),
        avg_latency_ms=float(data.get("avg_latency_ms", 0.0) or 0.0),
        avg_tokens=int(data.get("avg_tokens", 0) or 0),
        task_results=task_results,
        executed_at=str(data.get("executed_at") or ""),
    )

    artifact = artifact_from_benchmark_result(
        target_type=args.target_type,
        target_id=args.target_id,
        version=args.version,
        result=result,
        trace_id=args.trace_id,
        run_id=args.run_id,
        metadata={"source": "learning_cli", "benchmark_json": args.benchmark_json},
    )

    store = ExecutionStore(ExecutionStoreConfig(db_path=db))
    await store.init()
    await store.upsert_learning_artifact(artifact.to_record())

    print(artifact.artifact_id)
    return 0


def _load_benchmark_result_from_json(path: str):
    from core.apps.evaluation.types import BenchmarkResult, TaskResult

    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)

    task_results = []
    for tr in (data.get("task_results") or []):
        if isinstance(tr, dict):
            task_results.append(
                TaskResult(
                    task_id=str(tr.get("task_id") or ""),
                    success=bool(tr.get("success", False)),
                    latency_ms=int(tr.get("latency_ms", 0) or 0),
                    tokens_used=int(tr.get("tokens_used", 0) or 0),
                    tool_calls=tr.get("tool_calls") if isinstance(tr.get("tool_calls"), list) else [],
                    error=tr.get("error"),
                    metadata=tr.get("metadata") if isinstance(tr.get("metadata"), dict) else {},
                )
            )

    return BenchmarkResult(
        benchmark_name=str(data.get("benchmark_name") or "unknown"),
        total_tasks=int(data.get("total_tasks", len(task_results)) or 0),
        passed_tasks=int(data.get("passed_tasks", 0) or 0),
        pass_at_1=float(data.get("pass_at_1", 0.0) or 0.0),
        pass_at_3=float(data.get("pass_at_3", 0.0) or 0.0),
        pass_at_k=float(data.get("pass_at_k", 0.0) or 0.0),
        avg_latency_ms=float(data.get("avg_latency_ms", 0.0) or 0.0),
        avg_tokens=int(data.get("avg_tokens", 0) or 0),
        task_results=task_results,
        executed_at=str(data.get("executed_at") or ""),
    )


async def _list_artifacts(db: str, args: argparse.Namespace) -> int:
    from core.services.execution_store import ExecutionStore, ExecutionStoreConfig

    store = ExecutionStore(ExecutionStoreConfig(db_path=db))
    await store.init()
    out = await store.list_learning_artifacts(
        target_type=args.target_type,
        target_id=args.target_id,
        trace_id=args.trace_id,
        run_id=args.run_id,
        limit=args.limit,
        offset=args.offset,
    )
    print(json.dumps(out, ensure_ascii=False, indent=2))
    return 0


async def _summarize_run(db: str, args: argparse.Namespace) -> int:
    from core.services.execution_store import ExecutionStore, ExecutionStoreConfig
    from core.learning.pipeline import artifact_from_online_run_summary

    store = ExecutionStore(ExecutionStoreConfig(db_path=db))
    await store.init()

    agent_exec = await store.get_agent_execution(args.run_id)
    if not agent_exec:
        print(f"agent_execution not found: {args.run_id}", file=sys.stderr)
        return 2

    # Fetch all syscall events for this run (paged)
    events: list[dict] = []
    offset = 0
    while True:
        page = await store.list_syscall_events(limit=500, offset=offset, run_id=args.run_id)
        items = page.get("items") or []
        events.extend(items)
        if len(items) < 500:
            break
        offset += 500

    artifact = artifact_from_online_run_summary(
        target_type="agent",
        target_id=str(agent_exec.get("agent_id") or "unknown"),
        version=args.version,
        run_id=args.run_id,
        trace_id=agent_exec.get("trace_id"),
        agent_execution=agent_exec,
        syscall_events=events,
        metadata={"source": "learning_cli", "mode": "summarize-run"},
    )
    await store.upsert_learning_artifact(artifact.to_record())
    print(artifact.artifact_id)
    return 0


async def _create_regression_artifact(db: str, args: argparse.Namespace) -> int:
    from core.services.execution_store import ExecutionStore, ExecutionStoreConfig
    from core.learning.pipeline import artifact_from_regression_result

    current = _load_benchmark_result_from_json(args.current_json)
    baseline = _load_benchmark_result_from_json(args.baseline_json)

    artifact = artifact_from_regression_result(
        target_type=args.target_type,
        target_id=args.target_id,
        version=args.version,
        current=current,
        baseline=baseline,
        trace_id=args.trace_id,
        run_id=args.run_id,
        metadata={
            "source": "learning_cli",
            "mode": "regression",
            "current_json": args.current_json,
            "baseline_json": args.baseline_json,
        },
    )

    store = ExecutionStore(ExecutionStoreConfig(db_path=db))
    await store.init()
    await store.upsert_learning_artifact(artifact.to_record())
    print(artifact.artifact_id)
    return 0


def _load_skill_version_from_json(path: str):
    from datetime import datetime
    from core.apps.skills.evolution.types import SkillVersion, EvolutionType

    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    created_at = data.get("created_at")
    try:
        dt = datetime.fromisoformat(created_at) if isinstance(created_at, str) and created_at else datetime.utcnow()
    except Exception:
        dt = datetime.utcnow()
    evo_type = data.get("evolution_type")
    evo = None
    if isinstance(evo_type, str):
        try:
            evo = EvolutionType(evo_type)
        except Exception:
            evo = None

    return SkillVersion(
        id=str(data.get("id") or ""),
        skill_id=str(data.get("skill_id") or ""),
        version=str(data.get("version") or ""),
        parent_version=data.get("parent_version"),
        evolution_type=evo,
        trigger=str(data.get("trigger") or ""),
        content_hash=str(data.get("content_hash") or ""),
        diff=str(data.get("diff") or ""),
        created_at=dt,
        metadata=data.get("metadata") if isinstance(data.get("metadata"), dict) else {},
    )


async def _create_skill_version_artifact(db: str, args: argparse.Namespace) -> int:
    from core.services.execution_store import ExecutionStore, ExecutionStoreConfig
    from core.learning.pipeline import artifact_from_skill_version

    v = _load_skill_version_from_json(args.skill_version_json)
    artifact = artifact_from_skill_version(
        version_obj=v,
        artifact_version=args.version,
        trace_id=args.trace_id,
        run_id=args.run_id,
        metadata={"source": "learning_cli", "mode": "skill-version", "skill_version_json": args.skill_version_json},
    )
    store = ExecutionStore(ExecutionStoreConfig(db_path=db))
    await store.init()
    await store.upsert_learning_artifact(artifact.to_record())
    print(artifact.artifact_id)
    return 0


async def _create_skill_rollback_artifact(db: str, args: argparse.Namespace) -> int:
    from core.services.execution_store import ExecutionStore, ExecutionStoreConfig
    from core.learning.pipeline import artifact_from_skill_rollback

    artifact = artifact_from_skill_rollback(
        skill_id=args.skill_id,
        from_version=args.from_version,
        to_version=args.to_version,
        artifact_version=args.version,
        reason=args.reason or "",
        trace_id=args.trace_id,
        run_id=args.run_id,
        metadata={"source": "learning_cli", "mode": "skill-rollback"},
    )
    store = ExecutionStore(ExecutionStoreConfig(db_path=db))
    await store.init()
    await store.upsert_learning_artifact(artifact.to_record())
    print(artifact.artifact_id)
    return 0


async def _create_release_candidate(db: str, args: argparse.Namespace) -> int:
    from core.services.execution_store import ExecutionStore, ExecutionStoreConfig
    from core.learning.release import build_release_candidate

    artifact_ids = [s.strip() for s in (args.artifact_ids or "").split(",") if s.strip()]
    candidate = build_release_candidate(
        target_type=args.target_type,
        target_id=args.target_id,
        version=args.version,
        artifact_ids=artifact_ids,
        summary=args.summary or "",
        metadata={"source": "learning_cli", "mode": "release_candidate"},
    )
    store = ExecutionStore(ExecutionStoreConfig(db_path=db))
    await store.init()
    await store.upsert_learning_artifact(candidate.to_record())
    print(candidate.artifact_id)
    return 0


async def _create_prompt_revision_artifact(db: str, args: argparse.Namespace) -> int:
    from core.services.execution_store import ExecutionStore, ExecutionStoreConfig
    from core.learning.pipeline import artifact_from_prompt_revision

    patch: Dict[str, Any] = {}
    if args.patch_json:
        with open(args.patch_json, "r", encoding="utf-8") as f:
            data = json.load(f)
        if isinstance(data, dict):
            patch = data.get("patch") if isinstance(data.get("patch"), dict) else data
    else:
        if args.prepend:
            patch["prepend"] = args.prepend
        if args.append:
            patch["append"] = args.append

    artifact = artifact_from_prompt_revision(
        target_type=args.target_type,
        target_id=args.target_id,
        version=args.version,
        patch=patch,
        trace_id=args.trace_id,
        run_id=args.run_id,
        metadata={
            "source": "learning_cli",
            "mode": "prompt-revision",
            "exclusive_group": args.exclusive_group,
            "priority": args.priority,
        },
    )

    store = ExecutionStore(ExecutionStoreConfig(db_path=db))
    await store.init()
    await store.upsert_learning_artifact(artifact.to_record())
    print(artifact.artifact_id)
    return 0


async def _publish_release(db: str, args: argparse.Namespace) -> int:
    from core.services.execution_store import ExecutionStore, ExecutionStoreConfig
    from core.learning.manager import LearningManager
    from core.harness.infrastructure.approval.manager import ApprovalManager
    from core.learning.release import require_publish_approval, is_approved

    store = ExecutionStore(ExecutionStoreConfig(db_path=db))
    await store.init()
    mgr = LearningManager(execution_store=store)
    approval_mgr = ApprovalManager(execution_store=store)

    cand = await store.get_learning_artifact(args.candidate_id)
    if not cand:
        print("candidate_not_found", file=sys.stderr)
        return 2
    if cand.get("kind") != "release_candidate":
        print("not_a_release_candidate", file=sys.stderr)
        return 2

    require_approval = bool(args.require_approval)
    if require_approval:
        if not args.approval_request_id:
            req_id = await require_publish_approval(
                approval_manager=approval_mgr,
                user_id=args.user_id or "system",
                candidate_id=args.candidate_id,
                details=args.details or "",
            )
            print(req_id)
            return 0
        if not is_approved(approval_mgr, args.approval_request_id):
            print("not_approved", file=sys.stderr)
            return 3

    # Publish: candidate + referenced artifacts -> published
    now = __import__("time").time()
    meta_update = {"published_via": "learning_cli", "approval_request_id": args.approval_request_id, "published_at": now}
    if args.expires_at:
        try:
            meta_update["expires_at"] = float(args.expires_at)
        except Exception:
            pass
    if args.ttl_seconds:
        try:
            ttl = float(args.ttl_seconds)
            meta_update["ttl_seconds"] = ttl
            if "expires_at" not in meta_update:
                meta_update["expires_at"] = now + ttl
        except Exception:
            pass
    await mgr.set_artifact_status(
        artifact_id=args.candidate_id,
        status="published",
        metadata_update=meta_update,
    )
    ids = (cand.get("payload") or {}).get("artifact_ids") if isinstance(cand.get("payload"), dict) else []
    if isinstance(ids, list):
        for aid in ids:
            if isinstance(aid, str) and aid:
                await mgr.set_artifact_status(
                    artifact_id=aid,
                    status="published",
                    metadata_update={"published_by_candidate": args.candidate_id},
                )
    print("published")
    return 0


async def _approve(db: str, args: argparse.Namespace) -> int:
    from core.services.execution_store import ExecutionStore, ExecutionStoreConfig
    from core.harness.infrastructure.approval.manager import ApprovalManager

    store = ExecutionStore(ExecutionStoreConfig(db_path=db))
    await store.init()
    approval_mgr = ApprovalManager(execution_store=store)
    # Ensure request is loaded from store (CLI is stateless across processes)
    if approval_mgr.get_request(args.approval_request_id) is None:
        print("not_found", file=sys.stderr)
        return 2
    req = await approval_mgr.approve(args.approval_request_id, approved_by=args.approved_by or "reviewer", comments=args.comments or "")
    if not req:
        print("not_found", file=sys.stderr)
        return 2
    print("approved")
    return 0


async def _cleanup_rollback_approvals(db: str, args: argparse.Namespace) -> int:
    """
    Phase 6.26: Cancel stale pending rollback approvals (learning:rollback_release)
    when the candidate is no longer in a state that needs rollback.
    """
    import time as _time

    from core.services.execution_store import ExecutionStore, ExecutionStoreConfig
    from core.harness.infrastructure.approval.manager import ApprovalManager
    from core.harness.infrastructure.approval.types import RequestStatus

    store = ExecutionStore(ExecutionStoreConfig(db_path=db))
    await store.init()
    approval_mgr = ApprovalManager(execution_store=store)

    now = float(args.now) if args.now is not None else _time.time()

    page_size = int(getattr(args, "page_size", 500) or 500)
    page_size = max(1, min(page_size, 2000))

    cancelled = []
    kept = 0
    checked = 0
    matched = 0
    # Important: do NOT mutate (cancel) while paginating with offset, otherwise offsets may skip rows.
    to_process: list[dict] = []
    offset = 0
    while True:
        page = await store.list_approval_requests(
            status=RequestStatus.PENDING.value,
            user_id=getattr(args, "user_id", None),
            limit=page_size,
            offset=offset,
        )
        items = page.get("items") or []
        if not items:
            break
        checked += len(items)
        for it in items:
            if it.get("operation") != "learning:rollback_release":
                continue
            meta = it.get("metadata") if isinstance(it.get("metadata"), dict) else {}
            candidate_id = meta.get("candidate_id")
            req_id = it.get("request_id")
            if not isinstance(candidate_id, str) or not candidate_id:
                continue
            if not isinstance(req_id, str) or not req_id:
                continue
            if getattr(args, "candidate_id", None) and candidate_id != getattr(args, "candidate_id"):
                continue
            to_process.append({"request_id": req_id, "candidate_id": candidate_id})
        if len(items) < page_size:
            break
        offset += page_size

    matched = len(to_process)
    for it in to_process:
        candidate_id = it["candidate_id"]
        req_id = it["request_id"]

        cand = await store.get_learning_artifact(candidate_id)
        reason = None
        if not cand:
            reason = "candidate_not_found"
        else:
            st = cand.get("status")
            if st != "published":
                reason = f"candidate_status={st}"

        if reason is None:
            kept += 1
            continue

        if args.dry_run:
            cancelled.append({"approval_request_id": req_id, "candidate_id": candidate_id, "reason": reason})
            continue

        req = approval_mgr.get_request(req_id)
        if not req:
            continue
        await approval_mgr.cancel_request(req.request_id)
        cancelled.append({"approval_request_id": req.request_id, "candidate_id": candidate_id, "reason": reason})

    print(json.dumps({"now": now, "checked": checked, "matched": matched, "kept": kept, "cancelled": cancelled}, ensure_ascii=False))
    return 0


async def _rollback_release(db: str, args: argparse.Namespace) -> int:
    from core.services.execution_store import ExecutionStore, ExecutionStoreConfig
    from core.learning.manager import LearningManager

    store = ExecutionStore(ExecutionStoreConfig(db_path=db))
    await store.init()
    mgr = LearningManager(execution_store=store)

    cand = await store.get_learning_artifact(args.candidate_id)
    if not cand:
        print("candidate_not_found", file=sys.stderr)
        return 2
    if cand.get("kind") != "release_candidate":
        print("not_a_release_candidate", file=sys.stderr)
        return 2

    await mgr.set_artifact_status(
        artifact_id=args.candidate_id,
        status="rolled_back",
        metadata_update={"rolled_back_via": "learning_cli", "reason": args.reason or ""},
    )
    ids = (cand.get("payload") or {}).get("artifact_ids") if isinstance(cand.get("payload"), dict) else []
    if isinstance(ids, list):
        for aid in ids:
            if isinstance(aid, str) and aid:
                await mgr.set_artifact_status(
                    artifact_id=aid,
                    status="rolled_back",
                    metadata_update={"rolled_back_by_candidate": args.candidate_id},
                )
    print("rolled_back")
    return 0


async def _rollback_candidate(
    *,
    store,
    mgr,
    candidate_id: str,
    reason: str,
    now: float,
) -> bool:
    cand = await store.get_learning_artifact(candidate_id)
    if not cand or cand.get("kind") != "release_candidate":
        return False
    await mgr.set_artifact_status(
        artifact_id=candidate_id,
        status="rolled_back",
        metadata_update={"rolled_back_via": "learning_cli", "reason": reason, "rolled_back_at": now},
    )
    payload = cand.get("payload") if isinstance(cand.get("payload"), dict) else {}
    ids = payload.get("artifact_ids") if isinstance(payload.get("artifact_ids"), list) else []
    for aid in ids:
        if isinstance(aid, str) and aid:
            await mgr.set_artifact_status(
                artifact_id=aid,
                status="rolled_back",
                metadata_update={"rolled_back_by_candidate": candidate_id, "rolled_back_at": now},
            )
    return True


async def _expire_releases(db: str, args: argparse.Namespace) -> int:
    """
    Expire published release candidates based on metadata.expires_at (unix epoch seconds).
    This is offline and only changes artifact statuses to rolled_back.
    """
    import time as _time

    from core.services.execution_store import ExecutionStore, ExecutionStoreConfig
    from core.learning.manager import LearningManager

    store = ExecutionStore(ExecutionStoreConfig(db_path=db))
    await store.init()
    mgr = LearningManager(execution_store=store)

    now = float(args.now) if args.now is not None else _time.time()

    expired_ids: list[str] = []
    checked = 0
    offset = 0
    while True:
        page = await store.list_learning_artifacts(
            target_type=args.target_type,
            target_id=args.target_id,
            limit=500,
            offset=offset,
        )
        items = page.get("items") or []
        if not items:
            break
        for it in items:
            checked += 1
            if it.get("kind") != "release_candidate" or it.get("status") != "published":
                continue
            meta = it.get("metadata") if isinstance(it.get("metadata"), dict) else {}
            expires_at = meta.get("expires_at")
            if expires_at is None:
                continue
            try:
                exp = float(expires_at)
            except Exception:
                continue
            if exp <= now:
                cid = str(it.get("artifact_id") or "")
                if not cid:
                    continue
                if args.dry_run:
                    expired_ids.append(cid)
                    continue

                # Rollback: candidate + referenced artifacts
                await _rollback_candidate(store=store, mgr=mgr, candidate_id=cid, reason="expired", now=now)
                expired_ids.append(cid)

        if len(items) < 500:
            break
        offset += 500

    print(json.dumps({"now": now, "checked": checked, "expired_candidates": expired_ids}, ensure_ascii=False))
    return 0


async def _auto_rollback_metrics(db: str, args: argparse.Namespace) -> int:
    """
    Phase 6.15: Offline auto rollback based on recent online metrics.
    Current scope:
      - failure rate based on agent_executions.status != completed
      - optional avg duration_ms threshold
    """
    import time as _time

    from core.services.execution_store import ExecutionStore, ExecutionStoreConfig
    from core.learning.manager import LearningManager

    store = ExecutionStore(ExecutionStoreConfig(db_path=db))
    await store.init()
    mgr = LearningManager(execution_store=store)

    now = float(args.now) if args.now is not None else _time.time()

    # Determine candidate id
    candidate_id = args.candidate_id
    if not candidate_id:
        # pick latest published release_candidate for this agent
        la = await store.list_learning_artifacts(target_type="agent", target_id=args.agent_id, limit=50, offset=0)
        published = [x for x in (la.get("items") or []) if x.get("kind") == "release_candidate" and x.get("status") == "published"]
        if not published:
            print(json.dumps({"status": "no_active_candidate"}, ensure_ascii=False))
            return 0
        published.sort(key=lambda x: float(x.get("created_at") or 0.0), reverse=True)
        candidate_id = str(published[0].get("artifact_id"))

    # Load recent executions and filter by candidate
    limit = int(args.window or 50)
    hist, total = await store.list_agent_history(args.agent_id, limit=limit, offset=0)
    matched = []
    for r in hist:
        meta = r.get("metadata") if isinstance(r.get("metadata"), dict) else {}
        ar = meta.get("active_release") if isinstance(meta.get("active_release"), dict) else {}
        if ar.get("candidate_id") == candidate_id:
            matched.append(r)

    n = len(matched)
    if n < int(args.min_samples or 1):
        print(json.dumps({"status": "insufficient_samples", "candidate_id": candidate_id, "samples": n}, ensure_ascii=False))
        return 0

    failures = 0
    duration_sum = 0.0
    duration_n = 0
    for r in matched:
        st = (r.get("status") or "").lower()
        if st not in ("completed", "success", "succeeded"):
            failures += 1
        try:
            d = float(r.get("duration_ms") or 0.0)
            if d > 0:
                duration_sum += d
                duration_n += 1
        except Exception:
            pass

    error_rate = failures / max(1, n)
    avg_duration_ms = (duration_sum / duration_n) if duration_n else None

    should_rb = False
    reason_parts = []
    thr = float(args.error_rate_threshold)
    if error_rate >= thr:
        should_rb = True
        reason_parts.append(f"error_rate={error_rate:.3f}>=thr({thr:.3f})")
    if args.max_avg_duration_ms is not None and avg_duration_ms is not None:
        maxd = float(args.max_avg_duration_ms)
        if avg_duration_ms >= maxd:
            should_rb = True
            reason_parts.append(f"avg_duration_ms={avg_duration_ms:.1f}>=max({maxd:.1f})")

    out = {
        "candidate_id": candidate_id,
        "agent_id": args.agent_id,
        "window": limit,
        "samples": n,
        "failures": failures,
        "error_rate": error_rate,
        "avg_duration_ms": avg_duration_ms,
        "should_rollback": should_rb,
    }

    if should_rb and not args.dry_run:
        ok = await _rollback_candidate(store=store, mgr=mgr, candidate_id=candidate_id, reason=";".join(reason_parts), now=now)
        out["rollback"] = "done" if ok else "failed"
    else:
        out["rollback"] = "skipped"

    print(json.dumps(out, ensure_ascii=False))
    return 0


def _compute_exec_metrics(items: list[dict]) -> dict:
    n = len(items)
    failures = 0
    duration_sum = 0.0
    duration_n = 0
    for r in items:
        st = (r.get("status") or "").lower()
        if st not in ("completed", "success", "succeeded"):
            failures += 1
        try:
            d = float(r.get("duration_ms") or 0.0)
            if d > 0:
                duration_sum += d
                duration_n += 1
        except Exception:
            pass
    return {
        "samples": n,
        "failures": failures,
        "error_rate": (failures / max(1, n)) if n else None,
        "avg_duration_ms": (duration_sum / duration_n) if duration_n else None,
    }


def _merge_unique_cap(existing: Any, new: Any, *, cap: int) -> list[str]:
    """
    Merge two lists with stable order (existing first), dedupe, and cap length.
    """
    out: list[str] = []
    seen: set[str] = set()
    for src in (existing, new):
        if not isinstance(src, list):
            continue
        for x in src:
            if not isinstance(x, str) or not x:
                continue
            if x in seen:
                continue
            out.append(x)
            seen.add(x)
            if len(out) >= cap:
                return out
    return out


async def _auto_rollback_regression(db: str, args: argparse.Namespace) -> int:
    """
    Phase 6.16: Offline auto rollback by regression detection.

    Compare "current" executions for a candidate vs "baseline" executions.
    Baseline selection policy (minimal):
      - if baseline_candidate_id provided: active_release.candidate_id == baseline_candidate_id
      - else: active_release.candidate_id != current candidate (including None)
    Baseline window is taken from executions older than the current window's oldest start_time.
    """
    import time as _time

    from core.services.execution_store import ExecutionStore, ExecutionStoreConfig
    from core.learning.manager import LearningManager

    store = ExecutionStore(ExecutionStoreConfig(db_path=db))
    await store.init()
    mgr = LearningManager(execution_store=store)

    now = float(args.now) if args.now is not None else _time.time()

    # Determine candidate id
    candidate_id = args.candidate_id
    if not candidate_id:
        la = await store.list_learning_artifacts(target_type="agent", target_id=args.agent_id, limit=50, offset=0)
        published = [x for x in (la.get("items") or []) if x.get("kind") == "release_candidate" and x.get("status") == "published"]
        if not published:
            print(json.dumps({"status": "no_active_candidate"}, ensure_ascii=False))
            return 0
        published.sort(key=lambda x: float(x.get("created_at") or 0.0), reverse=True)
        candidate_id = str(published[0].get("artifact_id"))
        # Also allow baseline auto-selection from this published list.
        published_candidates_sorted = published
    else:
        la = await store.list_learning_artifacts(target_type="agent", target_id=args.agent_id, limit=50, offset=0)
        published_candidates_sorted = [x for x in (la.get("items") or []) if x.get("kind") == "release_candidate" and x.get("status") == "published"]
        published_candidates_sorted.sort(key=lambda x: float(x.get("created_at") or 0.0), reverse=True)

    current_window = int(args.current_window or 50)
    baseline_window = int(args.baseline_window or 50)
    min_samples = int(args.min_samples or 10)

    # Pull a sufficiently large slice of history to satisfy both windows.
    pull = max(500, (current_window + baseline_window) * 10)
    hist, total = await store.list_agent_history(args.agent_id, limit=pull, offset=0)

    current: list[dict] = []
    baseline: list[dict] = []
    oldest_current_start = None

    def _candidate_of(meta: dict) -> str | None:
        ar = meta.get("active_release") if isinstance(meta.get("active_release"), dict) else {}
        cid = ar.get("candidate_id")
        return str(cid) if isinstance(cid, str) and cid else None

    # Collect current first (latest N)
    for r in hist:
        meta = r.get("metadata") if isinstance(r.get("metadata"), dict) else {}
        cid = _candidate_of(meta)
        if cid == candidate_id:
            current.append(r)
            try:
                st = float(r.get("start_time") or 0.0)
                oldest_current_start = st if oldest_current_start is None else min(oldest_current_start, st)
            except Exception:
                pass
        if len(current) >= current_window:
            break

    if len(current) < min_samples:
        print(json.dumps({"status": "insufficient_current_samples", "candidate_id": candidate_id, "samples": len(current)}, ensure_ascii=False))
        return 0

    baseline_candidate_id = args.baseline_candidate_id
    baseline_selection: dict = {
        "mode": "explicit" if baseline_candidate_id else "auto",
        "chosen_candidate_id": None,
        "tried": [],  # list[{candidate_id, samples}]
        "fallback": None,
    }
    # Phase 6.18: if baseline not specified, prefer "previous published candidates" with multi-level fallback.
    if not baseline_candidate_id:
        try:
            for x in published_candidates_sorted:
                cid = str(x.get("artifact_id") or "")
                if cid and cid != candidate_id:
                    baseline_selection["tried"].append({"candidate_id": cid, "samples": 0})
        except Exception:
            pass
    def _collect_baseline_for_candidate(cid_filter: str | None) -> list[dict]:
        out: list[dict] = []
        for r in hist:
            try:
                st = float(r.get("start_time") or 0.0)
                if oldest_current_start is not None and st >= oldest_current_start:
                    continue
            except Exception:
                continue
            meta = r.get("metadata") if isinstance(r.get("metadata"), dict) else {}
            cid = _candidate_of(meta)
            if cid_filter is not None:
                if cid != cid_filter:
                    continue
            else:
                if cid == candidate_id:
                    continue
            out.append(r)
            if len(out) >= baseline_window:
                break
        return out

    # If explicit baseline candidate given, use it; else try previous published candidates in order.
    if baseline_candidate_id:
        baseline = _collect_baseline_for_candidate(baseline_candidate_id)
        baseline_selection["chosen_candidate_id"] = baseline_candidate_id
        baseline_selection["tried"] = [{"candidate_id": baseline_candidate_id, "samples": len(baseline)}]
    else:
        chosen = None
        tried_list = baseline_selection.get("tried") if isinstance(baseline_selection.get("tried"), list) else []
        for item in tried_list:
            cid_try = item.get("candidate_id")
            if not isinstance(cid_try, str) or not cid_try:
                continue
            b = _collect_baseline_for_candidate(cid_try)
            item["samples"] = len(b)
            if len(b) >= min_samples and chosen is None:
                chosen = cid_try
                baseline = b
                break

        if chosen is not None:
            baseline_candidate_id = chosen
            baseline_selection["chosen_candidate_id"] = chosen
            baseline_selection["mode"] = "prev_published"
        else:
            # Final fallback: use != current strategy.
            baseline = _collect_baseline_for_candidate(None)
            baseline_candidate_id = None
            baseline_selection["chosen_candidate_id"] = None
            baseline_selection["fallback"] = "not_equal_current"
            baseline_selection["mode"] = "not_equal_current"

    if len(baseline) < min_samples:
        print(
            json.dumps(
                {
                    "status": "insufficient_baseline_samples",
                    "candidate_id": candidate_id,
                    "baseline_candidate_id": baseline_candidate_id,
                    "samples": len(baseline),
                    "baseline_selection": baseline_selection,
                },
                ensure_ascii=False,
            )
        )
        return 0

    cur_m = _compute_exec_metrics(current)
    base_m = _compute_exec_metrics(baseline)

    # Phase 6.20: collect evidence links to trace/run.
    current_execution_ids = [str(r.get("id")) for r in current if r.get("id")]
    baseline_execution_ids = [str(r.get("id")) for r in baseline if r.get("id")]
    evidence_trace_ids = []
    for r in (current + baseline):
        tid = r.get("trace_id")
        if isinstance(tid, str) and tid and tid not in evidence_trace_ids:
            evidence_trace_ids.append(tid)
    evidence_trace_id = evidence_trace_ids[0] if evidence_trace_ids else None

    cur_er = float(cur_m["error_rate"] or 0.0)
    base_er = float(base_m["error_rate"] or 0.0)
    er_delta = cur_er - base_er

    cur_d = cur_m["avg_duration_ms"]
    base_d = base_m["avg_duration_ms"]
    d_delta = None
    try:
        if cur_d is not None and base_d is not None:
            d_delta = float(cur_d) - float(base_d)
    except Exception:
        d_delta = None

    should_rb = False
    reason_parts = []
    er_thr = float(args.error_rate_delta_threshold)
    if er_delta >= er_thr:
        should_rb = True
        reason_parts.append(f"error_rate_delta={er_delta:.3f}>=thr({er_thr:.3f})")

    if args.avg_duration_delta_threshold is not None and d_delta is not None:
        d_thr = float(args.avg_duration_delta_threshold)
        if d_delta >= d_thr:
            should_rb = True
            reason_parts.append(f"avg_duration_delta_ms={d_delta:.1f}>=thr({d_thr:.1f})")

    out = {
        "candidate_id": candidate_id,
        "agent_id": args.agent_id,
        "baseline_candidate_id": baseline_candidate_id,
        "baseline_selection": baseline_selection,
        "current": cur_m,
        "baseline": base_m,
        "error_rate_delta": er_delta,
        "avg_duration_delta_ms": d_delta,
        "should_rollback": should_rb,
    }

    regression_report_id = None
    updated_execution_links = 0
    updated_baseline_links = 0
    if should_rb and not args.dry_run:
        # Phase 6.25: approval gate for rollback (optional).
        approval_required = bool(getattr(args, "require_approval", False))
        approval_request_id = getattr(args, "approval_request_id", None)
        if approval_required:
            from core.harness.infrastructure.approval.manager import ApprovalManager
            from core.learning.release import require_rollback_approval, is_approved

            approval_mgr = ApprovalManager(execution_store=store)
            if approval_request_id:
                # Ensure request is loaded from store for CLI statelessness.
                if approval_mgr.get_request(approval_request_id) is None:
                    print("not_found", file=sys.stderr)
                    return 2
                if not is_approved(approval_mgr, approval_request_id):
                    print("not_approved", file=sys.stderr)
                    return 3
            else:
                # Create regression report first (published decision artifact), then request approval.
                try:
                    from core.learning.pipeline import artifact_from_regression_decision

                    report_run_id = f"auto-rollback-regression:{candidate_id}:{int(now)}"
                    report = artifact_from_regression_decision(
                        target_type="agent",
                        target_id=args.agent_id,
                        candidate_id=candidate_id,
                        baseline_candidate_id=baseline_candidate_id,
                        current=cur_m,
                        baseline=base_m,
                        deltas={
                            "error_rate_delta": er_delta,
                            "avg_duration_delta_ms": d_delta,
                            "evidence": {
                                "current_execution_ids": current_execution_ids,
                                "baseline_execution_ids": baseline_execution_ids,
                                "trace_ids": evidence_trace_ids,
                                "linked_current_execution_ids": [],
                                "linked_baseline_execution_ids": [],
                                "linked_evidence_cap": int(args.max_linked_evidence or 200),
                            },
                        },
                        decision={
                            "should_rollback": True,
                            "approval_required": True,
                            "reason": ";".join(reason_parts),
                            "thresholds": {
                                "error_rate_delta_threshold": float(args.error_rate_delta_threshold),
                                "avg_duration_delta_threshold": float(args.avg_duration_delta_threshold)
                                if args.avg_duration_delta_threshold is not None
                                else None,
                            },
                        },
                        baseline_selection=baseline_selection,
                        artifact_version=f"regression:{candidate_id}:{int(now)}",
                        trace_id=evidence_trace_id,
                        run_id=report_run_id,
                        metadata={"source": "learning_cli", "mode": "auto-rollback-regression", "approval_gate": True},
                    )
                    await store.upsert_learning_artifact(report.to_record())
                    regression_report_id = report.artifact_id
                except Exception:
                    regression_report_id = None

                req_id = await require_rollback_approval(
                    approval_manager=approval_mgr,
                    user_id=args.user_id or "system",
                    candidate_id=candidate_id,
                    regression_report_id=regression_report_id,
                    details="auto-rollback-regression",
                )
                print(
                    json.dumps(
                        {
                            "status": "approval_required",
                            "candidate_id": candidate_id,
                            "approval_request_id": req_id,
                            "regression_report_id": regression_report_id,
                        },
                        ensure_ascii=False,
                    )
                )
                return 0

            # If approved and request has regression_report_id, reuse it (avoid creating duplicates).
            try:
                req = approval_mgr.get_request(approval_request_id)
                rid = None
                if req is not None and getattr(req, "metadata", None):
                    rid = (req.metadata or {}).get("regression_report_id")
                if isinstance(rid, str) and rid:
                    regression_report_id = rid
            except Exception:
                pass
            # If we have a pre-created report, reuse its run_id/trace_id for outputs.
            try:
                if regression_report_id:
                    rep0 = await store.get_learning_artifact(regression_report_id)
                    if rep0:
                        out["regression_report_run_id"] = rep0.get("run_id")
                        out["regression_report_trace_id"] = rep0.get("trace_id")
            except Exception:
                pass

        # Phase 6.19: artifactize "why rollback" as regression_report
        try:
            from core.learning.pipeline import artifact_from_regression_decision

            report_run_id = f"auto-rollback-regression:{candidate_id}:{int(now)}"
            report = artifact_from_regression_decision(
                target_type="agent",
                target_id=args.agent_id,
                candidate_id=candidate_id,
                baseline_candidate_id=baseline_candidate_id,
                current=cur_m,
                baseline=base_m,
                deltas={
                    "error_rate_delta": er_delta,
                    "avg_duration_delta_ms": d_delta,
                    "evidence": {
                        "current_execution_ids": current_execution_ids,
                        "baseline_execution_ids": baseline_execution_ids,
                        "trace_ids": evidence_trace_ids,
                        "linked_current_execution_ids": [],
                        "linked_baseline_execution_ids": [],
                    },
                },
                decision={
                    "should_rollback": True,
                    "reason": ";".join(reason_parts),
                    "thresholds": {
                        "error_rate_delta_threshold": float(args.error_rate_delta_threshold),
                        "avg_duration_delta_threshold": float(args.avg_duration_delta_threshold)
                        if args.avg_duration_delta_threshold is not None
                        else None,
                    },
                },
                baseline_selection=baseline_selection,
                artifact_version=f"regression:{candidate_id}:{int(now)}",
                trace_id=evidence_trace_id,
                run_id=report_run_id,
                metadata={"source": "learning_cli", "mode": "auto-rollback-regression"},
            )
            if not regression_report_id:
                await store.upsert_learning_artifact(report.to_record())
                regression_report_id = report.artifact_id
        except Exception:
            regression_report_id = None

        ok = await _rollback_candidate(store=store, mgr=mgr, candidate_id=candidate_id, reason=";".join(reason_parts), now=now)
        out["rollback"] = "done" if ok else "failed"
        if regression_report_id:
            out["regression_report_id"] = regression_report_id
            out.setdefault("regression_report_run_id", f"auto-rollback-regression:{candidate_id}:{int(now)}")
            out.setdefault("regression_report_trace_id", evidence_trace_id)
            if approval_required:
                out["approval_request_id"] = approval_request_id
            # Phase 6.21: write back report_id into current window executions for reverse lookup.
            try:
                linked_current = []
                for r in current:
                    eid = r.get("id")
                    if not isinstance(eid, str) or not eid:
                        continue
                    meta = r.get("metadata") if isinstance(r.get("metadata"), dict) else {}
                    # Phase 6.23: idempotent linking (skip if already linked to same report).
                    if meta.get("regression_report_id") == regression_report_id:
                        continue
                    meta2 = dict(meta)
                    meta2["regression_report_id"] = regression_report_id
                    meta2["regression_report_run_id"] = out["regression_report_run_id"]
                    meta2["regression_report_trace_id"] = evidence_trace_id
                    meta2["regression_report_kind"] = "auto-rollback-regression"
                    await store.upsert_agent_execution(
                        {
                            "id": eid,
                            "agent_id": r.get("agent_id") or args.agent_id,
                            "status": r.get("status"),
                            "input": r.get("input") or {},
                            "output": r.get("output") or {},
                            "error": r.get("error"),
                            "start_time": r.get("start_time"),
                            "end_time": r.get("end_time"),
                            "duration_ms": r.get("duration_ms"),
                            "trace_id": r.get("trace_id"),
                            "metadata": meta2,
                            "approval_request_id": r.get("approval_request_id"),
                        }
                    )
                    updated_execution_links += 1
                    linked_current.append(eid)
                out["linked_current_executions"] = updated_execution_links
                out["linked_current_execution_ids"] = linked_current
            except Exception:
                pass

            # Phase 6.22: optional link baseline window executions.
            if args.link_baseline:
                try:
                    linked_baseline = []
                    for r in baseline:
                        eid = r.get("id")
                        if not isinstance(eid, str) or not eid:
                            continue
                        meta = r.get("metadata") if isinstance(r.get("metadata"), dict) else {}
                        # Phase 6.23: idempotent linking (skip if already linked to same report).
                        if meta.get("regression_report_id") == regression_report_id:
                            continue
                        meta2 = dict(meta)
                        meta2["regression_report_id"] = regression_report_id
                        meta2["regression_report_run_id"] = out["regression_report_run_id"]
                        meta2["regression_report_trace_id"] = evidence_trace_id
                        meta2["regression_report_kind"] = "auto-rollback-regression"
                        await store.upsert_agent_execution(
                            {
                                "id": eid,
                                "agent_id": r.get("agent_id") or args.agent_id,
                                "status": r.get("status"),
                                "input": r.get("input") or {},
                                "output": r.get("output") or {},
                                "error": r.get("error"),
                                "start_time": r.get("start_time"),
                                "end_time": r.get("end_time"),
                                "duration_ms": r.get("duration_ms"),
                                "trace_id": r.get("trace_id"),
                                "metadata": meta2,
                                "approval_request_id": r.get("approval_request_id"),
                            }
                        )
                        updated_baseline_links += 1
                        linked_baseline.append(eid)
                    out["linked_baseline_executions"] = updated_baseline_links
                    out["linked_baseline_execution_ids"] = linked_baseline
                except Exception:
                    pass

            # Phase 6.22: best-effort update regression_report evidence with linked ids
            try:
                cap = int(args.max_linked_evidence or 200)
                cap = max(1, cap)
                rep = await store.get_learning_artifact(regression_report_id)
                if rep:
                    payload = rep.get("payload") if isinstance(rep.get("payload"), dict) else {}
                    deltas = payload.get("deltas") if isinstance(payload.get("deltas"), dict) else {}
                    ev = deltas.get("evidence") if isinstance(deltas.get("evidence"), dict) else {}
                    # Phase 6.23: merge/dedupe/cap to prevent evidence growth.
                    merged_current = _merge_unique_cap(
                        ev.get("linked_current_execution_ids"),
                        out.get("linked_current_execution_ids") or [],
                        cap=cap,
                    )
                    merged_baseline = _merge_unique_cap(
                        ev.get("linked_baseline_execution_ids"),
                        out.get("linked_baseline_execution_ids") or [],
                        cap=cap,
                    )
                    ev["linked_current_execution_ids"] = merged_current
                    ev["linked_baseline_execution_ids"] = merged_baseline
                    # Phase 6.24: truncation markers
                    ev["linked_evidence_cap"] = cap
                    ev["linked_current_truncated"] = (
                        isinstance(out.get("linked_current_execution_ids"), list) and len(out.get("linked_current_execution_ids")) > len(merged_current)
                    )
                    ev["linked_baseline_truncated"] = (
                        isinstance(out.get("linked_baseline_execution_ids"), list) and len(out.get("linked_baseline_execution_ids")) > len(merged_baseline)
                    )
                    deltas["evidence"] = ev
                    payload["deltas"] = deltas
                    await store.upsert_learning_artifact(
                        {
                            "artifact_id": rep.get("artifact_id"),
                            "kind": rep.get("kind"),
                            "target_type": rep.get("target_type"),
                            "target_id": rep.get("target_id"),
                            "version": rep.get("version"),
                            "status": rep.get("status"),
                            "trace_id": rep.get("trace_id"),
                            "run_id": rep.get("run_id"),
                            "payload": payload,
                            "metadata": rep.get("metadata") or {},
                            "created_at": rep.get("created_at"),
                        }
                    )
                    out["linked_evidence_cap"] = cap
                    out["linked_current_truncated"] = ev["linked_current_truncated"]
                    out["linked_baseline_truncated"] = ev["linked_baseline_truncated"]
            except Exception:
                pass
            # best-effort link from candidate metadata
            try:
                await mgr.set_artifact_status(
                    artifact_id=candidate_id,
                    status="rolled_back",
                    metadata_update={"rollback_regression_report_id": regression_report_id},
                )
            except Exception:
                pass
    else:
        out["rollback"] = "skipped"

    print(json.dumps(out, ensure_ascii=False))
    return 0


def main(argv: Optional[list[str]] = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", required=True, help="ExecutionStore sqlite path")

    sub = ap.add_subparsers(dest="cmd", required=True)

    c1 = sub.add_parser("create-eval-artifact", help="Create evaluation_report artifact from benchmark JSON")
    c1.add_argument("--target-type", required=True, choices=["agent", "skill", "prompt", "policy"])
    c1.add_argument("--target-id", required=True)
    c1.add_argument("--version", required=True)
    c1.add_argument("--benchmark-json", required=True)
    c1.add_argument("--trace-id")
    c1.add_argument("--run-id")

    c2 = sub.add_parser("list", help="List learning artifacts")
    c2.add_argument("--target-type")
    c2.add_argument("--target-id")
    c2.add_argument("--trace-id")
    c2.add_argument("--run-id")
    c2.add_argument("--limit", type=int, default=50)
    c2.add_argument("--offset", type=int, default=0)

    c3 = sub.add_parser("summarize-run", help="Summarize one agent run into a feedback_summary artifact")
    c3.add_argument("--run-id", required=True)
    c3.add_argument("--version", required=True)

    c4 = sub.add_parser("create-regression-artifact", help="Create regression_report artifact from current/baseline benchmark JSON")
    c4.add_argument("--target-type", required=True, choices=["agent", "skill", "prompt", "policy"])
    c4.add_argument("--target-id", required=True)
    c4.add_argument("--version", required=True)
    c4.add_argument("--current-json", required=True)
    c4.add_argument("--baseline-json", required=True)
    c4.add_argument("--trace-id")
    c4.add_argument("--run-id")

    c5 = sub.add_parser("create-skill-version-artifact", help="Create skill_evolution artifact from a SkillVersion JSON")
    c5.add_argument("--skill-version-json", required=True)
    c5.add_argument("--version", required=True, help="Artifact version label")
    c5.add_argument("--trace-id")
    c5.add_argument("--run-id")

    c6 = sub.add_parser("create-skill-rollback-artifact", help="Create skill_rollback artifact (record rollback)")
    c6.add_argument("--skill-id", required=True)
    c6.add_argument("--from-version")
    c6.add_argument("--to-version", required=True)
    c6.add_argument("--version", required=True, help="Artifact version label")
    c6.add_argument("--reason")
    c6.add_argument("--trace-id")
    c6.add_argument("--run-id")

    c7 = sub.add_parser("create-release-candidate", help="Create release_candidate artifact referencing artifact_ids")
    c7.add_argument("--target-type", required=True, choices=["agent", "skill", "prompt", "policy"])
    c7.add_argument("--target-id", required=True)
    c7.add_argument("--version", required=True)
    c7.add_argument("--artifact-ids", required=True, help="Comma-separated artifact ids")
    c7.add_argument("--summary")

    c7b = sub.add_parser("create-prompt-revision-artifact", help="Create prompt_revision artifact (prepend/append patch)")
    c7b.add_argument("--target-type", required=True, choices=["agent", "skill", "prompt", "policy"])
    c7b.add_argument("--target-id", required=True)
    c7b.add_argument("--version", required=True)
    c7b.add_argument("--prepend")
    c7b.add_argument("--append")
    c7b.add_argument("--patch-json", help="JSON file containing patch or {patch:{...}}")
    c7b.add_argument("--exclusive-group", help="Optional: conflicts within same group; strict mode keeps first only")
    c7b.add_argument("--priority", type=int, help="Optional: metadata priority (reserved)")
    c7b.add_argument("--trace-id")
    c7b.add_argument("--run-id")

    c8 = sub.add_parser("publish-release", help="Publish a release candidate (status transitions only)")
    c8.add_argument("--candidate-id", required=True)
    c8.add_argument("--user-id", default="system")
    c8.add_argument("--require-approval", action="store_true", default=False)
    c8.add_argument("--approval-request-id")
    c8.add_argument("--details")
    c8.add_argument("--ttl-seconds", help="Optional TTL (seconds) to set metadata.expires_at")
    c8.add_argument("--expires-at", help="Optional absolute expiry unix timestamp (seconds)")

    c9 = sub.add_parser("approve", help="Approve an approval_request_id (offline)")
    c9.add_argument("--approval-request-id", required=True)
    c9.add_argument("--approved-by", required=True)
    c9.add_argument("--comments")

    c9b = sub.add_parser("cleanup-rollback-approvals", help="Cancel stale pending rollback approvals (learning:rollback_release)")
    c9b.add_argument("--now", help="Override current time (unix seconds) for testing")
    c9b.add_argument("--dry-run", action="store_true", default=False)
    c9b.add_argument("--user-id", help="Optional filter by user_id")
    c9b.add_argument("--candidate-id", help="Optional filter by candidate_id")
    c9b.add_argument("--page-size", type=int, default=500, help="Pagination size for scanning approval_requests (default 500)")

    c10 = sub.add_parser("rollback-release", help="Rollback a published candidate (status transitions only)")
    c10.add_argument("--candidate-id", required=True)
    c10.add_argument("--reason")

    c11 = sub.add_parser("expire-releases", help="Rollback published release candidates that are expired")
    c11.add_argument("--target-type", choices=["agent", "skill", "prompt", "policy"])
    c11.add_argument("--target-id")
    c11.add_argument("--now", help="Override current time (unix seconds) for testing")
    c11.add_argument("--dry-run", action="store_true", default=False)

    c12 = sub.add_parser("auto-rollback-metrics", help="Auto rollback active release based on recent online metrics (offline)")
    c12.add_argument("--agent-id", required=True)
    c12.add_argument("--candidate-id", help="If omitted, use latest published release_candidate for agent")
    c12.add_argument("--window", type=int, default=50, help="How many recent executions to inspect")
    c12.add_argument("--min-samples", type=int, default=5)
    c12.add_argument("--error-rate-threshold", type=float, default=0.3)
    c12.add_argument("--max-avg-duration-ms", type=float)
    c12.add_argument("--now", help="Override current time (unix seconds) for testing")
    c12.add_argument("--dry-run", action="store_true", default=False)

    c13 = sub.add_parser("auto-rollback-regression", help="Auto rollback by comparing current window vs baseline window (offline)")
    c13.add_argument("--agent-id", required=True)
    c13.add_argument("--candidate-id", help="If omitted, use latest published release_candidate for agent")
    c13.add_argument("--baseline-candidate-id", help="Optional baseline candidate id; else use != current")
    c13.add_argument("--current-window", type=int, default=50)
    c13.add_argument("--baseline-window", type=int, default=50)
    c13.add_argument("--min-samples", type=int, default=10)
    c13.add_argument("--error-rate-delta-threshold", type=float, default=0.1)
    c13.add_argument("--avg-duration-delta-threshold", type=float)
    c13.add_argument("--now", help="Override current time (unix seconds) for testing")
    c13.add_argument("--dry-run", action="store_true", default=False)
    c13.add_argument("--link-baseline", action="store_true", default=False, help="Also link baseline executions to regression_report")
    c13.add_argument("--max-linked-evidence", type=int, default=200, help="Cap size of regression_report evidence linked_*_execution_ids (default 200)")
    c13.add_argument("--require-approval", action="store_true", default=False, help="Require human approval before rollback")
    c13.add_argument("--approval-request-id", help="Approval request id (required when --require-approval and already requested)")
    c13.add_argument("--user-id", default="system", help="User id for approval request")

    args = ap.parse_args(argv)

    if args.cmd == "create-eval-artifact":
        return anyio.run(_create_eval_artifact, args.db, args)
    if args.cmd == "list":
        return anyio.run(_list_artifacts, args.db, args)
    if args.cmd == "summarize-run":
        return anyio.run(_summarize_run, args.db, args)
    if args.cmd == "create-regression-artifact":
        return anyio.run(_create_regression_artifact, args.db, args)
    if args.cmd == "create-skill-version-artifact":
        return anyio.run(_create_skill_version_artifact, args.db, args)
    if args.cmd == "create-skill-rollback-artifact":
        return anyio.run(_create_skill_rollback_artifact, args.db, args)
    if args.cmd == "create-release-candidate":
        return anyio.run(_create_release_candidate, args.db, args)
    if args.cmd == "create-prompt-revision-artifact":
        return anyio.run(_create_prompt_revision_artifact, args.db, args)
    if args.cmd == "publish-release":
        return anyio.run(_publish_release, args.db, args)
    if args.cmd == "approve":
        return anyio.run(_approve, args.db, args)
    if args.cmd == "cleanup-rollback-approvals":
        return anyio.run(_cleanup_rollback_approvals, args.db, args)
    if args.cmd == "rollback-release":
        return anyio.run(_rollback_release, args.db, args)
    if args.cmd == "expire-releases":
        return anyio.run(_expire_releases, args.db, args)
    if args.cmd == "auto-rollback-metrics":
        return anyio.run(_auto_rollback_metrics, args.db, args)
    if args.cmd == "auto-rollback-regression":
        return anyio.run(_auto_rollback_regression, args.db, args)
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
