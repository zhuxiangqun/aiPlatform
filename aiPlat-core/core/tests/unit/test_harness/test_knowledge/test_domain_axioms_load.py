"""Domain YAML axioms load + domain-preferring constraint compiler."""
from __future__ import annotations

from pathlib import Path


def test_load_axioms_from_yaml(tmp_path, monkeypatch):
    monkeypatch.setenv("AIPLAT_HOME", str(tmp_path))
    onto = tmp_path / "ontologies"
    onto.mkdir()
    (onto / "demo-domain.yaml").write_text(
        """
name: Demo
namespace: http://example/demo/
classes:
  Order:
    label: 订单
    required_fields: [order_id]
axioms:
  - id: D-A1
    severity: error
    description: "订单必须有 order_id"
    check: "required order_id"
""",
        encoding="utf-8",
    )
    from core.harness.knowledge.ontology_loader import load_ontology_from_yaml

    dom = load_ontology_from_yaml(str(onto / "demo-domain.yaml"))
    assert len(dom.axioms) == 1
    assert dom.axioms[0].id == "D-A1"
    assert "order_id" in dom.axioms[0].description


def test_compiler_prefers_domain_axioms(tmp_path, monkeypatch):
    monkeypatch.setenv("AIPLAT_HOME", str(tmp_path))
    onto = tmp_path / "ontologies"
    onto.mkdir()
    (onto / "lock-service.yaml").write_text(
        """
name: Lock
namespace: http://example/lock/
classes:
  InstallOrder:
    label: 安装工单
    required_fields: [order_id, status]
axioms:
  - id: LS-A1
    severity: error
    description: "安装工单仅允许从 pending 状态接单"
""",
        encoding="utf-8",
    )
    from core.harness.knowledge.ontology_constraint_compiler import (
        compile_ontology_constraints,
        compile_axiom_rules,
    )

    out = compile_ontology_constraints("lock-service")
    assert "pending" in out
    assert "MUST" in out
    rules = compile_axiom_rules("lock-service")
    assert any("pending" in r for r in rules)
