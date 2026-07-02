"""
Pipeline Sandbox — deployment gate that synthesizes variant scenarios from
past successful runs and validates the pipeline against them.

Design principle (from Shanghai AI Lab / trading simulation paper):
  "静态回测忽略市场影响 → 实盘崩溃"
  → Sandbox generates interactive variant scenarios to surface hidden fragility.

Core workflow:
  1. Take N past successful pipeline configs + their inputs
  2. Synthesize M variant scenarios (inject boundary values, reorder fields, reword inputs)
  3. Execute pipeline on all M scenarios
  4. If any FAIL → block deployment + return per-scenario diagnostics

Lightweight: deterministic mutations only, no LLM needed for scenario synthesis.

callers: /pipeline/ship (pre-deployment gate), /pipeline/sandbox (standalone test)
"""

from __future__ import annotations

import copy
import json as _json
import logging
import os as _os
import random
import time as _time
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)


# ══════════════════════════════════════════════════════════════
# Data Models
# ══════════════════════════════════════════════════════════════

@dataclass
class ScenarioResult:
    scenario_id: str
    stage_id: str = ""
    passed: bool = False
    error: str = ""
    assess_overall: str = ""
    execution_time_ms: float = 0.0
    mutation_applied: str = ""


@dataclass
class SandboxReport:
    total_scenarios: int
    passed: int
    failed: int
    blocked: bool                           # True → deployment blocked
    scenarios: List[ScenarioResult] = field(default_factory=list)
    summary: str = ""


# ══════════════════════════════════════════════════════════════
# Scenario Synthesizer — deterministic mutations from seed input
# ══════════════════════════════════════════════════════════════

_MUTATIONS: List[Tuple[str, Callable]] = [
    ("empty_description", lambda p: {**p, "description": ""}),
    ("extreme_gross_demand", lambda p: {**p, "gross_demand": random.randint(0, 10) if "gross_demand" in p else p.get("gross_demand", 0)}),
    ("max_gross_demand", lambda p: {**p, "gross_demand": 99999} if "gross_demand" in p else p),
    ("zero_safety_stock", lambda p: {**p, "safety_stock": 0} if "safety_stock" in p else p),
    ("extreme_safety_stock", lambda p: {**p, "safety_stock": 10000} if "safety_stock" in p else p),
    ("negative_inventory", lambda p: {**p, "on_hand_inventory": -100} if "on_hand_inventory" in p else p),
    ("swap_demand_inventory", lambda p: _swap_fields(p, "gross_demand", "on_hand_inventory")),
    ("null_collection_id", lambda p: {**p, "collection_id": ""} if "collection_id" in p else p),
    ("very_long_description", lambda p: {**p, "description": "test " * 50} if "description" in p else p),
    ("special_chars_description", lambda p: {**p, "description": "test <script>alert(1)</script>"} if "description" in p else p),
]


def _swap_fields(params: Dict[str, Any], field_a: str, field_b: str) -> Dict[str, Any]:
    u"""Swap two numeric fields for boundary testing."""
    p = dict(params)
    if field_a in p and field_b in p:
        p[field_a], p[field_b] = p[field_b], p[field_a]
    return p


def synthesize_scenarios(
    seed_params: Dict[str, Any],
    *,
    scenario_count: int = 10,
    seed: int = 42,
) -> List[Dict[str, Any]]:
    u"""Generate variant scenarios from a seed parameter set.

    Uses deterministic mutations (no LLM):
      - Empty/null injection
      - Extreme boundary values
      - Field swaps
      - Special character injection

    Args:
        seed_params: the original working parameters.
        scenario_count: how many variant scenarios to generate.
        seed: random seed for reproducibility.

    Returns:
        List of {scenario_id, params, mutation_name} dicts.
    """
    random.seed(seed)
    scenarios = []

    for i in range(min(scenario_count, len(_MUTATIONS))):
        mutation_name = _MUTATIONS[i][0]
        mutation_fn = _MUTATIONS[i][1]
        mutated = mutation_fn(dict(seed_params))
        scenarios.append({
            "scenario_id": f"sandbox_{mutation_name}_{i}",
            "params": mutated,
            "mutation": mutation_name,
        })

    # If more scenarios needed than mutations, cycle with different seeds
    while len(scenarios) < scenario_count:
        idx = len(scenarios) % len(_MUTATIONS)
        random.seed(seed + len(scenarios))
        mutation_name = _MUTATIONS[idx][0]
        mutation_fn = _MUTATIONS[idx][1]
        mutated = mutation_fn(dict(seed_params))
        scenarios.append({
            "scenario_id": f"sandbox_{mutation_name}_{len(scenarios)}",
            "params": mutated,
            "mutation": mutation_name,
        })

    return scenarios


