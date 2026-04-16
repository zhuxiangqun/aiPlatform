"""
Phase 6.1: offline learning pipeline helpers (no behavior change).

This module provides pure helpers to convert existing evaluation/feedback/evolution
outputs into versioned LearningArtifact records, and optionally persist them via
LearningManager / ExecutionStore.

Constraints:
- Must be side-effect free with respect to agent execution (no sys_tool_call/sys_skill_call).
"""

from __future__ import annotations

import uuid
from typing import Any, Dict, Optional

from core.apps.evaluation.types import BenchmarkResult
from core.apps.evaluation.regression import RegressionDetector
from core.apps.skills.evolution.types import SkillVersion

from .types import LearningArtifact, LearningArtifactKind, LearningArtifactStatus


def summarize_syscall_events(events: list[dict]) -> dict:
    """
    Compute a minimal, JSON-serializable summary from syscall_events.
    Intended for Phase 6.2 offline feedback aggregation.
    """
    total = len(events)
    by_kind: Dict[str, int] = {}
    by_status: Dict[str, int] = {}
    approvals = 0
    duration_ms_sum = 0.0

    prompt_version_total = 0
    prompt_version_present = 0

    for e in events:
        kind = str(e.get("kind") or "unknown")
        status = str(e.get("status") or "unknown")
        by_kind[kind] = by_kind.get(kind, 0) + 1
        by_status[status] = by_status.get(status, 0) + 1

        if e.get("approval_request_id"):
            approvals += 1

        try:
            duration_ms_sum += float(e.get("duration_ms") or 0.0)
        except Exception:
            pass

        if kind == "llm":
            prompt_version_total += 1
            pv = (e.get("result") or {}).get("prompt_version") if isinstance(e.get("result"), dict) else None
            if pv:
                prompt_version_present += 1

    return {
        "total": total,
        "by_kind": by_kind,
        "by_status": by_status,
        "approvals": approvals,
        "duration_ms_sum": duration_ms_sum,
        "prompt_version_coverage": (prompt_version_present / prompt_version_total) if prompt_version_total else 1.0,
        "prompt_version_total": prompt_version_total,
    }


def artifact_from_benchmark_result(
    *,
    target_type: str,
    target_id: str,
    version: str,
    result: BenchmarkResult,
    trace_id: Optional[str] = None,
    run_id: Optional[str] = None,
    status: LearningArtifactStatus = LearningArtifactStatus.DRAFT,
    metadata: Optional[Dict[str, Any]] = None,
) -> LearningArtifact:
    """Create an evaluation_report artifact from a BenchmarkResult."""
    return LearningArtifact(
        artifact_id=str(uuid.uuid4()),
        kind=LearningArtifactKind.EVALUATION_REPORT,
        target_type=target_type,
        target_id=target_id,
        version=version,
        status=status,
        trace_id=trace_id,
        run_id=run_id,
        payload={
            "benchmark": result.to_dict(),
            "summary": {
                "benchmark_name": result.benchmark_name,
                "success_rate": result.success_rate,
                "pass_at_1": result.pass_at_1,
                "avg_latency_ms": result.avg_latency_ms,
                "avg_tokens": result.avg_tokens,
            },
        },
        metadata=metadata or {},
    )


def artifact_from_regression_result(
    *,
    target_type: str,
    target_id: str,
    version: str,
    current: BenchmarkResult,
    baseline: BenchmarkResult,
    trace_id: Optional[str] = None,
    run_id: Optional[str] = None,
    status: LearningArtifactStatus = LearningArtifactStatus.DRAFT,
    metadata: Optional[Dict[str, Any]] = None,
    detector: Optional[RegressionDetector] = None,
) -> LearningArtifact:
    """Create a regression_report artifact by comparing current vs baseline."""
    det = detector or RegressionDetector()
    reg = det.detect(current, baseline)
    return LearningArtifact(
        artifact_id=str(uuid.uuid4()),
        kind=LearningArtifactKind.REGRESSION_REPORT,
        target_type=target_type,
        target_id=target_id,
        version=version,
        status=status,
        trace_id=trace_id,
        run_id=run_id,
        payload={
            "has_regression": reg.has_regression,
            "changes": reg.changes,
            "recommendations": reg.recommendations,
            "current": current.to_dict(),
            "baseline": baseline.to_dict(),
        },
        metadata=metadata or {},
    )


