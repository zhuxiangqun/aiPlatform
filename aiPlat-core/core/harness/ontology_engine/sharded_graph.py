"""
Sharded Graph Index — multi-domain graph operations.

Wraps multiple GraphIndex instances (one per domain) and provides
cross-domain traversal and query capabilities.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from core.harness.ontology_engine.graph_index import GraphIndex


class ShardedGraphIndex:
    """Multi-domain graph aggregator."""

    def __init__(self):
        self._shards: Dict[str, GraphIndex] = {}

    def get_shard(self, domain_id: str) -> GraphIndex:
        """Get or load a domain shard."""
        if domain_id not in self._shards:
            self._shards[domain_id] = GraphIndex.load(domain_id)
        return self._shards[domain_id]

    def cross_domain_neighbors(
        self,
        entity_name: str,
        *,
        domains: Optional[List[str]] = None,
        primary_domain: str = None,
        allow_cross: bool = True,
    ) -> Dict[str, List[str]]:
        """Find entities with same name across domains.

        Args:
            primary_domain: scope lookup to this domain only.
            allow_cross: if False, ignore `domains` and ONLY search primary_domain.

        Returns {domain_id: [neighbor_names], ...}
        """
        if not allow_cross and primary_domain:
            domains = [primary_domain]
        elif primary_domain and domains is None:
            domains = [primary_domain]
        elif domains is None:
            domains = list(self._shards.keys())

        result = {}
        for did in domains:
            shard = self.get_shard(did)
            node = shard.find_by_name(entity_name)
            if node:
                neighbors = shard.get_neighbors(node.entity_id, direction="both")
                result[did] = [n.entity_name for n in neighbors]
        return result

    def stats_all(self) -> Dict[str, Dict[str, Any]]:
        """Get stats for all loaded shards."""
        return {did: shard.stats() for did, shard in self._shards.items()}

    def total_stats(self) -> Dict[str, Any]:
        """Aggregate stats across all shards."""
        nodes = sum(len(s) for s in self._shards.values())
        edges = sum(s.stats().get("edge_count", 0) for s in self._shards.values())
        return {
            "shards": len(self._shards),
            "total_nodes": nodes,
            "total_edges": edges,
            "domains": list(self._shards.keys()),
        }

    def __len__(self) -> int:
        return len(self._shards)