# ══════════════════════════════════════════════════════════════
# Sandbox Executor
# ══════════════════════════════════════════════════════════════

async def run_sandbox_validation(
    seed_params: Dict[str, Any],
    *,
    scenario_count: int = 10,
    assessment_rubric: Optional[List[Dict[str, Any]]] = None,
) -> SandboxReport:
    u"""Run the sandbox: synthesize scenarios + validate each one.

    Each scenario is a variant of the seed input. The pipeline is NOT
    actually re-executed here (that requires a live PipelineEngine instance).
    Instead, each scenario is validated against the assessment rubric.

    For full pipeline re-execution, use the /pipeline/ship endpoint
    which will invoke this sandbox as a pre-deployment gate.

    Args:
        seed_params: the original parameters that worked successfully.
        scenario_count: number of variant scenarios to generate.
        assessment_rubric: optional rubric to validate each scenario against.

    Returns:
        SandboxReport with per-scenario results and a deployment-block decision.
    """
    scenarios = synthesize_scenarios(seed_params, scenario_count=scenario_count)
    results: List[ScenarioResult] = []

    for sc in scenarios:
        params = sc["params"]
        errors = _validate_params(params, assessment_rubric)

        passed = len(errors) == 0
        results.append(ScenarioResult(
            scenario_id=sc["scenario_id"],
            passed=passed,
            error=errors[0] if errors else "",
            mutation_applied=sc["mutation"],
        ))

    passed = sum(1 for r in results if r.passed)
    failed = len(results) - passed
    blocked = failed > 0

    summary = (
        f"Sandbox: {passed}/{len(results)} scenarios passed."
        if not blocked
        else f"Sandbox BLOCKED: {failed}/{len(results)} scenarios failed. "
             f"Failures: {[r.mutation_applied for r in results if not r.passed][:5]}"
    )

    return SandboxReport(
        total_scenarios=len(results),
        passed=passed,
        failed=failed,
        blocked=blocked,
        scenarios=results,
        summary=summary,
    )


def _validate_params(
    params: Dict[str, Any],
    rubric: Optional[List[Dict[str, Any]]] = None,
) -> List[str]:
    u"""Validate parameters against basic constraints and optional rubric."""
    errors = []

    # Basic sanity checks
    for key in ("gross_demand", "safety_stock", "on_hand_inventory"):
        val = params.get(key)
        if val is not None:
            try:
                if float(val) < 0:
                    errors.append(f"Negative value for {key}: {val}")
            except (ValueError, TypeError):
                errors.append(f"Non-numeric value for {key}: {val}")

    # Description must not be empty (pipeline requires it)
    desc = params.get("description")
    if desc is not None and (not desc or not str(desc).strip()):
        errors.append("Empty description — pipeline input validation")

    # Special character injection detection
    if desc and isinstance(desc, str) and "<script>" in desc:
        errors.append(f"Potential XSS in description: {desc[:50]}")

    # Rubric-based validation
    if rubric:
        for rc in rubric:
            if not isinstance(rc, dict):
                continue
            field = rc.get("field", "")
            constraint = rc.get("constraint", "")
            expected = rc.get("expected")
            actual = params.get(field)
            if constraint == "range" and isinstance(expected, (list, tuple)) and len(expected) == 2:
                try:
                    v = float(actual) if actual is not None else None
                    if v is not None and (v < expected[0] or v > expected[1]):
                        errors.append(f"Value out of range for {field}: {v} not in {expected}")
                except (ValueError, TypeError) as e:
                    logging.warning(str(e), exc_info=True)

    return errors


# ══════════════════════════════════════════════════════════════
# Integration helper: check against assessment rubric
# ══════════════════════════════════════════════════════════════

def is_deployment_blocked(report: SandboxReport) -> bool:
    u"""Quick check: should deployment be blocked based on sandbox results?"""
    return report.blocked
