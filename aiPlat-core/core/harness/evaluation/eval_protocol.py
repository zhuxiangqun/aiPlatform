"""Eval Protocol v0 — normalize internal eval artifacts to the public exchange shape.

SSOT schema: reports/five-products/modules/evaluation/contracts/schemas/eval_protocol.schema.json
"""
from __future__ import annotations

from typing import Any, Dict, Mapping, MutableMapping, Optional


SCHEMA_VERSION = "eval.protocol.v0"

_STATUS_MAP = {
    "ok": "passed",
    "pass": "passed",
    "passed": "passed",
    "success": "passed",
    "fail": "failed",
    "failed": "failed",
    "error": "error",
    "skipped": "skipped",
    "skip": "skipped",
    "pending": "pending",
    "running": "running",
}


def _as_dict(obj: Any) -> Dict[str, Any]:
    return dict(obj) if isinstance(obj, Mapping) else {}


def normalize_eval_status(raw: Any) -> str:
    s = str(raw or "").strip().lower()
    if s in _STATUS_MAP:
        return _STATUS_MAP[s]
    if s in {"passed", "failed", "skipped", "error", "pending", "running"}:
        return s
    return "error" if s else "pending"


def to_eval_protocol_v0(
    *,
    task_id: str,
    target_kind: str,
    target_ref: str,
    status: Any = "pending",
    suite: Optional[str] = None,
    params: Optional[Mapping[str, Any]] = None,
    trajectory_ref: Optional[str] = None,
    metrics: Optional[Mapping[str, Any]] = None,
    report: Optional[Mapping[str, Any]] = None,
    evidence_refs: Optional[list] = None,
    extra: Optional[Mapping[str, Any]] = None,
) -> Dict[str, Any]:
    """Build a protocol v0 object (always includes schema_version)."""
    kind = str(target_kind or "workflow").strip().lower()
    if kind not in {"agent", "skill", "workflow", "bundle", "http", "cli"}:
        kind = "workflow"
    out: Dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "task": {
            "id": str(task_id or "").strip() or "eval-unknown",
            "target_kind": kind,
            "target_ref": str(target_ref or "").strip() or "unknown",
        },
        "status": normalize_eval_status(status),
    }
    if suite:
        out["task"]["suite"] = str(suite)
    if params:
        out["task"]["params"] = dict(params)
    if trajectory_ref:
        out["trajectory_ref"] = str(trajectory_ref)
    if metrics:
        out["metrics"] = dict(metrics)
    if report:
        rep = dict(report)
        # Map common gate/pass fields
        if "gate" not in rep and "pass" in rep:
            rep["gate"] = "pass" if bool(rep.get("pass")) else "fail"
        out["report"] = rep
    if evidence_refs:
        out["evidence_refs"] = [str(x) for x in evidence_refs if x is not None]
    if extra:
        # Non-contract extras nest under extensions to avoid schema fights
        out["extensions"] = dict(extra)
    return out


def from_run_evaluation(
    *,
    run_id: str,
    evaluator: str = "evaluator",
    report: Optional[Mapping[str, Any]] = None,
    artifact: Optional[Mapping[str, Any]] = None,
) -> Dict[str, Any]:
    """Map persist_evaluation / learning artifact shapes → protocol v0."""
    art = _as_dict(artifact)
    payload = _as_dict(art.get("payload")) if art else {}
    rep = _as_dict(report) or _as_dict(payload.get("report")) or payload
    if not rep and art:
        rep = _as_dict(art)

    status_raw = rep.get("status")
    if status_raw is None and "pass" in rep:
        status_raw = "passed" if bool(rep.get("pass")) else "failed"

    metrics: Dict[str, Any] = {}
    for k in ("score", "pass_rate", "precision", "recall", "f1"):
        if k in rep and isinstance(rep.get(k), (int, float, bool, str)):
            metrics[k] = rep[k]
    if isinstance(rep.get("metrics"), Mapping):
        metrics.update({str(k): v for k, v in rep["metrics"].items()})

    evidence_refs = []
    for key in ("base_evidence_pack_id", "evidence_pack_id", "report_id"):
        if rep.get(key):
            evidence_refs.append(str(rep[key]))

    return to_eval_protocol_v0(
        task_id=f"run-eval:{run_id}",
        target_kind="workflow",
        target_ref=str(run_id),
        status=status_raw if status_raw is not None else "pending",
        suite=str(evaluator or "evaluator"),
        metrics=metrics or None,
        report={
            "summary": str(rep.get("summary") or rep.get("reason") or "")[:500],
            "score": rep.get("score"),
            "gate": (
                "pass"
                if bool(rep.get("pass"))
                else ("fail" if "pass" in rep else str(rep.get("gate") or "skip"))
            ),
        },
        evidence_refs=evidence_refs or None,
        extra={"artifact_id": art.get("id") or art.get("artifact_id"), "source": "run_evaluation"},
    )


