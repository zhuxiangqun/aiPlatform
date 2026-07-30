"""
Graph Traversal — BFS multi-hop traversal on GraphIndex.

Explores the ontology knowledge graph by following edges up to max_hops,
recording complete reasoning paths. Used for impact analysis, root cause
tracing, and knowledge graph-enhanced retrieval.

Usage:
  graph = GraphIndex.load("ai-knowledge")
  result = traverse("RAG", graph, max_hops=2)
  # → TraversalResult with paths[] and terminal_entities[]
"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Set
import time as _time

from core.harness.ontology_engine.graph_index import GraphIndex, GraphEdge, GraphNode


@dataclass
class TraversalStep:
    entity_id: str
    entity_name: str
    class_name: str
    relation_name: str = ""   # how we got here from previous step
    relation_label: str = ""
    hop: int = 0
    confidence: float = 1.0

    def to_dict(self) -> dict:
        return {
            "entity_id": self.entity_id,
            "entity_name": self.entity_name,
            "class_name": self.class_name,
            "relation_name": self.relation_name,
            "relation_label": self.relation_label,
            "hop": self.hop,
            "confidence": self.confidence,
        }


@dataclass
class TraversalPath:
    steps: List[TraversalStep] = field(default_factory=list)
    total_weight: float = 1.0
    min_weight_on_path: float = 1.0

    @property
    def length(self) -> int:
        return max(0, len(self.steps) - 1)

    @property
    def terminal(self) -> Optional[TraversalStep]:
        return self.steps[-1] if self.steps else None

    def to_dict(self) -> dict:
        return {
            "length": self.length,
            "steps": [s.to_dict() for s in self.steps],
            "total_weight": self.total_weight,
            "min_weight_on_path": self.min_weight_on_path,
        }


@dataclass
class TraversalResult:
    paths: List[TraversalPath] = field(default_factory=list)
    terminal_entities: List[Dict[str, Any]] = field(default_factory=list)
    ranked_terminals: List[Dict[str, Any]] = field(default_factory=list)
    truncated: bool = False
    timing_ms: float = 0.0
    stats: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "paths": [p.to_dict() for p in self.paths],
            "terminal_entities": self.terminal_entities,
            "ranked_terminals": self.ranked_terminals,
            "truncated": self.truncated,
            "stats": self.stats,
        }


def traverse(
    start_entity: str,
    graph: GraphIndex,
    *,
    max_hops: int = 2,
    relation_filter: Optional[List[str]] = None,
    direction: str = "both",
    node_limit: int = 1000,
    min_weight: float = 0.0,
    relation_weights: Optional[Dict[str, float]] = None,
    use_cache: bool = True,
    # Phase 50: reasoning evidence trace
    record_path: bool = False,
    run_id: str = "",
) -> TraversalResult:
    """BFS traversal from start_entity, recording complete paths.

    Args:
        start_entity: entity_id or entity_name to start from
        graph: loaded GraphIndex
        max_hops: maximum edge hops from start (1 = direct neighbors, 2 = neighbors of neighbors)
        relation_filter: optional list of relation names to follow
        direction: "outgoing" | "incoming" | "both"
        node_limit: abort if visited nodes exceed this (safety valve)
        min_weight: skip edges with weight below this threshold
        relation_weights: {relation_name → weight} map; default inferred from properties
        use_cache: whether to use TraversalCache (default True)

    Returns:
        TraversalResult with all paths found and terminal entities
    """
    # Try cache first
    if use_cache and not relation_filter and not relation_weights:
        from core.harness.ontology_engine.traversal_cache import get_traversal_cache
        cache = get_traversal_cache(getattr(graph, 'domain_id', 'default'))
        cached = cache.get(start_entity, max_hops, direction)
        if cached is not None:
            return cached

    t0 = _time.time()
    # Resolve start entity (by id or name)
    start_node = graph.get_node(start_entity) or graph.find_by_name(start_entity)
    if not start_node:
        return TraversalResult()

    start_id = start_node.entity_id
    start_step = TraversalStep(
        entity_id=start_id,
        entity_name=start_node.entity_name,
        class_name=start_node.class_name,
        hop=0,
    )

    result = TraversalResult()
    visited: Set[str] = {start_id}
    seen_terminals: Set[str] = set()

    # BFS queue: (current_node_id, path_so_far)
    queue: deque = deque()
    queue.append((start_id, TraversalPath(steps=[start_step])))

    while queue and len(visited) < node_limit:
        current_id, current_path = queue.popleft()

        # If we've reached max_hops, this path terminates here
        if current_path.length >= max_hops:
            if current_id not in seen_terminals:
                seen_terminals.add(current_id)
                result.terminal_entities.append({
                    "entity_id": current_id,
                    "entity_name": current_path.terminal.entity_name if current_path.terminal else "",
                    "class_name": current_path.terminal.class_name if current_path.terminal else "",
                })
            result.paths.append(current_path)
            continue

        # Explore neighbors (binary edges)
        neighbors = graph.get_neighbors(current_id, direction=direction, relation_filter=relation_filter)
        # Also explore hyperedge neighbors (SAG-style: all entities in shared hyperedges)
        he_neighbors = graph.get_hyperedge_neighbors(current_id) if hasattr(graph, 'get_hyperedge_neighbors') else []
        all_neighbors = neighbors + he_neighbors
        has_unvisited = False

        for neighbor in all_neighbors:
            nid = neighbor.entity_id
            if nid in visited:
                continue
            # Skip returning to start node on inverse edges
            if nid == start_id and current_path.length > 0:
                continue

            # Find the edge that connected us
            connecting_edges = _find_connecting_edges(graph, current_id, nid, direction)
            if not connecting_edges:
                # Check if connected via hyperedge
                if hasattr(graph, 'get_hyperedges_for_entity'):
                    he_list = graph.get_hyperedges_for_entity(current_id)
                    for he in he_list:
                        if nid in he.entity_ids:
                            from core.harness.ontology_engine.graph_index import GraphEdge
                            connecting_edges = [GraphEdge(
                                source_id=current_id, target_id=nid,
                                relation_name="hyperedge", relation_label=f"via:{he.event_id[:20]}",
                                confidence=he.confidence,
                            )]
                            break
                if not connecting_edges:
                    continue

            edge = connecting_edges[0]  # Take first connecting edge
            # Weight pruning
            if min_weight > 0 and relation_weights:
                w = relation_weights.get(edge.relation_name, 0.5)
                if w < min_weight:
                    continue
            step = TraversalStep(
                entity_id=nid,
                entity_name=neighbor.entity_name,
                class_name=neighbor.class_name,
                relation_name=edge.relation_name,
                relation_label=edge.relation_label,
                hop=current_path.length + 1,
                confidence=edge.confidence,
            )
            new_path = TraversalPath(
                steps=list(current_path.steps) + [step],
                total_weight=current_path.total_weight * (relation_weights.get(edge.relation_name, 0.5) if relation_weights else 1.0),
                min_weight_on_path=min(
                    current_path.min_weight_on_path,
                    relation_weights.get(edge.relation_name, 0.5) if relation_weights else 1.0,
                ),
            )

            if nid not in visited:
                visited.add(nid)
                queue.append((nid, new_path))
                has_unvisited = True

                # Phase 50: Record traversal step for reasoning evidence
                if record_path and run_id:
                    try:
                        from core.harness.infrastructure.lineage_store import LineageStore
                        store = LineageStore.get()
                        step_idx = len(new_path.steps) - 1
                        store.record_traversal_step(
                            run_id=run_id,
                            step_index=step_idx,
                            from_entity=current_id,
                            from_name=current_path.terminal.entity_name if current_path.terminal else current_id,
                            to_entity=nid,
                            to_name=neighbor.entity_name,
                            to_class=neighbor.class_name,
                            relation=edge.relation_name,
                            relation_label=edge.relation_label,
                            confidence=edge.confidence,
                            hop=current_path.length + 1,
                            parent_decision_id="",
                            intermediate_value="",
                        )
                    except Exception:
                        pass  # best-effort, don't block traversal
            elif nid == start_id and current_path.length > 0:
                # Cycle back to start — record as terminal
                result.paths.append(new_path)

        # If no unvisited neighbors found, this is a terminal
        if not has_unvisited and current_path.length > 0:
            if current_id not in seen_terminals:
                seen_terminals.add(current_id)
                result.terminal_entities.append({
                    "entity_id": current_id,
                    "entity_name": current_path.terminal.entity_name if current_path.terminal else "",
                    "class_name": current_path.terminal.class_name if current_path.terminal else "",
                })
            result.paths.append(current_path)

    result.truncated = len(visited) >= node_limit
    result.timing_ms = round((_time.time() - t0) * 1000, 2)
    result.stats = {
        "nodes_visited": len(visited),
        "paths_found": len(result.paths),
        "terminals_found": len(result.terminal_entities),
        "max_hops": max_hops,
        "direction": direction,
    }

    # Cache the result
    if use_cache and not relation_filter and not relation_weights:
        cache.set(start_entity, max_hops, direction, result)

    return result


def _find_connecting_edges(
    graph: GraphIndex,
    from_id: str,
    to_id: str,
    direction: str,
) -> List[GraphEdge]:
    """Find edges connecting from_id → to_id in the specified direction."""
    edges = []
    from_node = graph.get_node(from_id)
    to_node = graph.get_node(to_id)
    if not from_node or not to_node:
        return edges


def traverse_multi(
    start_entities: List[str],
    graph: GraphIndex,
    *,
    max_hops: int = 2,
    relation_filter: Optional[List[str]] = None,
    direction: str = "both",
    node_limit: int = 1000,
    min_weight: float = 0.0,
    relation_weights: Optional[Dict[str, float]] = None,
) -> TraversalResult:
    """Multi-start local subgraph expansion (SAG-style).

    Runs BFS from multiple start entities simultaneously, finding
    connecting paths between them. Only the relevant subgraph around
    the query entities is activated — no global traversal.

    This mirrors SAG's approach: "activate only the local relationship
    network needed for the current question."

    Args:
        start_entities: list of entity IDs/names to expand from
        ... (same as traverse())
    """
    from collections import defaultdict

    if not start_entities:
        return TraversalResult()

    # Resolve all start entities
    resolved = []
    for ent in start_entities:
        node = graph.get_node(ent) or graph.find_by_name(ent)
        if node:
            resolved.append(node.entity_id)

    if not resolved:
        return TraversalResult()

    # For single entity, delegate to standard traverse
    if len(resolved) == 1:
        return traverse(
            resolved[0], graph, max_hops=max_hops,
            relation_filter=relation_filter, direction=direction,
            node_limit=node_limit, min_weight=min_weight,
            relation_weights=relation_weights,
        )

    # Multi-entity expansion: run separate traversals, merge results
    merged = TraversalResult()
    seen_entities: set = set()

    for entity_id in resolved:
        sub = traverse(
            entity_id, graph, max_hops=max_hops,
            relation_filter=relation_filter, direction=direction,
            node_limit=node_limit // len(resolved),
            min_weight=min_weight, relation_weights=relation_weights,
        )
        merged.paths.extend(sub.paths)
        merged.truncated = merged.truncated or sub.truncated
        for term in sub.terminal_entities:
            key = term["entity_id"]
            if key not in seen_entities:
                seen_entities.add(key)
                merged.terminal_entities.append(term)
        merged.timing_ms += sub.timing_ms

    merged.stats = {
        "nodes_visited": len(seen_entities),
        "paths_found": len(merged.paths),
        "terminals_found": len(merged.terminal_entities),
        "max_hops": max_hops,
        "direction": direction,
        "start_entities": len(resolved),
    }
    # ── Rank terminals by path coverage ──
    if merged.paths and len(resolved) > 1:
        coverage: dict = {}
        for p in merged.paths:
            t = p.terminal
            if t:
                key = t.entity_id
                # Weight: 1 / path_length, shorter paths carry more weight
                score = 1.0 / max(1, p.length)
                coverage[key] = coverage.get(key, 0) + score
        merged.ranked_terminals = sorted(
            [{"entity_id": k, "entity_name": "", "score": round(v, 3)}
             for k, v in coverage.items()],
            key=lambda x: -x["score"],
        )
        # Fill entity names from terminal_entities
        name_map = {t["entity_id"]: t.get("entity_name", "") for t in merged.terminal_entities}
        for rt in merged.ranked_terminals:
            rt["entity_name"] = name_map.get(rt["entity_id"], rt["entity_id"])
    return merged


def _find_connecting_edges(
    graph: GraphIndex,
    from_id: str,
    to_id: str,
    direction: str,
) -> List[GraphEdge]:
    """Find edges connecting from_id → to_id in the specified direction."""
    edges = []
    from_node = graph.get_node(from_id)
    to_node = graph.get_node(to_id)
    if not from_node or not to_node:
        return edges

    # Outgoing: from_id's out_edges → to_id
    if direction in ("outgoing", "both"):
        for e in from_node.out_edges:
            if e.target_id == to_id:
                edges.append(e)
    # Incoming: from_id's in_edges ← to_id (i.e., to_id's out_edges → from_id)
    if direction in ("incoming", "both"):
        for e in from_node.in_edges:
            if e.source_id == to_id:
                # Create a synthetic edge showing the inverse direction
                edges.append(GraphEdge(
                    source_id=from_id,
                    target_id=to_id,
                    relation_name=e.relation_name,
                    relation_label=e.relation_label,
                    confidence=e.confidence,
                ))

    return edges
