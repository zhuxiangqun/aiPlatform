"""
Failure Clusterer — Weakness Mining for Self-Harness optimization.

Implements Stage 1 of the Self-Harness loop:
  1. Collect execution traces from pipeline runs
  2. Classify failures by three dimensions (Verifier Cause / Causal Status / Abstract Mechanism)
  3. Cluster into signatures — only identical on all three dimensions are grouped
  4. Split into held-in (proposer sees) and held-out (validation gate uses)

Design reference: Shanghai AI Lab Self-Harness paper (2026)
  "Only when two failure cases are fully identical across the three dimensions above are they grouped into the same cluster"

callers: pipeline_engine (post-execution), wiki.py (view clusters), core_facade
"""

from __future__ import annotations

import hashlib
import json as _json
import logging
import os as _os
import time as _time
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)


# ══════════════════════════════════════════════════════════════
# Data Models
# ══════════════════════════════════════════════════════════════

@dataclass
class FailureSignature:
    verifier_cause: str
    causal_status: str
    abstract_mechanism: str
    stage_id: str = ""
    count: int = 1
    examples: List[Dict[str, str]] = field(default_factory=list)
    failure_type: str = ""  # "memory_loss" | "retrieval_interference" | "both"


@dataclass
class ClusterResult:
    signatures: List[FailureSignature]
    total_failures: int
    total_runs: int
    failure_rate: float
    collected_at: str = ""


# ══════════════════════════════════════════════════════════════
# Failure Classification
# ══════════════════════════════════════════════════════════════

def classify_verifier_cause(state: Dict[str, Any], stage_id: str) -> str:
    u"""Identify the final rejection reason from verifiers.

    Priority: assess_fail > compile_error > missing_artifact > timeout > assert_fail > unknown
    """
    assess = state.get(f"_assess_{stage_id}")
    if isinstance(assess, dict) and assess.get("overall") == "FAIL":
        return "assess_fail"

    bv = state.get(f"_behavior_verify_{stage_id}")
    if isinstance(bv, dict) and not bv.get("verified", True):
        return "compile_error"

    error = str(state.get("error", ""))
    if "missing" in error.lower() or "not found" in error.lower():
        return "missing_artifact"
    if "timeout" in error.lower() or "timeout" in str(state.get("_last_action_reason", "")):
        return "timeout"
    if "assert" in error.lower() or "failed" in error.lower():
        return "assert_fail"
    if "policy_denied" in error.lower() or "toolset_denied" in error.lower():
        return "policy_deny"

    return "unknown"


def classify_causal_status(state: Dict[str, Any], stage_id: str) -> str:
    u"""Classify how Agent behavior led to the failure.

    Uses stage output, quick check issues, and reflection data.
    """
    # Check for infinite exploration
    output = state.get(f"_stage_output_{stage_id}", "")
    last_reason = str(state.get("_last_action_reason", ""))
    if "budget_exhausted" in last_reason or "stagnation" in last_reason:
        return "exhausted_budget"
    if "stagnation" in last_reason or "max_iterations" in str(state.get("iteration", 0)):
        return "infinite_exploration"

    # Check for premature deletion
    if "deleted" in str(output).lower() or "remove" in str(output).lower():
        return "deleted_dependency"

    # Check for repeated failed attempts
    checks = state.get("_quick_check_issues", [])
    if len(checks) >= 3:
        return "repeated_failures"

    # Check for wrong tool usage
    if "invalid_tool" in str(error := state.get("error", "")).lower():
        return "wrong_tool_usage"

    if "format" in str(output).lower() and ("json" in str(output).lower() or "parse" in str(output).lower()):
        return "output_format_error"

    if "token_budget" in str(state.get("error", "")):
        return "context_overflow"

    return "unknown_behavior"


