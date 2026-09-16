"""it-ops alert triage L1: open → triaging → rooted (+ wrong-state block)."""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from core.harness.ontology_engine.action_registry import AsyncActionRegistry
from core.harness.ontology_engine.builtin_actions import register_all
from core.harness.ontology_engine.graph_index import GraphIndex

DOMAIN = "it-ops"
TRIAGE = "customer_action:it-ops:triage_alert"
LINK = "customer_action:it-ops:link_suspect"
MARK = "customer_action:it-ops:mark_root_cause"


@pytest.fixture()
def aiplat_home(tmp_path, monkeypatch):
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setenv("AIPLAT_HOME", str(home))
    GraphIndex._loaded_instances.clear()
    return home


def _seed_alert(eid: str = "ALT-UT-0001") -> str:
    g = GraphIndex(DOMAIN)
    for tid, tname, tcls in [
        ("SVC-CAST-QUERY", "cast-query", "服务"),
        ("SVC-CAST-ACTION", "cast-action", "服务"),
        ("MW-REDIS-1", "redis-1", "中间件"),
        ("HOST-1", "10.0.0.8", "主机"),
    ]:
        g.add_entity(tid, tname, tcls, source_doc_id="t")
    g.add_relation("SVC-CAST-QUERY", "SVC-CAST-ACTION", "calls", relation_label="调用")
    g.add_relation("SVC-CAST-ACTION", "MW-REDIS-1", "calls", relation_label="调用")
    g.add_entity(eid, "积分告警", "告警", source_doc_id="t")
    g.add_entity_property(eid, "state", "open")
    g.save()
    GraphIndex._loaded_instances.clear()
    return eid


@pytest.mark.asyncio
async def test_it_ops_actions_registered(aiplat_home):
    reg = AsyncActionRegistry(store=AsyncMock())
    register_all(reg)
    for aid in (TRIAGE, LINK, MARK):
        assert reg.get(aid) is not None, aid


@pytest.mark.asyncio
async def test_triage_blocked_when_not_open(aiplat_home):
    eid = _seed_alert("ALT-BAD-0001")
    g = GraphIndex.load(DOMAIN)
    g.update_entity_property(eid, "state", "rooted")
    g.save()
    GraphIndex._loaded_instances.clear()

    store = AsyncMock()
    store.insert_audit = AsyncMock(return_value="aud_x")
    reg = AsyncActionRegistry(store=store)
    register_all(reg)

    r = await reg.execute(
        TRIAGE,
        (DOMAIN, eid),
        {"new_state": "triaging"},
        actor="fda-1",
        role="agent",
        _bypass_approval=True,
    )
    assert r.get("status") == "blocked", r
    assert r.get("constraint_type") == "state"
    store.insert_audit.assert_awaited()


@pytest.mark.asyncio
async def test_alert_triage_full_path(aiplat_home):
    eid = _seed_alert()
    store = AsyncMock()
    store.insert_audit = AsyncMock(side_effect=lambda rec: "aud")
    reg = AsyncActionRegistry(store=store)
    register_all(reg)

    r1 = await reg.execute(
        TRIAGE,
        (DOMAIN, eid),
        {"new_state": "triaging", "suspected_root": "MW-REDIS-1"},
        actor="fda-1",
        role="agent",
        _bypass_approval=True,
    )
    assert r1.get("status") == "executed", r1

    r2 = await reg.execute(
        LINK,
        (DOMAIN, eid),
        {
            "new_state": "triaging",
            "suspected_root": "MW-REDIS-1",
            "path_note": "cast-query→cast-action→redis",
        },
        actor="fda-1",
        role="agent",
        _bypass_approval=True,
    )
    assert r2.get("status") == "executed", r2

    r3 = await reg.execute(
        MARK,
        (DOMAIN, eid),
        {"new_state": "rooted", "root_entity_id": "MW-REDIS-1"},
        actor="fda-1",
        role="agent",
        _bypass_approval=True,
    )
    assert r3.get("status") == "executed", r3

    GraphIndex._loaded_instances.clear()
    g = GraphIndex.load(DOMAIN)
    node = g._nodes[eid]
    meta = node.metadata or {}
    assert (meta.get("state") or meta.get("status")) == "rooted"
    assert meta.get("root_entity_id") == "MW-REDIS-1"


@pytest.mark.asyncio
async def test_complex_demo_seed_triage(aiplat_home):
    """Path C complex template: multi-alert topology; primary alert triageable."""
    from core.apps.fde.service.it_ops_demo_seed import seed_it_ops_demo_graph

    GraphIndex._loaded_instances.clear()
    g = GraphIndex(DOMAIN)
    eid = "ALT-COMPLEX-0001"
    meta = seed_it_ops_demo_graph(
        g,
        profile="complex",
        primary_alert_id=eid,
        primary_alert_name="ALT-主",
        primary_state="open",
        source_doc_id="ut-complex",
    )
    g.save()
    GraphIndex._loaded_instances.clear()

    assert meta["profile"] == "complex"
    assert len(meta["alerts"]) == 5
    assert "MW-Redis主" in meta["topology"]
    assert "SVC-查询" in meta["topology"]

    g2 = GraphIndex.load(DOMAIN)
    assert eid in g2._nodes
    assert g2._nodes[eid].metadata.get("service_name") == "SVC-查询"
    assert g2._nodes["MW-Redis主"].metadata.get("pool_util") == "98"

    store = AsyncMock()
    store.insert_audit = AsyncMock(return_value="aud_c")
    reg = AsyncActionRegistry(store=store)
    register_all(reg)
    r = await reg.execute(
        TRIAGE,
        (DOMAIN, eid),
        {"new_state": "triaging", "suspected_root": "MW-Redis主"},
        actor="fda-1",
        role="agent",
        _bypass_approval=True,
    )
    assert r.get("status") == "executed", r


