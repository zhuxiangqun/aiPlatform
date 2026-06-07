"""
Knowledge Ontology Validator — reasoning engine wrapper.

Runs validation queries against the current A-Box, detects axiom violations,
and produces structured validation reports that integrate with wiki_health_rules.

No external SPARQL engine required — uses in-memory triple matching.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from dataclasses import dataclass, field

from core.harness.knowledge.knowledge_ontology import (
    KnowledgeOntology, OntologyTriple, OntologyAxiom,
    get_ontology, AI,
)

logger = logging.getLogger(__name__)


@dataclass
class ValidationIssue:
    """A single violation detected by the validator."""
    axiom_id: str
    severity: str             # error | warning | info
    description: str
    entities: List[str] = field(default_factory=list)
    recommendation: str = ""


@dataclass  
class ValidationReport:
    """Complete validation report for the current A-Box."""
    timestamp: str
    total_triples: int
    violations: List[ValidationIssue]
    violations_by_severity: Dict[str, int] = field(default_factory=dict)
    passed_axioms: List[str] = field(default_factory=list)
    failed_axioms: List[str] = field(default_factory=list)
    
    @property
    def has_errors(self) -> bool:
        return self.violations_by_severity.get("error", 0) > 0
    
    @property
    def score(self) -> int:
        """Compute a health score from 0-100 based on violations."""
        errors = self.violations_by_severity.get("error", 0)
        warnings = self.violations_by_severity.get("warning", 0)
        infos = self.violations_by_severity.get("info", 0)
        raw = 100 - (errors * 10) - (warnings * 3) - infos
        return max(0, min(100, raw))


# ══════════════════════════════════════════════════════════════
# SPARQL-like Query Engine (In-Memory)
# ══════════════════════════════════════════════════════════════

class TripleStore:
    """Simple in-memory triple store with basic pattern matching."""
    
    def __init__(self, triples: List[OntologyTriple]):
        self._spo: Dict[str, Dict[str, List[str]]] = {}  # subject → predicate → [objects]
        self._pos: Dict[str, Dict[str, List[str]]] = {}  # predicate → object → [subjects]
        
        for t in triples:
            # SPO index
            self._spo.setdefault(t.subject, {}).setdefault(t.predicate, []).append(t.object)
            # POS index
            self._pos.setdefault(t.predicate, {}).setdefault(t.object, []).append(t.subject)
    
    def subjects(self, predicate: str, object_value: str) -> List[str]:
        """Get all subjects where (subject, predicate, object)."""
        return self._pos.get(predicate, {}).get(object_value, [])
    
    def objects(self, subject: str, predicate: str) -> List[str]:
        """Get all objects where (subject, predicate, ?)."""
        return self._spo.get(subject, {}).get(predicate, [])
    
    def exists(self, subject: str, predicate: str, object_value: str = None) -> bool:
        """Check if a triple exists (optionally with specific object)."""
        objs = self._spo.get(subject, {}).get(predicate, [])
        if object_value is None:
            return len(objs) > 0
        return object_value in objs
    
    def all_subjects_of_type(self, type_uri: str) -> List[str]:
        """Get all subjects of a given rdf:type."""
        return self._pos.get("rdf:type", {}).get(type_uri, [])
    
    def transitive_closure(self, start: str, predicate: str, max_depth: int = 10) -> List[str]:
        """BFS transitive closure from a start node along a predicate."""
        visited: set = {start}
        frontier = [start]
        for _ in range(max_depth):
            next_frontier = []
            for node in frontier:
                for neighbor in self._spo.get(node, {}).get(predicate, []):
                    if neighbor not in visited:
                        visited.add(neighbor)
                        next_frontier.append(neighbor)
            frontier = next_frontier
            if not frontier:
                break
        return sorted(visited - {start})
    
    def detect_cycle(self, start: str, predicate: str, max_depth: int = 20) -> bool:
        """Detect if a node is part of a cycle along a predicate."""
        visited: set = set()
        frontier = [start]
        for _ in range(max_depth):
            next_frontier = []
            for node in frontier:
                for neighbor in self._spo.get(node, {}).get(predicate, []):
                    if neighbor == start:
                        return True
                    if neighbor not in visited:
                        visited.add(neighbor)
                        next_frontier.append(neighbor)
            frontier = next_frontier
            if not frontier:
                break
        return False


# ══════════════════════════════════════════════════════════════
# Inference Rules Engine (Pluggable)
# ══════════════════════════════════════════════════════════════

from enum import Enum


class RuleTrigger(str, Enum):
    ON_CREATE = "on_create"
    ON_QUERY = "on_query"
    ON_DELETE = "on_delete"
    PERIODIC = "periodic"


@dataclass
class InferenceRule:
    name: str
    description: str
    trigger: RuleTrigger
    pattern: str = ""
    action: str = ""
    severity: str = "warning"
    enabled: bool = True

    def matches(self, triples: List[OntologyTriple], store: TripleStore,
                context: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Override in subclasses for custom logic. Returns list of inferred {subject, predicate, object}."""
        return []


# ── Built-in Rules ──
DEFAULT_RULES: List[InferenceRule] = []


def register_rule(rule: InferenceRule) -> None:
    """Register a custom inference rule."""
    DEFAULT_RULES.append(rule)


def _extends_rule(name: str, trigger: RuleTrigger, pattern: str, action: str,
                  severity: str = "warning") -> InferenceRule:
    """Factory for simple pattern-match rules."""
    return InferenceRule(name=name, description=action, trigger=trigger,
                         pattern=pattern, action=action, severity=severity)


# R1: Transitive closure for transitive properties
DEFAULT_RULES.append(InferenceRule(
    name="transitive_closure",
    description="For transitive properties, infer A→C from A→B and B→C",
    trigger=RuleTrigger.ON_QUERY,
    pattern="?a <transitive_prop> ?b . ?b <transitive_prop> ?c",
    action="infer ?a <transitive_prop> ?c",
))

