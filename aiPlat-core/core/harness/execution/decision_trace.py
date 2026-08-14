"""Decision Trace Graph — generic pipeline decision provenance.

Records per-stage decisions (confidence + upstream dependencies) so that
failure localization can walk the dependency graph backward and attribute
error contribution to the most likely source node.

Storage: in-memory cache + local JSON under ``~/.aiplat/decision_traces/``,
keyed by ``run_id`` (survives process restart). This is a GENERIC engine
capability — no business concepts, no hardcoded stage/artifact names.

Callers:
- ``core.harness.execution.pipeline_engine._run_stage_skill`` (record_decision)
- ``core.api.core_facade`` canonical re-export (locate_max_error_node)
"""
from __future__ import annotations

import json
import os
import threading
from typing import Any, Dict, List, Optional

_TRACE_DIR = os.path.expanduser("~/.aiplat/decision_traces")
_DEFAULT_CONFIDENCE = 0.7

_lock = threading.RLock()
_cache: Dict[str, Dict[str, Any]] = {}


def _trace_file(run_id: str) -> str:
    return os.path.join(_TRACE_DIR, f"{run_id}.json")


def _load(run_id: str) -> Dict[str, Any]:
    with _lock:
        if run_id in _cache:
            return _cache[run_id]
        data: Dict[str, Any] = {"run_id": run_id, "decisions": {}, "failed": []}
        try:
            if os.path.isfile(_trace_file(run_id)):
                with open(_trace_file(run_id), "r", encoding="utf-8") as fh:
                    data = json.load(fh)
        except Exception:  # noqa: best-effort-read — corrupt/missing trace treated as empty
            pass
        _cache[run_id] = data
        return data


def _save(run_id: str) -> None:
    with _lock:
        try:
            os.makedirs(_TRACE_DIR, exist_ok=True)
            with open(_trace_file(run_id), "w", encoding="utf-8") as fh:
                json.dump(_cache.get(run_id, {}), fh, ensure_ascii=False, indent=2)
        except Exception:  # noqa: best-effort-write — trace persistence is non-critical
            pass


def record_decision(
    run_id: str,
    stage_id: str,
    depends_on: Optional[List[str]] = None,
    confidence: Optional[float] = None,
    error_contribution: Optional[float] = None,
    agent_id: Optional[str] = None,
) -> Dict[str, Any]:
    """Record one stage decision into the trace graph.

    ``decision_id`` is ``f"{run_id}_{stage_id}"``. ``depends_on`` holds the
    upstream stage_ids; they are normalized to decision_ids internally.
    ``confidence`` is a 0-1 float (stage self-assessment), defaulting to 0.7
    when omitted. ``error_contribution`` is populated later by
    :func:`locate_max_error_node`. ``agent_id`` is recorded so that callers
    can resolve failures by agent_id (the id the fix flow knows) in addition
    to stage_id.
    """
    data = _load(run_id)
    decision_id = f"{run_id}_{stage_id}"
    upstream = [f"{run_id}_{sid}" for sid in (depends_on or [])]
    record = {
        "run_id": run_id,
        "stage_id": stage_id,
        "agent_id": agent_id or "",
        "decision_id": decision_id,
        "depends_on": upstream,
        "confidence": confidence if confidence is not None else _DEFAULT_CONFIDENCE,
        "error_contribution": error_contribution,
    }
    data["decisions"][decision_id] = record
    _save(run_id)
    return record


def _resolve_decision_id(run_id: str, sid: str) -> Optional[str]:
    """Resolve a stage_id or agent_id to the actual decision_id in the trace.

    The fix flow knows agents by ``agent_id`` (e.g. ``agent_engineer``), while
    decisions are keyed by ``stage_id`` (e.g. ``canvas_node_3``). This bridges
    the two: first try the direct ``f"{run_id}_{sid}"`` key, then fall back to
    matching a decision's ``agent_id`` field.
    """
    decisions = _load(run_id).get("decisions", {})
    direct = f"{run_id}_{sid}"
    if direct in decisions:
        return direct
    for did, rec in decisions.items():
        if rec.get("agent_id") == sid:
            return did
    return None


