"""
Ontology Query Mapper — rewrite user queries using T-Box class/property knowledge.

Bridges the gap between natural language questions and ontology-aware retrieval:
  1. Parse user question → match against T-Box class labels and property labels
  2. Match against registered concept keywords
  3. Rewrite query to include class/property context for better retrieval precision

Example:
  User: "轴承库存多少" 
  → matched_class: "Material", matched_property: "on_hand_inventory"
  → rewritten: "Material 类 库存 on_hand_inventory 轴承"

Injection point: called before sys_wiki_context / sys_kb_retrieve to rewrite queries.

callers: sys_wiki_context, sys_kb_retrieve, sys_ontology_context
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple


def map_query_to_ontology(
    question: str,
    *,
    collection_id: str = "default",
    max_matches: int = 3,
) -> Dict[str, Any]:
    u"""Map a natural language question to T-Box classes and properties.

    Returns:
        {
            "matched_classes": [{"uri": "...", "label": "Material", "score": 0.9}],
            "matched_properties": [{"uri": "...", "label": "on_hand_inventory", "score": 0.8}],
            "matched_concepts": [{"keyword": "库存", "tbox_label": "on_hand_inventory"}],
            "rewritten_query": "Material 类 on_hand_inventory 属性 查询: 轴承库存多少",
            "confidence": 0.85,
        }
    """
    from core.harness.knowledge.knowledge_ontology import (
        CLASSES, OBJECT_PROPERTIES, DATA_PROPERTIES, get_ontology,
    )

    onto = get_ontology()
    q_lower = question.lower()

    matched_classes: List[Dict[str, Any]] = []
    matched_properties: List[Dict[str, Any]] = []
    matched_concepts: List[Dict[str, Any]] = []

    # ── Match T-Box classes ──
    for cls in CLASSES:
        label_lower = cls.label.lower()
        # Check if any word from class label appears in question
        words = label_lower.split()
        # Also check Chinese characters — match by character overlap
        chinese_chars = [c for c in label_lower if '\u4e00' <= c <= '\u9fff']
        chinese_match = any(c in q_lower for c in chinese_chars) if chinese_chars else False
        # Check full label presence
        label_match = label_lower in q_lower or any(w in q_lower for w in words if len(w) >= 2)
        
        if label_match or chinese_match:
            score = 0.9 if label_match else 0.6
            matched_classes.append({
                "uri": cls.uri,
                "label": cls.label,
                "score": score,
                "match_type": "label" if label_match else "chinese",
            })

    # ── Match data properties (by label + registered concepts) ──
    concept_map = _get_concept_map()
    for dp in DATA_PROPERTIES:
        prop_label = dp.label.lower()
        # Direct label match
        if any(w in q_lower for w in prop_label.split()) or prop_label in q_lower:
            matched_properties.append({
                "uri": dp.uri,
                "label": dp.label,
                "score": 0.85,
                "match_type": "label",
            })

    # ── Concept keyword mapping ──
    for keyword, tbox_concept in concept_map.items():
        if keyword in q_lower:
            matched_concepts.append({
                "keyword": keyword,
                "tbox_label": tbox_concept,
                "score": 0.95,
            })

    # ── Object property matching ──
    for op in OBJECT_PROPERTIES:
        op_label = op.label.lower()
        if any(w in q_lower for w in op_label.split()) or op_label in q_lower:
            matched_properties.append({
                "uri": op.uri,
                "label": op.label,
                "score": 0.8,
                "match_type": "object_property",
            })

    # ── Rewrite query ──
    rewritten = _rewrite_query(question, matched_classes, matched_properties, matched_concepts)

    # ── Confidence ──
    all_scores = (
        [m["score"] for m in matched_classes]
        + [m["score"] for m in matched_properties]
        + [m["score"] for m in matched_concepts]
    )
    confidence = round(sum(all_scores) / max(1, len(all_scores)), 2)

    return {
        "matched_classes": matched_classes[:max_matches],
        "matched_properties": matched_properties[:max_matches],
        "matched_concepts": matched_concepts[:max_matches],
        "rewritten_query": rewritten,
        "confidence": confidence,
    }


def _rewrite_query(
    question: str,
    classes: List[Dict],
    properties: List[Dict],
    concepts: List[Dict],
) -> str:
    u"""Rewrite the query to include ontology context for better retrieval precision."""
    parts = []

    if classes:
        class_labels = [c["label"] for c in classes[:2]]
        parts.append(f"类: {'/'.join(class_labels)}")

    if properties:
        prop_labels = [p["label"] for p in properties[:2]]
        parts.append(f"属性: {'/'.join(prop_labels)}")

    if concepts:
        concept_strs = [f"{c['keyword']}({c['tbox_label']})" for c in concepts[:2]]
        parts.append(f"概念: {'/'.join(concept_strs)}")

    if parts:
        return f"{', '.join(parts)}。查询: {question}"
    return question


def _get_concept_map() -> Dict[str, str]:
    u"""Return a mapping of domain-specific keywords to T-Box concept labels.

    This is a curated list that maps common business terms to ontology concepts.
    Future: could be auto-generated from T-Box class labels and their
    extraction_prompt / template_markdown content.
    """
    return {
        # Supply chain / inventory domain
        "库存": "on_hand_inventory",
        "需求": "gross_demand",
        "采购": "planned_order_quantity",
        "供应商": "hasSource",
        "订单": "net_requirement",
        "BOM": "物料清单",
        "安全库存": "safety_stock",

        # Knowledge management domain
        "引用": "cites",
        "矛盾": "contradicts",
        "来源": "hasSource",
        "父概念": "parentOf",
        "案例": "example_of",
        "摘要": "summary",
        "文档": "KBDocument",
        "页面": "WikiPage",

        # Learning domain
        "前置": "prerequisiteOf",
        "掌握度": "masteryScore",
        "评估": "Assessment",
        "章节": "Chapter",
        "学习路径": "LearningPath",

        # Quality domain
        "质量": "qualityScore",
        "盲区": "source_less_concepts",
        "孤立": "orphan_pages",
    }


def enrich_query_for_retrieval(
    question: str,
    *,
    collection_id: str = "default",
) -> str:
    u"""Convenience function: map query and return the rewritten version.

    Use this directly in sys_wiki_context and sys_kb_retrieve as a
    one-line pre-processing step.

    Example:
        enriched = enrich_query_for_retrieval("轴承库存")
        results = sys_wiki_retrieve(enriched)
    """
    result = map_query_to_ontology(question, collection_id=collection_id)
    return result.get("rewritten_query", question)
