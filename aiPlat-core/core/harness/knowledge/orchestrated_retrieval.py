"""Orchestrated retrieval — unified ontology→graph traversal pipeline.



Phase 1 refactoring: extracts the 3-step pipeline duplicated between

MaterialsChatAgent and MultiAgentOrchestrator into a single shared function.



Pipeline:

  1. map_query_to_ontology(query) → matched_classes

  2. GraphIndex.find_by_name(label) → entity IDs

  3. traverse_multi(entity_ids, graph) → terminal entities

"""



from __future__ import annotations



import logging

from typing import Any, Dict, List, Optional, Tuple



logger = logging.getLogger("aiplat.orchestrated_retrieval")





def traverse_ontology_graph(

    query: str,

    domain_id: str,

    *,

    max_hops: int = 2,

    max_classes: int = 3,

) -> Dict[str, Any]:

    """Run the ontology→graph traversal pipeline.



    Args:

        query: User question text.

        domain_id: Ontology domain (e.g., "ai-knowledge").

        max_hops: Maximum graph traversal hops.

        max_classes: Maximum matched ontology classes to follow.



    Returns:

        Dict with keys:

            - ontology_mapping: dict from map_query_to_ontology

            - matched_entity_ids: List[str] of entity IDs found in graph

            - terminal_entities: List[dict] from traversal result

            - terminal_names: List[str] of terminal entity names

            - traversal_paths: List[TraversalPath] from traversal (empty if no match)

            - success: bool

    """

    result: Dict[str, Any] = {

        "ontology_mapping": {},

        "matched_entity_ids": [],

        "terminal_entities": [],

        "terminal_names": [],

        "traversal_paths": [],

        "success": False,

    }



    # Step 1: Ontology mapping

    try:

        from core.harness.knowledge.ontology_query_mapper import map_query_to_ontology

        result["ontology_mapping"] = map_query_to_ontology(query, domain_id=domain_id)

    except Exception as e:

        logger.debug("ontology mapping failed: %s", e)

        return result



    # Step 2: Entity lookup in GraphIndex

    try:

        from core.harness.ontology_engine.graph_index import GraphIndex



        graph = GraphIndex.load(domain_id)

        if not graph or len(graph) == 0:

            return result



        matched_classes = result["ontology_mapping"].get("matched_classes") or []

        entity_ids: List[str] = []

        for mc in matched_classes[:max_classes]:

            label = mc.get("label", "")

            if label:

                node = graph.find_by_name(label)

                if node:

                    entity_ids.append(node.entity_id)

                else:

                    entity_ids.append(label)  # fallback: use label as entity ID



        if not entity_ids:

            return result



        result["matched_entity_ids"] = entity_ids



        # Step 3: Graph traversal

        from core.harness.ontology_engine.graph_traversal import traverse_multi



        trav = traverse_multi(entity_ids, graph, max_hops=max_hops)

        result["terminal_entities"] = trav.terminal_entities

        result["terminal_names"] = [t.get("entity_name", "") for t in trav.terminal_entities[:5] if t.get("entity_name")]

        result["traversal_paths"] = trav.paths

        result["success"] = True



        return result

    except Exception as e:

        logger.debug("graph traversal failed: %s", e)

        return result





async def ontology_first_retrieve(

    query: str,

    ontology_class_uri: str,

    *,

    domain_id: str = "",

    collection_id: str = "",

    top_k: int = 8,

) -> Tuple[str, List[dict]]:

    """Ontology-first multi-class retrieval with neighbor class expansion.



    Pipeline:

      1. Build target_classes from ontology_class_uri + 1-hop graph neighbors

      2. Parallel async retrieval for each target class

      3. Merge results and deduplicate by title



    Returns (retrieved_docs: str, citations: List[dict]).

    """

    try:

        from core.harness.ontology_engine.graph_index import GraphIndex

        from core.harness.syscalls.retrieval import sys_knowledge_retrieve



        target_classes = [ontology_class_uri]



        # Neighbor class expansion

        try:

            g = GraphIndex.load("ai-knowledge")

            if len(g) > 0:

                short = ontology_class_uri.rsplit("/", 1)[-1] if "/" in ontology_class_uri else ontology_class_uri

                node = g.find_by_name(short)

                if node:

                    neighbors = g.get_neighbors(node.entity_id, direction="both")

                    for n in neighbors[:3]:

                        if n.class_name and n.class_name not in target_classes:

                            target_classes.append(n.uri if hasattr(n, 'uri') else n.class_name)

        except Exception:

            logging.getLogger(__name__).debug('ontology_first_retrieve failed', exc_info=True)


        # Multi-class parallel retrieval

        import asyncio

        wiki_ids = [collection_id] if collection_id else []

        tasks = [

            sys_knowledge_retrieve(

                query=query,

                wiki_first=True,

                wiki_collection_ids=wiki_ids,

                target_class=tc,

                expand_subclasses=True,

                top_k=top_k,

            )

            for tc in target_classes[:3]

        ]

        all_batches = await asyncio.gather(*tasks, return_exceptions=True)



        # Merge & dedup by title

        seen_titles = set()

        merged = []

        for batch in all_batches:

            if isinstance(batch, Exception):

                continue

            for r in batch:

                key = r.get("title", r.get("source", str(r)[:80]))

                if key not in seen_titles:

                    seen_titles.add(key)

                    merged.append(r)



        if not merged:

            return "", []



        retrieved_docs = "\n\n---\n\n".join(

            f"[{r.get('source', 'wiki')}] {r.get('content', str(r))[:2000]}"

            for r in merged

        )

        citations = [

            {"source": r.get("source", "wiki"), "text": str(r.get("content", ""))[:200]}

            for r in merged

        ]

        return retrieved_docs, citations

    except Exception:

        return "", []





def build_reasoning_path(

    question: str,

    ontology_mapping: Optional[dict],

    traversal_result: Optional[dict],

) -> List[Dict[str, Any]]:

    """Build a structured reasoning path from ontology mapping + graph traversal.



    Extracted from MaterialsChatAgent. Returns a list of step dicts showing

    how the agent arrived at its answer: intent_classify → traversal → retrieval.

    """

    path: List[Dict[str, Any]] = []



    # Step 1: intent classification

    if ontology_mapping:

        matched = ontology_mapping.get("matched_classes") or []

        if matched:

            matched_name = matched[0].get("label", "")

            path.append({

                "step": 1,

                "from": question[:60],

                "to": matched_name or "",

                "via": "intent_classify",

                "confidence": matched[0].get("score", 0),

            })



    # Step 2: graph traversal

    if traversal_result and traversal_result.get("success"):

        for tpath in (traversal_result.get("traversal_paths") or [])[:5]:

            for s in (tpath.steps or [])[1:]:

                path.append({

                    "step": len(path) + 1,

                    "from": s.entity_name,

                    "to": "",

                    "via": f"traversal:{s.relation_name}" if s.relation_name else "traversal",

                    "relation_label": s.relation_label,

                    "confidence": s.confidence,

                })



    # Step 3: knowledge retrieval

    path.append({

        "step": len(path) + 1,

        "from": "knowledge_base",

        "to": "answer",

        "via": "knowledge_retrieve",

    })



    return path

