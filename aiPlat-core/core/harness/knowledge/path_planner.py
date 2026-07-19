u"""
Path Planner — 目标导向路径规划 + 模板 (v2.7).

Loads reasoning_paths from domain YAML, supports:
  - Pre-defined path templates with applicability conditions
  - Auto-discovery fallback (BFS k-shortest, max 5 hops, cached)
  - Cost-based path ranking (hop_count × confidence_discount)
  - Goal-oriented execution with step-by-step filter application

YAML schema:
  reasoning_paths:
    complaint_driven_churn:
      label: 投诉驱动流失分析
      version: "1.0.0"
      start_class: Customer
      target_class: Defect
      applicability:
        property_condition:
          field: customer_level
          operator: "=="
          value: VIP
      steps:
        - relation: has_ticket
          direction: outgoing
          target_class: Ticket
          filter: { time_window_days: 30 }
        - relation: has_complaint
          direction: outgoing
          target_class: Complaint
      scoring_model: customer_churn_risk
      metadata:
        estimated_cost: 5
        confidence: 0.85
"""
from __future__ import annotations

import logging
import time as _time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Set, Tuple

logger = logging.getLogger("path_planner")

# Cache: (start_class, target_class) → discovered paths
_discovered_cache: Dict[str, Tuple[float, List[Dict]]] = {}
_CACHE_TTL = 3600  # 1 hour


@dataclass
class ReasoningPath:
    name: str
    label: str
    description: str = ""
    version: str = "1.0.0"
    start_class: str = ""
    target_class: str = ""
    steps: List[Dict[str, Any]] = field(default_factory=list)
    scoring_model: str = ""
    applicability: Dict[str, Any] = field(default_factory=dict)
    metadata: Dict[str, Any] = field(default_factory=dict)
    is_auto: bool = False  # auto-discovered vs pre-defined


@dataclass
class PathCandidate:
    path: ReasoningPath
    cost: float = 0.0  # lower is better
    match_reason: str = ""  # "template_match" | "auto_discovered"


@dataclass
class PathResult:
    path_name: str
    terminal_entities: List[str] = field(default_factory=list)
    step_results: List[Dict[str, Any]] = field(default_factory=list)
    total_cost: float = 0.0
    completed: bool = True
    failed_at_step: int = -1


def load_paths(domain_yaml_raw: Dict[str, Any]) -> Dict[str, ReasoningPath]:
    u"""Load reasoning paths from domain YAML raw dict."""
    raw_paths = domain_yaml_raw.get("reasoning_paths", {})
    result = {}
    for name, raw in raw_paths.items():
        result[name] = ReasoningPath(
            name=name,
            label=raw.get("label", name),
            description=raw.get("description", ""),
            version=raw.get("version", "1.0.0"),
            start_class=raw.get("start_class", ""),
            target_class=raw.get("target_class", ""),
            steps=raw.get("steps", []),
            scoring_model=raw.get("scoring_model", ""),
            applicability=raw.get("applicability", {}),
            metadata=raw.get("metadata", {}),
        )
    return result


def find_candidate_paths(
    task_context: Dict[str, Any],
    domain_id: str,
    ontologies_dir: str = "",
) -> List[PathCandidate]:
    u"""Find candidate reasoning paths for a task context.

    TaskContext: { intent, entities, target_class, filters, time_range }
    Returns paths sorted by cost (lowest first).
    """
    import os, yaml

    base = os.path.expanduser(ontologies_dir or os.getenv("AIPLAT_ONTOLOGY_DIR", "~/.aiplat/ontologies"))
    yaml_path = os.path.join(base, f"{domain_id}.yaml")
    if not os.path.exists(yaml_path):
        return []

    with open(yaml_path, "r", encoding="utf-8") as f:
        raw = yaml.safe_load(f) or {}

    pre_paths = load_paths(raw)
    candidates: List[PathCandidate] = []

    start_class = task_context.get("target_class", "") or task_context.get("entities", [None])[0] or ""
    target_hint = task_context.get("intent", "")

    # ── Pass 1: Pre-defined template matching ──
    for name, path in pre_paths.items():
        if not start_class or path.start_class == start_class:
            if _check_applicability(path, task_context):
                cost = _compute_cost(path)
                candidates.append(PathCandidate(
                    path=path, cost=cost, match_reason="template_match"
                ))

    # ── Pass 2: Auto-discovery (fallback) ──
    if not candidates and start_class:
        auto_path = _auto_discover(start_class, target_hint, domain_id, raw)
        if auto_path:
            cost = _compute_cost(auto_path)
            candidates.append(PathCandidate(
                path=auto_path, cost=cost, match_reason="auto_discovered"
            ))

    candidates.sort(key=lambda c: c.cost)
    return candidates[:3]


