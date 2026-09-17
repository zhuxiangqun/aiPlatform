"""Phase A–E: table_map Path B, pillars, code suggestions, offline OWL, scaffold."""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from core.harness.ontology_engine.action_registry import AsyncActionRegistry
from core.harness.ontology_engine.builtin_actions import register_all
from core.harness.ontology_engine.graph_index import GraphIndex


@pytest.fixture()
def aiplat_home(tmp_path, monkeypatch):
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setenv("AIPLAT_HOME", str(home))
    GraphIndex._loaded_instances.clear()
    return home


def test_map_table_rows_and_csv_parse():
    from core.apps.fde.service.abox_connector import map_table_rows_to_payload, parse_csv_text

    rows = parse_csv_text("id,name,class,state\nA1,alert,告警,open\nS1,svc,服务,\n")
    assert len(rows) == 2
    payload = map_table_rows_to_payload(
        rows,
        table_map={"id_column": "id", "class_column": "class"},
        relation_rows=[{"from": "A1", "to": "S1", "rel": "suspects"}],
    )
    assert payload["entities"][0]["id"] == "A1"
    assert payload["relations"][0]["rel"] == "suspects"


def test_table_map_import_then_triage(aiplat_home):
    from core.apps.fde.service.abox_connector import (
        ensure_connector_config,
        import_table_map_payload,
    )
    from core.apps.fde.service.it_ops_demo_seed import ensure_it_ops_fault_ontology

    ensure_it_ops_fault_ontology()
    ensure_connector_config("it-ops")
    GraphIndex._loaded_instances.clear()
    g = GraphIndex.load("it-ops")
    meta = import_table_map_payload(g, domain_id="it-ops", use_sample=True)
    g.save()
    assert meta.get("source_type") == "table_map" or meta.get("profile") == "table_map"
    assert meta.get("created_entities")
    primary = meta.get("primary_id") or meta.get("primary_alert_id")
    assert primary
    assert primary in GraphIndex.load("it-ops")._nodes


@pytest.mark.asyncio
async def test_table_map_e2e_action(aiplat_home):
    from core.apps.fde.service.abox_connector import (
        ensure_connector_config,
        import_table_map_payload,
    )
    from core.apps.fde.service.it_ops_demo_seed import ensure_it_ops_fault_ontology

    ensure_it_ops_fault_ontology()
    ensure_connector_config("it-ops")
    GraphIndex._loaded_instances.clear()
    g = GraphIndex.load("it-ops")
    meta = import_table_map_payload(g, domain_id="it-ops", use_sample=True)
    g.save()
    primary = meta.get("primary_id") or meta.get("primary_alert_id")
    assert primary

    store = AsyncMock()
    store.insert_audit = AsyncMock(return_value="aud_tm")
    reg = AsyncActionRegistry(store=store)
    register_all(reg)
    out = await reg.execute(
        action_id="customer_action:it-ops:triage_alert",
        entity_ref=("it-ops", primary),
        params={"new_state": "triaging"},
        actor="ut",
        role="analyst",
        _bypass_approval=True,
    )
    assert out.get("status") == "executed", out


def test_ontology_pillars_shape(aiplat_home):
    from core.apps.fde.service.it_ops_demo_seed import ensure_it_ops_fault_ontology
    from core.apps.fde.service.ontology_pillars import get_ontology_pillars
    from core.apps.fde.service.abox_connector import (
        ensure_connector_config,
        import_table_map_payload,
    )

    ensure_it_ops_fault_ontology()
    ensure_connector_config("it-ops")
    GraphIndex._loaded_instances.clear()
    g = GraphIndex.load("it-ops")
    import_table_map_payload(g, domain_id="it-ops", use_sample=True)
    g.save()

    pillars = get_ontology_pillars("it-ops")
    assert pillars["domain_id"] == "it-ops"
    assert "data" in pillars and "logic" in pillars and "action" in pillars
    assert pillars["data"]["entity_count"] >= 1
    assert pillars.get("authority_note")


@pytest.mark.asyncio
async def test_code_suggestions_draft_no_auto_apply(aiplat_home):
    from core.apps.fde.service.ontology_code_suggestions import (
        suggest_classes_from_snippets_async,
    )

    # Ensure domain yaml exists for VersionedOntologyStore
    onto = aiplat_home / "ontologies"
    onto.mkdir(parents=True)
    (onto / "it-ops.yaml").write_text(
        "name: it-ops\nnamespace: http://aiplat.local/ontology/it-ops/\nclasses: {}\n",
        encoding="utf-8",
    )
    result = await suggest_classes_from_snippets_async(
        "it-ops",
        snippets=["class ServiceEndpoint:\n    pass\nentity: AlertEvent"],
        enqueue=True,
    )
    assert result["auto_apply"] is False
    assert result["suggestions"]
    assert result.get("proposal_id")  # draft only


