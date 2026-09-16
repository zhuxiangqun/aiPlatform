"""OCS + Phase A lifecycle actions + confirm→proposal (D1)."""
from __future__ import annotations

from unittest.mock import AsyncMock

import pytest
import yaml

from core.harness.knowledge.ontology_completeness import compute_domain_ocs
from core.harness.knowledge.ontology_loader import load_ontology_from_yaml
from core.harness.knowledge_pipeline.extractor import ExtractionResult, PendingExtractionStore
from core.harness.ontology_engine.action_registry import AsyncActionRegistry
from core.harness.ontology_engine.builtin_actions import register_all
from core.harness.ontology_engine.graph_index import GraphIndex

DOMAIN = "lock-service"


@pytest.fixture()
def aiplat_home(tmp_path, monkeypatch):
    home = tmp_path / "home"
    onto = home / "ontologies"
    onto.mkdir(parents=True)
    # Minimal but OCS-friendly YAML
    (onto / f"{DOMAIN}.yaml").write_text(
        yaml.dump(
            {
                "name": "锁",
                "namespace": "http://example/lock/",
                "classes": {
                    "InstallOrder": {
                        "label": "安装工单",
                        "required_fields": ["order_id"],
                        "states": {
                            "default": "pending",
                            "enum": [
                                {"name": "pending"},
                                {"name": "accepted"},
                                {"name": "assigned"},
                                {"name": "in_progress"},
                                {"name": "completed"},
                            ],
                            "transitions": [
                                {"from": "pending", "to": "accepted"},
                                {"from": "accepted", "to": "assigned"},
                                {"from": "assigned", "to": "in_progress"},
                                {"from": "in_progress", "to": "completed"},
                            ],
                        },
                    },
                    "Technician": {"label": "安装师傅", "required_fields": ["name"]},
                },
                "axioms": [
                    {"id": "A1", "severity": "error", "description": "pending only"},
                    {"id": "A2", "severity": "error", "description": "evidence"},
                    {"id": "A3", "severity": "warning", "description": "assignee"},
                ],
                "interfaces": {"Assignable": {"label": "可派单"}},
            },
            allow_unicode=True,
        ),
        encoding="utf-8",
    )
    monkeypatch.setenv("AIPLAT_HOME", str(home))
    GraphIndex._loaded_instances.clear()
    g = GraphIndex(DOMAIN)
    g.add_entity("IO-1", "o1", "安装工单", source_doc_id="t")
    g.add_entity_property("IO-1", "state", "accepted")
    g.add_entity("T-1", "tech", "安装师傅", source_doc_id="t")
    g.save()
    GraphIndex._loaded_instances.clear()
    return home


def test_ocs_lock_service_pilot_or_better(aiplat_home):
    r = compute_domain_ocs(DOMAIN, credit_test_evidence=True)
    assert r["ocs"] >= 70, r
    assert r["dimensions"]["C3"] >= 100
    assert r["dimensions"]["C4"] > 0


def test_ui_demo_create_install_order_abox(aiplat_home):
    """Mirrors POST /fde/graph/entities — UI can mint pending InstallOrder + Technician."""
    GraphIndex._loaded_instances.clear()
    g = GraphIndex.load(DOMAIN)
    tech_id = "TECH-DEMO-001"
    entity_id = "IO-DEMO-UI-1"
    g.add_entity(tech_id, "演示安装师傅", "安装师傅", source_doc_id="ui-demo")
    g.add_entity(entity_id, "演示安装工单", "安装工单", source_doc_id="ui-demo")
    g.add_entity_property(entity_id, "state", "pending")
    g.add_entity_property(entity_id, "status", "pending")
    g.save()
    GraphIndex._loaded_instances.clear()
    g2 = GraphIndex.load(DOMAIN)
    ents = g2.get_entities_by_class("安装工单")
    assert any(n.entity_id == entity_id for n in ents)
    assert (g2.get_node(entity_id).metadata or {}).get("state") == "pending"
    assert g2.get_node(tech_id) is not None


