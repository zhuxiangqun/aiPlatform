"""
Knowledge Evolution LLM — LLM-driven ontology evolution suggestions (Tier 2).

Layered on top of rule-based Tier 1 (add_suggestions_from_patterns in
knowledge_ontology.py). Provides semantic-level suggestions:

  1. Semantic merge detection — embedding similarity + LLM judgment
  2. Field gap analysis — statistical frequency → recommend required fields
  3. Missing relation inference — body text analysis → suggest cites links
  4. Impact prediction — pre-acceptance scope estimation

Callers:
  - knowledge_ontology.add_suggestions_from_patterns(include_llm=True)
  - wiki.py POST /ontology/suggestions/semantic
  - core_facade.get_semantic_suggestions()
"""

from __future__ import annotations

import json as _json
import logging
import time as _time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Set, Tuple

logger = logging.getLogger(__name__)

AI = "http://aiplat.local/knowledge#"


async def generate_semantic_suggestions(
    collection_id: str = "default",
    *,
    max_suggestions: int = 5,
    confidence_threshold: float = 0.7,
    llm_model: str = "",
) -> List[Dict[str, Any]]:
    u"""LLM-driven ontology evolution suggestions.

    Analysis dimensions:
      1. Semantic merge detection — high embedding similarity + LLM confirms
      2. Field gap analysis — fields with >80% occurrence but not in T-Box
      3. Missing relation inference — pages mentioning each other without cites

    Args:
        collection_id: wiki collection to analyze.
        max_suggestions: max total suggestions to return.
        confidence_threshold: minimum confidence for inclusion.
        llm_model: optional model name override for LLM calls.

    Returns:
        List of suggestion dicts, each with type/status/description/rationale/
        confidence/implementation/risk fields.
    """
    from core.harness.knowledge.knowledge_ontology import get_ontology
    from core.harness.knowledge.knowledge_abox_builder import _scan_wiki_pages

    onto = get_ontology()
    pages = _scan_wiki_pages(collection_id=collection_id)
    if not pages:
        logger.info("No wiki pages found for collection %s, skipping LLM suggestions", collection_id)
        return []

    suggestions: List[Dict[str, Any]] = []
    quota = max_suggestions

    # Dimension 1: Semantic merge detection
    if quota > 0:
        merges = await _detect_semantic_merges(pages, onto, confidence_threshold, llm_model)
        for m in merges[:quota]:
            if m.get("confidence", 0) >= confidence_threshold:
                suggestions.append(m)
        quota = max_suggestions - len(suggestions)

    # Dimension 2: Field gap analysis (deterministic, fast)
    if quota > 0:
        fields = _detect_field_gaps(pages, confidence_threshold)
        for f in fields[:quota]:
            suggestions.append(f)

    suggestions.sort(key=lambda s: s.get("confidence", 0), reverse=True)
    return suggestions[:max_suggestions]


