"""
GraphRAG Retriever (Phase 3, 2026-07-30).

Three-layer retrieval:
  1. Entity Router: extract entities from query → locate in GraphIndex
  2. Subgraph Extraction: BFS 2-hop neighborhood from seed entities
  3. Targeted Vector Retrieval: filter chunks by subgraph document IDs

Augments standard RAG with entity links + reasoning paths for LLM context.
"""
from __future__ import annotations

import logging
from collections import deque
from typing import Any, Dict, List, Optional, Set, Tuple

logger = logging.getLogger(__name__)


class GraphRAGRetriever:
    """Entity-aware retrieval with subgraph-enhanced context."""

    def __init__(self):
        self._entity_cache: Dict[str, List[Dict]] = {}

    # ═══════════════════════════════════════════════════════
    # Layer 1: Entity Router
    # ═══════════════════════════════════════════════════════

    async def retrieve(self, query: str, domain_id: str = "default",
                       top_k: int = 10, run_id: str = "") -> Dict[str, Any]:
        """Full GraphRAG retrieval pipeline."""
        # ── Layer 1: Entity extraction from query ──
        entities = await self._extract_query_entities(query, domain_id)
        if not entities:
            return {"mode": "vector_only", "chunks": [], "reasoning_paths": [],
                    "entities": [], "note": "No entities extracted from query"}

        # Locate entities in graph
        entity_nodes = []
        for ent in entities:
            node = self._find_node(ent["name"], domain_id, ent.get("class_type"))
            if node:
                entity_nodes.append({**node, "query_class": ent.get("class_type")})

        if not entity_nodes:
            chunks = await self._vector_search(query, domain_id, top_k)
            return {"mode": "vector_only", "chunks": chunks, "reasoning_paths": [],
                    "entities": entities, "note": "Entities found in query but not in graph"}

        # ── Layer 2: Subgraph extraction (2-hop) ──
        subgraph = self._extract_subgraph(entity_nodes, domain_id, hops=2, run_id=run_id)

        # ── Layer 3: Targeted vector retrieval ──
        doc_ids = self._get_doc_ids_from_subgraph(subgraph)
        chunks = await self._vector_search(query, domain_id, top_k, filter_doc_ids=doc_ids)

        # If targeted retrieval returns too few, fall back to untargeted
        if len(chunks) < 3:
            chunks = await self._vector_search(query, domain_id, top_k)

        # ── Layer 4: Reasoning paths ──
        paths = self._extract_reasoning_paths(subgraph, entity_nodes, query)

        return {
            "mode": "graphrag",
            "entities": entity_nodes,
            "subgraph_size": len(subgraph.get("nodes", [])),
            "chunks": chunks,
            "reasoning_paths": paths,
        }

    # ═══════════════════════════════════════════════════════
    # Entity extraction from query (LLM or keyword)
    # ═══════════════════════════════════════════════════════

    async def _extract_query_entities(self, query: str, domain_id: str) -> List[Dict[str, str]]:
        """Extract named entities from user query.

        Uses LLM if available, falls back to graph index lookup (keyword match).
        """
        prompt = f"""从用户查询中提取实体名称和类型。
输出 JSON 数组: [{{"name": "实体名", "class_type": "人物|组织|产品|地点|时间|事件|文档|概念|方法"}}]
只输出 JSON，不要解释。
查询: {query[:500]}
"""

        try:
            from core.harness.syscalls.llm import sys_llm_generate
            result = await sys_llm_generate([{"role": "user", "content": prompt}], purpose="chat")
            import json, re
            text = str(result.get("content", "") or result)
            cleaned = re.sub(r'```(?:json)?\s*', '', text).replace('```', '').strip()
            return json.loads(cleaned) if cleaned.startswith('[') else []
        except Exception:
            logger.debug("LLM entity extraction failed, using keyword fallback", exc_info=True)

        # Fallback: scan graph nodes for keyword matches
        entities = []
        try:
            from core.harness.ontology_engine.graph_index import GraphIndex
            g = GraphIndex.load(domain_id)
            for node in g._nodes.values():
                name = getattr(node, 'name', '') or getattr(node, 'entity_text', '')
                if name and name in query:
                    entities.append({"name": name, "class_type": getattr(node, 'class_name', '概念')})
        except Exception:
            logger.debug('entity extraction fallback failed', exc_info=True)
        return entities[:5]

    # ═══════════════════════════════════════════════════════
    # Graph lookup
    # ═══════════════════════════════════════════════════════

    def _find_node(self, name: str, domain_id: str, class_type: str = "") -> Optional[Dict]:
        """Find an entity node in the graph by name."""
        try:
            from core.harness.ontology_engine.graph_index import GraphIndex
            g = GraphIndex.load(domain_id)
            # Try exact match first
            for node_id, node in g._nodes.items():
                node_name = getattr(node, 'name', '') or getattr(node, 'entity_text', '')
                if node_name == name:
                    cls = getattr(node, 'class_name', '')
                    if not class_type or cls == class_type or not class_type:
                        return {"id": node_id, "name": node_name, "class": cls}
            # Try contains match
            for node_id, node in g._nodes.items():
                node_name = getattr(node, 'name', '') or getattr(node, 'entity_text', '')
                if name in node_name or node_name in name:
                    cls = getattr(node, 'class_name', '')
                    return {"id": node_id, "name": node_name, "class": cls}
        except Exception:
            logger.debug('node lookup failed', exc_info=True)
        return None

    # ═══════════════════════════════════════════════════════
    # Layer 2: Subgraph Extraction (BFS)
    # ═══════════════════════════════════════════════════════

    def _extract_subgraph(self, seed_nodes: List[Dict], domain_id: str,
                          hops: int = 2, run_id: str = "") -> Dict[str, Any]:
        """BFS from seed nodes up to `hops` hops, returning nodes + edges."""
        try:
            from core.harness.ontology_engine.graph_index import GraphIndex
            g = GraphIndex.load(domain_id)
        except Exception:
            return {"nodes": [], "edges": []}

        visited_nodes: Set[str] = set()
        edges: List[str] = []
        queue = deque()

        for seed in seed_nodes:
            sid = seed.get("id", "")
            if sid:
                visited_nodes.add(sid)
                queue.append((sid, 0))

        while queue:
            current_id, depth = queue.popleft()
            if depth >= hops:
                continue

            node = g._nodes.get(current_id)
            if not node:
                continue

            # In-edges + out-edges
            for edge in (getattr(node, 'in_edges', []) or []) + (getattr(node, 'out_edges', []) or []):
                target = getattr(edge, 'target_id', '') or getattr(edge, 'source_id', '')
                rel_label = getattr(edge, 'relation_label', 'related_to')
                edge_str = f"{current_id} --{rel_label}--> {target}"
                if edge_str not in edges:
                    edges.append(edge_str)

                if target and target not in visited_nodes:
                    visited_nodes.add(target)
                    queue.append((target, depth + 1))

                    # Phase 50: Record traversal step for reasoning evidence
                    if run_id:
                        try:
                            from core.harness.infrastructure.lineage_store import LineageStore
                            target_node = g._nodes.get(target)
                            store = LineageStore.get()
                            store.record_traversal_step(
                                run_id=run_id,
                                step_index=depth,
                                from_entity=current_id,
                                from_name=getattr(node, 'entity_name', current_id),
                                to_entity=target,
                                to_name=getattr(target_node, 'entity_name', target) if target_node else target,
                                to_class=getattr(target_node, 'class_name', '') if target_node else '',
                                relation=rel_label,
                                relation_label=rel_label,
                                confidence=1.0,
                                hop=depth + 1,
                            )
                        except Exception:
                            pass  # best-effort

            # Phase 1: Hyperedge traversal — expand via multi-entity hyperedges
            for he in g.get_hyperedges_for_entity(current_id):
                for member_id in he.entity_ids:
                    if member_id and member_id not in visited_nodes and member_id != current_id:
                        visited_nodes.add(member_id)
                        queue.append((member_id, depth + 1))
                        edges.append(f"HYPEREDGE:{he.event_id}:{current_id}→{member_id}")

        nodes = []
        for nid in visited_nodes:
            node = g._nodes.get(nid)
            if node:
                name = getattr(node, 'name', '') or getattr(node, 'entity_text', '') or nid
                nodes.append({"id": nid, "name": name, "class": getattr(node, 'class_name', '')})

        return {"nodes": nodes, "edges": edges}

    # ═══════════════════════════════════════════════════════
    # Document ID extraction from subgraph
    # ═══════════════════════════════════════════════════════

    def _get_doc_ids_from_subgraph(self, subgraph: Dict) -> Set[str]:
        """Extract document IDs linked to subgraph entities."""
        doc_ids: Set[str] = set()
        for node_info in subgraph.get("nodes", []):
            nid = node_info.get("id", "")
            # Source doc ID is often embedded in the entity ID pattern
            if "_" in str(nid):
                parts = str(nid).split("_")
                if len(parts) > 1:
                    doc_ids.add(parts[0])
        return doc_ids

    # ═══════════════════════════════════════════════════════
    # Layer 4: Reasoning path extraction
    # ═══════════════════════════════════════════════════════

    def _extract_reasoning_paths(self, subgraph: Dict, seed_nodes: List[Dict],
                                  query: str) -> List[str]:
        """Extract human-readable reasoning paths from the subgraph."""
        paths: List[str] = []
        edges = subgraph.get("edges", [])

        # Filter edges that include seed nodes
        seed_ids = {n.get("id", "") for n in seed_nodes}
        for edge in edges[:20]:
            for sid in seed_ids:
                if sid and sid in edge:
                    paths.append(edge)
                    break

        if not paths and edges:
            paths = edges[:10]

        return paths

    # ═══════════════════════════════════════════════════════
    # Vector search (delegated to existing infrastructure)
    # ═══════════════════════════════════════════════════════

    async def _vector_search(self, query: str, domain_id: str, top_k: int,
                             filter_doc_ids: Optional[Set[str]] = None) -> List[Dict[str, Any]]:
        """Search vector store for relevant chunks. Falls back to wiki search."""
        try:
            from core.harness.knowledge.wiki_engine import search_pages
            pages = search_pages(query=query, limit=top_k, collection_id=domain_id)
            chunks = []
            for p in pages:
                title = p.get("title", "")
                body = p.get("body", "")[:500]
                if filter_doc_ids:
                    # Only include if page is linked to subgraph docs
                    source = p.get("source_doc", p.get("source_articles", ""))
                    if not any(did in str(source) for did in filter_doc_ids):
                        continue
                chunks.append({
                    "title": title,
                    "content": body,
                    "source": p.get("source_articles", domain_id),
                })
            return chunks[:top_k]
        except Exception:
            logger.debug("Vector search failed, returning empty", exc_info=True)
            return []

    # ═══════════════════════════════════════════════════════
    # Context injection for ActionRegistry
    # ═══════════════════════════════════════════════════════

    async def get_entity_context(self, entity_id: str, domain_id: str,
                                  action_context: str = "") -> Dict[str, Any]:
        """Pre-load entity context for action execution awareness."""
        result = await self.retrieve(
            query=action_context or entity_id,
            domain_id=domain_id,
            top_k=5,
        )
        return {
            "entity_id": entity_id,
            "related_entities": result.get("entities", []),
            "reasoning_paths": result.get("reasoning_paths", []),
            "mode": result.get("mode", "unknown"),
        }
