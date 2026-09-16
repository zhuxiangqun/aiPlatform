"""P4: GraphIndex ABox ACL + data-gov B4 seed / mount_catalog."""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from core.harness.ontology_engine.action_registry import AsyncActionRegistry
from core.harness.ontology_engine.builtin_actions import register_all
from core.harness.ontology_engine.graph_index import GraphIndex
from core.policy.graph_abox_acl import (
    check_entity_acl,
    redact_entity_fields,
    seed_demo_data_gov_acl,
    set_entity_acl,
    set_field_acl,
)

DOMAIN = "data-gov"
MOUNT = "customer_action:data-gov:mount_catalog"
DISCARD = "customer_action:data-gov:discard_ghost"


@pytest.fixture()
def aiplat_home(tmp_path, monkeypatch):
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setenv("AIPLAT_HOME", str(home))
    GraphIndex._loaded_instances.clear()
    return home


def test_abox_acl_deny_viewer_read(aiplat_home):
    set_entity_acl(
        DOMAIN,
        "TBL-tmp_export",
        deny_roles={"viewer": ["read", "state_change"]},
        allow_roles={"admin": ["*"]},
    )
    assert check_entity_acl(DOMAIN, "TBL-tmp_export", "viewer", "read") is False
    assert check_entity_acl(DOMAIN, "TBL-tmp_export", "admin", "read") is True
    assert check_entity_acl(DOMAIN, "TBL-tmp_export", "", "read") is True


def test_abox_field_redaction(aiplat_home):
    set_field_acl(
        DOMAIN,
        "DA-积分流水",
        "owner_contact",
        visibility="role:admin",
        redaction="replace",
        replace_with="[REDACTED]",
    )
    payload = {
        "entity_id": "DA-积分流水",
        "metadata": {"owner_contact": "ops@example.com", "state": "meta_ready"},
    }
    out = redact_entity_fields(DOMAIN, "DA-积分流水", payload, "viewer")
    assert out["metadata"]["owner_contact"] == "[REDACTED]"
    out_admin = redact_entity_fields(DOMAIN, "DA-积分流水", payload, "admin")
    assert out_admin["metadata"]["owner_contact"] == "ops@example.com"


@pytest.mark.asyncio
async def test_data_gov_seed_mount_and_discard(aiplat_home):
    from core.apps.fde.service.data_gov_demo_seed import seed_data_gov_demo_graph

    GraphIndex._loaded_instances.clear()
    g = GraphIndex(DOMAIN)
    meta = seed_data_gov_demo_graph(g, seed_acl=True)
    g.save()
    GraphIndex._loaded_instances.clear()

    assert meta["primary_asset_id"] == "DA-积分流水"
    assert check_entity_acl(DOMAIN, "TBL-tmp_export", "viewer", "read") is False

    store = AsyncMock()
    store.insert_audit = AsyncMock(return_value="aud_gov")
    reg = AsyncActionRegistry(store=store)
    register_all(reg)
    assert reg.get(MOUNT) is not None
    assert reg.get(DISCARD) is not None

    r_mount = await reg.execute(
        MOUNT,
        (DOMAIN, "DA-积分流水"),
        {"new_state": "cataloged", "catalog_id": "CAT-积分流水"},
        actor="fda-1",
        role="analyst",
        _bypass_approval=True,
    )
    assert r_mount.get("status") == "executed", r_mount

    r_disc = await reg.execute(
        DISCARD,
        (DOMAIN, "TBL-tmp_export"),
        {"new_state": "discarded"},
        actor="fda-1",
        role="analyst",
        _bypass_approval=True,
    )
    assert r_disc.get("status") == "executed", r_disc

    GraphIndex._loaded_instances.clear()
    g2 = GraphIndex.load(DOMAIN)
    assert (g2._nodes["DA-积分流水"].metadata or {}).get("state") == "cataloged"
    assert (g2._nodes["TBL-tmp_export"].metadata or {}).get("state") == "discarded"


@pytest.mark.asyncio
async def test_mount_blocked_when_not_meta_ready(aiplat_home):
    from core.apps.fde.service.data_gov_demo_seed import seed_data_gov_demo_graph

    GraphIndex._loaded_instances.clear()
    g = GraphIndex(DOMAIN)
    seed_data_gov_demo_graph(g, seed_acl=False)
    g.update_entity_property("DA-积分流水", "state", "raw")
    g.save()
    GraphIndex._loaded_instances.clear()

    store = AsyncMock()
    store.insert_audit = AsyncMock(return_value="aud_b")
    reg = AsyncActionRegistry(store=store)
    register_all(reg)
    r = await reg.execute(
        MOUNT,
        (DOMAIN, "DA-积分流水"),
        {"new_state": "cataloged", "catalog_id": "CAT-积分流水"},
        actor="fda-1",
        role="analyst",
        _bypass_approval=True,
    )
    assert r.get("status") == "blocked", r


def test_viewer_acl_blocks_state_change_check(aiplat_home):
    """P5: same rule AcceptTab「viewer试丢弃」uses before execute."""
    seed_demo_data_gov_acl(DOMAIN)
    assert check_entity_acl(DOMAIN, "TBL-tmp_export", "viewer", "state_change") is False
    assert check_entity_acl(DOMAIN, "TBL-tmp_export", "analyst", "state_change") is True