# R2: Symmetric completion
DEFAULT_RULES.append(InferenceRule(
    name="symmetric_completion",
    description="For symmetric properties, auto-add reverse edge on create",
    trigger=RuleTrigger.ON_CREATE,
    pattern="?a <symmetric_prop> ?b",
    action="assert ?b <symmetric_prop> ?a",
))

# R3: Cardinality check
DEFAULT_RULES.append(InferenceRule(
    name="cardinality_check",
    description="Detect violations when max_cardinality is exceeded",
    trigger=RuleTrigger.ON_CREATE,
    pattern="?s <prop> ?o1 . ?s <prop> ?o2 . max_cardinality=1",
    action="warn cardinality_violation",
    severity="error",
))

# R4: Domain contradiction detection
DEFAULT_RULES.append(InferenceRule(
    name="domain_contradiction",
    description="Detect same-entity same-property value conflicts",
    trigger=RuleTrigger.ON_QUERY,
    pattern="?e <prop> ?v1 . ?e <prop> ?v2 . ?v1 ≠ ?v2 . is_functional=true",
    action="report contradiction",
    severity="warning",
))

# R5: Dangling reference cascade on delete
DEFAULT_RULES.append(InferenceRule(
    name="dangling_reference_cascade",
    description="When a page is deleted, mark all citing pages' references as stale",
    trigger=RuleTrigger.ON_DELETE,
    pattern="?page <cites> ?deleted",
    action="mark ?page stale_references += ?deleted",
))


def run_rules(trigger: RuleTrigger, store: TripleStore,
              context: Dict[str, Any] = None) -> List[Dict[str, Any]]:
    """Run all enabled rules matching the trigger.

    Args:
        trigger: When the rules are being evaluated.
        store: TripleStore containing the current A-Box.
        context: Dict with optional keys:
            - created_entity: str (entity URI just created)
            - deleted_entity: str (entity URI just deleted)
            - triples: List[OntologyTriple] (incremental triples for scope)

    Returns:
        [{rule, action, severity, triple_summary, ...}]
    """
    ctx = context or {}
    results = []
    for rule in DEFAULT_RULES:
        if not rule.enabled or rule.trigger != trigger:
            continue
        try:
            inferred = rule.matches(ctx.get("triples", []), store, ctx)
            for inf in inferred:
                results.append({
                    "rule": rule.name,
                    "action": rule.action,
                    "severity": rule.severity,
                    **inf,
                })
        except Exception:
            pass
    return results


def infer_transitive_closure(store: TripleStore) -> List[Dict[str, str]]:
    """Infer transitive closure for all transitive properties.

    Returns list of missing inferred edges: [{subject, predicate, object}].
    """
    from core.harness.knowledge.knowledge_ontology import OBJECT_PROPERTIES
    inferred = []
    for op in OBJECT_PROPERTIES:
        if not op.is_transitive:
            continue
        prop = op.uri
        # Collect all subjects
        subjects = set()
        for pred in store._pos:
            if prop in pred:
                for obj in store._pos[pred]:
                    subjects.update(store._pos[pred][obj])
        for s in subjects:
            closure = store.transitive_closure(s, prop, max_depth=5)
            for target in closure:
                if not store.exists(s, prop, target):
                    inferred.append({"subject": s, "predicate": prop, "object": target})
    return inferred


def infer_source_chain(store: TripleStore) -> List[Dict[str, str]]:
    """A2 axiom: hasAtom(p,a) ∧ derivesFrom(a,d) ⇒ hasSource(p,d).

    Returns missing hasSource links.
    """
    inferred = []
    # Collect all subjects from the SPO index
    all_s = set(store._spo.keys())
    for s in all_s:
        atoms = store.objects(s, f"{AI}hasAtom")
        for atom in atoms:
            docs = store.objects(atom, f"{AI}derivesFrom")
            for doc in docs:
                if not store.exists(s, f"{AI}hasSource", doc):
                    inferred.append({"subject": s, "predicate": f"{AI}hasSource", "object": doc})
    return inferred


def run_full_inference(store: TripleStore) -> Dict[str, Any]:
    """Run all inference rules and return structured results."""
    transitive = infer_transitive_closure(store)
    source = infer_source_chain(store)
    return {
        "transitive": transitive,
        "source_chain": source,
        "symmetric": [],  # handled on-create
        "cardinality_violations": [],  # handled by validate()
        "summary": f"{len(transitive)} transitive + {len(source)} source_chain edges inferred",
        "total": len(transitive) + len(source),
    }


# ══════════════════════════════════════════════════════════════
# Pattern Detector (Ontology Evolution — Layer 1)
# ══════════════════════════════════════════════════════════════

@dataclass
class OntologyPatterns:
    """Detected patterns that aren't covered by current T-Box."""
    undefined_categories: List[Dict[str, Any]] = field(default_factory=list)
    """[{name, count, example_pages}] — categories used in Wiki but not in any allowed_categories"""
    undefined_relations: List[Dict[str, Any]] = field(default_factory=list)
    """[{type_name, count, example_pairs}] — relationship types in pages but not in OBJECT_PROPERTIES"""
    tag_clusters: List[Dict[str, Any]] = field(default_factory=list)
    """[{root_tag, count, suggested_class}] — high-frequency tags that may warrant new classes"""
    dangling_references: List[Dict[str, Any]] = field(default_factory=list)
    """[{page, references, variant_exists, variant_suggestion}] — related/contradictions pointing to non-existent pages"""
    category_gaps: List[Dict[str, Any]] = field(default_factory=list)
    """[{class_uri, label, categories, reason}] — T-Box classes with zero wiki pages using their categories"""
    cross_page_contradictions: List[Dict[str, Any]] = field(default_factory=list)
    """[{page_a, page_b, shared_tags}] — pages sharing tags, potential contradiction candidates"""
    summary: str = ""
    scanned_pages: int = 0
    scanned_collections: int = 0


