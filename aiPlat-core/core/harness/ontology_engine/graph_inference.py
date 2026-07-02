"""
Graph Inference — Rule-based reasoning on GraphIndex to derive new edges.

Reads inference_rules from domain YAML, matches premise chains against
the graph, and generates inferred edges with confidence discounts.

Usage:
  inferencer = GraphInference(domain, graph)
  result = inferencer.infer()
  # → InferenceResult with inferred edges and rule hit counts
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Set
from collections import deque

from core.harness.ontology_engine.graph_index import GraphIndex, GraphEdge


@dataclass
class InferenceResult:
    inferred_edges: List[GraphEdge] = field(default_factory=list)
    rule_hits: Dict[str, int] = field(default_factory=dict)
    stats: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "inferred_edges": [
                {
                    "source": e.source_id,
                    "target": e.target_id,
                    "relation_name": e.relation_name,
                    "relation_label": e.relation_label,
                    "confidence": e.confidence,
                    "inferred": True,
                    "rule_name": getattr(e, "rule_name", ""),
                }
                for e in self.inferred_edges
            ],
            "rule_hits": self.rule_hits,
            "stats": self.stats,
        }


class GraphInference:
    """Rule-based reasoning engine for GraphIndex."""

    def __init__(self, domain, graph: GraphIndex):
        self._domain = domain
        self._graph = graph
        self._rules: List[Dict[str, Any]] = list(
            getattr(domain, "inference_rules", None) or []
        )

    def infer(self) -> InferenceResult:
        """Run all inference rules against the graph."""
        result = InferenceResult()
        if not self._rules:
            return result

        # Build node list
        all_nodes = [nid for nid in self._graph._nodes]

        for rule in self._rules:
            rule_name = str(rule.get("name", ""))
            premises = rule.get("premises") or []
            conclusion = rule.get("conclusion") or {}
            if not rule_name or not premises or not conclusion:
                continue

            hit_count = 0
            for source_id in all_nodes:
                source_node = self._graph.get_node(source_id)
                if not source_node:
                    continue

                target_ids = self._match_premise_chain(source_id, premises)
                for target_id in target_ids:
                    # Build inferred edge
                    conf = self._compute_confidence(premises, conclusion)
                    edge = GraphEdge(
                        source_id=source_id,
                        target_id=target_id,
                        relation_name=str(conclusion.get("relation", "inferred")),
                        relation_label=str(conclusion.get("label", "推断关系")),
                        confidence=conf,
                    )
                    edge.inferred = True
                    edge.rule_name = rule_name
                    edge.inferred_confidence = conf
                    result.inferred_edges.append(edge)
                    hit_count += 1

            result.rule_hits[rule_name] = hit_count

        result.stats = {
            "rules_evaluated": len(self._rules),
            "total_inferred": len(result.inferred_edges),
            "node_count": len(all_nodes),
        }
        return result

    def _match_premise_chain(
        self,
        start_id: str,
        premises: List[Dict[str, Any]],
    ) -> Set[str]:
        """BFS from start_id following the premise relation chain.

        Returns set of terminal node IDs reached by successfully matching
        all premises in sequence.
        """
        if not premises:
            return set()

        # BFS queue: (current_node_id, premise_index)
        queue: deque = deque()
        queue.append((start_id, 0))
        terminals: Set[str] = set()

        while queue:
            current_id, p_idx = queue.popleft()
            if p_idx >= len(premises):
                terminals.add(current_id)
                continue

            premise = premises[p_idx]
            rel_name = str(premise.get("relation", ""))
            direction = str(premise.get("direction", "outgoing"))

            # Find neighbors reachable via this relation
            neighbors = self._graph.get_neighbors(
                current_id,
                direction=direction,
                relation_filter=[rel_name] if rel_name else None,
            )

            for neighbor in neighbors:
                queue.append((neighbor.entity_id, p_idx + 1))

        return terminals

    def _compute_confidence(
        self,
        premises: List[Dict[str, Any]],
        conclusion: Dict[str, Any],
    ) -> float:
        """Compute inferred edge confidence: product of hop confidences × conclusion factor."""
        # Start with base
        base_conf = float(conclusion.get("confidence", 0.7))
        # Discount per hop (0.9^n)
        hop_discount = 0.9 ** len(premises)
        return round(base_conf * hop_discount, 3)

    def apply_to_graph(self, result: InferenceResult) -> int:
        """Apply inferred edges to the graph via add_inferred_edge (SQL-backed)."""
        added = 0
        for edge in result.inferred_edges:
            if self._graph.add_inferred_edge(
                source_id=edge.source_id,
                target_id=edge.target_id,
                relation_name=edge.relation_name,
                relation_label=edge.relation_label,
                confidence=edge.confidence,
                rule_name=edge.rule_name,
            ):
                added += 1
        return added

    def remove_inferred_edges(self) -> int:
        """Remove all inferred edges. Delegates to GraphIndex (SQL-backed)."""
        return self._graph.remove_inferred_edges()

    # ── Phase F: Runtime rule CRUD ──

    def add_rule(self, rule: Dict[str, Any]) -> str:
        """Add or overwrite a rule at runtime. Returns rule name."""
        name = str(rule.get("name", ""))
        if not name:
            raise ValueError("Rule must have a 'name' field")
        for i, r in enumerate(self._rules):
            if r.get("name") == name:
                self._rules[i] = rule
                return name
        self._rules.append(rule)
        return name

    def remove_rule(self, name: str) -> bool:
        """Remove a rule by name. Returns True if removed."""
        for i, r in enumerate(self._rules):
            if r.get("name") == name:
                del self._rules[i]
                return True
        return False

    def list_rules(self) -> List[Dict[str, Any]]:
        """Return all active inference rules (read-only snapshot)."""
        return [dict(r) for r in self._rules]