def test_offline_owl_review_no_false_green(aiplat_home):
    from core.apps.fde.service.offline_owl_review import review_domain_owl_offline

    result = review_domain_owl_offline("it-ops")
    # Without owlready2 (or without successful check) must not claim valid
    if not result.get("checks_run"):
        assert result["status"] in ("unchecked", "error")
        assert result["valid"] is False
    assert result.get("runtime_authority") is False


@pytest.mark.asyncio
async def test_confirm_extraction_graph_and_proposal_regression(aiplat_home, tmp_path):
    """B1: confirm → Path B graph write + Path A proposal (regression)."""
    pytest.importorskip("aiosqlite")
    from core.harness.knowledge_pipeline.extractor import (
        ExtractionResult,
        PendingExtractionStore,
    )

    db = tmp_path / "pending.db"
    pending = PendingExtractionStore(db_path=str(db))
    await pending.initialize()
    onto = aiplat_home / "ontologies"
    onto.mkdir(parents=True)
    (onto / "lock-service.yaml").write_text(
        "name: lock-service\nnamespace: http://aiplat.local/ontology/lock-service/\n"
        "classes:\n  InstallOrder:\n    label: 安装工单\n",
        encoding="utf-8",
    )
    await pending.save(
        ExtractionResult(
            extraction_id="ext_b1",
            domain_id="lock-service",
            source_doc="ut-doc",
            overall_confidence=0.8,
            entities=[{"name": "演示工单", "type": "安装工单"}],
            relations=[],
            status="pending",
            draft_yaml_path="",
        )
    )
    receipt = await pending.confirm("ext_b1", write_graph=True, enqueue_proposal=True)
    assert receipt.get("ok")
    assert receipt.get("proposal_id") or (receipt.get("graph_write") or {}).get("created_entities") is not None


@pytest.mark.asyncio
async def test_scaffold_domain_blocked_executed(aiplat_home, tmp_path, monkeypatch):
    """Phase E: scaffold-like domain action smoke without editing harness."""
    # Install minimal action YAML seed path used by register_all
    actions_dir = aiplat_home / "actions"
    actions_dir.mkdir(parents=True)
    (actions_dir / "scaffold-demo_assign.yaml").write_text(
        """
actions:
  - action_id: "customer_action:scaffold-demo:assign"
    label: "派单"
    category: mutation
    scope: domain
    domain_id: scaffold-demo
    target_class: 工单
    required_state: pending
    risk_level: medium
    require_approval: false
    throttle_limit: 0
    action_namespace: customer_action
    eval_gate: customer_action_safety
    handler: "core.harness.ontology_engine.builtin_handlers:set_entity_state"
    input_schema:
      type: object
      required: [new_state]
      properties:
        new_state:
          type: string
          const: assigned
""",
        encoding="utf-8",
    )
    GraphIndex._loaded_instances.clear()
    g = GraphIndex("scaffold-demo")
    g.add_entity("WO-1", "demo", "工单", source_doc_id="scaffold")
    g.add_entity_property("WO-1", "state", "pending")
    g.save()
    GraphIndex._loaded_instances.clear()

    store = AsyncMock()
    store.insert_audit = AsyncMock(return_value="aud_sc")
    reg = AsyncActionRegistry(store=store)
    register_all(reg)
    aid = "customer_action:scaffold-demo:assign"
    assert reg.get(aid) is not None

    ok = await reg.execute(
        aid,
        ("scaffold-demo", "WO-1"),
        {"new_state": "assigned"},
        actor="scaffold",
        role="analyst",
        _bypass_approval=True,
    )
    assert ok.get("status") == "executed", ok

    g2 = GraphIndex.load("scaffold-demo")
    g2.add_entity("WO-2", "blocked", "工单", source_doc_id="scaffold")
    g2.add_entity_property("WO-2", "state", "completed")
    g2.save()
    GraphIndex._loaded_instances.clear()
    blocked = await reg.execute(
        aid,
        ("scaffold-demo", "WO-2"),
        {"new_state": "assigned"},
        actor="scaffold",
        role="analyst",
        _bypass_approval=True,
    )
    assert blocked.get("status") == "blocked"