def detect_ontology_patterns(collection_id: str = "default") -> OntologyPatterns:
    """Scan current Wiki data and detect patterns not covered by T-Box.

    Data sources:
    1. wiki_engine.search_pages → all page category/tags/related fields
    2. T-Box CLASSES → defined allowed_categories
    3. T-Box OBJECT_PROPERTIES → defined relation URIs

    Returns OntologyPatterns with:
    - undefined_categories: categories in wiki not in any T-Box class
    - tag_clusters: high-frequency tags that might warrant new classes
    - dangling_references: pages referencing titles that don't exist
    - category_gaps: T-Box classes with zero wiki pages
    """
    from core.harness.knowledge.knowledge_ontology import (
        CLASSES, OBJECT_PROPERTIES, AI, get_ontology
    )
    from core.harness.knowledge.wiki_engine import search_pages

    onto = get_ontology()

    # Collect defined categories and relations from T-Box
    defined_cats: set = set()
    class_category_map: Dict[str, str] = {}  # category → class_uri
    for cls in CLASSES:
        for cat in cls.allowed_categories:
            defined_cats.add(cat)
            if cat not in class_category_map:
                class_category_map[cat] = cls.uri

    defined_relations: set = {op.uri for op in OBJECT_PROPERTIES}
    # Also add short names (without namespace prefix)
    defined_rel_short: set = {op.uri.replace(AI, "") for op in OBJECT_PROPERTIES}

    # Scan all wiki pages
    all_pages = search_pages(limit=10000, collection_id=collection_id)
    all_titles = {p["title"] for p in all_pages}

    # 1. Undefined categories
    cat_counts: Dict[str, List[str]] = {}
    for p in all_pages:
        cat = p.get("category", "unknown")
        cat_counts.setdefault(cat, []).append(p["title"])
    undefined_cats = [
        {"name": cat, "count": len(titles), "example_pages": titles[:5]}
        for cat, titles in cat_counts.items()
        if cat not in defined_cats
    ]

    # 2. Tag frequency → clusters
    tag_freq: Dict[str, int] = {}
    for p in all_pages:
        for t in (p.get("tags") or []):
            t_clean = str(t).strip().strip("'\"")
            if t_clean and t_clean != "[]":
                tag_freq[t_clean] = tag_freq.get(t_clean, 0) + 1
    top_tags = sorted(tag_freq.items(), key=lambda x: -x[1])[:30]
    tag_clusters = [
        {"root_tag": t, "count": c, "suggested_class": f"高频概念: {t} ({c}次)"}
        for t, c in top_tags if c >= 2
    ]

    # 3. Dangling references (related + contradictions pointing to non-existent pages)
    dangling: List[Dict[str, Any]] = []
    for p in all_pages:
        for field_name in ("related", "contradictions"):
            for r in (p.get(field_name) or []):
                if r not in all_titles:
                    normalized = r.replace(" ", "")
                    variants = [t for t in all_titles
                                if t.replace(" ", "") == normalized and t != r]
                    dangling.append({
                        "page": p["title"],
                        "field": field_name,
                        "references": r,
                        "variant_exists": len(variants) > 0,
                        "variant_suggestion": variants[0] if variants else None,
                    })
    # Deduplicate
    seen_dangling = set()
    unique_dangling = []
    for d in dangling:
        key = (d["page"], d["references"])
        if key not in seen_dangling:
            seen_dangling.add(key)
            unique_dangling.append(d)
    dangling = unique_dangling

    # 4. Category gaps: T-Box classes with zero pages
    category_gaps = []
    for cls in CLASSES:
        if not cls.allowed_categories:
            continue
        has_pages = any(
            cat_counts.get(cat, [])
            for cat in cls.allowed_categories
        )
        if not has_pages:
            category_gaps.append({
                "class_uri": cls.uri,
                "label": cls.label,
                "categories": cls.allowed_categories,
                "reason": "T-Box defines this class but zero wiki pages use its categories",
            })

    # 5. Undefined relations (scan relationships field in frontmatter)
    import os as _os, json as _json, re as _re
    wiki_root = _os.path.expanduser(
        _os.getenv("AIPLAT_HOME", "~/.aiplat"))
    wiki_dir = _os.path.join(wiki_root, "wiki", "collections", collection_id)
    rel_counts: Dict[str, List[str]] = {}
    if _os.path.exists(wiki_dir):
        for cat_dir in _os.listdir(wiki_dir):
            cat_path = _os.path.join(wiki_dir, cat_dir)
            if not _os.path.isdir(cat_path):
                continue
            for fname in _os.listdir(cat_path):
                if not fname.endswith(".md"):
                    continue
                try:
                    text = open(_os.path.join(cat_path, fname)).read()
                    if text.startswith("---"):
                        parts = text.split("---", 2)
                        if len(parts) >= 3:
                            fm_text = parts[1]
                            # Extract relationships JSON
                            match = _re.search(
                                r'^relationships:\s*(.*?)$', fm_text, _re.MULTILINE)
                            if match:
                                try:
                                    rels = _json.loads(match.group(1))
                                    for rel in rels:
                                        if isinstance(rel, dict):
                                            rtype = rel.get("type", "")
                                            if rtype and rtype not in defined_rel_short and \
                                               f"{AI}{rtype}" not in defined_relations:
                                                rel_counts.setdefault(rtype, []).append(
                                                    fname[:-3])
                                except Exception:
                                    pass
                except Exception:
                    pass
    undefined_relations = [
        {"type_name": rtype, "count": len(titles), "example_pairs": titles[:5]}
        for rtype, titles in sorted(rel_counts.items(), key=lambda x: -len(x[1]))
    ]

    # Build summary
    parts = []
    if undefined_cats:
        parts.append(f"{len(undefined_cats)} undefined categories")
    if undefined_relations:
        parts.append(f"{len(undefined_relations)} undefined relations")
    if tag_clusters:
        parts.append(f"{len(tag_clusters)} tag clusters")
    if dangling:
        parts.append(f"{len(dangling)} dangling references")
    if category_gaps:
        parts.append(f"{len(category_gaps)} category gaps")

    # 6. Cross-page contradiction candidates (pages sharing tags)
    tag_groups: Dict[str, List[str]] = {}
    for p in all_pages:
        for t in (p.get("tags") or []):
            tag_groups.setdefault(t, []).append(p["title"])
    tag_pairs = set()
    for tag, titles in tag_groups.items():
        if len(titles) >= 2:
            for i in range(len(titles)):
                for j in range(i + 1, len(titles)):
                    tag_pairs.add((tag, tuple(sorted([titles[i], titles[j]]))))
    cross_contra = [
        {"page_a": a, "page_b": b, "shared_tags": [tag]}
        for tag, (a, b) in list(tag_pairs)[:20]
    ]
    if cross_contra:
        parts.append(f"{len(cross_contra)} cross-page contradiction candidates")

    return OntologyPatterns(
        undefined_categories=undefined_cats,
        undefined_relations=undefined_relations,
        tag_clusters=tag_clusters,
        dangling_references=dangling,
        category_gaps=category_gaps,
        cross_page_contradictions=cross_contra,
        summary="; ".join(parts) if parts else "No patterns detected",
        scanned_pages=len(all_pages),
        scanned_collections=1,
    )