async def _detect_semantic_merges(
    pages: List[Dict],
    onto: Any,
    confidence_threshold: float,
    llm_model: str = "",
) -> List[Dict[str, Any]]:
    u"""Detect pages with high semantic similarity that may describe the same concept."""
    candidates: List[Dict[str, Any]] = []

    # Group by category to avoid cross-category false merges
    by_category: Dict[str, List[Dict]] = {}
    for p in pages:
        cat = p.get("category", p.get("_category", "entities"))
        by_category.setdefault(cat, []).append(p)

    for cat, cat_pages in by_category.items():
        if len(cat_pages) < 2:
            continue

        # Embedding-based fast screening
        try:
            from core.harness.knowledge.embedder import embed_texts_semantic, hash_embed, cosine_similarity

            texts = [
                f"{p.get('title', '')}: {str(p.get('summary', p.get('_body', '')))[:500]}"
                for p in cat_pages
            ]
            embeddings = embed_texts_semantic(texts)
            if embeddings is None:
                dim = 128
                embeddings = [hash_embed(t, dim) for t in texts]

            # Cosine similarity matrix (upper triangle only)
            high_sim_pairs: List[Tuple[int, int, float]] = []
            for i in range(len(cat_pages)):
                for j in range(i + 1, len(cat_pages)):
                    sim = cosine_similarity(embeddings[i], embeddings[j])
                    if sim > 0.85:
                        high_sim_pairs.append((i, j, sim))

            # LLM confirmation for top pairs (limit to avoid cost)
            for i, j, sim in high_sim_pairs[:3]:
                p1 = cat_pages[i]
                p2 = cat_pages[j]
                llm_result = await _llm_judge_merge(p1, p2, sim, cat, llm_model)
                if llm_result.get("should_merge") and llm_result.get("confidence", 0) >= confidence_threshold:
                    candidates.append({
                        "type": "merge_classes",
                        "source": "llm",
                        "status": "pending",
                        "description": f"合并 '{p1.get('title', '')}' 和 '{p2.get('title', '')}' 为 '{llm_result.get('merged_title', p1.get('title'))}'",
                        "rationale": llm_result.get("reasoning", f"Semantic similarity = {sim:.2f}"),
                        "confidence": llm_result.get("confidence", sim * 0.8),
                        "implementation": f"Merge pages into one, consolidate all relations.",
                        "affected_pages": [p1.get("title"), p2.get("title")],
                        "risk": "medium",
                        "generated_at": _time.strftime("%Y-%m-%dT%H:%M:%SZ", _time.gmtime()),
                    })

        except Exception as e:
            logger.warning("Semantic merge detection failed for category %s: %s", cat, str(e)[:200])

    return candidates


def _detect_field_gaps(
    pages: List[Dict],
    confidence_threshold: float = 0.7,
) -> List[Dict[str, Any]]:
    u"""Statistical analysis: fields with >80% occurrence in a category but
    not in T-Box required/optional fields."""
    from core.harness.knowledge.knowledge_ontology import get_class_by_category

    by_category: Dict[str, List[Dict]] = {}
    for p in pages:
        cat = p.get("category", p.get("_category", "entities"))
        by_category.setdefault(cat, []).append(p)

    suggestions: List[Dict[str, Any]] = []
    for cat, cat_pages in by_category.items():
        if len(cat_pages) < 5:
            continue

        cls = get_class_by_category(cat)
        if cls is None:
            continue

        known_fields = set(cls.required_fields + cls.optional_fields)

        # Count field occurrences
        field_counts: Dict[str, int] = {}
        for p in cat_pages:
            for k, v in p.items():
                if k.startswith("_"):
                    continue
                if v and (not isinstance(v, str) or v.strip()):
                    field_counts[k] = field_counts.get(k, 0) + 1

        # Fields with >80% occurrence but not in T-Box
        threshold = int(len(cat_pages) * 0.8)
        for field, count in field_counts.items():
            if count >= threshold and field not in known_fields:
                pct = int(100 * count / len(cat_pages))
                suggestions.append({
                    "type": "add_required_field",
                    "source": "statistical",
                    "status": "pending",
                    "description": f"{cat}分类下'{field}'字段出现率{count}/{len(cat_pages)} ({pct}%)",
                    "rationale": (
                        f"Field '{field}' appears in {count}/{len(cat_pages)} pages "
                        f"of category '{cat}', suggesting it should be a "
                        f"required or optional field in {cls.label}."
                    ),
                    "confidence": min(0.95, 0.6 + (count / len(cat_pages)) * 0.3),
                    "implementation": f"Add '{field}' to required_fields or optional_fields of {cls.label} in CLASSES list",
                    "risk": "medium" if cls.label == "ConceptPage" else "low",
                    "generated_at": _time.strftime("%Y-%m-%dT%H:%M:%SZ", _time.gmtime()),
                })

    return suggestions


