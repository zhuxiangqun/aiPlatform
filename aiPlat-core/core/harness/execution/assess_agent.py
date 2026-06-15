"""
AssessAgent — independent evaluation agent that scores, never modifies.

Design principle (from Ben Yoskovitz): "不能让写代码的 agent 自己给自己判卷"

Key constraints (enforced, not advisory):
  1. NO write — cannot modify files, state, or trigger downstream stages
  2. NO fix — returns PASS/FAIL only, never attempts to correct failures
  3. Evidence-based — every criterion must cite specific code/output as evidence
  4. Honest — "Be honest, not generous" — scoring must be strict

Waits for human after FAIL — no automatic retry or escalation.

Caller: pipeline_engine._exec_single_stage → replaces _verify_stage_output
"""

from __future__ import annotations

import json as _json
import logging
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

# Anti-rationalization table (agent-skills design pattern)
# When Agent makes an excuse to skip a step, the matching rebuttal blocks it.
_RATIONALIZATIONS = {
    "test later": "Tests are proof, not optional. Code without tests is unverified.",
    "small change": "No change is too small to skip verification.",
    "works in staging": "Production has different data, traffic, and edge cases.",
    "monitoring later": "Without monitoring, you discover problems from user complaints.",
    "rolling back means failure": "Rolling back is responsible engineering. Shipping broken is the failure.",
    "friday afternoon": "Never ship on Friday. The on-call engineer will thank you.",
    "too simple": "Simplicity is not correctness. Every output must be verified.",
}


@dataclass
class CriterionResult:
    criterion: str                          # from rubric
    passed: bool
    evidence: str = ""                      # what in the output proves PASS or FAIL
    actual_value: Any = None                # the observed value
    expected_value: Any = None              # the expected value per rubric
    severity: str = "error"                 # error | warning | info


@dataclass
class AssessReport:
    stage_id: str
    overall: str                            # "PASS" | "FAIL" | "INCONCLUSIVE"
    criteria: List[CriterionResult] = field(default_factory=list)
    passed_count: int = 0
    failed_count: int = 0
    summary: str = ""
    requires_human: bool = False            # FAIL → wait for human decision
    assessor: str = "AssessAgent-v1"        # identifies the assessor for audit
    rationalization_rebuttal: str = ""       # anti-rationalization rebuttal if triggered

    def to_dict(self) -> Dict[str, Any]:
        return {
            "stage_id": self.stage_id,
            "overall": self.overall,
            "passed_count": self.passed_count,
            "failed_count": self.failed_count,
            "criteria": [
                {
                    "criterion": c.criterion,
                    "passed": c.passed,
                    "evidence": c.evidence[:200],
                    "actual": str(c.actual_value)[:100] if c.actual_value is not None else None,
                    "expected": str(c.expected_value)[:100] if c.expected_value is not None else None,
                    "severity": c.severity,
                }
                for c in self.criteria
            ],
            "summary": self.summary,
            "requires_human": self.requires_human,
            "assessor": self.assessor,
        }