def artifact_from_prompt_revision(
    *,
    target_type: str,
    target_id: str,
    version: str,
    patch: Dict[str, Any],
    trace_id: Optional[str] = None,
    run_id: Optional[str] = None,
    status: LearningArtifactStatus = LearningArtifactStatus.DRAFT,
    metadata: Optional[Dict[str, Any]] = None,
) -> LearningArtifact:
    """
    Create a prompt_revision artifact.

    Patch schema:
      {"prepend": "...", "append": "..."} (both optional)
    """
    p: Dict[str, Any] = {}
    if isinstance(patch.get("prepend"), str) and patch["prepend"].strip():
        p["prepend"] = patch["prepend"]
    if isinstance(patch.get("append"), str) and patch["append"].strip():
        p["append"] = patch["append"]
    return LearningArtifact(
        artifact_id=str(uuid.uuid4()),
        kind=LearningArtifactKind.PROMPT_REVISION,
        target_type=target_type,
        target_id=target_id,
        version=version,
        status=status,
        trace_id=trace_id,
        run_id=run_id,
        payload={"patch": p},
        metadata=metadata or {},
    )


def artifact_from_regression_decision(
    *,
    target_type: str,
    target_id: str,
    candidate_id: str,
    baseline_candidate_id: Optional[str],
    current: Dict[str, Any],
    baseline: Dict[str, Any],
    deltas: Dict[str, Any],
    decision: Dict[str, Any],
    baseline_selection: Optional[Dict[str, Any]] = None,
    artifact_version: Optional[str] = None,
    trace_id: Optional[str] = None,
    run_id: Optional[str] = None,
    metadata: Optional[Dict[str, Any]] = None,
) -> LearningArtifact:
    """
    Phase 6.19: Create a regression_report artifact for an online rollback decision.
    """
    ver = artifact_version or f"regression:{candidate_id}"
    payload = {
        "candidate_id": candidate_id,
        "baseline_candidate_id": baseline_candidate_id,
        "current": current,
        "baseline": baseline,
        "deltas": deltas,
        "decision": decision,
        "baseline_selection": baseline_selection or {},
    }
    return LearningArtifact(
        artifact_id=str(uuid.uuid4()),
        kind=LearningArtifactKind.REGRESSION_REPORT,
        target_type=target_type,
        target_id=target_id,
        version=ver,
        status=LearningArtifactStatus.PUBLISHED,
        trace_id=trace_id,
        run_id=run_id,
        payload=payload,
        metadata=metadata or {},
    )


def artifact_from_feedback_summary(
    *,
    target_type: str,
    target_id: str,
    version: str,
    feedback: Dict[str, Any],
    trace_id: Optional[str] = None,
    run_id: Optional[str] = None,
    status: LearningArtifactStatus = LearningArtifactStatus.DRAFT,
    metadata: Optional[Dict[str, Any]] = None,
) -> LearningArtifact:
    """Create a feedback_summary artifact from arbitrary feedback dict."""
    return LearningArtifact(
        artifact_id=str(uuid.uuid4()),
        kind=LearningArtifactKind.FEEDBACK_SUMMARY,
        target_type=target_type,
        target_id=target_id,
        version=version,
        status=status,
        trace_id=trace_id,
        run_id=run_id,
        payload={"feedback": feedback},
        metadata=metadata or {},
    )


