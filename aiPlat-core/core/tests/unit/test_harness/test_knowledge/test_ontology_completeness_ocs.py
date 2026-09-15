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
    assert await pending.confirm("ext_d1") is True
    from core.harness.knowledge.versioned_ontology_store import VersionedOntologyStore

    props = await VersionedOntologyStore(DOMAIN).list_proposals(DOMAIN)
    assert any(p.get("author", "").startswith("extract:") for p in props)