def _mark_failed(run_id: str, stage_ids: List[str]) -> None:
    """Mark downstream stages as failed so error propagates upstream."""
    data = _load(run_id)
    failed = data.setdefault("failed", [])
    for sid in stage_ids:
        decision_id = _resolve_decision_id(run_id, sid) or f"{run_id}_{sid}"
        if decision_id not in failed:
            failed.append(decision_id)
    _save(run_id)


def locate_max_error_node(
    run_id: str, failed_stage_ids: Optional[List[str]] = None
) -> Dict[str, Any]:
    """Walk the decision graph backward and return the node with max error contribution.

    ``error_contribution = (failed_downstream / total_downstream) * (1 - confidence)``.

    Returns a dict with ``stage_id`` / ``decision_id`` / ``error_contribution``
    (plus ``confidence`` / ``failed_downstream`` / ``total_downstream`` for
    transparency), or ``{"stage_id": None, "error_contribution": 0.0}`` when no
    upstream candidate explains any failure.
    """
    if failed_stage_ids:
        _mark_failed(run_id, failed_stage_ids)
    data = _load(run_id)
    decisions = data.get("decisions", {})
    failed = set(data.get("failed", []))

    downstream: Dict[str, List[str]] = {did: [] for did in decisions}
    for did, rec in decisions.items():
        for up in rec.get("depends_on", []):
            downstream.setdefault(up, []).append(did)

    # Propagate failure transitively backward — all ancestors are implicated
    # because their output flowed into the failing node.
    implicated = set(failed)
    frontier = list(failed)
    while frontier:
        cur = frontier.pop()
        for up in decisions.get(cur, {}).get("depends_on", []):
            if up not in implicated:
                implicated.add(up)
                frontier.append(up)

    best: Optional[Dict[str, Any]] = None
    for did, rec in decisions.items():
        total_downstream = len(downstream.get(did, []))
        if total_downstream == 0:
            continue
        failed_downstream = sum(1 for d in downstream.get(did, []) if d in implicated)
        if failed_downstream == 0:
            continue
        conf = float(rec.get("confidence", _DEFAULT_CONFIDENCE))
        contribution = (failed_downstream / total_downstream) * (1.0 - conf)
        rec["error_contribution"] = round(contribution, 4)
        candidate = {
            "stage_id": rec.get("stage_id"),
            "decision_id": did,
            "error_contribution": round(contribution, 4),
            "confidence": conf,
            "failed_downstream": failed_downstream,
            "total_downstream": total_downstream,
        }
        if best is None or contribution > best["error_contribution"]:
            best = candidate

    _save(run_id)
    return best or {
        "stage_id": None,
        "decision_id": None,
        "error_contribution": 0.0,
    }