def classify_abstract_mechanism(state: Dict[str, Any], stage_id: str) -> str:
    u"""Identify the reusable behavioral pattern from the failure.

    These are the high-level patterns that Self-Harness can target.
    """
    causal = classify_causal_status(state, stage_id)

    mechanism_map = {
        "exhausted_budget": "early_endless_search",
        "infinite_exploration": "no_early_artifact_creation",
        "deleted_dependency": "delete_instead_of_fix",
        "repeated_failures": "identical_retry_loop",
        "wrong_tool_usage": "tool_selection_mismatch",
        "output_format_error": "format_drift",
        "context_overflow": "context_bloat",
        "unknown_behavior": "unclassified_pattern",
    }
    return mechanism_map.get(causal, "unclassified_pattern")


def classify_failure_type(
    state: Dict[str, Any],
    stage_id: str,
) -> str:
    u"""Classify failure as memory_loss, retrieval_interference, or both.

    Design from Neuron 2025 KV-memory paper:
      - memory_loss: artifact actually deleted or corrupted
      - retrieval_interference: artifact exists but couldn't be found/matched
      - both: signs of both problems

    This distinction matters for Self-Harness proposals:
      - retrieval_interference → fix indexing/search, not content creation
      - memory_loss → fix artifact persistence strategy
    """
    verifier = classify_verifier_cause(state, stage_id)
    causal = classify_causal_status(state, stage_id)
    error = str(state.get("error", "")).lower()

    # Signs of memory_loss: file not found, deleted, missing, corrupted
    memory_loss_signs = [
        "missing_artifact" in verifier,
        "not found" in error,
        "deleted" in error,
        "deleted_dependency" in causal,
    ]

    # Signs of retrieval_interference: format error, wrong tool, search mismatch
    retrieval_signs = [
        "output_format_error" in causal,
        "wrong_tool_usage" in causal,
        "format_drift" in str(state.get("_last_action_reason", "")),
        "assess_fail" in verifier,
        "assert_fail" in verifier and "file" not in error and "missing" not in error,
    ]

    if any(memory_loss_signs) and any(retrieval_signs):
        return "both"
    if any(retrieval_signs):
        return "retrieval_interference"
    if any(memory_loss_signs):
        return "memory_loss"
    return "memory_loss"  # default: assume content was lost


def generate_failure_example(state: Dict[str, Any], stage_id: str) -> Dict[str, str]:
    u"""Extract a minimal example from a failed run for the cluster."""
    return {
        "stage_id": stage_id,
        "error": str(state.get("error", ""))[:200],
        "last_reason": str(state.get("_last_action_reason", ""))[:100],
        "output_excerpt": str(state.get(f"_stage_output_{stage_id}", ""))[:200],
    }


# ══════════════════════════════════════════════════════════════
# Clustering Engine
# ══════════════════════════════════════════════════════════════

def _signature_key(verifier: str, causal: str, mechanism: str) -> str:
    u"""Hash the three-dimension signature for deduplication."""
    raw = f"{verifier}|{causal}|{mechanism}"
    return hashlib.md5(raw.encode()).hexdigest()[:12]


