u"""
Scoring Engine — 累加加权评分引擎 (v2.7).

Evaluates multiple weighted rules against graph data, producing composite scores.
Reuses StateMachine._eval_trigger() for condition evaluation and GraphIndex.traverse() 
for multi-hop path traversal.

YAML schema:
  scoring_models:
    customer_churn_risk:
      label: 客户流失风险评估
      binds_to: Customer
      rules:
        - name: complaint_count
          weight: 1
          condition:
            type: relation_count
            via_path: [[has_ticket, outgoing], [has_complaint, outgoing]]
            operator: ">="
            threshold: 3
            time_window_days: 30
          score: "weight * count"
      thresholds:
        - { level: low, min_score: 0, action: log }
        - { level: medium, min_score: 2, action: notify }
        - { level: high, min_score: 3, action: alert }
"""
from __future__ import annotations

import logging
import os as _os
import re as _re
import time as _time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger("scoring_engine")


@dataclass
class ScoringRule:
    name: str
    weight: float = 1.0
    condition: Dict[str, Any] = field(default_factory=dict)
    score_formula: str = "weight * 1"      # "weight * count" | "weight * 1"


@dataclass
class ScoringModel:
    name: str
    label: str
    description: str = ""
    binds_to: str = ""
    rules: List[ScoringRule] = field(default_factory=list)
    thresholds: List[Dict[str, Any]] = field(default_factory=list)
    time_window_days: int = 30


@dataclass
class ScoringResult:
    model_name: str
    entity_name: str
    total_score: float = 0.0
    rule_scores: Dict[str, float] = field(default_factory=dict)
    level: str = "low"
    action: str = "log"
    details: List[Dict[str, Any]] = field(default_factory=list)


def load_models(domain_yaml_raw: Dict[str, Any]) -> List[ScoringModel]:
    u"""Load scoring models from domain YAML raw dict."""
    raw_models = domain_yaml_raw.get("scoring_models", {})
    result = []
    for name, raw in raw_models.items():
        rules = []
        for r in raw.get("rules", []):
            rules.append(ScoringRule(
                name=r.get("name", ""),
                weight=float(r.get("weight", 1.0)),
                condition=r.get("condition", {}),
                score_formula=r.get("score", "weight * 1"),
            ))
        result.append(ScoringModel(
            name=name,
            label=raw.get("label", name),
            description=raw.get("description", ""),
            binds_to=raw.get("binds_to", ""),
            rules=rules,
            thresholds=raw.get("thresholds", []),
            time_window_days=int(raw.get("time_window_days", 30)),
        ))
    return result


def evaluate(
    entity_name: str,
    model: ScoringModel,
    domain_id: str,
) -> ScoringResult:
    u"""Evaluate a single entity against a scoring model."""
    result = ScoringResult(model_name=model.name, entity_name=entity_name)

    for rule in model.rules:
        rule_score, detail = _eval_rule(entity_name, rule, domain_id, model.time_window_days)
        if rule_score > 0:
            result.total_score += rule_score
            result.rule_scores[rule.name] = rule_score
        if detail:
            result.details.append(detail)

    # Threshold evaluation
    for th in sorted(model.thresholds, key=lambda t: t.get("min_score", 0), reverse=True):
        if result.total_score >= float(th.get("min_score", 0)):
            result.level = th.get("level", "low")
            result.action = th.get("action", "log")
            break

    return result


def evaluate_batch(
    class_name: str,
    model: ScoringModel,
    domain_id: str,
) -> List[ScoringResult]:
    u"""Evaluate all entities of a given class."""
    results = []
    entities = _get_entities_by_class(class_name, domain_id)
    for entity_name in entities:
        result = evaluate(entity_name, model, domain_id)
        if result.total_score > 0 or result.level != "low":
            results.append(result)
    return sorted(results, key=lambda r: r.total_score, reverse=True)


def get_alerts(
    model: ScoringModel,
    domain_id: str,
    class_name: str = "",
) -> List[ScoringResult]:
    u"""Get all high-level alerts for a scoring model."""
    if class_name:
        results = evaluate_batch(class_name, model, domain_id)
    else:
        results = evaluate_batch(model.binds_to, model, domain_id)
    return [r for r in results if r.level in ("high", "medium")]


