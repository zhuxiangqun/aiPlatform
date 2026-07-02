"""
Stage Output Verification & Replay Engine — deterministic guard for LLM outputs.

Two complementary mechanisms:
  1. Expected Outcome Verification — check algorithmic stage output against
     declared expected ranges/values before proceeding.
  2. Replay Verification — re-execute the same input and compare outputs.
     If results diverge, escalate to HITL.

Architecture:
  Verification is a pipeline hook, not a separate service. It runs AFTER
  stage output is produced but BEFORE it flows to downstream stages or
  external writebacks.

callers:
  - pipeline_engine._exec_single_stage (after stage completion)
  - policy_gate (verify gate)
  - core_facade (expose verification replay for auditing)
"""

from __future__ import annotations

import hashlib
import json as _json
import logging
import os as _os
import time as _time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)


@dataclass
class ExpectedOutcome:
    field: str                      # field name in stage output
    constraint: str                 # "range", "equals", "in_set", "gt", "lt", "not_null", "matches_like"
    expected: Any = None            # the expected value/range
    severity: str = "error"         # "error" (block) | "warning" (log only)


@dataclass
class VerificationResult:
    stage_id: str
    verified: bool
    checks_passed: int
    checks_failed: int
    failures: List[Dict[str, Any]] = field(default_factory=list)
    replay_consistent: bool = True
    replay_diff: Optional[List[str]] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "stage_id": self.stage_id,
            "verified": self.verified,
            "checks_passed": self.checks_passed,
            "checks_failed": self.checks_failed,
            "failures": self.failures[:10],
            "replay_consistent": self.replay_consistent,
            "replay_diff": self.replay_diff,
        }


# ══════════════════════════════════════════════════════════════
# Expected Outcome Verification
# ══════════════════════════════════════════════════════════════

def verify_against_expected(
    artifact: Any,
    expected_outcomes: List[Dict[str, Any]],
    *,
    stage_id: str = "",
) -> VerificationResult:
    u"""Check stage output against declared expected outcomes.

    Expected outcome dicts:
      {"field": "net_requirement", "constraint": "range", "expected": [0, 1000]}
      {"field": "status", "constraint": "in_set", "expected": ["OK", "WARN"]}
      {"field": "order_id", "constraint": "not_null"}
      {"field": "total", "constraint": "gt", "expected": 0}

    Returns VerificationResult with pass/fail details.
    """
    outcomes = [ExpectedOutcome(**e) if isinstance(e, dict) else e for e in expected_outcomes]
    failures: List[Dict] = []
    checks_passed = 0
    checks_failed = 0

    for outcome in outcomes:
        value = _get_field_value(artifact, outcome.field)
        ok, err = _check_constraint(value, outcome)
        if ok:
            checks_passed += 1
        else:
            checks_failed += 1
            failures.append({
                "field": outcome.field,
                "constraint": outcome.constraint,
                "expected": outcome.expected,
                "actual": str(value)[:200] if value is not None else None,
                "error": err,
                "severity": outcome.severity,
            })

    # Only "error" severity failures block
    blocking = [f for f in failures if f["severity"] == "error"]
    verified = len(blocking) == 0

    return VerificationResult(
        stage_id=stage_id,
        verified=verified,
        checks_passed=checks_passed,
        checks_failed=checks_failed,
        failures=failures,
    )


def _get_field_value(artifact: Any, field: str) -> Any:
    u"""Get a nested field value from dict, JSON string, or object attribute."""
    if artifact is None:
        return None
    if isinstance(artifact, dict):
        if "." in field:
            parts = field.split(".")
            current = artifact
            for p in parts:
                if isinstance(current, dict):
                    current = current.get(p)
                else:
                    return None
            return current
        return artifact.get(field)
    if isinstance(artifact, str):
        try:
            d = _json.loads(artifact)
            return d.get(field) if isinstance(d, dict) else None
        except Exception:
            return None
    return getattr(artifact, field, None)


def _check_constraint(value: Any, outcome: ExpectedOutcome) -> Tuple[bool, str]:
    c = outcome.constraint
    e = outcome.expected

    if c == "not_null":
        return value is not None and str(value).strip() != "", "value is null or empty"

    if c == "equals":
        return value == e, f"expected {e}, got {repr(value)}"

    if c == "range":
        if not isinstance(e, (list, tuple)) or len(e) < 2:
            return False, f"range constraint needs [min, max], got {e}"
        lo, hi = e[0], e[1]
        try:
            v = float(value)
        except (TypeError, ValueError):
            return False, f"value {value} is not numeric"
        return lo <= v <= hi, f"value {v} not in range [{lo}, {hi}]"

    if c == "gt":
        try:
            return float(value) > float(e), f"value {value} <= {e}"
        except (TypeError, ValueError):
            return False, f"value {value} not numeric"

    if c == "lt":
        try:
            return float(value) < float(e), f"value {value} >= {e}"
        except (TypeError, ValueError):
            return False, f"value {value} not numeric"

    if c == "in_set":
        if not isinstance(e, (list, tuple, set)):
            return False, f"in_set constraint needs a list, got {type(e)}"
        return value in e, f"value {repr(value)} not in {list(e)[:10]}"

    if c == "matches_like":
        return str(value) == str(e), f"value '{str(value)[:100]}' does not match '{str(e)[:100]}'"

    return True, ""  # unknown constraint → pass