def test_ocs_lock_service_seed_ratchet_complete(tmp_path, monkeypatch):
    """CI ratchet: workspace seed lock-service + minimal ABox ⇒ OCS ≥ 80."""
    import shutil
    from pathlib import Path

    home = tmp_path / "ocs_home"
    onto = home / "ontologies"
    onto.mkdir(parents=True)
    seed = (
        Path(__file__).resolve().parents[5]
        / "workspace_seeds"
        / "ontologies"
        / "lock-service.yaml"
    )
    assert seed.is_file(), f"missing seed {seed}"
    shutil.copy(seed, onto / "lock-service.yaml")
    monkeypatch.setenv("AIPLAT_HOME", str(home))
    GraphIndex._loaded_instances.clear()
    g = GraphIndex(DOMAIN)
    for i in range(6):
        g.add_entity(f"IO-{i}", f"o{i}", "安装工单", source_doc_id="seed")
    g.add_relation("IO-0", "assigned_to", "IO-1")
    g.save()
    GraphIndex._loaded_instances.clear()
    r = compute_domain_ocs(DOMAIN, credit_test_evidence=True)
    assert r["ocs"] >= 80, r
    assert r["level"] == "complete", r


def test_seed_cross_domain_config_unified_customer(tmp_path, monkeypatch):
    """Production consumer path: seed ensures unified_customer view in registry."""
    import json
    from pathlib import Path

    from core.harness.knowledge_pipeline import resolver as resolver_mod

    home = tmp_path / "cd_home"
    home.mkdir()
    reg_path = home / "registry.json"
    reg_path.write_text("{}", encoding="utf-8")
    monkeypatch.setattr(resolver_mod, "REGISTRY_PATH", str(reg_path))
    assert resolver_mod.seed_cross_domain_config() is True
    views = json.loads(reg_path.read_text(encoding="utf-8")).get("cross_domain_views") or {}
    uc = views.get("unified_customer") or {}
    sources = uc.get("sources") or []
    assert len(sources) >= 2
    domains = {s.get("domain") for s in sources}
    assert "lock-service" in domains and "service-domain" in domains
    # idempotent
    assert resolver_mod.seed_cross_domain_config() is False
    assert resolver_mod.ensure_unified_customer_view().get("sources")


@pytest.mark.asyncio
async def test_lifecycle_assign_requires_accepted(aiplat_home):
    store = AsyncMock()
    store.insert_audit = AsyncMock(return_value="a")
    reg = AsyncActionRegistry(store=store)
    register_all(reg)
    aid = "customer_action:lock-service:assign_technician"
    assert reg.get(aid) is not None
    # wrong state
    g = GraphIndex.load(DOMAIN)
    g.update_entity_property("IO-1", "state", "pending")
    g.save()
    GraphIndex._loaded_instances.clear()
    blocked = await reg.execute(
        aid,
        (DOMAIN, "IO-1"),
        {"new_state": "assigned", "assigned_technician": "T-1"},
        actor="t",
        role="agent",
        _bypass_approval=True,
    )
    assert blocked.get("status") == "blocked"
    # correct state
    g = GraphIndex.load(DOMAIN)
    g.update_entity_property("IO-1", "state", "accepted")
    g.save()
    GraphIndex._loaded_instances.clear()
    ok = await reg.execute(
        aid,
        (DOMAIN, "IO-1"),
        {"new_state": "assigned", "assigned_technician": "T-1"},
        actor="t",
        role="agent",
        _bypass_approval=True,
    )
    assert ok.get("status") == "executed", ok
    GraphIndex._loaded_instances.clear()
    g2 = GraphIndex.load(DOMAIN)
    node = g2.get_node("IO-1")
    assert (node.metadata or {}).get("state") == "assigned"
    outs = getattr(node, "out_edges", None) or getattr(node, "edges", None) or []
    # GraphNode stores outgoing in out_edges list of GraphEdge
    rel_names = []
    if outs:
        for e in outs:
            rel_names.append(getattr(e, "relation_name", "") or getattr(e, "name", ""))
    else:
        # fallback: scan internal structure
        for e in getattr(g2, "_edges", []) or []:
            src = getattr(e, "source_id", None) or (e[0] if isinstance(e, tuple) else None)
            if src == "IO-1":
                rel_names.append(getattr(e, "relation_name", "") or "")
    assert "assigned_to" in rel_names, f"expected assigned_to edge, got {rel_names}"