def cluster_failures(
    run_states: List[Dict[str, Any]],
    *,
    hold_out_ratio: float = 0.3,
) -> Tuple[ClusterResult, Dict[str, List[int]]]:
    u"""Cluster failures from multiple pipeline runs into signatures.

    Each run_state is a dict containing pipeline state after execution.
    Expects run_state to have: _current_stage_idx, stage config, error, etc.

    Returns:
        ClusterResult with clustered signatures.
        Dict mapping signature_key → [held_in_indices, held_out_indices]
    """
    clusters: Dict[str, FailureSignature] = {}
    hold_out_map: Dict[str, Tuple[List[int], List[int]]] = defaultdict(lambda: ([], []))
    total_runs = len(run_states)
    total_failures = 0

    for idx, state in enumerate(run_states):
        stage_idx = state.get("_current_stage_idx", 0)
        # Get all stages that produced errors
        stages = state.get("_graph_trace", [])
        failed_stages = [s for s in stages if s.get("status") in ("failed", "paused")]
        if not failed_stages:
            # Fallback: check global error
            if state.get("error"):
                stage_id = "pipeline"
                verifier = classify_verifier_cause(state, "pipeline")
                causal = classify_causal_status(state, "pipeline")
                mechanism = classify_abstract_mechanism(state, "pipeline")
                key = _signature_key(verifier, causal, mechanism)
                if key not in clusters:
                    clusters[key] = FailureSignature(
                        verifier_cause=verifier,
                        causal_status=causal,
                        abstract_mechanism=mechanism,
                        stage_id=stage_id,
                    )
                clusters[key].count += 1
                clusters[key].examples.append(generate_failure_example(state, stage_id))
                total_failures += 1
                hold_out_map[key][1 if idx % 3 == 0 else 0].append(idx)
            continue

        for fs in failed_stages:
            stage_id = fs.get("node", "unknown")
            verifier = classify_verifier_cause(state, stage_id)
            causal = classify_causal_status(state, stage_id)
            mechanism = classify_abstract_mechanism(state, stage_id)
            ftype = classify_failure_type(state, stage_id)
            key = _signature_key(verifier, causal, mechanism)

            if key not in clusters:
                clusters[key] = FailureSignature(
                    verifier_cause=verifier,
                    causal_status=causal,
                    abstract_mechanism=mechanism,
                    stage_id=stage_id,
                    failure_type=ftype,
                )
            clusters[key].count += 1
            clusters[key].examples.append(generate_failure_example(state, stage_id))
            total_failures += 1
            hold_out_map[key][1 if idx % 3 == 0 else 0].append(idx)

    signatures = sorted(clusters.values(), key=lambda s: s.count, reverse=True)
    hold_out_dict = {key: {"held_in": hi, "held_out": ho} for key, (hi, ho) in hold_out_map.items()}

    return ClusterResult(
        signatures=signatures,
        total_failures=total_failures,
        total_runs=total_runs,
        failure_rate=round(total_failures / max(1, total_runs), 3),
        collected_at=_time.strftime("%Y-%m-%dT%H:%M:%SZ", _time.gmtime()),
    ), hold_out_dict


# ══════════════════════════════════════════════════════════════
# Storage
# ══════════════════════════════════════════════════════════════

def _cluster_path() -> str:
    home = _os.getenv("AIPLAT_HOME", _os.path.expanduser("~/.aiplat"))
    return _os.path.join(home, "harness", "failure_clusters.json")


def save_clusters(clusters: ClusterResult) -> None:
    path = _cluster_path()
    _os.makedirs(_os.path.dirname(path), exist_ok=True)
    data = {
        "version": "v1.0",
        "updated_at": _time.time(),
        "total_failures": clusters.total_failures,
        "total_runs": clusters.total_runs,
        "failure_rate": clusters.failure_rate,
        "collected_at": clusters.collected_at,
        "signatures": [
            {
                "verifier_cause": s.verifier_cause,
                "causal_status": s.causal_status,
                "abstract_mechanism": s.abstract_mechanism,
                "stage_id": s.stage_id,
                "count": s.count,
                "examples": s.examples[:3],
            }
            for s in clusters.signatures
        ],
    }
    with open(path, "w", encoding="utf-8") as f:
        _json.dump(data, f, indent=2, ensure_ascii=False)


def load_clusters() -> Optional[ClusterResult]:
    path = _cluster_path()
    if not _os.path.exists(path):
        return None
    try:
        data = _json.load(open(path, "r", encoding="utf-8"))
        signatures = [
            FailureSignature(
                verifier_cause=s.get("verifier_cause", ""),
                causal_status=s.get("causal_status", ""),
                abstract_mechanism=s.get("abstract_mechanism", ""),
                stage_id=s.get("stage_id", ""),
                count=s.get("count", 0),
                examples=s.get("examples", []),
            )
            for s in data.get("signatures", [])
        ]
        return ClusterResult(
            signatures=signatures,
            total_failures=data.get("total_failures", 0),
            total_runs=data.get("total_runs", 0),
            failure_rate=data.get("failure_rate", 0.0),
            collected_at=data.get("collected_at", ""),
        )
    except Exception:
        return None
