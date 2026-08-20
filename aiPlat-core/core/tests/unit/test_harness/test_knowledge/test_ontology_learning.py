"""Ontology learning output — suggestions → OWL/Turtle (P-补全).

Covers:
  - export_suggestions_to_owl serializes pending new_class/new_property into
    loadable OWL/Turtle (owl:Ontology + owl:Class + rdfs:subClassOf)
  - _infer_parent_from_label derives subclassOf from existing classes
  - write_suggestions_owl_file persists to ~/.aiplat/ontologies/{id}.learned.ttl
"""
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[5]))


def _seed_suggestions(ko, collection_id="default"):
    ko.save_suggestions([
        {"id": "sug_1", "type": "new_class", "status": "pending",
         "description": "高频概念: 用户认证 (8次)"},
        {"id": "sug_2", "type": "new_property", "status": "pending",
         "description": "关联设备"},
    ], collection_id)


class TestSuggestionsToOwl:
    def test_export_serializes_classes_and_properties(self, tmp_path, monkeypatch):
        import core.harness.knowledge.knowledge_ontology as ko

        monkeypatch.setenv("AIPLAT_HOME", str(tmp_path))
        _seed_suggestions(ko)
        ttl = ko.export_suggestions_to_owl("default")
        assert "owl:Ontology" in ttl
        assert "owl:Class" in ttl
        assert "rdfs:subClassOf" in ttl
        assert "用户认证" in ttl
        assert "owl:ObjectProperty" in ttl
        assert "关联设备" in ttl

    def test_write_persists_file(self, tmp_path, monkeypatch):
        import core.harness.knowledge.knowledge_ontology as ko

        monkeypatch.setenv("AIPLAT_HOME", str(tmp_path))
        _seed_suggestions(ko)
        path = ko.write_suggestions_owl_file("default")
        assert path is not None
        assert path.endswith("ontologies/default.learned.ttl")
        assert os.path.exists(path)
        content = open(path, encoding="utf-8").read()
        assert "owl:Class" in content and "subClassOf" in content

    def test_no_suggestions_returns_none(self, tmp_path, monkeypatch):
        import core.harness.knowledge.knowledge_ontology as ko

        monkeypatch.setenv("AIPLAT_HOME", str(tmp_path))
        assert ko.write_suggestions_owl_file("empty") is None


class TestParentInference:
    def test_exact_label_match(self):
        import core.harness.knowledge.knowledge_ontology as ko

        uri = ko._infer_parent_from_label("知识原子", ko.CLASSES)
        # "知识原子" is a real class in CLASSES → its own URI (or its parent chain)
        assert uri.startswith("http://aiplat.local/knowledge#")

    def test_unmatched_falls_back_to_concept_page(self):
        import core.harness.knowledge.knowledge_ontology as ko

        uri = ko._infer_parent_from_label("完全不存在的概念XYZ", ko.CLASSES)
        assert uri.endswith("ConceptPage")