def from_skill_eval_run(
    *,
    run_id: str,
    suite_id: str = "",
    run_row: Optional[Mapping[str, Any]] = None,
    result: Any = None,
) -> Dict[str, Any]:
    """Map skill-eval suite run row → protocol v0."""
    row = _as_dict(run_row)
    status = row.get("status") or row.get("state") or "pending"
    metrics = _as_dict(row.get("metrics"))
    if isinstance(result, Mapping):
        for k in ("pass_rate", "passed", "failed", "total"):
            if k in result and k not in metrics:
                metrics[k] = result[k]
        if "ok" in result and "pass_rate" not in metrics:
            metrics["ok"] = bool(result.get("ok"))
    return to_eval_protocol_v0(
        task_id=f"skill-eval:{run_id}",
        target_kind="skill",
        target_ref=str(suite_id or row.get("suite_id") or "suite"),
        status=status,
        suite=str(suite_id or row.get("suite_id") or ""),
        metrics=metrics or None,
        report={
            "summary": str(row.get("summary") or "")[:500],
            "gate": "pass" if normalize_eval_status(status) == "passed" else "fail",
        },
        extra={"source": "skill_eval", "raw_status": status},
    )


def from_gold_eval_result(
    *,
    result: Optional[Mapping[str, Any]] = None,
    profile: str = "balanced",
) -> Dict[str, Any]:
    """Map code-review gold eval result → protocol v0."""
    res = _as_dict(result)
    ok = res.get("ok")
    if ok is None:
        status = "passed" if res.get("precision") is not None else "error"
    else:
        status = "passed" if bool(ok) else "failed"
    metrics: Dict[str, Any] = {}
    for k in ("precision", "recall", "f1", "p0_recall", "n_cases", "duration_s"):
        if k in res and isinstance(res.get(k), (int, float, bool, str)):
            metrics[k] = res[k]
    score = res.get("f1")
    if score is None:
        score = res.get("precision")
    return to_eval_protocol_v0(
        task_id=f"code-review-gold:{profile}",
        target_kind="agent",
        target_ref=str(res.get("profile") or profile),
        status=status,
        suite=str(profile),
        metrics=metrics or None,
        report={
            "summary": str(res.get("error") or res.get("summary") or "")[:500],
            "score": score,
            "gate": "pass" if status == "passed" else "fail",
        },
        evidence_refs=[str(res["report_path"])] if res.get("report_path") else None,
        extra={"source": "code_review_gold"},
    )


def from_generic_eval(
    *,
    task_id: str,
    target_kind: str,
    target_ref: str,
    result: Optional[Mapping[str, Any]] = None,
    suite: str = "",
) -> Dict[str, Any]:
    """Best-effort map for kb/prompt eval payloads."""
    res = _as_dict(result)
    status = res.get("status") or ("passed" if res.get("ok") else None) or "pending"
    metrics = _as_dict(res.get("metrics"))
    for k in ("score", "pass_rate", "passed", "failed", "total"):
        if k in res and k not in metrics:
            metrics[k] = res[k]
    return to_eval_protocol_v0(
        task_id=task_id,
        target_kind=target_kind,
        target_ref=target_ref,
        status=status,
        suite=suite or None,
        metrics=metrics or None,
        report={
            "summary": str(res.get("summary") or res.get("error") or "")[:500],
            "score": res.get("score"),
            "gate": "pass" if normalize_eval_status(status) == "passed" else "fail",
        },
        extra={"source": "generic_eval"},
    )


def attach_protocol(response: MutableMapping[str, Any], protocol: Mapping[str, Any]) -> MutableMapping[str, Any]:
    """Attach protocol under `eval_protocol` without removing legacy fields."""
    response["eval_protocol"] = dict(protocol)
    return response


def to_evaluation_healthz(
    *,
    status: str = "ok",
    version: str = "0.0.0",
    protocol: str = SCHEMA_VERSION,
) -> Dict[str, Any]:
    """Evaluation capability healthz (A1/D1 co-hosted on Central)."""
    st = normalize_eval_status(status)
    # Map protocol statuses → healthz enum
    if st in {"passed", "pending", "running"}:
        hz = "ok"
    elif st in {"skipped"}:
        hz = "degraded"
    else:
        hz = "fail" if st in {"failed", "error"} else "ok"
    raw = str(status or "").strip().lower()
    if raw in {"ok", "healthy", "degraded", "fail"}:
        hz = "ok" if raw == "healthy" else raw
    return {
        "status": hz,
        "version": str(version or "0.0.0"),
        "product_id": "evaluation",
        "capability_id": "evaluation",
        "deploy_unit": "central",
        "protocol": str(protocol or SCHEMA_VERSION),
    }


# Alias used by some call sites
from_gold_eval = from_gold_eval_result