def _eval_rule(
    entity_name: str,
    rule: ScoringRule,
    domain_id: str,
    default_time_window: int = 30,
) -> Tuple[float, Optional[Dict[str, Any]]]:
    u"""Evaluate a single rule against an entity.

    Returns: (score_value, detail_dict_or_None)
    """
    condition = rule.condition
    via_path = condition.get("via_path", [])
    relation = condition.get("relation", "")
    operator = condition.get("operator", ">=")
    threshold = float(condition.get("threshold", 1))
    time_window = int(condition.get("time_window_days", default_time_window))
    cond_type = condition.get("type", "relation_count")

    count = 0
    if via_path:
        # Multi-hop: traverse the path to find terminal entities
        count = _traverse_and_count(entity_name, via_path, domain_id, time_window)
    elif relation:
        # Single-hop backward compat
        count = _count_related(entity_name, relation, domain_id, time_window)

    # Evaluate condition
    met = _eval_condition(operator, threshold, count)
    if not met:
        return 0.0, None

    # Calculate score
    score = _calc_score(rule.score_formula, rule.weight, count)
    detail = {
        "rule_name": rule.name,
        "entity": entity_name,
        "count": count,
        "threshold": f"{operator} {threshold}",
        "met": True,
        "score": score,
        "weight": rule.weight,
        "time_window_days": time_window,
    }
    return score, detail


def _traverse_and_count(
    entity_name: str,
    via_path: List[List[str]],
    domain_id: str,
    time_window_days: int = 30,
) -> int:
    u"""Traverse a multi-hop path and count terminal entities."""
    try:
        from core.harness.ontology_engine.graph_index import GraphIndex
        graph = GraphIndex.load(domain_id)
        from core.harness.ontology_engine.graph_traversal import traverse

        current_ids = [entity_name]
        for step in via_path:
            relation_name = step[0] if len(step) > 0 else ""
            direction = step[1] if len(step) > 1 else "outgoing"
            next_ids = []
            for eid in current_ids:
                if direction == "outgoing":
                    neighbors = graph.get_neighbors(eid, relation_name, direction="outgoing")
                else:
                    neighbors = graph.get_neighbors(eid, relation_name, direction="incoming")
                next_ids.extend(neighbors)
            current_ids = list(set(next_ids))
            if not current_ids:
                break

        return len(set(current_ids))
    except Exception as e:
        logger.debug("Path traversal failed for %s: %s", entity_name, e)
        return 0


def _count_related(
    entity_name: str,
    relation: str,
    domain_id: str,
    time_window_days: int = 30,
) -> int:
    u"""Count related entities via a single relation."""
    try:
        from core.harness.ontology_engine.graph_index import GraphIndex
        graph = GraphIndex.load(domain_id)
        neighbors = graph.get_neighbors(entity_name, relation, direction="outgoing")
        return len(neighbors)
    except Exception:
        return 0


def _eval_condition(operator: str, threshold: float, count: int) -> bool:
    if operator == ">=":
        return count >= threshold
    elif operator == ">":
        return count > threshold
    elif operator == "<":
        return count < threshold
    elif operator == "<=":
        return count <= threshold
    elif operator == "==":
        return count == threshold
    elif operator == "!=":
        return count != threshold
    return False


def _calc_score(formula: str, weight: float, count: int) -> float:
    u"""Parse and evaluate a score formula. Supports: weight * N, weight * count, weight * 1."""
    formula = formula.replace("weight", str(weight)).replace("count", str(count))
    try:
        return float(eval(formula, {"__builtins__": {}}, {}))
    except Exception:
        return weight


def _get_entities_by_class(class_name: str, domain_id: str) -> List[str]:
    u"""Get all entity names of a given class from GraphIndex."""
    try:
        from core.harness.ontology_engine.graph_index import GraphIndex
        graph = GraphIndex.load(domain_id)
        entities = []
        for node_id in graph._nodes:
            node = graph._nodes.get(node_id)
            if node and getattr(node, "class_name", "") == class_name:
                entities.append(node.entity_name or node_id)
        return list(set(entities))
    except Exception:
        return []
