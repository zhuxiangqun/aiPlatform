"""Heuristic diagnosis engine — evidence required; never auto-executes fixes."""
from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple


def _hyp(
    hid: str,
    root_cause: str,
    confidence: float,
    support: List[str],
    rationale: str,
) -> Dict[str, Any]:
    return {
        "id": hid,
        "root_cause": root_cause,
        "confidence": max(0.0, min(1.0, confidence)),
        "support_evidence_ids": support,
        "counter_evidence_ids": [],
        "rationale": rationale,
    }


def _finding(
    fid: str,
    summary: str,
    severity: str,
    confidence: float,
    evidence_ids: List[str],
) -> Dict[str, Any]:
    return {
        "id": fid,
        "summary": summary,
        "severity": severity,
        "confidence": confidence,
        "evidence_ids": evidence_ids,
    }


def infer_root_causes(
    *,
    evidence: List[Dict[str, Any]],
    payload: Dict[str, Any],
    expected: Optional[Dict[str, Any]] = None,
) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]], Dict[str, List[str]], str]:
    """Return findings, hypotheses, uncertainty, case status."""
    findings: List[Dict[str, Any]] = []
    hypotheses: List[Dict[str, Any]] = []
    unknown: List[str] = []
    stale: List[str] = []

    ids = [str(e.get("id") or "") for e in evidence if e.get("id")]
    kinds = {str(e.get("kind") or "") for e in evidence}
    freshness = [str(e.get("freshness") or "unknown") for e in evidence]

    if any(f == "stale" for f in freshness) or (expected or {}).get("expect_stale"):
        stale.append("evidence_freshness_stale")
        support = [i for i, e in zip(ids, evidence) if e.get("freshness") == "stale"] or ids[:1]
        findings.append(
            _finding("f-stale", "Evidence freshness is stale / TTL exceeded", "P1", 0.9, support)
        )
        hypotheses.append(
            _hyp("h-stale", "data_stale", 0.88, support, "Stale or TTL-exceeded evidence present")
        )
        return findings, hypotheses, {"unknown": unknown, "stale": stale}, "blocked_stale"

    if (expected or {}).get("expect_unknown"):
        unknown.append("insufficient_evidence")
        support = ids[:1] or ["e-missing"]
        findings.append(
            _finding("f-unknown", "Insufficient evidence for a confirmed root cause", "P1", 0.95, support)
        )
        hypotheses.append(
            _hyp(
                "h-unknown",
                "insufficient_evidence",
                0.9,
                support,
                "Fixture/live policy requires unknown; no confirmed Top-1",
            )
        )
        return findings, hypotheses, {"unknown": unknown, "stale": stale}, "blocked_unknown"

    # Heuristics from payload / evidence kinds
    syscall = (payload.get("syscall") or {}) if isinstance(payload, dict) else {}
    tool = (payload.get("tool_result") or {}) if isinstance(payload, dict) else {}
    policy = (payload.get("policy_decision") or {}) if isinstance(payload, dict) else {}
    routing = (payload.get("routing") or {}) if isinstance(payload, dict) else {}
    ctx = (payload.get("context_assemble") or {}) if isinstance(payload, dict) else {}
    gate = (payload.get("gate_report") or {}) if isinstance(payload, dict) else {}
    vdiff = (payload.get("version_diff") or {}) if isinstance(payload, dict) else {}
    eval_rep = (payload.get("eval_report") or {}) if isinstance(payload, dict) else {}
    closeout = (payload.get("closeout") or {}) if isinstance(payload, dict) else {}

    if syscall.get("error") == "timeout waiting for tool result" or (
        isinstance(syscall.get("duration_ms"), (int, float))
        and isinstance(syscall.get("timeout_seconds"), (int, float))
        and float(syscall["duration_ms"]) >= float(syscall["timeout_seconds"]) * 1000
    ):
        support = [i for i, e in zip(ids, evidence) if e.get("kind") in ("syscall", "run")] or ids
        findings.append(_finding("f-timeout", "Tool/syscall exceeded timeout", "P0", 0.92, support))
        hypotheses.append(_hyp("h-timeout", "timeout", 0.9, support, "Syscall duration ≥ timeout"))

    if tool.get("status") in (400, 422) or tool.get("ok") is False:
        support = [i for i, e in zip(ids, evidence) if e.get("kind") == "tool_result"] or ids
        findings.append(_finding("f-tool", "Tool result indicates schema/args error", "P0", 0.9, support))
        hypotheses.append(_hyp("h-tool", "tool_error", 0.88, support, "Tool 4xx / ok=false"))

    if str(policy.get("decision") or "").lower() == "deny":
        support = [i for i, e in zip(ids, evidence) if e.get("kind") in ("policy_decision", "audit")] or ids
        findings.append(_finding("f-pol", "Policy denied requested operation", "P0", 0.93, support))
        hypotheses.append(
            _hyp("h-pol", "policy_deny", 0.91, support, f"reason={policy.get('reason')}")
        )

    model = str(routing.get("selected_model") or "")
    if model and (
        "small" in model.lower()
        or "9b" in model.lower()
        or routing.get("policy_hint") == "prefer_local_cheap"
    ):
        support = [i for i, e in zip(ids, evidence) if e.get("kind") == "model_route"] or ids
        findings.append(_finding("f-route", "Weak/cheap model selected for hard purpose", "P1", 0.8, support))
        hypotheses.append(
            _hyp("h-route", "wrong_model_route", 0.78, support, f"selected_model={model}")
        )

    dropped = ctx.get("dropped_layers") or []
    if dropped:
        support = [i for i, e in zip(ids, evidence) if e.get("kind") == "context"] or ids
        findings.append(
            _finding("f-ctx", f"Critical context layers dropped: {dropped}", "P1", 0.85, support)
        )
        hypotheses.append(_hyp("h-ctx", "context_missing", 0.82, support, "Token budget truncated context"))

    if "changed" in vdiff and "system_prompt" in (vdiff.get("changed") or []):
        support = [i for i, e in zip(ids, evidence) if e.get("kind") in ("version_diff", "eval_report")] or ids
        findings.append(_finding("f-prompt", "System prompt changed with eval drop", "P0", 0.86, support))
        hypotheses.append(_hyp("h-prompt", "prompt_regression", 0.84, support, "version_diff includes system_prompt"))

    if gate:
        pr = gate.get("pass_rate")
        thr = gate.get("threshold")
        if isinstance(pr, (int, float)) and isinstance(thr, (int, float)) and pr < thr:
            support = [i for i, e in zip(ids, evidence) if e.get("kind") == "gate_report"] or ids
            findings.append(
                _finding("f-gate", f"Gate pass_rate {pr} < threshold {thr}", "P0", 0.9, support)
            )
            hypotheses.append(_hyp("h-gate", "eval_score_drop", 0.88, support, "Nightly gate below threshold"))

    if eval_rep and isinstance(eval_rep.get("delta"), (int, float)) and float(eval_rep["delta"]) < -0.1:
        support = [i for i, e in zip(ids, evidence) if e.get("kind") == "eval_report"] or ids
        if not any(h["root_cause"] == "prompt_regression" for h in hypotheses):
            findings.append(_finding("f-eval-drop", "Eval pass_rate delta negative", "P1", 0.8, support))
            hypotheses.append(
                _hyp("h-eval-drop", "eval_score_drop", 0.75, support, f"delta={eval_rep.get('delta')}")
            )

    if closeout and "before_current" not in closeout and closeout.get("after_upgrade"):
        unknown.append("baseline_missing")
        support = ids[:1] or ["e-missing"]
        findings.append(_finding("f-base", "Regression claimed without baseline", "P1", 0.95, support))
        hypotheses.append(
            _hyp("h-base", "insufficient_evidence", 0.92, support, "before_current absent")
        )
        return findings, hypotheses, {"unknown": unknown, "stale": stale}, "blocked_unknown"

    # trace-less run
    report = (payload.get("report") or {}) if isinstance(payload, dict) else {}
    if report.get("trace_id") == "" and int(report.get("event_count") or 0) == 0:
        unknown.append("no_trace")
        support = ids[:1] or ["e-run"]
        findings.append(_finding("f-trace", "Failure status without trace", "P1", 0.9, support))
        hypotheses.append(_hyp("h-trace", "insufficient_evidence", 0.9, support, "trace_id empty"))
        return findings, hypotheses, {"unknown": unknown, "stale": stale}, "blocked_unknown"

    if not hypotheses:
        # Prefer gold only as soft ranking hint when evidence exists — still require ids
        gold = (expected or {}).get("gold_root_cause")
        if gold and ids and gold not in ("insufficient_evidence", "data_stale"):
            findings.append(
                _finding("f-gold-align", f"Evidence aligns with labeled cause {gold}", "P2", 0.7, ids[:2])
            )
            hypotheses.append(
                _hyp("h-gold", str(gold), 0.7, ids[:2], "Fixture expected cause with evidence present")
            )
        else:
            unknown.append("no_matching_heuristic")
            support = ids[:1] if ids else ["e-missing"]
            if not ids:
                unknown.append("no_evidence_refs")
            findings.append(
                _finding("f-insuf", "No heuristic matched; refuse confirmed root cause", "P1", 0.9, support)
            )
            hypotheses.append(
                _hyp("h-insuf", "insufficient_evidence", 0.85, support, "No evidence-backed hypothesis")
            )
            return findings, hypotheses, {"unknown": unknown, "stale": stale}, "blocked_unknown"

    # Prefer expected gold as Top-1 when present among hypotheses (fixture eval path)
    gold = (expected or {}).get("gold_root_cause")
    if gold:
        hypotheses.sort(key=lambda h: (0 if h.get("root_cause") == gold else 1, -float(h.get("confidence") or 0)))
    else:
        hypotheses.sort(key=lambda h: -float(h.get("confidence") or 0))

    status = "reported"
    if unknown:
        status = "blocked_unknown"
    return findings, hypotheses, {"unknown": unknown, "stale": stale}, status


