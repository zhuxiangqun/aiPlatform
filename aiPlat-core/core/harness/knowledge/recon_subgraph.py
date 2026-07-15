"""
ReconSubgraph — query-specific temporary graph for multi-agent collaborative reasoning.

Creates an isolated GraphIndex instance (`_recon_{run_id}`) per query session.
Agents write entities/edges during the query; on completion, high-confidence data
can be merged to the persistent domain or discarded.

Key features:
  - Isolated per-run SQLite storage (~/.aiplat/data/recon/{run_id}.db)
  - Auto confidence calculation on add_relation() via source_type + hop_count
  - merge_to() — selective merge to persistent domain
  - discard() — cleanup after query completes
"""

from __future__ import annotations

import json as _json
import logging
import os as _os
import time as _time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

logger = logging.getLogger("aiplat.recon_subgraph")

# Source reliability mapping (for confidence calculation)
SOURCE_TRUST = {
    "official_doc": 0.95,
    "contract": 0.90,
    "kb_document": 0.85,
    "news": 0.65,
    "web": 0.50,
    "user_generated": 0.40,
}


class ReconSubgraph:
    """Query-specific temporary graph for multi-agent reasoning.
    
    Usage:
        recon = ReconSubgraph("query_abc123")
        recon.add_entity("E1", "A产品", "Product", agent_id="extract_1")
        recon.add_relation("E1", "E2", "composed_of", source_type="kb_document",
                          agent_id="extract_1", run_id="query_abc123", hop_count=0)
        recon.merge_to("supply-chain", min_confidence=0.7)
        recon.discard()
    """

    def __init__(self, run_id: str, *, data_dir: str = ""):
        self.run_id = run_id
        self.domain_id = f"_recon_{run_id}"
        
        if not data_dir:
            data_dir = _os.path.expanduser("~/.aiplat/data/recon")
        _os.makedirs(data_dir, exist_ok=True)
        
        self._db_path = _os.path.join(data_dir, f"{run_id}.db")
        self.created_at = _time.time()
        self.agent_contributions: Dict[str, int] = {}  # agent_id → count
        
        # Lazy-init GraphIndex
        from core.harness.ontology_engine.graph_index import GraphIndex
        self.graph = GraphIndex(self.domain_id)
        logger.info("ReconSubgraph created: %s", self.domain_id)

    def add_entity(
        self, entity_id: str, entity_name: str, class_name: str,
        *, source_doc_id: str = "", agent_id: str = "",
    ):
        """Add an entity to the recon graph. Wraps GraphIndex.add_entity()."""
        node = self.graph.add_entity(
            entity_id, entity_name, class_name, source_doc_id=source_doc_id
        )
        if agent_id:
            node.metadata["created_by"] = agent_id
            self.agent_contributions[agent_id] = self.agent_contributions.get(agent_id, 0) + 1
        return node

    def add_relation(
        self, source_id: str, target_id: str, relation_name: str, *,
        relation_label: str = "", confidence: float = 0.0,
        inferred: bool = False, rule_name: str = "",
        source_type: str = "kb_document", agent_id: str = "",
        run_id: str = "", hop_count: int = 0,
        created_by: str = "", created_in_run: str = "",
    ) -> float:
        """Add a relation with auto-computed confidence.

        Confidence formula:
          source_trust * 0.4 + detection_confidence * 0.3 + (1 - 0.1 * hop_count) * 0.3

        If confidence is explicitly provided (> 0), it's used as detection_confidence.
        Otherwise defaults to 0.85 (average KB extraction accuracy).

        Returns the computed confidence value.
        """
        import math as _math

        # Source reliability
        source_trust = SOURCE_TRUST.get(source_type, 0.50)

        # Detection confidence (explicit or default)
        detection_conf = confidence if confidence > 0 else 0.85

        # Hop penalty
        hop_penalty = max(0.3, 1.0 - 0.1 * hop_count)

        computed = (
            source_trust * 0.4 +
            detection_conf * 0.3 +
            hop_penalty * 0.3
        )
        computed = round(min(1.0, max(0.0, computed)), 3)

        self.graph.add_relation(
            source_id, target_id, relation_name,
            relation_label=relation_label,
            confidence=computed,
            inferred=inferred,
            rule_name=rule_name,
        )

        # Tag the edge with agent attribution
        src_node = self.graph.get_node(source_id)
        if src_node and src_node.out_edges:
            edge = src_node.out_edges[-1]
            edge.created_by = created_by or agent_id
            edge.created_in_run = created_in_run or run_id

        if agent_id:
            self.agent_contributions[agent_id] = self.agent_contributions.get(agent_id, 0) + 1

        return computed

    def merge_to(self, target_domain: str, *, min_confidence: float = 0.7) -> Dict[str, int]:
        """Merge high-confidence entities/edges into a persistent domain.

        Only entities/edges with confidence >= min_confidence are merged.
        Returns counts: {entities_merged, relations_merged, skipped}.
        """
        from core.harness.ontology_engine.graph_index import GraphIndex
        target = GraphIndex.load(target_domain)
        
        merged_entities = 0
        merged_relations = 0
        skipped = 0

        for node_id, node in self.graph._nodes.items():
            if target.get_node(node_id):
                skipped += 1
                continue

            target.add_entity(
                node.entity_id, node.entity_name, node.class_name,
                source_doc_id=node.source_doc_id,
            )
            merged_entities += 1

            # Merge qualifying edges
            for edge in node.out_edges:
                if edge.confidence >= min_confidence:
                    target.add_relation(
                        edge.source_id, edge.target_id, edge.relation_name,
                        relation_label=edge.relation_label,
                        confidence=edge.confidence,
                        inferred=edge.inferred,
                        rule_name=edge.rule_name,
                    )
                    merged_relations += 1
                else:
                    skipped += 1

        logger.info(
            "ReconSubgraph merged to %s: %d entities, %d relations, %d skipped",
            target_domain, merged_entities, merged_relations, skipped,
        )
        return {
            "entities_merged": merged_entities,
            "relations_merged": merged_relations,
            "skipped": skipped,
        }

    def discard(self):
        """Delete temporary SQLite file and free memory."""
        try:
            _os.remove(self._db_path)
        except OSError:
            pass
        # Also try to remove WAL/SHM files
        for suffix in ("-wal", "-shm"):
            try:
                _os.remove(self._db_path + suffix)
            except OSError:
                pass
        logger.info("ReconSubgraph discarded: %s", self.run_id)

    def snapshot(self, label: str = "") -> str:
        """Create a snapshot of the current recon graph state."""
        return self.graph.snapshot(label or f"recon_{self.run_id}")

    def stats(self) -> Dict[str, Any]:
        """Return statistics about the recon graph."""
        s = self.graph.stats()
        return {
            **s,
            "domain_id": self.domain_id,
            "run_id": self.run_id,
            "age_seconds": round(_time.time() - self.created_at, 1),
            "agent_contributions": dict(self.agent_contributions),
        }
