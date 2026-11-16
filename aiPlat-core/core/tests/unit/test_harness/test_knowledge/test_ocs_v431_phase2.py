"""W10 OCS v4.3.1：覆盖计分 + 门槛门；禁止节点数替代。"""
from __future__ import annotations

import yaml

from core.harness.knowledge import ontology_completeness as ocs
from core.harness.ontology_engine.graph_index import GraphIndex


def test_weights_sum_100():
    assert sum(ocs.WEIGHTS.values()) == 100


def test_c5_coverage_not_node_count_tiers(tmp_path, monkeypatch):
    """单实例覆盖全部 logic 类应高分；多样本单类不能靠节点数刷满。"""
    home = tmp_path / "home"
    onto = home / "ontologies"
    onto.mkdir(parents=True)
    (onto / "demo.yaml").write_text(
        yaml.dump(
            {
                "name": "demo",
                "namespace": "http://example/demo/",
                "ocs_threshold": 80,
                "classes": {
                    "Alpha": {
                        "label": "Alpha",
                        "tier": "logic",
                        "required_fields": ["id"],
                    },
                    "Beta": {
                        "label": "Beta",
                        "tier": "logic",
                        "required_fields": ["id"],
                    },
                    "EdgeStub": {
                        "label": "EdgeStub",
                        "tier": "edge",
                        "required_fields": ["id"],
                    },
                },
                "object_properties": [],
            },
            allow_unicode=True,
        ),
        encoding="utf-8",
    )
    monkeypatch.setenv("AIPLAT_HOME", str(home))
    GraphIndex._loaded_instances.clear()

    # 仅覆盖 Alpha：C5 应为 50（1/2 logic），与节点数无关
    g = GraphIndex("demo")
    for i in range(30):
        g.add_entity(f"A-{i}", f"a{i}", "Alpha", source_doc_id="t")
    g.save()
    GraphIndex._loaded_instances.clear()
    r1 = ocs.compute_domain_ocs("demo", credit_test_evidence=False)
    assert r1["dimensions"]["C5"] == 50.0
    assert r1["node_count_substitute"] is False

    # 再覆盖 Beta → C5=100
    GraphIndex._loaded_instances.clear()
    g2 = GraphIndex.load("demo")
    g2.add_entity("B-1", "b1", "Beta", source_doc_id="t")
    g2.save()
    GraphIndex._loaded_instances.clear()
    r2 = ocs.compute_domain_ocs("demo", credit_test_evidence=False)
    assert r2["dimensions"]["C5"] == 100.0


def test_evaluate_ocs_gate_threshold(tmp_path, monkeypatch):
    home = tmp_path / "home"
    onto = home / "ontologies"
    onto.mkdir(parents=True)
    (onto / "thin.yaml").write_text(
        yaml.dump(
            {
                "name": "thin",
                "namespace": "http://example/thin/",
                "classes": {
                    "Only": {"label": "Only", "required_fields": ["id"]},
                },
            },
            allow_unicode=True,
        ),
        encoding="utf-8",
    )
    monkeypatch.setenv("AIPLAT_HOME", str(home))
    GraphIndex._loaded_instances.clear()
    gate = ocs.evaluate_ocs_gate("thin", credit_test_evidence=False)
    assert gate["pass"] is False
    assert "ocs_below_threshold" in gate["issues"]
    assert gate["accuracy_claim"] is False
    assert gate["threshold"] >= 80


def test_honesty_flags_on_report(tmp_path, monkeypatch):
    home = tmp_path / "home"
    onto = home / "ontologies"
    onto.mkdir(parents=True)
    (onto / "lock-service.yaml").write_text(
        yaml.dump(
            {
                "name": "锁",
                "namespace": "http://example/lock/",
                "classes": {
                    "InstallOrder": {
                        "label": "安装工单",
                        "tier": "logic",
                        "required_fields": ["order_id"],
                        "states": {
                            "enum": [{"name": "pending"}],
                            "transitions": [{"from": "pending", "to": "done"}],
                        },
                    },
                },
                "axioms": [
                    {"id": "A1", "severity": "error", "description": "x"},
                    {"id": "A2", "severity": "error", "description": "y"},
                    {"id": "A3", "severity": "warning", "description": "z"},
                ],
            },
            allow_unicode=True,
        ),
        encoding="utf-8",
    )
    monkeypatch.setenv("AIPLAT_HOME", str(home))
    GraphIndex._loaded_instances.clear()
    g = GraphIndex("lock-service")
    g.add_entity("IO-1", "o1", "安装工单", source_doc_id="t")
    g.save()
    GraphIndex._loaded_instances.clear()
    r = ocs.compute_domain_ocs("lock-service", credit_test_evidence=True)
    assert r.get("accuracy_claim") is False
    assert r.get("faithfulness_claim") is False
    assert r.get("action_audit_substitute") is False
    assert r.get("node_count_substitute") is False
    assert "C5" in r["dimensions"]