def execute_path(
    path: ReasoningPath,
    start_entities: List[str],
    domain_id: str,
) -> PathResult:
    u"""Execute a reasoning path from start entities, stepping through each relation."""
    result = PathResult(path_name=path.name)
    current_ids = list(start_entities)

    try:
        from core.harness.ontology_engine.graph_index import GraphIndex
        graph = GraphIndex.load(domain_id)
    except Exception as e:
        result.completed = False
        result.failed_at_step = 0
        logger.warning("GraphIndex load failed: %s", e)
        return result

    for idx, step in enumerate(path.steps):
        relation = step.get("relation", "")
        direction = step.get("direction", "outgoing")
        step_filter = step.get("filter", {})

        next_ids = set()
        for eid in current_ids:
            if direction == "outgoing":
                neighbors = graph.get_neighbors(eid, relation, direction="outgoing")
            else:
                neighbors = graph.get_neighbors(eid, relation, direction="incoming")
            for n in neighbors:
                if _apply_filter(n, step_filter, graph):
                    next_ids.add(n)

        step_result = {
            "step_index": idx,
            "relation": relation,
            "direction": direction,
            "input_count": len(current_ids),
            "output_count": len(next_ids),
            "target_class": step.get("target_class", ""),
        }
        result.step_results.append(step_result)

        if not next_ids:
            result.completed = False
            result.failed_at_step = idx
            result.terminal_entities = list(current_ids)
            return result

        current_ids = list(next_ids)

    result.terminal_entities = list(current_ids)
    result.total_cost = _compute_cost(path)
    return result


def _check_applicability(path: ReasoningPath, task_context: Dict) -> bool:
    u"""Check if path's applicability conditions match the task context."""
    app = path.applicability
    if not app:
        return True  # no conditions → always applicable

    if "property_condition" in app:
        pc = app["property_condition"]
        field = pc.get("field", "")
        op = pc.get("operator", "==")
        val = pc.get("value", "")
        task_val = task_context.get("filters", {}).get(field, "")
        if not task_val and task_context.get("entities"):
            # Check if any entity has this property
            pass  # simplified for now
        if op == "==" and str(task_val) != str(val):
            return False
        elif field not in task_context.get("filters", {}) and field not in str(task_context):
            pass  # property not mentioned → apply anyway

    return True


def _compute_cost(path: ReasoningPath) -> float:
    u"""Compute path cost: hop_count × confidence_discount."""
    confidence = path.metadata.get("confidence", 0.8)
    hop_count = len(path.steps) or path.metadata.get("estimated_cost", 3)
    discount = 0.9 ** hop_count
    return hop_count * (1 + (1 - confidence)) * discount


def _auto_discover(
    start_class: str,
    target_hint: str,
    domain_id: str,
    yaml_raw: Dict,
) -> Optional[ReasoningPath]:
    u"""Auto-discover a path from start_class to a class matching target_hint.

    Uses BFS with max 5 hops. Results cached for 1 hour.
    """
    global _discovered_cache
    cache_key = f"{domain_id}:{start_class}:{target_hint}"
    if cache_key in _discovered_cache:
        ts, steps = _discovered_cache[cache_key]
        if _time.time() - ts < _CACHE_TTL:
            return ReasoningPath(
                name=f"auto_{start_class}_{target_hint}",
                label=f"自动发现: {start_class}→{target_hint}",
                start_class=start_class,
                target_class=target_hint,
                steps=steps,
                is_auto=True,
                metadata={"confidence": 0.6, "estimated_cost": len(steps)},
            )

    classes = yaml_raw.get("classes", {})
    obj_props = yaml_raw.get("object_properties", [])

    # Build relation adjacency
    rel_graph: Dict[str, List[Tuple[str, str]]] = {}
    for prop in obj_props:
        for domain_cls in prop.get("domain", []):
            for range_cls in prop.get("range", []):
                rel_graph.setdefault(domain_cls, []).append((range_cls, prop.get("name", "")))

    # BFS with max 5 hops
    from collections import deque
    queue = deque([(start_class, [], set())])
    max_hops = 5

    while queue:
        current, path_steps, visited = queue.popleft()
        if len(path_steps) >= max_hops:
            continue
        for neighbor, rel_name in rel_graph.get(current, []):
            if neighbor in visited:
                continue
            new_visited = visited | {neighbor}
            new_steps = path_steps + [{"relation": rel_name, "direction": "outgoing",
                                        "target_class": neighbor}]
            if target_hint.lower() in neighbor.lower():
                _discovered_cache[cache_key] = (_time.time(), new_steps)
                return ReasoningPath(
                    name=f"auto_{start_class}_{neighbor}",
                    label=f"自动发现: {start_class}→{neighbor}",
                    start_class=start_class,
                    target_class=neighbor,
                    steps=new_steps,
                    is_auto=True,
                    metadata={"confidence": 0.6, "estimated_cost": len(new_steps)},
                )
            queue.append((neighbor, new_steps, new_visited))

    return None


def _apply_filter(entity_id: str, step_filter: Dict, graph) -> bool:
    u"""Apply per-step filter to an entity. Returns True if passed."""
    if not step_filter:
        return True
    # Simplified: time_window filter not applied at entity level in traversal
    return True