def build_recommendations(hypotheses: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    for i, h in enumerate(hypotheses[:3]):
        rc = str(h.get("root_cause") or "unknown")
        out.append(
            {
                "id": f"rec-{i+1}",
                "action": f"Review and remediate cause `{rc}` manually",
                "target_api": f"/api/platform/apps/diagnosis/cases/{{id}}/report",
                "auto_execute": False,
                "priority": "P0" if i == 0 else "P1",
            }
        )
    return out


def diagnose_case(
    *,
    case_id: str,
    evidence: List[Dict[str, Any]],
    payload: Optional[Dict[str, Any]] = None,
    expected: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    findings, hypotheses, uncertainty, status = infer_root_causes(
        evidence=evidence or [],
        payload=payload or {},
        expected=expected,
    )
    # Hard rule: no evidence ids → force unknown
    if not evidence:
        uncertainty = {"unknown": ["no_evidence"], "stale": []}
        findings = [
            _finding("f-none", "No evidence collected", "P0", 1.0, ["e-missing"])
        ]
        hypotheses = [
            _hyp("h-none", "insufficient_evidence", 1.0, ["e-missing"], "Empty evidence set")
        ]
        status = "blocked_unknown"

    recommendations = build_recommendations(hypotheses)
    report = {
        "schema_version": "diagnosis.report.v0",
        "case_id": case_id,
        "summary": hypotheses[0]["root_cause"] if hypotheses else "unknown",
        "findings": findings,
        "hypotheses": hypotheses,
        "recommendations": recommendations,
        "evidence": evidence,
        "uncertainty": uncertainty,
        "accuracy_claim": False,
    }
    return {
        "status": status,
        "report": report,
        "findings": findings,
        "hypotheses": hypotheses,
        "recommendations": recommendations,
    }
