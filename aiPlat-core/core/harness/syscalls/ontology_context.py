"""
sys_ontology_context — ontology knowledge context for Agents.

Phase D: knowledge_gaps tells the Agent "here's what we need to find out"
rather than just "here's what we know".
"""

from __future__ import annotations

from typing import Any, Dict, List


def sys_ontology_context(
    question: str = "",
    *,
    max_pages: int = 10,
    collection_id: str = "default",
    include_contradictions: bool = True,
    include_state_summary: bool = True,
    include_gaps: bool = True,
) -> Dict[str, Any]:
    u"""Query ontology state for Agent context injection.

    返回: state_summary, contradicted_entities, health_score,
    axiom_violations, related_pages, knowledge_gaps.

    边界:
      - 只读——不修改本体状态
      - 公验分数反映的是 T-Box 约束违规数，不是知识质量
      - knowledge_gaps 中的计数依赖于当前 A-Box 的完整性
    退路:
      - 健康分低 → 触发 /ontology/health/triggers 自动策展
      - 特定实体 → 用 get_entity_quality_score() 获取单实体质量分
    """
    from core.harness.knowledge.knowledge_ontology import get_ontology

    onto = get_ontology()
    result: Dict[str, Any] = {}

    if include_state_summary:
        result["state_summary"] = _get_state_summary(onto)

    if include_contradictions:
        result["contradicted_entities"] = _get_contradicted(onto)

    try:
        from core.harness.knowledge.knowledge_validator import validate_all
        report = validate_all(collection_id=collection_id)
        result["health_score"] = report.score
        result["axiom_violations"] = [
            {"axiom_id": v.axiom_id, "severity": v.severity,
             "description": v.description, "entities": v.entities[:5]}
            for v in report.violations[:10]
        ]
    except Exception:
        result["health_score"] = 100
        result["axiom_violations"] = []

    if question:
        try:
            from core.harness.knowledge.wiki_engine import search_pages
            pages = search_pages(question, limit=max_pages, collection_id=collection_id)
            result["related_pages"] = [
                {"title": p.get("title", ""), "summary": str(p.get("summary", ""))[:150]}
                for p in pages[:max_pages]
            ]
        except Exception:
            result["related_pages"] = []

    if include_gaps:
        result["knowledge_gaps"] = _get_knowledge_gaps(onto)

    return result


def _get_knowledge_gaps(onto: Any) -> Dict[str, Any]:
    AI = "http://aiplat.local/knowledge#"
    gaps: Dict[str, Any] = {}

    # 1. Source-less concepts (A1: ConceptPages without KB source)
    source_less = []
    for t in onto.triples:
        if t.predicate == "rdf:type" and f"{AI}ConceptPage" in t.object:
            uri = t.subject
            has_source = any(
                tt.subject == uri and tt.predicate == f"{AI}hasSource"
                for tt in onto.triples
            )
            if not has_source:
                source_less.append(uri.replace(AI, ""))
    if source_less:
        gaps["source_less_concepts"] = source_less[:10]
        gaps["source_less_count"] = len(source_less)

    # 2. Unmined KB docs (docs not yet converted to wiki pages)
    kb_docs = set()
    for t in onto.triples:
        if t.predicate == "rdf:type" and "KBDocument" in t.object:
            kb_docs.add(t.subject)
    referenced = set()
    for t in onto.triples:
        if t.predicate == f"{AI}hasSource":
            referenced.add(t.object)
    unmined = [d.replace(AI, "") for d in kb_docs if d not in referenced]
    if unmined:
        gaps["unmined_kb_documents"] = unmined[:10]
        gaps["unmined_count"] = len(unmined)

    # 3. Unidirectional citations
    outbound: Dict[str, set] = {}
    inbound: Dict[str, set] = {}
    for t in onto.triples:
        if t.predicate == f"{AI}cites":
            outbound.setdefault(t.subject, set()).add(t.object)
            inbound.setdefault(t.object, set()).add(t.subject)
    one_way = []
    for src, targets in outbound.items():
        for target in targets:
            if target not in inbound or src not in inbound.get(target, set()):
                one_way.append(f"{src.replace(AI, '')[:60]} → {target.replace(AI, '')[:60]}")
    if one_way:
        gaps["unidirectional_citations"] = one_way[:10]
        gaps["unidirectional_count"] = len(one_way)

    # 4. Orphan pages (no links at all)
    all_wiki = set()
    for t in onto.triples:
        if t.predicate == "rdf:type" and "WikiPage" in t.object:
            all_wiki.add(t.subject)
    linked = set(outbound.keys()) | set(inbound.keys())
    orphans = [u.replace(AI, "") for u in all_wiki if u not in linked]
    if orphans:
        gaps["orphan_pages"] = orphans[:10]
        gaps["orphan_count"] = len(orphans)

    gaps["total_gaps"] = (
        gaps.get("source_less_count", 0) + gaps.get("unmined_count", 0)
        + gaps.get("unidirectional_count", 0) + gaps.get("orphan_count", 0)
    )
    return gaps


def _get_state_summary(onto: Any) -> Dict[str, Any]:
    AI = "http://aiplat.local/knowledge#"
    counts: Dict[str, int] = {}
    for t in onto.triples:
        if t.predicate == f"{AI}lifecycleState":
            s = t.object.strip('"')
            counts[s] = counts.get(s, 0) + 1
    return {
        "total": sum(counts.values()), "by_state": counts,
        "published": counts.get("published", 0),
        "contradicted": counts.get("contradicted", 0),
        "under_review": counts.get("under_review", 0),
        "proposed": counts.get("proposed", 0),
    }


def _get_contradicted(onto: Any) -> List[Dict[str, Any]]:
    AI = "http://aiplat.local/knowledge#"
    uris = set()
    for t in onto.triples:
        if t.predicate == f"{AI}lifecycleState" and t.object.strip('"') == "contradicted":
            uris.add(t.subject)
    result = []
    for uri in list(uris)[:20]:
        name = uri.replace(AI, "")
        opposes = []
        for t in onto.triples:
            if t.predicate == f"{AI}contradicts" and t.subject == uri:
                opp = t.object.replace(AI, "")
                if opp not in opposes:
                    opposes.append(opp)
        result.append({"entity": name, "contradicts": opposes})
    return result