def test_ensure_it_ops_fault_ontology_replaces_knowledge(aiplat_home):
    """Path C: if AIPLAT_HOME has knowledge it-ops (无告警类), replace with fault seed."""
    from pathlib import Path

    from core.apps.fde.service.it_ops_demo_seed import ensure_it_ops_fault_ontology

    ont = Path(aiplat_home) / "ontologies"
    ont.mkdir(parents=True, exist_ok=True)
    (ont / "it-ops.yaml").write_text(
        "name: IT运维知识\nclasses:\n  Infrastructure:\n    label: 基础设施\n",
        encoding="utf-8",
    )
    out = ensure_it_ops_fault_ontology()
    assert out["action"] == "installed", out
    text = (ont / "it-ops.yaml").read_text(encoding="utf-8")
    assert "label: 告警" in text
    assert (ont / "it-ops.knowledge-bak.yaml").is_file()


@pytest.mark.asyncio
async def test_complex_seed_no_unknown_class_after_ensure(aiplat_home, caplog):
    """After ensure, GraphIndex should know 告警/服务 labels (no unknown-class WARNING)."""
    import logging

    from core.apps.fde.service.it_ops_demo_seed import seed_it_ops_demo_graph

    GraphIndex._loaded_instances.clear()
    g = GraphIndex(DOMAIN)
    with caplog.at_level(logging.WARNING):
        seed_it_ops_demo_graph(
            g,
            profile="complex",
            primary_alert_id="ALT-ENSURE-1",
            ensure_ontology=True,
        )
        g.save()
    unknown = [r for r in caplog.records if "unknown class" in r.getMessage()]
    assert not unknown, f"unexpected unknown-class warnings: {[r.getMessage() for r in unknown]}"


def test_import_sample_payload_writes_graph(aiplat_home):
    """Path B: bundled monitor JSON → GraphIndex entities + relations."""
    from core.apps.fde.service.it_ops_demo_seed import (
        import_it_ops_alert_payload,
        load_it_ops_import_sample,
    )

    GraphIndex._loaded_instances.clear()
    g = GraphIndex(DOMAIN)
    payload = load_it_ops_import_sample()
    meta = import_it_ops_alert_payload(g, payload, source_doc_id="ut-import")
    g.save()
    GraphIndex._loaded_instances.clear()

    assert meta["profile"] == "import"
    assert meta["primary_alert_id"] == "ALT-IMPORT-MAIN"
    assert "ALT-IMPORT-MAIN" in meta["alerts"]
    assert "ALT-IMPORT-DISK" in meta["alerts"]
    assert "MW-Redis主" in meta["created_entities"]
    assert "SVC-动作-calls->MW-Redis主" in meta["relations"]

    g2 = GraphIndex.load(DOMAIN)
    assert "ALT-IMPORT-MAIN" in g2._nodes
    assert g2._nodes["ALT-IMPORT-MAIN"].metadata.get("state") == "open"
    assert g2._nodes["MW-Redis主"].metadata.get("pool_util") == "98"


def test_import_rejects_unknown_class(aiplat_home):
    from core.apps.fde.service.it_ops_demo_seed import import_it_ops_alert_payload

    GraphIndex._loaded_instances.clear()
    g = GraphIndex(DOMAIN)
    meta = import_it_ops_alert_payload(
        g,
        {
            "entities": [
                {"id": "X-1", "name": "bad", "class": "未知类"},
                {"id": "ALT-OK", "name": "ok", "class": "告警", "state": "open"},
            ],
            "relations": [],
            "primary_alert_id": "ALT-OK",
        },
        source_doc_id="ut-skip",
    )
    assert "ALT-OK" in meta["created_entities"]
    assert any(s.get("reason", "").startswith("class_not_allowed") for s in meta["skipped"])
    assert "X-1" not in g._nodes


@pytest.mark.asyncio
async def test_import_sample_then_triage(aiplat_home):
    """Path B E2E: import sample → triage primary alert."""
    from core.apps.fde.service.it_ops_demo_seed import (
        import_it_ops_alert_payload,
        load_it_ops_import_sample,
    )

    GraphIndex._loaded_instances.clear()
    g = GraphIndex(DOMAIN)
    meta = import_it_ops_alert_payload(g, load_it_ops_import_sample())
    g.save()
    GraphIndex._loaded_instances.clear()
    eid = meta["primary_alert_id"]

    store = AsyncMock()
    store.insert_audit = AsyncMock(return_value="aud_imp")
    reg = AsyncActionRegistry(store=store)
    register_all(reg)
    r = await reg.execute(
        TRIAGE,
        (DOMAIN, eid),
        {"new_state": "triaging", "suspected_root": "MW-Redis主"},
        actor="fda-1",
        role="agent",
        _bypass_approval=True,
    )
    assert r.get("status") == "executed", r
