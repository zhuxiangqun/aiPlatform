"""Phase 1–2: Path B webhook connector + ABox role bridge + retail-ops isomorphic domain."""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from core.harness.ontology_engine.action_registry import AsyncActionRegistry
from core.harness.ontology_engine.builtin_actions import register_all
from core.harness.ontology_engine.graph_index import GraphIndex
from core.policy.graph_abox_acl import (
    check_entity_acl,
    normalize_abox_role,
    resolve_abox_actor_role,
    set_entity_acl,
)


@pytest.fixture()
def aiplat_home(tmp_path, monkeypatch):
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setenv("AIPLAT_HOME", str(home))
    GraphIndex._loaded_instances.clear()
    return home


def test_normalize_and_resolve_roles():
    assert normalize_abox_role("guest") == "viewer"
    assert normalize_abox_role("operator") == "analyst"
    assert normalize_abox_role("platform_admin") == "admin"
    assert resolve_abox_actor_role(explicit_role="viewer") == "viewer"
    assert resolve_abox_actor_role(header_role="developer") == "analyst"
    assert resolve_abox_actor_role(scopes=["kb:write", "kb:read"]) == "analyst"
    assert resolve_abox_actor_role(scopes=["admin"]) == "admin"
    # explicit wins over header
    assert (
        resolve_abox_actor_role(explicit_role="viewer", header_role="admin") == "viewer"
    )


def test_role_alias_hits_acl(aiplat_home):
    set_entity_acl(
        "data-gov",
        "TBL-tmp_export",
        deny_roles={"viewer": ["read", "state_change"]},
        allow_roles={"admin": ["*"], "analyst": ["read", "state_change"]},
    )
    # guest → viewer
    assert check_entity_acl("data-gov", "TBL-tmp_export", "guest", "read") is False
    # operator → analyst
    assert check_entity_acl("data-gov", "TBL-tmp_export", "operator", "state_change") is True
    # platform_admin → admin
    assert check_entity_acl("data-gov", "TBL-tmp_export", "platform_admin", "read") is True


def test_webhook_ingest_it_ops(aiplat_home):
    from core.apps.fde.service.abox_connector import ensure_connector_config, ingest_webhook_payload
    from core.apps.fde.service.it_ops_demo_seed import (
        ensure_it_ops_fault_ontology,
        load_it_ops_import_sample,
    )

    ensure_it_ops_fault_ontology()
    ensure_connector_config("it-ops")
    payload = load_it_ops_import_sample()
    result = ingest_webhook_payload("monitor-alerts", payload)
    assert result["status"] == "imported"
    assert result["domain_id"] == "it-ops"
    assert result["primary_id"] or result.get("primary_alert_id")
    assert result["created_entities"]
    g = GraphIndex.load("it-ops")
    primary = result.get("primary_id") or result.get("primary_alert_id")
    assert primary in g._nodes


@pytest.mark.asyncio
async def test_webhook_then_triage(aiplat_home):
    from core.apps.fde.service.abox_connector import ensure_connector_config, ingest_webhook_payload
    from core.apps.fde.service.it_ops_demo_seed import (
        ensure_it_ops_fault_ontology,
        load_it_ops_import_sample,
    )

    ensure_it_ops_fault_ontology()
    ensure_connector_config("it-ops")
    result = ingest_webhook_payload("monitor-alerts", load_it_ops_import_sample())
    primary = result.get("primary_id") or result.get("primary_alert_id")
    assert primary

    store = AsyncMock()
    store.insert_audit = AsyncMock(return_value="aud_wh")
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


@pytest.mark.asyncio
async def test_retail_ops_isomorphic_triage(aiplat_home):
    from core.apps.fde.service.retail_ops_demo_seed import seed_retail_ops_demo_graph

    GraphIndex._loaded_instances.clear()
    g = GraphIndex("retail-ops")
    meta = seed_retail_ops_demo_graph(g)
    g.save()
    GraphIndex._loaded_instances.clear()

    aid = meta["primary_alert_id"]
    store = AsyncMock()
    store.insert_audit = AsyncMock(return_value="aud_ret")
    reg = AsyncActionRegistry(store=store)
    register_all(reg)

    for aid_name in (
        "customer_action:retail-ops:triage_alert",
        "customer_action:retail-ops:link_suspect",
        "customer_action:retail-ops:mark_root_cause",
    ):
        assert reg.get(aid_name) is not None, aid_name

    r1 = await reg.execute(
        action_id="customer_action:retail-ops:triage_alert",
        entity_ref=("retail-ops", aid),
        params={"new_state": "triaging"},
        actor="ut",
        role="analyst",
        _bypass_approval=True,
    )
    assert r1.get("status") == "executed", r1

    g2 = GraphIndex.load("retail-ops")
    g2.add_entity("ALT-BLOCK", "block-test", "告警", source_doc_id="ut")
    g2.add_entity_property("ALT-BLOCK", "state", "open")
    g2.add_entity_property("ALT-BLOCK", "status", "open")
    g2.save()
    GraphIndex._loaded_instances.clear()

    blocked = await reg.execute(
        action_id="customer_action:retail-ops:mark_root_cause",
        entity_ref=("retail-ops", "ALT-BLOCK"),
        params={"new_state": "rooted", "root_entity_id": "MW-Redis"},
        actor="ut",
        role="analyst",
        _bypass_approval=True,
    )
    assert blocked.get("status") == "blocked"
    assert blocked.get("constraint_type") == "state"


def test_webhook_secret_rejects(aiplat_home, monkeypatch):
    from core.apps.fde.service.abox_connector import ensure_connector_config, ingest_webhook_payload
    from core.apps.fde.service.it_ops_demo_seed import ensure_it_ops_fault_ontology, load_it_ops_import_sample

    ensure_it_ops_fault_ontology()
    ensure_connector_config("it-ops")
    monkeypatch.setenv("AIPLAT_ABOX_WEBHOOK_SECRET", "s3cret")
    bad = ingest_webhook_payload("monitor-alerts", load_it_ops_import_sample(), secret="wrong")
    assert bad["status"] == "unauthorized"
    ok = ingest_webhook_payload("monitor-alerts", load_it_ops_import_sample(), secret="s3cret")
    assert ok["status"] == "imported"