def trace_root_cause_chain(
    run_id: str, failed_stage_ids: Optional[List[str]] = None
) -> List[Dict[str, Any]]:
    """Trace the full vertical root-cause chain from failure node(s) back to root.

    Unlike :func:`locate_max_error_node` (single max contributor), this returns
    the ordered chain of every implicated stage — deepest root first, failure
    node last — each with confidence + error_contribution + depth. This is the
    vertical drill-down for multi-level diagnosis.
    """
    if failed_stage_ids:
        _mark_failed(run_id, failed_stage_ids)
    data = _load(run_id)
    decisions = data.get("decisions", {})
    failed = set(data.get("failed", []))

    downstream: Dict[str, List[str]] = {did: [] for did in decisions}
    for did, rec in decisions.items():
        for up in rec.get("depends_on", []):
            downstream.setdefault(up, []).append(did)

    # BFS upward from failed nodes, recording depth (distance from failure).
    implicated = set(failed)
    depth = {d: 0 for d in failed}
    frontier = list(failed)
    while frontier:
        cur = frontier.pop(0)
        for up in decisions.get(cur, {}).get("depends_on", []):
            if up not in implicated:
                implicated.add(up)
                depth[up] = depth[cur] + 1
                frontier.append(up)

    # Compute error_contribution for each implicated node (consistent with locate).
    chain: List[Dict[str, Any]] = []
    for did in implicated:
        rec = decisions[did]
        total_downstream = len(downstream.get(did, []))
        failed_downstream = sum(1 for d in downstream.get(did, []) if d in implicated)
        conf = float(rec.get("confidence", _DEFAULT_CONFIDENCE))
        contribution = 0.0
        if total_downstream and failed_downstream:
            contribution = (failed_downstream / total_downstream) * (1.0 - conf)
        rec["error_contribution"] = round(contribution, 4)
        chain.append({
            "stage_id": rec.get("stage_id"),
            "decision_id": did,
            "confidence": conf,
            "error_contribution": round(contribution, 4),
            "depth": depth.get(did, 0),
            "failed_downstream": failed_downstream,
            "total_downstream": total_downstream,
        })

    _save(run_id)
    chain.sort(key=lambda x: -x["depth"])  # deepest root first
    return chain


def get_trace(run_id: str) -> Dict[str, Any]:
    """Return the full trace graph for ``run_id``."""
    return _load(run_id)


def build_fix_plan(
    run_id: str,
    failed_stage_ids: Optional[List[str]] = None,
    test_report: Optional[str] = None,
) -> List[str]:
    """Hybrid fix plan: prefer a single root cause, else the earliest failed stage.

    Returns the list of stage identifiers (agent_id preferred, falling back to
    stage_id) to regenerate. A single entry means "regenerate this stage and
    its downstream" (covers every failed stage in a linear pipeline).

    - Single root cause: when the trace shows a low-confidence node whose
      ``error_contribution`` is high (≥ 0.5), return just that node.
    - Otherwise: return the earliest (upstream-most) failed stage — its
      regeneration re-runs all downstream failed stages.

    ``test_report`` is reserved for future hypothesis-aware planning.
    """
    failed = list(failed_stage_ids or [])
    if not failed:
        return []
    if len(failed) == 1:
        return failed

    # 1) Prefer a strong single root cause.
    max_err = locate_max_error_node(run_id, failed)
    stage = max_err.get("stage_id")
    contribution = float(max_err.get("error_contribution", 0.0) or 0.0)
    if stage and contribution >= 0.5:
        did = _resolve_decision_id(run_id, stage)
        if did:
            rec = _load(run_id).get("decisions", {}).get(did, {})
            stage = rec.get("agent_id") or rec.get("stage_id")
        return [stage]

    # 2) Fall back: earliest (upstream-most) failed stage.
    decisions = _load(run_id).get("decisions", {})
    if not decisions:
        return [failed[0]]
    failed_dids = [_resolve_decision_id(run_id, s) or f"{run_id}_{s}" for s in failed]
    failed_set = set(failed_dids)

    def _ancestors(did: str) -> set:
        out = set()
        frontier = [did]
        while frontier:
            cur = frontier.pop()
            for up in decisions.get(cur, {}).get("depends_on", []):
                if up not in out:
                    out.add(up)
                    frontier.append(up)
        return out

    for did in failed_dids:
        if not (_ancestors(did) & failed_set):
            rec = decisions.get(did, {})
            return [rec.get("agent_id") or rec.get("stage_id") or did.rsplit("_", 1)[-1]]
    return failed


def clear_trace(run_id: str) -> None:
    """Drop the in-memory cache and JSON file for ``run_id``."""
    with _lock:
        _cache.pop(run_id, None)
        try:
            if os.path.isfile(_trace_file(run_id)):
                os.remove(_trace_file(run_id))
        except Exception:  # noqa: cleanup-best-effort — trace file may already be gone
            pass