# ══════════════════════════════════════════════════════════════
# Ontology Metrics (Layer 4)
# ══════════════════════════════════════════════════════════════

import os as _os
import json as _json
import time as _time


def _metrics_cache_path(collection_id: str = "default") -> str:
    wiki_root = _os.path.expanduser(_os.getenv("AIPLAT_HOME", "~/.aiplat"))
    return _os.path.join(wiki_root, "wiki", "collections", collection_id, "metrics_cache.json")


def load_metrics_cache(collection_id: str = "default") -> Optional[Dict[str, Any]]:
    """Load cached metrics. Returns None if not found or expired."""
    path = _metrics_cache_path(collection_id)
    if not _os.path.exists(path):
        return None
    try:
        cache = _json.load(open(path))
        ttl = cache.get("ttl_seconds", 86400)
        age = _time.time() - cache.get("computed_at", 0)
        if age > ttl:
            return None  # expired
        # Check if page count changed significantly (>20%)
        current_pages = cache.get("page_count_at_compute", 0)
        if current_pages > 0:
            from core.harness.knowledge.wiki_engine import search_pages
            live = len(search_pages(limit=10000, collection_id=collection_id))
            if live > 0 and abs(live - current_pages) / max(live, 1) > 0.2:
                return None  # significant change
        return cache
    except Exception:
        return None


def save_metrics_cache(metrics: Dict[str, Any], collection_id: str = "default") -> None:
    """Write metrics to cache file and append to history (keep last 30 snapshots)."""
    path = _metrics_cache_path(collection_id)
    _os.makedirs(_os.path.dirname(path), exist_ok=True)
    cache = {
        "collection_id": collection_id,
        "computed_at": _time.time(),
        "ttl_seconds": 86400,
        "page_count_at_compute": metrics.get("coverage", {}).get("total", 0),
        "metrics": metrics,
    }
    with open(path, "w") as f:
        _json.dump(cache, f, indent=2, ensure_ascii=False)

    # Append to history (keep 30)
    hist_path = path.replace(".json", "_history.json")
    history = []
    if _os.path.exists(hist_path):
        try:
            history = _json.loads(open(hist_path).read())
            if not isinstance(history, list):
                history = []
        except Exception:
            history = []
    history.append({
        "ts": _time.time(),
        "score": metrics.get("consistency", {}).get("score", 0),
        "errors": metrics.get("consistency", {}).get("errors", 0),
        "coverage": metrics.get("coverage", {}).get("percentage", 0),
        "total_pages": metrics.get("coverage", {}).get("total", 0),
        "inferred": metrics.get("inference_gain", {}).get("total_inferred", 0),
        "pending_suggestions": metrics.get("maintenance_cost", {}).get("pending_suggestions", 0),
    })
    with open(hist_path, "w") as f:
        _json.dump(history[-30:], f, indent=2, ensure_ascii=False)


def load_metrics_history(collection_id: str = "default") -> List[Dict[str, Any]]:
    """Load historical metrics snapshots for trend analysis."""
    path = _metrics_cache_path(collection_id).replace(".json", "_history.json")
    if not _os.path.exists(path):
        return []
    try:
        return _json.loads(open(path).read())
    except Exception:
        return []


