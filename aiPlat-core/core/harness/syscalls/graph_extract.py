"""
sys_graph_extract — online entity/relation extraction into ReconSubgraph.

Lightweight wrapper around existing engine pipeline (ClassMapper +
PropertyExtractor + RelationMapper), adapted for on-demand, single-chunk
extraction by agents.

Agent usage:
  sys_graph_extract("A公司使用B供应商的芯片", domain="supply-chain", run_id="abc")
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

logger = logging.getLogger("aiplat.syscalls.graph_extract")


async def sys_graph_extract(
    text: str,
    *,
    domain_id: str = "default",
    operation: str = "auto",
    source_type: str = "kb_document",
    run_id: str = "",
    agent_id: str = "",
) -> Dict[str, Any]:
    """Extract entities and relations from text into a ReconSubgraph.

    Args:
        text: Raw text to extract from (chunk or document section)
        domain_id: Target ontology domain
        operation: "entities" → ClassMapper + PropertyExtractor
                   "relations" → RelationMapper on existing entities
                   "auto" → full pipeline (entities + relations)
        source_type: trust tier for confidence calc (official_doc/contract/kb_document/news/web)
        run_id: ReconSubgraph run identifier
        agent_id: Agent performing the extraction (for attribution)

    Returns:
        {entities_extracted, relations_detected, graph_domain, status}
    """
    if not text or len(text) < 10:
        return {"entities_extracted": 0, "relations_detected": 0, "status": "empty_text"}

    try:
        from core.harness.knowledge.recon_subgraph import ReconSubgraph
    except ImportError:
        return {"status": "error", "error": "recon_subgraph module not available"}

    if not run_id:
        return {"status": "error", "error": "run_id required for ReconSubgraph"}

    recon = ReconSubgraph(run_id)

    entities_extracted = 0
    relations_detected = 0

    # ── Entity extraction ──
    if operation in ("entities", "auto"):
        try:
            from core.harness.ontology_engine.class_mapper import ClassMapper
            from core.harness.ontology_engine.property_extractor import PropertyExtractor

            # Classify: find matching ontology class
            mapper = ClassMapper()
            class_results = mapper.map_entities([{"text": text}], domain_id=domain_id)

            for chunk_result in class_results:
                class_name = chunk_result.get("class_name", "")
                confidence = chunk_result.get("confidence", 0.5)
                if not class_name or class_name == "Unknown":
                    continue

                # Extract structured properties
                try:
                    extractor = PropertyExtractor()
                    props = await extractor.extract(
                        chunk={"text": text}, class_name=class_name, domain_id=domain_id
                    )
                except Exception:
                    props = {}

                entity_name = props.get("name", "") or class_name
                entity_id = f"{class_name.lower()}_{entity_name.replace(' ', '_')}"

                recon.add_entity(
                    entity_id, entity_name, class_name,
                    source_doc_id=run_id, agent_id=agent_id,
                )
                entities_extracted += 1
        except Exception as e:
            logger.debug("entity extraction failed: %s", e)

    # ── Relation detection ──
    if operation in ("relations", "auto"):
        try:
            from core.harness.ontology_engine.relation_mapper import RelationMapper

            mapper = RelationMapper()
            relations = mapper.detect_co_occurrence(
                chunks=[{"text": text}], domain_id=domain_id
            )

            for rel in relations:
                source_id = rel.get("source_id", "")
                target_id = rel.get("target_id", "")
                rel_name = rel.get("relation_name", "")
                rel_confidence = rel.get("confidence", 0.85)

                if not source_id or not target_id or not rel_name:
                    continue

                recon.add_relation(
                    source_id, target_id, rel_name,
                    confidence=rel_confidence,
                    source_type=source_type,
                    agent_id=agent_id,
                    run_id=run_id,
                    hop_count=0,
                )
                relations_detected += 1
        except Exception as e:
            logger.debug("relation detection failed: %s", e)

    return {
        "entities_extracted": entities_extracted,
        "relations_detected": relations_detected,
        "graph_domain": recon.domain_id,
        "status": "ok",
    }