@pytest.mark.asyncio
async def test_lifecycle_full_chain_writes_relations(aiplat_home):
    """pending→accepted→assigned→in_progress→completed with evidence relations."""
    store = AsyncMock()
    store.insert_audit = AsyncMock(return_value="a")
    reg = AsyncActionRegistry(store=store)
    register_all(reg)
    GraphIndex._loaded_instances.clear()
    g = GraphIndex.load(DOMAIN)
    g.update_entity_property("IO-1", "state", "pending")
    g.save()
    GraphIndex._loaded_instances.clear()

    async def run(aid, params):
        return await reg.execute(
            aid, (DOMAIN, "IO-1"), params, actor="t", role="agent", _bypass_approval=True
        )

    r1 = await run("customer_action:lock-service:accept_order", {})
    assert r1.get("status") == "executed", r1
    r2 = await run(
        "customer_action:lock-service:assign_technician",
        {"new_state": "assigned", "assigned_technician": "T-1"},
    )
    assert r2.get("status") == "executed", r2
    r3 = await run(
        "customer_action:lock-service:start_install",
        {"new_state": "in_progress", "assigned_technician": "T-1"},
    )
    assert r3.get("status") == "executed", r3
    r4 = await run(
        "customer_action:lock-service:complete_install",
        {"new_state": "completed", "installed_by": "T-1"},
    )
    assert r4.get("status") == "executed", r4
    GraphIndex._loaded_instances.clear()
    g = GraphIndex.load(DOMAIN)
    assert (g.get_node("IO-1").metadata or {}).get("state") == "completed"
    n = g.get_node("IO-1")
    names = [getattr(e, "relation_name", "") for e in (getattr(n, "out_edges", None) or [])]
    assert "assigned_to" in names
    assert "visited_at" in names
    assert "installed_by" in names


@pytest.mark.asyncio
async def test_confirm_enqueues_ontology_proposal(aiplat_home, tmp_path):
    pending = PendingExtractionStore(db_path=str(tmp_path / "e.db"))
    await pending.initialize()
    await pending.save(
        ExtractionResult(
            extraction_id="ext_d1",
            domain_id=DOMAIN,
            source_doc="doc.md",
            overall_confidence=0.8,
            entities=[{"name": "新配件", "type": "SpareKit"}],
            relations=[],
            status="pending",
            draft_yaml_path="",
        )
    )
    receipt = await pending.confirm("ext_d1")
    assert receipt.get("ok") is True, receipt
    gw = receipt.get("graph_write") or {}
    assert "新配件" in gw.get("created_entities", []), gw
    from core.harness.knowledge.versioned_ontology_store import VersionedOntologyStore

    props = await VersionedOntologyStore(DOMAIN).list_proposals(DOMAIN)
    assert any(p.get("author", "").startswith("extract:") for p in props)

    GraphIndex._loaded_instances.clear()
    g = GraphIndex.load(DOMAIN)
    assert "新配件" in g._nodes


@pytest.mark.asyncio
async def test_confirm_writes_relations_receipt(aiplat_home, tmp_path):
    """P2 gate: confirm → GraphIndex entities + relations + receipt."""
    pending = PendingExtractionStore(db_path=str(tmp_path / "e2.db"))
    await pending.initialize()
    await pending.save(
        ExtractionResult(
            extraction_id="ext_abox",
            domain_id=DOMAIN,
            source_doc="ops.md",
            overall_confidence=0.75,
            entities=[
                {"name": "积分查询", "class_type": "服务", "entity_id": "SVC-查询"},
                {"name": "Redis主", "class_type": "中间件", "entity_id": "MW-Redis主"},
            ],
            relations=[
                {"source": "积分查询", "type": "依赖", "target": "Redis主"},
            ],
            status="pending",
            draft_yaml_path="",
        )
    )
    receipt = await pending.confirm("ext_abox", enqueue_proposal=False)
    assert receipt.get("ok") is True, receipt
    gw = receipt.get("graph_write") or {}
    assert set(gw.get("created_entities", [])) >= {"SVC-查询", "MW-Redis主"}
    assert any("依赖" in r for r in gw.get("relations", [])), gw
    assert receipt.get("proposal_id") is None

    GraphIndex._loaded_instances.clear()
    g = GraphIndex.load(DOMAIN)
    assert g._nodes["SVC-查询"].class_name == "服务"
    assert g._nodes["MW-Redis主"].metadata.get("source") == "extract-confirm"