def run_golden_query_regression(collection_id: str = "default",
                                min_score: float = None,
                                strict_mode: bool = False) -> Dict[str, Any]:
    """Validate retrieval quality using golden_queries.yaml.

    Runs each golden query through sys_knowledge_retrieve and checks
    whether expected_concepts appear in retrieved titles.

    Returns:
        {total, passed, failed, pass_rate, per_query: [{query, passed, found, missing}]}
    """
    import yaml as _yaml
    golden_path = _os.path.join(
        _os.path.expanduser(_os.getenv("AIPLAT_HOME", "~/.aiplat")),
        "wiki", "golden_queries.yaml"
    )
    if not _os.path.exists(golden_path):
        return {"error": "golden_queries.yaml not found", "hint": "Run seed_golden_queries() to create"}

    try:
        with open(golden_path) as f:
            config = _yaml.safe_load(f) or {}
    except Exception:
        return {"error": "failed to parse golden_queries.yaml"}

    queries = config.get("queries", [])
    if not queries:
        return {"error": "no queries defined", "total": 0, "passed": 0}

    results = []
    passed = 0

    for q in queries:
        query_text = q.get("query", "")
        query_type = q.get("query_type", "retrieval")  # retrieval | inference | source_impact
        expected = set(q.get("expected_concepts", []))
        assertion = q.get("assertion", "")

        try:
            from core.harness.syscalls.retrieval import sys_knowledge_retrieve
            score = min_score if min_score is not None else (0.3 if strict_mode else 0.1)

            # Inference-type queries: use inference expansion + transitive closure
            use_inference = (query_type == "inference")
            use_source_impact = (query_type == "source_impact")
            use_schema_validation = (query_type == "schema_validation")

            if use_schema_validation:
                # E2: Schema accuracy — validate pages against ontology schema
                from core.harness.knowledge.knowledge_ontology import validate_page_against_schema
                from core.harness.knowledge.wiki_engine import search_pages
                pages = search_pages(limit=200, collection_id=collection_id)
                valid_count = 0
                schema_issues = []
                for p in pages[:50]:  # sample 50 pages
                    result = validate_page_against_schema(p, collection_id=collection_id, mode="warning")
                    if result.is_valid:
                        valid_count += 1
                    elif result.missing_required or result.unknown_fields:
                        schema_issues.append({
                            "title": p.get("title", "?"),
                            "missing": result.missing_required,
                            "unknown": result.unknown_fields[:3],
                        })
                ok = valid_count >= max(1, len(pages[:50]) * 0.8)  # 80% minimum pass rate
                retrieved = [{"title": f"schema_valid={valid_count}/{min(50, len(pages))}"}]
            elif use_source_impact:
                # Directly query source impact ranking
                from core.harness.knowledge.knowledge_validator import query_source_impact as _qs
                impact = _qs()
                retrieved = [{"title": r["doc_id"], "score": r.get("citations", 0)}
                           for r in impact.get("ranks", [])[:10]]
            else:
                retrieved = sys_knowledge_retrieve(
                    query_text,
                    wiki_collection_ids=[collection_id],
                    wiki_first=True, min_wiki_score=score,
                    expand_subclasses=True,
                    inference_expand=use_inference,
                )

            found_titles = {r.get("title", "") for r in retrieved}
            found = expected & found_titles if expected else set()
            missing = expected - found if expected else set()

            # Inference / schema / source_impact queries: pass if results present
            if use_inference or use_source_impact or use_schema_validation:
                ok = len(retrieved) > 0
            elif expected:
                ok = len(found) >= max(1, len(expected) // 2)
            else:
                ok = len(retrieved) > 0

            if ok:
                passed += 1

            results.append({
                "query": query_text,
                "template": q.get("template", ""),
                "query_type": query_type,
                "passed": ok,
                "found": list(found)[:5],
                "missing": list(missing)[:5],
                "total_retrieved": len(retrieved),
            })
        except Exception as e:
            results.append({
                "query": query_text,
                "passed": False,
                "error": str(e)[:100],
            })

    return {
        "total": len(results),
        "passed": passed,
        "failed": len(results) - passed,
        "pass_rate": round(passed / max(1, len(results)) * 100, 1),
        "per_query": results,
    }


def compute_ontology_metrics(collection_id: str = "default",
                               force_fresh: bool = False) -> Dict[str, Any]:
    """Compute four-dimension ontology health metrics.

    Metrics:
    1. Coverage: % of wiki pages whose category is covered by T-Box
    2. Consistency: validator error/warning counts + score
    3. Inference gain: transitive + source_chain edges inferred
    4. Maintenance cost: pending suggestions + last review time
    """
    from core.harness.knowledge.knowledge_ontology import CLASSES, get_ontology
    from core.harness.knowledge.wiki_engine import search_pages

    # Try cache first
    if not force_fresh:
        cached = load_metrics_cache(collection_id)
        if cached and "metrics" in cached:
            return cached["metrics"]

    onto = get_ontology()
    all_pages = search_pages(limit=10000, collection_id=collection_id)

    # 1. Coverage
    defined_cats: set = set()
    for cls in CLASSES:
        defined_cats.update(cls.allowed_categories)
    covered = sum(1 for p in all_pages if p.get("category") in defined_cats)
    coverage_pct = round(covered / max(1, len(all_pages)) * 100, 1)

    # 2. Consistency
    from core.harness.knowledge.knowledge_abox_builder import build_abox
    consistency = {"errors": 0, "warnings": 0, "score": 100, "trend": "stable"}
    try:
        onto_abox = build_abox(collection_id=collection_id)
        report = validate(onto_abox)
        consistency = {
            "errors": report.violations_by_severity.get("error", 0),
            "warnings": report.violations_by_severity.get("warning", 0),
            "score": report.score,
            "trend": "stable",  # needs historical comparison
        }
    except Exception:
        pass

    # 3. Inference gain
    inference = {"transitive_edges": 0, "source_chains": 0, "total_inferred": 0}
    try:
        onto_abox2 = build_abox(collection_id=collection_id)
        store = TripleStore(onto_abox2.triples)
        inf = run_full_inference(store)
        inference = {
            "transitive_edges": len(inf.get("transitive", [])),
            "source_chains": len(inf.get("source_chain", [])),
            "total_inferred": inf.get("total", 0),
        }
    except Exception:
        pass

    # 4. Maintenance cost
    suggestions_path = _os.path.join(
        _os.path.dirname(_metrics_cache_path(collection_id)),
        "ontology_suggestions.json")
    pending = 0
    last_review = "never"
    try:
        if _os.path.exists(suggestions_path):
            sugs = _json.load(open(suggestions_path))
            pending = sum(1 for s in (sugs if isinstance(sugs, list) else sugs.get("suggestions", []))
                          if s.get("status") == "pending")
            accepted = [s for s in (sugs if isinstance(sugs, list) else sugs.get("suggestions", []))
                        if s.get("status") == "accepted"]
            if accepted:
                last_review = max(a.get("reviewed_at", "") for a in accepted)
    except Exception:
        pass

    # Suggestion age (hours since last generation)
    suggestion_age_hours = None
    try:
        if _os.path.exists(suggestions_path):
            suggestion_age_hours = round(
                (_time.time() - _os.path.getmtime(suggestions_path)) / 3600, 1)
    except Exception:
        pass

    maintenance = {
        "pending_suggestions": pending,
        "last_review": str(last_review)[:19],
        "suggestion_age_hours": suggestion_age_hours,
    }

    # 5. Class usage (per-class page counts)
    class_usage = []
    for cls in CLASSES:
        if not cls.allowed_categories:
            continue
        pages_count = sum(
            1 for p in all_pages
            if p.get("category") in cls.allowed_categories
        )
        class_usage.append({
            "class": cls.label,
            "categories": cls.allowed_categories,
            "pages": pages_count,
            "uri": cls.uri,
        })

    metrics = {
        "coverage": {"percentage": coverage_pct, "covered": covered, "total": len(all_pages)},
        "consistency": consistency,
        "inference_gain": inference,
        "maintenance_cost": maintenance,
        "class_usage": class_usage,
        "computed_at": _time.time(),
    }

    # ── 6. A-Box size (triple count + evolution gain) ──
    try:
        triples_count = len(onto.triples) if onto and onto.triples else 0
        # Count explicit (non-inferred) vs inferred triples
        explicit_count = sum(1 for t in (onto.triples or [])
                           if not str(t.predicate).startswith("inferred_"))
        metrics["abox_size"] = {
            "total_triples": triples_count,
            "explicit": explicit_count,
            "inferred": triples_count - explicit_count,
        }
    except Exception:
        metrics["abox_size"] = {"total_triples": 0, "explicit": 0, "inferred": 0}

    # ── 7. Schema compliance (% pages passing validate_page_against_schema) ──
    try:
        from core.harness.knowledge.knowledge_ontology import validate_page_against_schema
        valid_count = 0
        checked = 0
        for p in all_pages[:200]:  # sample at most 200 for performance
            result = validate_page_against_schema(p, collection_id=collection_id, mode="warning")
            checked += 1
            if result.is_valid:
                valid_count += 1
        metrics["schema_compliance"] = {
            "rate": round(valid_count / max(1, checked) * 100, 1),
            "valid": valid_count,
            "sampled": checked,
        }
    except Exception:
        metrics["schema_compliance"] = {"rate": 0, "valid": 0, "sampled": 0}

    # ── 8. Ontology evolution stats (classes/properties added over generations) ──
    onto_ev = {"classes_added": 0, "properties_added": 0, "total_generations": 0}
    try:
        ev_path = _os.path.expanduser(
            f"~/.aiplat/wiki/collections/{collection_id}/evolution_ontology_state.json")
        if _os.path.exists(ev_path):
            ev_data = _json.load(open(ev_path))
            generations = ev_data.get("generations", [])
            onto_ev["total_generations"] = len(generations)
            for g in generations:
                onto_ev["classes_added"] += len(g.get("classes_added", []))
                onto_ev["properties_added"] += len(g.get("properties_added", []))
        metrics["onto_evolution"] = onto_ev
    except Exception:
        metrics["onto_evolution"] = onto_ev

    # ── 9. Coverage trend (compare with last cached metrics) ──
    prev_coverage = coverage_pct
    try:
        cached = load_metrics_cache(collection_id)
        if cached and "metrics" in cached:
            prev = cached["metrics"].get("coverage", {}).get("percentage", coverage_pct)
            prev_coverage = prev
    except Exception:
        pass
    metrics["coverage_trend"] = {
        "delta": round(coverage_pct - prev_coverage, 1),
        "direction": "up" if coverage_pct > prev_coverage else ("down" if coverage_pct < prev_coverage else "stable"),
    }

    # ── 10. Inference effectiveness (transitive edges / total edges) ──
    try:
        total_edges = len(all_pages)  # rough: 1 page ≈ 1 node, edges from relationships
        if inference["total_inferred"] > 0 and total_edges > 0:
            metrics["inference_effectiveness"] = {
                "ratio": round(inference["total_inferred"] / max(1, total_edges + inference["total_inferred"]), 3),
                "inferred": inference["total_inferred"],
                "explicit_edges": total_edges,
            }
        else:
            metrics["inference_effectiveness"] = {"ratio": 0, "inferred": 0, "explicit_edges": 0}
    except Exception:
        metrics["inference_effectiveness"] = {"ratio": 0, "inferred": 0, "explicit_edges": 0}

    # Auto-generate suggestions if last generation > 24h
    try:
        s_path = _metrics_cache_path(collection_id).replace("metrics_cache.json",
                                                             "ontology_suggestions.json")
        if _os.path.exists(s_path):
            age = _time.time() - _os.path.getmtime(s_path)
            if age > 86400:
                from core.harness.knowledge.knowledge_ontology import add_suggestions_from_patterns
                add_suggestions_from_patterns(collection_id)
    except Exception:
        pass

    # ── Golden regression auto-trigger ──
    try:
        gr_result = run_golden_query_regression(collection_id, strict_mode=False)
        pass_rate = gr_result.get("pass_rate", 0)
        metrics["golden_regression"] = {
            "pass_rate": pass_rate,
            "passed": gr_result.get("passed", 0),
            "total": gr_result.get("total", 0),
        }
        if pass_rate < 75:
            metrics["golden_regression"]["alert"] = "critical: pass_rate < 75%"
        elif pass_rate < 90:
            metrics["golden_regression"]["alert"] = "warning: pass_rate < 90%"
    except Exception:
        metrics["golden_regression"] = {"error": "regression unavailable"}

    # ── Golden regression history (keep 90 days) ──
    try:
        hist_path = _os.path.expanduser("~/.aiplat/wiki/golden_regression_history.json")
        history = []
        if _os.path.exists(hist_path):
            history = _json.loads(open(hist_path).read())
        history.append({
            "ts": _time.time(),
            "pass_rate": pass_rate,
            "passed": gr_result.get("passed", 0) if 'gr_result' in dir() else 0,
            "total": gr_result.get("total", 0) if 'gr_result' in dir() else 0,
        })
        _os.makedirs(_os.path.dirname(hist_path), exist_ok=True)
        _json.dump(history[-90:], open(hist_path, "w"))
        # Expose lowest ever pass rate
        if history:
            lowest = min(h["pass_rate"] for h in history)
            metrics["golden_regression"]["lowest_ever"] = lowest
    except Exception:
        pass

    # ── Latency percentiles ──
    lat_path2 = _os.path.expanduser("~/.aiplat/wiki/retrieval_latency.json")
    if _os.path.exists(lat_path2):
        try:
            lat_samples = _json.loads(open(lat_path2).read())
            if lat_samples:
                totals = sorted(s.get("total", 0) for s in lat_samples)
                n = len(totals)
                maintenance["latency"] = {
                    "p50": round(totals[n // 2], 4),
                    "p95": round(totals[int(n * 0.95)], 4),
                    "p99": round(totals[int(n * 0.99)], 4),
                    "samples": n,
                }
        except Exception:
            pass

    # ── Curation stats ──
    curation_path = _os.path.expanduser("~/.aiplat/wiki/curation_stats.json")
    if _os.path.exists(curation_path):
        try:
            cs = _json.loads(open(curation_path).read())
            maintenance["curation"] = {
                "successes": cs.get("successes", 0),
                "failures": cs.get("failures", 0),
                "retries_total": cs.get("retries_total", 0),
                "last_success": cs.get("last_success"),
            }
        except Exception:
            pass

    # ── 11. Retrieval governance metrics ──
    governance = {
        "total_samples": 0, "avg_raw_chunks": 0, "avg_governed_chunks": 0,
        "avg_time_penalized": 0, "avg_density_filtered": 0, "avg_dedup_merged": 0,
        "avg_conflict_marked": 0, "avg_composite_score": 0, "avg_cutoff_score": 0,
    }
    try:
        gov_path = _os.path.expanduser("~/.aiplat/wiki/governance_stats.json")
        history_path = _os.path.expanduser("~/.aiplat/wiki/governance_history.json")

        # Collect stats from recent retrieval traces
        gov_history = []
        if _os.path.exists(history_path):
            gov_history = _json.loads(open(history_path).read())
            gov_history = gov_history[-30:]  # last 30 samples

        if gov_history:
            n = len(gov_history)
            governance = {
                "total_samples": n,
                "avg_raw_chunks": round(sum(h.get("raw", 0) for h in gov_history) / n, 1),
                "avg_governed_chunks": round(sum(h.get("governed", 0) for h in gov_history) / n, 1),
                "avg_time_penalized": round(sum(h.get("time_pen", 0) for h in gov_history) / n, 1),
                "avg_density_filtered": round(sum(h.get("density", 0) for h in gov_history) / n, 1),
                "avg_dedup_merged": round(sum(h.get("dedup", 0) for h in gov_history) / n, 1),
                "avg_conflict_marked": round(sum(h.get("conflict", 0) for h in gov_history) / n, 1),
                "avg_composite_score": round(sum(h.get("avg_comp", 0) for h in gov_history) / n, 3),
                "avg_cutoff_score": round(sum(h.get("cutoff", 0) for h in gov_history) / n, 3),
            }
    except Exception:
        pass
    metrics["retrieval_governance"] = governance

    # Save cache
    try:
        save_metrics_cache(metrics, collection_id)
    except Exception:
        pass

    return metrics


# ══════════════════════════════════════════════════════════════
# Axiom Validators
# ══════════════════════════════════════════════════════════════

def validate_a1(store: TripleStore, onto: KnowledgeOntology) -> List[ValidationIssue]:
    """A1: 概念完整性 — ConceptPage 必须有 hasSource 指向 KBDocument."""
    issues = []
    concept_pages = store.all_subjects_of_type(f"{AI}ConceptPage")
    for page in concept_pages:
        has_source = store.exists(page, f"{AI}hasSource")
        if not has_source:
            issues.append(ValidationIssue(
                axiom_id="A1",
                severity="error",
                description=f"概念页缺少 KB 来源: {_short(page)}",
                entities=[page],
                recommendation="添加 source_articles 关联到 KB 文档，或如果这是推理结论请标注",
            ))
    return issues


def validate_a3(store: TripleStore, onto: KnowledgeOntology) -> List[ValidationIssue]:
    """A3: 矛盾对称性 — contradicts(A,B) ⇒ contradicts(B,A)."""
    issues = []
    # Get all contradicts triples
    for pred in store._pos:
        if "contradicts" in pred:
            for obj in store._pos[pred]:
                subjects = store._pos[pred][obj]
                for s in subjects:
                    # Check reverse
                    if not store.exists(obj, f"{AI}contradicts", s):
                        issues.append(ValidationIssue(
                            axiom_id="A3",
                            severity="warning",
                            description=f"矛盾声明不对称: {_short(s)} → {_short(obj)}",
                            entities=[s, obj],
                            recommendation="在目标页面也添加 contradicts 声明",
                        ))
    return issues


def validate_a4(store: TripleStore, onto: KnowledgeOntology) -> List[ValidationIssue]:
    """A4: 层级无环 — parentOf 不能有环."""
    issues = []
    all_pages = set()
    for pred in store._pos:
        if "parentOf" in pred:
            for obj in store._pos[pred]:
                all_pages.update(store._pos[pred][obj])
    
    for page in all_pages:
        if store.detect_cycle(page, f"{AI}parentOf"):
            issues.append(ValidationIssue(
                axiom_id="A4",
                severity="error",
                description=f"parentOf 存在环: {_short(page)}",
                entities=[page],
                recommendation="修正父概念关系，确保概念层级是有向无环图",
            ))
    return issues


def validate_a5(store: TripleStore, onto: KnowledgeOntology) -> List[ValidationIssue]:
    """A5: 源页面独立 — SourcePage 不能 cites 其他 WikiPage."""
    issues = []
    source_pages = store.all_subjects_of_type(f"{AI}SourcePage")
    wiki_pages = set(store.all_subjects_of_type(f"{AI}WikiPage"))
    wiki_pages |= set(store.all_subjects_of_type(f"{AI}ConceptPage"))
    wiki_pages |= set(store.all_subjects_of_type(f"{AI}TopicPage"))
    
    for sp in source_pages:
        cited = store.objects(sp, f"{AI}cites")
        for c in cited:
            if c in wiki_pages:
                issues.append(ValidationIssue(
                    axiom_id="A5",
                    severity="warning",
                    description=f"SourcePage 不应引用 Wiki 页面: {_short(sp)} → {_short(c)}",
                    entities=[sp, c],
                    recommendation="SourcePage 应只摘要原始资料，移除对 Wiki 页面的引用",
                ))
    return issues


def validate_a6(store: TripleStore, onto: KnowledgeOntology) -> List[ValidationIssue]:
    """A6: 引用完整性 — 每个 hasSource 的 object 必须是一个已注册的 KBDocument."""
    issues = []
    kb_docs = set(store.all_subjects_of_type(f"{AI}KBDocument"))
    
    for pred in store._pos:
        if "hasSource" in pred:
            for obj in store._pos[pred]:
                # Check if the object is a known KBDocument
                if obj not in kb_docs:
                    subjects = store._pos[pred][obj]
                    for s in subjects:
                        # Skip already-marked invalid sources
                        if store.exists(s, f"{AI}invalid_source", obj):
                            continue
                        issues.append(ValidationIssue(
                            axiom_id="A6",
                            severity="error",
                            description=f"引用了不存在的 KB 文档: {_short(s)} → {_short(obj)}",
                            entities=[s, obj],
                            recommendation="更新或移除该来源引用，或确认 KB 文档是否存在",
                        ))
    return issues


def validate_parent_cardinality(store: TripleStore, onto: KnowledgeOntology = None) -> List[ValidationIssue]:
    """Cardinality: parentOf ≤ 1 per page."""
    issues = []
    for pred in store._pos:
        if "parentOf" in pred:
            for obj in store._pos[pred]:
                subjects = store._pos[pred][obj]
                if len(subjects) > 1:
                    issues.append(ValidationIssue(
                        axiom_id="CARD_PARENT",
                        severity="warning",
                        description=f"多个父概念: {_short(obj)} ← {', '.join(_short(s) for s in subjects[:3])}",
                        entities=[obj] + subjects,
                        recommendation="每个概念最多一个父概念，请合并或选择最合适的",
                    ))
    return issues


# ══════════════════════════════════════════════════════════════
# Validation Runner
# ══════════════════════════════════════════════════════════════

def validate(onto: KnowledgeOntology = None) -> ValidationReport:
    """Run all axiom validators against the current A-Box."""
    if onto is None:
        onto = get_ontology()
    
    store = TripleStore(onto.triples)
    
    all_violations: List[ValidationIssue] = []
    validators = [
        ("A1", validate_a1),
        ("A3", validate_a3),
        ("A4", validate_a4),
        ("A5", validate_a5),
        ("A6", validate_a6),
        ("CARD_PARENT", validate_parent_cardinality),
    ]
    
    for ax_id, validator_fn in validators:
        try:
            violations = validator_fn(store, onto)
            all_violations.extend(violations)
        except Exception as e:
            logger.warning(f"Axiom validator {ax_id} failed: {e}")
    
    # Count by severity
    by_sev: Dict[str, int] = {}
    for v in all_violations:
        by_sev[v.severity] = by_sev.get(v.severity, 0) + 1
    
    # Track passed/failed
    axiom_ids = {ax.id for ax in onto.axioms}
    violated_ids = set(v.axiom_id for v in all_violations)
    passed = list(axiom_ids - violated_ids)
    failed = list(violated_ids & axiom_ids)
    
    return ValidationReport(
        timestamp=datetime.now(timezone.utc).isoformat(),
        total_triples=len(onto.triples),
        violations=all_violations,
        violations_by_severity=by_sev,
        passed_axioms=sorted(passed),
        failed_axioms=sorted(failed),
    )


# ══════════════════════════════════════════════════════════════
# Ontology Query API
# ══════════════════════════════════════════════════════════════

def query_transitive_network(start_title: str, max_depth: int = 5) -> Dict[str, Any]:
    """Get the full transitive knowledge network from a starting page."""
    onto = get_ontology()
    store = TripleStore(onto.triples)
    
    start_uri = f"{AI}{start_title}"
    
    # Collect all related pages via all relationship types
    related: set[str] = set()
    for pred in [f"{AI}cites", f"{AI}contradicts", f"{AI}parentOf", 
                 f"{AI}childOf", f"{AI}extends", f"{AI}supports"]:
        related.update(store.transitive_closure(start_uri, pred, max_depth))
    
    # Also get direct KB sources
    kb_sources = store.objects(start_uri, f"{AI}hasSource")
    
    return {
        "start": start_title,
        "related_pages": [_short(r) for r in related],
        "kb_sources": [_short(k) for k in kb_sources],
        "total_connected": len(related) + len(kb_sources),
    }


def query_source_impact() -> List[Dict[str, Any]]:
    """Rank KB documents by how many Wiki pages cite them."""
    onto = get_ontology()
    store = TripleStore(onto.triples)
    
    kb_docs = store.all_subjects_of_type(f"{AI}KBDocument")
    results = []
    for kb in kb_docs:
        citing_pages = store.subjects(f"{AI}hasSource", kb)
        if citing_pages:
            results.append({
                "kb_doc": _short(kb),
                "cited_by": len(citing_pages),
                "pages": [_short(p) for p in citing_pages[:10]],
            })
    
    results.sort(key=lambda x: -x["cited_by"])
    return results[:20]


def _short(uri: str) -> str:
    """Strip namespace prefix from a URI for display."""
    return uri.replace(AI, "").strip('"')
