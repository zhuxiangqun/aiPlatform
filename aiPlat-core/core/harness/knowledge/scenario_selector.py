u"""
Scenario Selector — 场景选择器 (v2.7).

Implements the article's framework:
  - 5 high-value criteria evaluation (0-100 score)
  - 4-quadrant pain point mapping (P0-P3)
  - Value opportunity formula generation
  - Domain recommendation with computed priority

Key concept: "which domain should we build first?" — answered with COMPUTED data, not LLM guess.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

logger = logging.getLogger("scenario_selector")

QUADRANT_LABELS = {
    ("high", "high"):   ("P0", "优先试点 (build first)"),
    ("high", "low"):    ("P1", "第二阶段 (plan)"),
    ("low", "high"):    ("P2", "快速处理 (no heavy modeling)"),
    ("low", "low"):     ("P3", "Backlog"),
}


@dataclass
class Scenario:
    name: str
    domain_id: str = ""
    pain: str = ""
    impact: str = "medium"            # high | medium | low
    urgency: str = "medium"
    process_closure: str = "unknown"  # clear | partial | unknown
    data_availability: str = "unknown" # available | partial | unavailable
    value_verifiability: str = "unknown" # verifiable | estimated | unknown
    semantic_asset_reuse: str = "medium" # high | medium | low

    # Computed fields
    maturity_score: float = 0.0
    gap_cost_hours: float = 0.0
    priority_score: float = 0.0
    quadrant: str = "P3"
    value_formula: str = ""


def _discrete_to_score(value: str, mapping: Dict[str, float]) -> float:
    return mapping.get(value.lower(), mapping.get("medium", 10))


def evaluate_scenario_5_criteria(scenario: Scenario) -> Dict[str, Any]:
    u"""Evaluate a scenario against 5 high-value criteria. Returns 0-100 score + breakdown.

    Criteria weights:
      1. Business pain clarity:  impact×urgency → discrete mapping (20pts)
      2. Process closure:        clear=20, partial=12, unknown=4 (20pts)
      3. Data availability:      available=20, partial=12, unavailable=4 (20pts)
      4. Value verifiability:    verifiable=20, estimated=12, unknown=4 (20pts)
      5. Semantic asset reuse:   high=20, medium=12, low=4 (20pts)
    """
    impact_map = {"high": 20, "medium": 14, "low": 8}
    urgency_map = {"high": 20, "medium": 14, "low": 8}
    pain_score = (impact_map.get(scenario.impact, 10) + urgency_map.get(scenario.urgency, 10)) / 2

    closure_map = {"clear": 20, "partial": 12, "unknown": 4}
    data_map = {"available": 20, "partial": 12, "unavailable": 4}
    value_map = {"verifiable": 20, "estimated": 12, "unknown": 4}
    reuse_map = {"high": 20, "medium": 12, "low": 4}

    scores = {
        "business_pain": round(pain_score, 1),
        "process_closure": closure_map.get(scenario.process_closure, 4),
        "data_availability": data_map.get(scenario.data_availability, 4),
        "value_verifiability": value_map.get(scenario.value_verifiability, 4),
        "semantic_reuse": reuse_map.get(scenario.semantic_asset_reuse, 4),
    }

    total = sum(scores.values())

    recommendation = "strongly_recommended" if total >= 80 else \
                     "recommended" if total >= 60 else "defer"

    return {"total": total, "scores": scores, "recommendation": recommendation}


def prioritize_scenarios(scenarios: List[Scenario]) -> List[Scenario]:
    u"""Apply 4-quadrant priority + 5 criteria scoring → return sorted list.

    priority_score = 0.6 × criteria_score + 0.4 × maturity_score
    """
    for s in scenarios:
        criteria = evaluate_scenario_5_criteria(s)
        s.priority_score = round(
            0.6 * criteria["total"] + 0.4 * s.maturity_score, 1
        )
        s.quadrant = QUADRANT_LABELS.get(
            (s.impact.lower(), s.urgency.lower()), ("P3", "Backlog")
        )[0]
        s.value_formula = value_opportunity_formula(s)

    return sorted(scenarios, key=lambda s: s.priority_score, reverse=True)


def value_opportunity_formula(scenario: Scenario) -> str:
    u"""Generate the value opportunity formula.

    Format: By [doing X] + help [who] + in [scenario] + achieve [A→B] = deliver [value]
    """
    return (
        f"通过 {scenario.name} 的语义建模 + "
        f"帮助 {scenario.domain_id} 域用户 + "
        f"在 {scenario.pain[:30] if scenario.pain else '日常运营'} 场景中 + "
        f"实现人工→智能决策 = "
        f"交付可验证的业务效率提升"
    )


def recommend_order(
    industry: str = "",
    pain_points: str = "",
    ontologies_dir: str = "",
    limit: int = 5,
) -> List[Dict[str, Any]]:
    u"""Recommend which domains to build first, with computed scores."""
    import json, os

    base = os.path.expanduser(ontologies_dir or os.getenv("AIPLAT_ONTOLOGY_DIR", "~/.aiplat/ontologies"))
    reg_path = os.path.join(base, "registry.json")
    if not os.path.exists(reg_path):
        return []

    with open(reg_path) as f:
        reg = json.load(f)

    from core.harness.knowledge.domain_maturity import compute_domain_maturity, compute_gap_cost

    scenarios = []
    for domain_id, domain_meta in reg.get("domains", {}).items():
        defined_scenarios = domain_meta.get("scenarios", [])
        if not defined_scenarios:
            # Create a default scenario from domain metadata
            scenarios.append(Scenario(
                name=domain_meta.get("name", domain_id),
                domain_id=domain_id,
                pain=domain_meta.get("description", ""),
                impact="medium",
                urgency="medium",
                maturity_score=compute_domain_maturity(domain_id, ontologies_dir)["maturity_score"],
                gap_cost_hours=compute_gap_cost(domain_id, ontologies_dir)["total_hours"],
            ))
        else:
            for sc in defined_scenarios:
                maturity = compute_domain_maturity(domain_id, ontologies_dir)
                gap_cost = compute_gap_cost(domain_id, ontologies_dir)
                scenarios.append(Scenario(
                    name=sc.get("name", ""),
                    domain_id=domain_id,
                    pain=sc.get("pain", ""),
                    impact=sc.get("impact", "medium"),
                    urgency=sc.get("urgency", "medium"),
                    process_closure=sc.get("process_closure", "unknown"),
                    data_availability=sc.get("data_availability", "unknown"),
                    value_verifiability=sc.get("value_verifiability", "unknown"),
                    semantic_asset_reuse=sc.get("semantic_asset_reuse", "medium"),
                    maturity_score=maturity["maturity_score"],
                    gap_cost_hours=gap_cost["total_hours"],
                ))

    # Industry filtering
    if industry:
        scenarios = [
            s for s in scenarios
            if industry in reg.get("domains", {}).get(s.domain_id, {}).get("applicable_industries", [])
        ] or scenarios  # fallback to all if industry filter removes everything

    sorted_scenarios = prioritize_scenarios(scenarios)
    result = []
    for s in sorted_scenarios[:limit]:
        result.append({
            "domain_id": s.domain_id,
            "scenario": s.name,
            "priority": s.quadrant,
            "priority_score": s.priority_score,
            "maturity_score": s.maturity_score,
            "gap_cost_hours": s.gap_cost_hours,
            "value_formula": s.value_formula,
            "recommendation": "build_first" if s.priority_score >= 70 else
                              "plan_second" if s.priority_score >= 50 else "defer",
        })

    return result