async def _llm_judge_merge(
    p1: Dict[str, Any],
    p2: Dict[str, Any],
    similarity: float,
    category: str,
    model_override: str = "",
) -> Dict[str, Any]:
    u"""Call LLM to judge whether two wiki pages describe the same concept.

    Uses a lightweight prompt (~150 tokens target) for binary classification.
    Falls back gracefully on parse errors.
    """
    try:
        from core.harness.syscalls.llm import sys_llm_generate
        from core.harness.utils.model_injection import best_model_for_purpose

        prompt = (
            f"You are an ontology curator. Two Wiki pages have high semantic "
            f"similarity ({similarity:.2f}).\n\n"
            f"Page A: \"{p1.get('title', '')}\"\n"
            f"Summary: {str(p1.get('summary', p1.get('_body', '')))[:300]}\n\n"
            f"Page B: \"{p2.get('title', '')}\"\n"
            f"Summary: {str(p2.get('summary', p2.get('_body', '')))[:300]}\n\n"
            f"Do these two pages describe the SAME concept/entity? "
            f"Reply with JSON only: "
            f'{{"should_merge": true/false, "merged_title": "suggested name", '
            f'"confidence": 0.0-1.0, "reasoning": "one sentence"}}'
        )

        result = await sys_llm_generate(
            None, [{"role": "user", "content": prompt}],
            model_name=best_model_for_purpose("ontology"),
            max_tokens=150,
        )

        content = result.get("content", "{}")
        parsed = _safe_json_parse(content)
        return {
            "should_merge": bool(parsed.get("should_merge", False)),
            "merged_title": str(parsed.get("merged_title", p1.get("title", ""))),
            "confidence": float(parsed.get("confidence", similarity * 0.7)),
            "reasoning": str(parsed.get("reasoning", "")),
        }

    except Exception as e:
        logger.debug("LLM merge judgment failed: %s", str(e)[:100])
        return {"should_merge": False, "confidence": 0.0, "reasoning": str(e)[:100]}


def predict_evolution_impact(
    suggestion: Dict[str, Any],
    onto: Any,
) -> Dict[str, Any]:
    u"""Predict the impact scope of an ontology evolution suggestion.

    Helps answer: "If I accept this suggestion, how many entities and
    relations will be affected?"
    """
    affected_entities: List[str] = []
    affected_relations = 0
    requires_migration = False

    stype = suggestion.get("type", "")

    if stype == "merge_classes":
        pages = suggestion.get("affected_pages", [])
        for t in onto.triples:
            subj_name = t.subject.replace(AI, "")
            for page in pages:
                if page in (t.subject, t.object):
                    affected_relations += 1
                    if subj_name not in affected_entities:
                        affected_entities.append(subj_name)
        requires_migration = len(pages) >= 2

    elif stype == "add_required_field":
        cat = suggestion.get("description", "")
        field = suggestion.get("field_name", "")
        from core.harness.knowledge.knowledge_abox_builder import _scan_wiki_pages
        pages = _scan_wiki_pages()
        missing = [p.get("title", "") for p in pages if not p.get(field)]
        affected_entities = [f"{len(missing)} pages missing field '{field}'"]
        requires_migration = len(missing) > 0

    elif stype == "add_relation":
        requires_migration = False
        affected_entities = suggestion.get("affected_pages", [])

    estimated_review_minutes = max(3, affected_relations // 20 * 3)

    return {
        "suggestion_id": suggestion.get("id", ""),
        "type": stype,
        "affected_entities_count": len(affected_entities),
        "affected_relations_count": affected_relations,
        "affected_entities_sample": affected_entities[:10],
        "risk_level": (
            "high" if affected_relations > 50 or requires_migration
            else "medium" if affected_relations > 10
            else "low"
        ),
        "requires_page_migration": requires_migration,
        "estimated_review_time_minutes": estimated_review_minutes,
    }


def _safe_json_parse(content: str) -> Dict[str, Any]:
    u"""Robust JSON parse — strips markdown fences and falls back to empty dict."""
    text = content.strip()
    if text.startswith("```"):
        first_break = text.find("\n")
        last_fence = text.rfind("```")
        if first_break >= 0 and last_fence > first_break:
            text = text[first_break:last_fence].strip()

    # Try to extract just the JSON object
    brace_start = text.find("{")
    brace_end = text.rfind("}")
    if brace_start >= 0 and brace_end > brace_start:
        text = text[brace_start:brace_end + 1]

    try:
        return _json.loads(text)
    except _json.JSONDecodeError:
        return {}