# ══════════════════════════════════════════════════════════════
# Replay Verification
# ══════════════════════════════════════════════════════════════

_REPLAY_STORE: Dict[str, Dict[str, Any]] = {}  # session_id → {input_hash: output_snapshot}


def record_replay_snapshot(
    session_id: str,
    stage_id: str,
    input_hash: str,
    output_snapshot: str,
    algorithm_result: Optional[Dict] = None,
) -> None:
    u"""Record a snapshot for later replay verification.

    Algorithm nodes always record. LLM stages only record if
    AIPLAT_ENABLE_REPLAY is set.
    """
    key = f"{session_id}:{stage_id}"
    if key not in _REPLAY_STORE:
        _REPLAY_STORE[key] = {}
    _REPLAY_STORE[key][input_hash] = {
        "output": output_snapshot,
        "algorithm": _json.dumps(algorithm_result, ensure_ascii=False) if algorithm_result else None,
        "timestamp": _time.time(),
        "tbox_hash": _compute_tbox_hash(),
    }


def _compute_tbox_hash() -> str:
    u"""Compute a hash of the current T-Box structure (classes only).

    Used for replay versioning: if the T-Box changed, old snapshots are
    marked stale rather than attempting to compare across versions.
    """
    try:
        import hashlib
        from core.harness.knowledge.knowledge_ontology import get_ontology
        onto = get_ontology()
        class_uris = sorted([c.uri for c in onto.classes])
        return hashlib.sha256(
            _json.dumps(class_uris, sort_keys=True).encode()
        ).hexdigest()[:16]
    except Exception:
        return "unknown"


def verify_replay(
    session_id: str,
    stage_id: str,
    input_hash: str,
    current_output: str,
    *,
    algorithm_result: Optional[Dict] = None,
) -> Optional[VerificationResult]:
    u"""Check if this input was seen before and output is consistent.

    Returns VerificationResult if a replay was found and compared.
    Returns None if no prior snapshot for this input.
    """
    key = f"{session_id}:{stage_id}"
    snapshots = _REPLAY_STORE.get(key, {})
    prior = snapshots.get(input_hash)

    if prior is None:
        return None

    # Phase 4 fix: version check — if T-Box changed, replay is stale
    prior_hash = prior.get("tbox_hash", "unknown")
    current_hash = _compute_tbox_hash()
    if prior_hash != "unknown" and prior_hash != current_hash:
        return VerificationResult(
            stage_id=stage_id,
            verified=False,
            checks_passed=0, checks_failed=0,
            replay_consistent=None,  # cannot determine
            replay_diff=[f"ontology_version_changed: tbox_hash {prior_hash} → {current_hash}"],
        )

    diff = []
    consistent = True

    # For algorithm nodes: extract numeric values and compare
    if algorithm_result and prior.get("algorithm"):
        try:
            prior_algo = _json.loads(prior["algorithm"])
            current_algo = algorithm_result
            for k in ("net_requirement", "total_allocated", "planned_order_quantity",
                       "converted_amount", "items_expanded"):
                pv = prior_algo.get("result", {}).get(k) or prior_algo.get(k)
                cv = current_algo.get("result", {}).get(k) or current_algo.get(k)
                if pv is not None and cv is not None and pv != cv:
                    diff.append(f"{k}: {pv} → {cv}")
                    consistent = False
        except Exception as e:
            logging.warning(str(e), exc_info=True)

    # For LLM outputs: compare hash (strict) or structural keys (loose)
    if not algorithm_result:
        prior_hash = hashlib.sha256(prior["output"].encode()).hexdigest()[:12]
        current_hash = hashlib.sha256(current_output.encode()).hexdigest()[:12]
        if prior_hash != current_hash:
            # Loose check: compare artifact key structure
            try:
                prior_keys = set(_json.loads(prior["output"]).keys()) if prior["output"].startswith("{") else set()
                current_keys = set(_json.loads(current_output).keys()) if current_output.startswith("{") else set()
                missing = prior_keys - current_keys
                extra = current_keys - prior_keys
                if missing or extra:
                    diff.append(f"keys changed: -{missing} +{extra}")
                    consistent = False
            except Exception:
                diff.append(f"hash mismatch: {prior_hash} vs {current_hash}")
                consistent = False

    return VerificationResult(
        stage_id=stage_id,
        verified=consistent,
        checks_passed=1 if consistent else 0,
        checks_failed=0 if consistent else 1,
        replay_consistent=consistent,
        replay_diff=diff if not consistent else None,
        failures=[] if consistent else [{"replay_inconsistent": True, "diff": diff}],
    )


def clear_replay_store() -> None:
    u"""Clear in-memory replay store (for testing or reset)."""
    _REPLAY_STORE.clear()
