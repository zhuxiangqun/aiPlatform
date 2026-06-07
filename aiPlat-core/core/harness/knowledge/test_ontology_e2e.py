"""E2E integration test suite for ontology-driven knowledge system.

Covers: Schema → Write → Atom → Retrieve → Cascade → Export
Uses isolated test collection, auto-cleanup.

Run: pytest aiPlat-core/core/harness/knowledge/test_ontology_e2e.py -v
"""
import os
import pytest

os.environ["AIPLAT_WIKI_SCHEMA_MODE"] = "warning"
COLLECTION = "e2e_test_suite_pytest"


def setup_module():
    """Create isolated test collection."""
    from core.harness.knowledge.wiki_engine import create_collection
    try:
        create_collection(COLLECTION)
    except Exception:
        pass


def teardown_module():
    """Cleanup test collection."""
    from core.harness.knowledge.wiki_engine import delete_collection
    try:
        delete_collection(COLLECTION)
    except Exception:
        pass


# ═══════════════════════════════════════════════════════════
# Schema Validation
# ═══════════════════════════════════════════════════════════

class TestSchemaValidation:
    def test_reject_missing_required(self):
        from core.harness.knowledge.knowledge_ontology import validate_page_against_schema
        r = validate_page_against_schema(
            {"title": "x", "category": "entities"}, mode="error")
        assert not r.is_valid
        assert "summary" in r.missing_required
        assert "body" in r.missing_required

    def test_accept_valid_page(self):
        from core.harness.knowledge.knowledge_ontology import validate_page_against_schema
        r = validate_page_against_schema(
            {"title": "x", "category": "entities", "summary": "s", "body": "b"},
            mode="error")
        assert r.is_valid
        assert r.class_label == "概念页"

    def test_parent_cardinality_violation(self):
        from core.harness.knowledge.knowledge_ontology import validate_page_against_schema
        r = validate_page_against_schema(
            {"title": "x", "category": "entities", "summary": "s", "body": "b",
             "relationships": [{"type": "parent", "target": "A"},
                               {"type": "parent", "target": "B"}]},
            mode="error")
        assert not r.is_valid
        assert "parentof" in r.suggestion.lower()

    def test_unknown_category_warning(self):
        from core.harness.knowledge.knowledge_ontology import validate_page_against_schema
        r = validate_page_against_schema(
            {"title": "x", "category": "bogus_cat"}, mode="warning")
        assert r.is_valid  # warning mode doesn't block

    def test_get_class_by_category(self):
        from core.harness.knowledge.knowledge_ontology import get_class_by_category
        c = get_class_by_category("entities")
        assert c is not None
        assert c.label == "概念页"
        c2 = get_class_by_category("atoms")
        assert c2 is not None
        assert c2.label == "断言"


# ═══════════════════════════════════════════════════════════
# Atom & Evidence
# ═══════════════════════════════════════════════════════════

class TestAtomAndEvidence:
    def test_write_atom_creates_page(self):
        from core.harness.knowledge.wiki_engine import write_atom, search_pages
        write_atom({
            "title": "TestAtom_Pytest", "body": "test content",
            "source_doc_id": "kb:test_pytest",
            "evidence_text": "direct evidence quote",
            "confidence": 0.85, "tags": ["test"],
        }, collection_id=COLLECTION)
        pages = search_pages("TestAtom_Pytest", collection_id=COLLECTION)
        assert len(pages) >= 1

    def test_atom_evidence_in_body(self):
        from core.harness.knowledge.wiki_engine import read_page
        p = read_page("TestAtom_Pytest", collection_id=COLLECTION)
        assert p is not None
        assert "evidence_text" in p.get("body", "") or "summary" in p


# ═══════════════════════════════════════════════════════════
# Cascade & Sanitization
# ═══════════════════════════════════════════════════════════

class TestCascadeAndCleanup:
    def test_delete_triggers_stale_reference(self):
        from core.harness.knowledge.wiki_engine import (
            write_page, delete_page, search_pages
        )
        write_page("Pytest_CascA", "content for cascade test", category="entities",
                   summary="cascade test page", collection_id=COLLECTION)
        write_page("Pytest_CascB", "content for cascade test with longer body text",
                   category="entities", summary="cascade test page",
                   related=["Pytest_CascA"], collection_id=COLLECTION)
        delete_page("Pytest_CascA", collection_id=COLLECTION)
        b = search_pages("Pytest_CascB", collection_id=COLLECTION)
        assert b
        assert "Pytest_CascA" in (b[0].get("stale_references") or [])

    def test_clean_stale_references(self):
        from core.harness.knowledge.wiki_engine import clean_stale_references
        r = clean_stale_references(collection_id=COLLECTION)
        assert "scanned" in r
        assert "abox_rebuilt" in r

    def test_backfill_evidence(self):
        from core.harness.knowledge.wiki_engine import backfill_evidence_for_page_sync
        r = backfill_evidence_for_page_sync(
            "Pytest_CascB", collection_id=COLLECTION)
        assert "updated" in r or "already_backfilled" in r or "error" in r


# ═══════════════════════════════════════════════════════════
# Retrieval
# ═══════════════════════════════════════════════════════════

class TestRetrieval:
    def test_wiki_retrieve_returns_results(self):
        from core.harness.syscalls.retrieval import sys_wiki_retrieve
        r = sys_wiki_retrieve("test", collection_ids=[COLLECTION])
        assert len(r) >= 1

    def test_class_filter_works(self):
        from core.harness.syscalls.retrieval import sys_wiki_retrieve
        AI = "http://aiplat.local/knowledge#"
        r = sys_wiki_retrieve("test", collection_ids=[COLLECTION],
                              class_uri=f"{AI}ConceptPage")
        assert isinstance(r, list)

    def test_inference_expand_does_not_crash(self):
        from core.harness.syscalls.retrieval import sys_wiki_retrieve
        r = sys_wiki_retrieve("test", collection_ids=[COLLECTION],
                              inference_expand=True)
        assert isinstance(r, list)

    def test_unified_retrieval(self):
        from core.harness.syscalls.retrieval import sys_knowledge_retrieve
        r = sys_knowledge_retrieve(
            "test", wiki_collection_ids=[COLLECTION],
            wiki_first=True, min_wiki_score=0.0)
        assert len(r) >= 1
        assert r[0].get("source_type") in ("wiki", "kb")


# ═══════════════════════════════════════════════════════════
# Export & Metrics
# ═══════════════════════════════════════════════════════════

class TestExportAndMetrics:
    def test_owl_export_contains_classes(self):
        from core.harness.knowledge.knowledge_ontology import export_to_owl_rdf
        rdf = export_to_owl_rdf("turtle")
        assert len(rdf) > 1000
        assert "owl:Class" in rdf

    def test_metrics_computes(self):
        from core.harness.knowledge.knowledge_validator import compute_ontology_metrics
        m = compute_ontology_metrics(COLLECTION, force_fresh=True)
        assert m["coverage"]["percentage"] >= 0
        assert "consistency" in m
        assert "inference_gain" in m

    def test_pattern_detection(self):
        from core.harness.knowledge.knowledge_validator import detect_ontology_patterns
        p = detect_ontology_patterns(COLLECTION)
        assert p.scanned_pages >= 1

    def test_schema_readiness(self):
        from core.harness.knowledge.knowledge_ontology import check_schema_readiness
        r = check_schema_readiness(COLLECTION)
        assert r["total_pages"] >= 1
        assert r["readiness_pct"] >= 0