def artifact_from_skill_evolution(
    *,
    skill_id: str,
    version: str,
    evolution: Dict[str, Any],
    trace_id: Optional[str] = None,
    run_id: Optional[str] = None,
    status: LearningArtifactStatus = LearningArtifactStatus.DRAFT,
    metadata: Optional[Dict[str, Any]] = None,
) -> LearningArtifact:
    """Create a skill_evolution artifact from evolution output dict."""
    return LearningArtifact(
        artifact_id=str(uuid.uuid4()),
        kind=LearningArtifactKind.SKILL_EVOLUTION,
        target_type="skill",
        target_id=skill_id,
        version=version,
        status=status,
        trace_id=trace_id,
        run_id=run_id,
        payload={"evolution": evolution},
        metadata=metadata or {},
    )


def artifact_from_skill_version(
    *,
    version_obj: SkillVersion,
    artifact_version: str,
    trace_id: Optional[str] = None,
    run_id: Optional[str] = None,
    status: LearningArtifactStatus = LearningArtifactStatus.DRAFT,
    metadata: Optional[Dict[str, Any]] = None,
) -> LearningArtifact:
    """
    Create a SKILL_EVOLUTION artifact from a SkillVersion object.
    This is the recommended mapping for Phase 6.4 lineage/version persistence.
    """
    payload = {
        "skill_version": {
            "id": version_obj.id,
            "skill_id": version_obj.skill_id,
            "version": version_obj.version,
            "parent_version": version_obj.parent_version,
            "evolution_type": version_obj.evolution_type.value if version_obj.evolution_type else None,
            "trigger": version_obj.trigger,
            "content_hash": version_obj.content_hash,
            "diff": version_obj.diff,
            "created_at": version_obj.created_at.isoformat() if getattr(version_obj, "created_at", None) else None,
            "metadata": version_obj.metadata or {},
        }
    }
    return LearningArtifact(
        artifact_id=str(uuid.uuid4()),
        kind=LearningArtifactKind.SKILL_EVOLUTION,
        target_type="skill",
        target_id=version_obj.skill_id,
        version=artifact_version,
        status=status,
        trace_id=trace_id,
        run_id=run_id,
        payload=payload,
        metadata=metadata or {},
    )


def artifact_from_skill_rollback(
    *,
    skill_id: str,
    from_version: Optional[str],
    to_version: str,
    artifact_version: str,
    reason: str = "",
    trace_id: Optional[str] = None,
    run_id: Optional[str] = None,
    status: LearningArtifactStatus = LearningArtifactStatus.DRAFT,
    metadata: Optional[Dict[str, Any]] = None,
) -> LearningArtifact:
    """Create a SKILL_ROLLBACK artifact (records rollback intent/outcome)."""
    return LearningArtifact(
        artifact_id=str(uuid.uuid4()),
        kind=LearningArtifactKind.SKILL_ROLLBACK,
        target_type="skill",
        target_id=skill_id,
        version=artifact_version,
        status=status,
        trace_id=trace_id,
        run_id=run_id,
        payload={
            "rollback": {
                "from_version": from_version,
                "to_version": to_version,
                "reason": reason,
            }
        },
        metadata=metadata or {},
    )


def artifact_from_online_run_summary(
    *,
    target_type: str,
    target_id: str,
    version: str,
    run_id: str,
    trace_id: Optional[str],
    agent_execution: Dict[str, Any],
    syscall_events: list[dict],
    status: LearningArtifactStatus = LearningArtifactStatus.DRAFT,
    metadata: Optional[Dict[str, Any]] = None,
) -> LearningArtifact:
    """Create a feedback_summary artifact from an online run (agent_executions + syscall_events)."""
    summary = summarize_syscall_events(syscall_events)
    payload = {
        "run": {
            "run_id": run_id,
            "trace_id": trace_id,
            "agent_id": agent_execution.get("agent_id"),
            "status": agent_execution.get("status"),
            "duration_ms": agent_execution.get("duration_ms"),
            "error": agent_execution.get("error"),
        },
        "syscalls": summary,
    }
    return LearningArtifact(
        artifact_id=str(uuid.uuid4()),
        kind=LearningArtifactKind.FEEDBACK_SUMMARY,
        target_type=target_type,
        target_id=target_id,
        version=version,
        status=status,
        trace_id=trace_id,
        run_id=run_id,
        payload=payload,
        metadata=metadata or {},
    )
