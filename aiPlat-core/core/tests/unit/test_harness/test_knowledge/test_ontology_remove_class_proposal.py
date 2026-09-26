"""Proposal change dict supports hard-remove of dirty classes."""

from __future__ import annotations

from core.harness.knowledge.versioned_ontology_store import project_ontology_changes


def test_project_ontology_changes_remove_class():
    current = {
        "classes": {
            "InstallOrder": {"label": "安装工单", "tier": "logic"},
            "安装工单": {"label": "智能锁安装服务", "tier": "edge"},
        },
        "object_properties": [],
    }
    out = project_ontology_changes(current, {"remove": ["安装工单"]})
    assert "InstallOrder" in out["classes"]
    assert "安装工单" not in out["classes"]
