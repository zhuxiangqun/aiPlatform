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
import logging

from typing import Any, Dict, List, Optional, Tuple


def map_query_to_ontology(
    question: str,
    *,
    domain_id: str = None,
    collection_id: str = "default",
    max_matches: int = 3,
) -> Dict[str, Any]:
    u"""Map a natural language question to T-Box classes and properties.

    Args:
        domain_id: ontology domain to search (e.g. "ai-knowledge", "it-ops").
                   If None, resolved from collection_id via DomainRouter.
        collection_id: wiki collection (backward compat, used if domain_id is None).

    Returns:
        {
            "matched_classes": [{"uri": "...", "label": "Material", "score": 0.9}],
            "matched_properties": [{"uri": "...", "label": "on_hand_inventory", "score": 0.8}],
            "matched_concepts": [{"keyword": "库存", "tbox_label": "on_hand_inventory"}],
            "rewritten_query": "Material 类 on_hand_inventory 属性 查询: 轴承库存多少",
            "confidence": 0.85,
        }
    """
    import os

    from core.harness.knowledge.knowledge_ontology import (
        CLASSES, OBJECT_PROPERTIES, DATA_PROPERTIES, get_ontology,
    )

    # ── Resolve domain_id ──
    if domain_id is None:
        from core.harness.knowledge.domain_router import DomainRouter
        domain_id = DomainRouter().resolve(collection_id)

    onto = get_ontology()
    q_lower = question.lower()

    matched_classes: List[Dict[str, Any]] = []
    matched_properties: List[Dict[str, Any]] = []
    matched_concepts: List[Dict[str, Any]] = []

    # ── Match T-Box classes (built-in + domain-specific) ──
    all_classes = list(CLASSES)
    adaptive_thresholds: Dict[str, float] = {}

    onto_path = os.path.expanduser(f"~/.aiplat/ontologies/{domain_id}.yaml")
    if os.path.exists(onto_path):
        try:
            from core.harness.knowledge.ontology_loader import load_ontology_from_yaml
            domain = load_ontology_from_yaml(onto_path)
            all_classes.extend(domain.classes)
            for cls in domain.classes:
                thresh = getattr(cls, 'confidence_threshold', None)
                adaptive_thresholds[cls.label] = float(thresh) if thresh else 0.7
        except Exception as e:
            logging.debug(str(e), exc_info=True)
    else:
        # Fallback: load all domains (backward compat)
        try:
            from core.harness.knowledge.ontology_loader import load_all_domains
            for d_id, d in load_all_domains().items():
                all_classes.extend(d.classes)
        except Exception as e:
            logging.debug(str(e), exc_info=True)

    # ── Match T-Box classes ──
    for cls in all_classes:
        label_lower = cls.label.lower()
        # Check if any word from class label appears in question
        words = label_lower.split()
        # Check Chinese characters — require ≥2 char overlap OR ≥50% label chars in question
        chinese_chars = [c for c in label_lower if '\u4e00' <= c <= '\u9fff']
        chinese_match = False
        if chinese_chars:
            matching = [c for c in chinese_chars if c in q_lower]
            chinese_match = len(matching) >= 2 or (len(matching) >= len(chinese_chars) * 0.5 and len(matching) >= 1)
        # Check full label presence
        label_match = label_lower in q_lower or any(w in q_lower for w in words if len(w) >= 2)
        
        if label_match or chinese_match:
            # Granular score based on character overlap percentage
            char_overlap = 0.0
            if chinese_chars:
                matching = [c for c in chinese_chars if c in q_lower]
                char_overlap = len(matching) / len(chinese_chars) if chinese_chars else 0
            # Also check word-level overlap
            word_matches = sum(1 for w in words if len(w) >= 2 and w in q_lower)
            word_overlap = word_matches / len([w for w in words if len(w) >= 2]) if [w for w in words if len(w) >= 2] else 0

            if label_match or (label_lower in q_lower):
                score = 0.75 + min(0.20, char_overlap * 0.25)  # [0.75, 0.95]
            elif chinese_match and char_overlap >= 0.8:
                score = 0.60 + char_overlap * 0.25  # [0.78, 0.85]
            elif chinese_match and word_overlap > 0:
                score = 0.45 + max(char_overlap, word_overlap) * 0.35  # [0.45, 0.80]
            else:
                score = 0.30 + char_overlap * 0.35  # [0.30, 0.65]
            score = min(0.95, max(0.15, round(score, 3)))
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

    # ── Phase 43: Formula/calculation decomposition ──
    decomposition_results = _apply_decompositions(question, domain_id)

    # ── Rewrite query ──
    rewritten = _rewrite_query(question, matched_classes, matched_properties, matched_concepts)

    # Phase 44: Inject decomposition terms into rewritten_query (all retrievers benefit)
    if decomposition_results:
        decomp_terms = []
        for d in decomposition_results:
            for p in d.get("parts", []):
                term = p.get("concept", "")
                if term:
                    decomp_terms.append(term)
        if decomp_terms:
            rewritten += f" [分解概念: {' '.join(decomp_terms)}]"

    # ── Confidence ──
    all_scores = (
        [m["score"] for m in matched_classes]
        + [m["score"] for m in matched_properties]
        + [m["score"] for m in matched_concepts]
    )
    confidence = round(sum(all_scores) / max(1, len(all_scores)), 2)

    # Determine best target class for retrieval filtering with adaptive threshold
    target_class = ""
    if matched_classes:
        best = matched_classes[0]
        class_threshold = adaptive_thresholds.get(best["label"], 0.7)
        if best["score"] >= class_threshold:
            target_class = best["uri"]

    return {
        "matched_classes": matched_classes[:max_matches],
        "matched_properties": matched_properties[:max_matches],
        "matched_concepts": matched_concepts[:max_matches],
        "rewritten_query": rewritten,
        "confidence": confidence,
        "target_class": target_class,
        "decompositions": decomposition_results,
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


def parse_to_logic_form(
    question: str,
    *,
    domain_id: str = "ai-knowledge",
) -> Dict[str, Any]:
    """NL2LF: Parse natural language question to structured Logic Form.

    Data Agent semantic layer: converts natural language questions
    into structured query representations for downstream engines.

    Returns: {intent, entities, target_class, metrics, filters, time_range, aggregation, confidence}
    """
    import re
    r = {
        "question": question, "intent": "fact_lookup",
        "entities": [], "target_class": "", "metrics": [],
        "filters": [], "time_range": "", "aggregation": "", "confidence": 0.0,
    }
    # Intent
    if any(k in question for k in ["最高","最大","最多","最低","最小","最少"]):
        r["intent"] = "comparative_ranking"
        r["aggregation"] = "max" if any(k in question for k in ["最高","最大","最多"]) else "min"
    elif any(k in question for k in ["为什么","原因","根因"]): r["intent"] = "root_cause"
    elif any(k in question for k in ["趋势","变化","增长","下降"]): r["intent"] = "trend_analysis"
    # Time
    for pat, tr in [(r"上(个?)月","last_month"),(r"本(个?)月","this_month"),(r"上周","last_week")]:
        if re.search(pat, question): r["time_range"] = tr; break
    # Ontology mapping
    m = map_query_to_ontology(question)
    if m:
        matched = m.get("matched_classes") or []
        if matched:
            r["target_class"] = matched[0].get("label","")
            r["confidence"] = matched[0].get("score",0)
            r["entities"] = [x.get("label","") for x in matched[:3]]
    # Metrics
    for kw, (nm, fm) in {"退货率":("return_rate","退货/总数"),"转化率":("conv_rate","成交/进店"),"客单价":("aov","金额/订单")}.items():
        if kw in question: r["metrics"].append({"name":nm,"formula":fm})
    # Region filter
    for reg in ["华东","华南","华北","一线城市"]:
        if reg in question: r["filters"].append({"field":"region","op":"=","value":reg})
    return r


# ══════════════════════════════════════════════════════════════
# DMQR-RAG: 4 Adaptive Multi-Query Rewrite Strategies
# ══════════════════════════════════════════════════════════════

def rewrite_generic(query: str) -> str:
    """Strategy 1: Clean noise, preserve all core info. Restore base intent."""
    import re
    q = re.sub(r'[？?！!。，,、\s]+$', '', query.strip())
    q = re.sub(r'\s+', ' ', q)
    return q

def rewrite_keywords(query: str) -> str:
    """Strategy 2: Extract core nouns and business topics, drop modifiers."""
    import re
    # Chinese: keep meaningful 2-4 char phrases
    cn = re.findall(r'[\u4e00-\u9fff]{2,4}', query)
    en = re.findall(r'[a-zA-Z]{2,}', query)
    # Filter common question words
    skip = {'是什么','为什么','如何','怎么','哪些','请问','能不能','可不可以','有没有','是否'}
    keywords = [w for w in cn if w not in skip][:5] + en[:3]
    return ' '.join(keywords) if keywords else query

def rewrite_pseudo_answer(query: str) -> str:
    """Strategy 3: Return empty — caller generates pseudo-answer via LLM."""
    return ""  # Requires LLM, handled by caller

def rewrite_core(query: str) -> str:
    """Strategy 4: Strip redundant details, keep core intent (first 3-5 meaningful chars)."""
    import re
    cn = re.findall(r'[\u4e00-\u9fff]{2,4}', query)
    en = re.findall(r'[a-zA-Z]{2,}', query)
    skip = {'是什么','为什么','如何','怎么','哪些','请问','能不能','可不可以','有没有','是否','请问一下','我想知道','帮我看','有没有人','有没有什么'}
    core = [w for w in cn if w not in skip][:3] + en[:2]
    return ' '.join(core) if core else query[:60]


def rewrite_multi_dmqr(
    query: str,
    *,
    strategies: list = None,
) -> List[str]:
    """DMQR-RAG: Adaptive multi-query rewrite.

    Applies all active strategies and returns deduplicated variants.
    Default strategies: generic + keywords (no LLM), core (no LLM).
    Pseudo-answer requires LLM and should be handled by caller.
    """
    active = strategies or ["generic", "keywords", "core"]
    variants = [query]

    strategy_map = {
        "generic": rewrite_generic,
        "keywords": rewrite_keywords,
        "core": rewrite_core,
    }

    for s_name in active:
        if s_name in strategy_map:
            v = strategy_map[s_name](query)
            if v and v != query:
                variants.append(v)

    return list(set(variants))


def rewrite_with_llm_pseudo_answer(query: str) -> str:
    """Generate a pseudo-answer using LLM for HyDE-like retrieval enrichment."""
    return (
        f"请用一段专业、正式的语言(50-100字)，描述以下问题的核心概念和可能的答案方向。"
        f"这个描述将用于检索文档，所以请使用文档中可能出现的术语。\n\n问题: {query}"
    )


def discover_cross_domain_analogs(
    concept: str,
    *,
    domains: List[str] = None,
    threshold: float = 0.7,
) -> Dict[str, List[Dict[str, Any]]]:
    u"""Discover semantically similar classes across all domain ontologies.

    For a given concept (e.g. "围标串标"), scans all loaded domains and returns
    classes whose labels/descriptions are semantically similar, along with their
    key properties for cross-domain diagnosis enrichment.

    Args:
        concept: The concept name to search for across domains
        domains: Optional domain filter (defaults to all registered domains)
        threshold: Cosine similarity threshold (default 0.7)

    Returns:
        {domain_id: [{class_label, uri, score, key_properties, description}]}

    callers: FDE diagnosis enrichment, cross-domain ontology context injection
    """
    import os

    import numpy as np

    from core.harness.knowledge.domain_router import DomainRouter
    from core.harness.knowledge.ontology_loader import load_ontology_from_yaml
    from core.harness.knowledge.embedder import embed_text_semantic

    router = DomainRouter()
    target_domains = domains or router.list_domains()

    concept_vec = embed_text_semantic(concept)
    if concept_vec is None:
        return {}
    concept_arr = np.array(concept_vec, dtype=np.float32)
    concept_arr = concept_arr / (np.linalg.norm(concept_arr) + 1e-8)

    results: Dict[str, List[Dict[str, Any]]] = {}
    for did in target_domains:
        path = os.path.expanduser(f"~/.aiplat/ontologies/{did}.yaml")
        if not os.path.exists(path):
            continue
        domain = load_ontology_from_yaml(path)
        matches: List[Dict[str, Any]] = []
        for cls in domain.classes:
            text = f"{cls.label} {getattr(cls, 'description', '')}"
            cls_vec = embed_text_semantic(text)
            if cls_vec is None:
                continue
            cls_arr = np.array(cls_vec, dtype=np.float32)
            cls_arr = cls_arr / (np.linalg.norm(cls_arr) + 1e-8)
            score = float(np.dot(concept_arr, cls_arr))
            if score >= threshold:
                fields = getattr(cls, 'required_fields', []) or []
                matches.append({
                    "class_label": cls.label,
                    "uri": cls.uri,
                    "score": round(score, 3),
                    "key_properties": list(fields)[:3],
                    "description": (getattr(cls, 'description', '') or "")[:200],
                })
        if matches:
            results[did] = sorted(matches, key=lambda x: x["score"], reverse=True)

    return results


def _apply_decompositions(
    question: str,
    domain_id: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """Phase 43: Decompose composite concepts into constituent parts.

    Reads decomposition_rules from domain YAML, matches the user query
    against known composite terms (e.g., "利润率" → "利润" + "营收"),
    and returns expansion hints for downstream retrieval.

    YAML format (in domain YAML):
        decomposition_rules:
          - name: profit_margin
            composite: "利润率"
            formula: "利润 / 营收"
            parts:
              - concept: "利润"
                relation: "分子"
              - concept: "营收"
                relation: "分母"
            units: "%"
            domain: finance
    """
    if not domain_id:
        return []

    import os as _os, json as _json
    onto_path = _os.path.expanduser(f"~/.aiplat/ontologies/{domain_id}.yaml")
    if not _os.path.exists(onto_path):
        return []

    try:
        import yaml as _yaml
        with open(onto_path) as f:
            domain_data = _yaml.safe_load(f) or {}
    except Exception:
        return []

    rules = domain_data.get("decomposition_rules", [])
    if not rules:
        return []

    q_lower = question.lower()
    results = []

    for rule in rules:
        composite = str(rule.get("composite", "")).lower()
        if not composite:
            continue
        if composite in q_lower or any(part.get("concept", "").lower() in q_lower
                                        for part in rule.get("parts", [])):
            parts = []
            for p in rule.get("parts", []):
                parts.append({
                    "concept": p.get("concept", ""),
                    "relation": p.get("relation", ""),
                })
            results.append({
                "composite": rule.get("composite", ""),
                "formula": rule.get("formula", ""),
                "units": rule.get("units", ""),
                "parts": parts,
            })
    return results