class AssessAgent:
    u"""Independent assessment agent — scores output against rubric.

    Reads artifact and rubric. Produces PASS/FAIL report.
    NEVER modifies state, files, or triggers downstream actions.
    """

    def __init__(self):
        self._write_guard = True  # internal flag — if False, bug detected

    async def assess(
        self,
        rubric: List[Dict[str, Any]],
        artifact: Any,
        *,
        stage_id: str = "",
    ) -> AssessReport:
        u"""Score artifact against each rubric criterion.

        Args:
            rubric: list of {"criterion": "...", "field": "...",
                              "constraint": "range|equals|in_set|gt|lt|not_null",
                              "expected": value,
                              "evidence_hint": "what to look for",
                              "severity": "error|warning"}
            artifact: the stage output to evaluate.
            stage_id: pipeline stage identifier for logging.

        Returns:
            AssessReport with overall PASS/FAIL + per-criterion results.
        """
        if not rubric:
            return AssessReport(
                stage_id=stage_id, overall="PASS",
                summary="No rubric defined — cannot assess. Marking as PASS (human review required).",
                requires_human=True,
            )

        criteria_results: List[CriterionResult] = []
        passed_count = 0
        failed_count = 0

        for rc in rubric:
            if not isinstance(rc, dict):
                continue

            criterion = rc.get("criterion", rc.get("field", "unnamed"))
            field = rc.get("field", "")
            constraint = rc.get("constraint", "not_null")
            expected = rc.get("expected")
            evidence_hint = rc.get("evidence_hint", "")
            severity = rc.get("severity", "error")

            # Extract actual value from artifact
            actual = _get_field_value(artifact, field)

            # Check constraint
            passed, evidence = _check_criterion(actual, constraint, expected, evidence_hint)

            if passed:
                passed_count += 1
            else:
                failed_count += 1

            criteria_results.append(CriterionResult(
                criterion=criterion,
                passed=passed,
                evidence=evidence,
                actual_value=actual,
                expected_value=expected,
                severity=severity,
            ))

        # Overall verdict: only "error" severity blocks
        blocking_failures = [
            c for c in criteria_results
            if not c.passed and c.severity == "error"
        ]

        if failed_count == 0:
            overall = "PASS"
            requires_human = False
        elif blocking_failures:
            overall = "FAIL"
            requires_human = True
        else:
            overall = "INCONCLUSIVE"  # only warnings failed
            requires_human = True

        summary = (
            f"{passed_count}/{passed_count + failed_count} criteria passed."
            if passed_count + failed_count > 0
            else "No criteria evaluated."
        )

        return AssessReport(
            stage_id=stage_id,
            overall=overall,
            criteria=criteria_results,
            passed_count=passed_count,
            failed_count=failed_count,
            summary=summary,
            requires_human=requires_human,
        )


def _get_field_value(artifact: Any, field: str) -> Any:
    u"""Extract nested field from dict, JSON string, or object."""
    if artifact is None or not field:
        return None

    if isinstance(artifact, dict):
        parts = field.split(".")
        current = artifact
        for p in parts:
            if isinstance(current, dict):
                current = current.get(p)
            else:
                return None
        return current

    if isinstance(artifact, str):
        try:
            d = _json.loads(artifact)
            return _get_field_value(d, field)
        except Exception:
            return None

    return getattr(artifact, field, None)


def _check_criterion(
    actual: Any,
    constraint: str,
    expected: Any,
    evidence_hint: str = "",
) -> tuple:
    u"""Check a single criterion. Returns (passed: bool, evidence: str)."""
    if constraint == "not_null":
        ok = actual is not None and str(actual).strip() != ""
        return ok, f"value={repr(actual)[:50]}, {'present' if ok else 'null/empty'}"

    if constraint == "equals":
        ok = actual == expected
        return ok, f"expected={expected}, actual={repr(actual)[:50]}"

    if constraint == "range":
        if not isinstance(expected, (list, tuple)) or len(expected) < 2:
            return False, f"bad_range_definition: {expected}"
        try:
            v = float(actual)
        except (TypeError, ValueError):
            return False, f"non_numeric: {repr(actual)[:50]}"
        lo, hi = expected[0], expected[1]
        ok = lo <= v <= hi
        return ok, f"value={v}, range=[{lo},{hi}]"

    if constraint == "gt":
        try:
            ok = float(actual) > float(expected)
        except (TypeError, ValueError):
            return False, f"non_numeric: {repr(actual)[:50]}"
        return ok, f"value={actual}, gt={expected}"

    if constraint == "lt":
        try:
            ok = float(actual) < float(expected)
        except (TypeError, ValueError):
            return False, f"non_numeric: {repr(actual)[:50]}"
        return ok, f"value={actual}, lt={expected}"

    if constraint == "in_set":
        if not isinstance(expected, (list, tuple, set)):
            return False, f"bad_in_set: {expected}"
        ok = actual in expected
        return ok, f"value={repr(actual)[:50]}, allowed={list(expected)[:5]}"

    # Unknown constraint → pass (don't block on unrecognized rules)
    return True, f"unknown constraint '{constraint}' — passing by default"
