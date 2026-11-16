"""Batch C：link.traverse ABox ACL（实例拒绝 + 跨租户负向）。"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

import pytest

from core.harness.knowledge_pipeline.link_traverse import traverse_links
from core.policy.graph_abox_acl import set_entity_acl, set_field_acl


class _FakeLedger:
    def __init__(self, facts: List[Dict[str, Any]]) -> None:
        self._facts = facts

    async def initialize(self) -> None:
        return None

    async def query_facts(
        self,
        *,
        tenant_id: str,
        domain_id: Optional[str] = None,
        limit: int = 2000,
        **kwargs: Any,
    ) -> List[Dict[str, Any]]:
        rows = [f for f in self._facts if f.get("tenant_id") == tenant_id]
        if domain_id:
            rows = [f for f in rows if f.get("domain_id") == domain_id]
        return rows[:limit]


def _fact(
    tenant_id: str,
    subject: str,
    predicate: str,
    obj: str,
    domain_id: str = "lock-service",
) -> Dict[str, Any]:
    return {
        "tenant_id": tenant_id,
        "domain_id": domain_id,
        "subject": subject,
        "predicate": predicate,
        "object": obj,
    }


@pytest.fixture()
def aiplat_home(tmp_path, monkeypatch):
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setenv("AIPLAT_HOME", str(home))
    return home


@pytest.fixture()
def ledger():
    return _FakeLedger(
        [
            _fact("t1", "InstallOrder:O-1", "assigned_to", "Person:P-1"),
            _fact("t1", "InstallOrder:O-1", "related_to", "InstallOrder:O-2"),
            _fact("t1", "Person:P-1", "member_of", "Team:T-1"),
            _fact("t2", "InstallOrder:O-1", "assigned_to", "Person:P-SECRET"),
        ]
    )


@pytest.mark.asyncio
async def test_entity_acl_drops_denied_neighbor(ledger, aiplat_home):
    set_entity_acl(
        "lock-service",
        "O-2",
        deny_roles={"viewer": ["read"]},
        allow_roles={"admin": ["*"]},
    )
    out = await traverse_links(
        {
            "start_id": "InstallOrder:O-1",
            "domain_id": "lock-service",
            "max_hops": 2,
        },
        tenant_id="t1",
        permissions=["kb:read"],
        role="viewer",
        ledger=ledger,
    )
    assert out["status"] == "ok", out
    ids = {n.get("id") for n in out["nodes"]}
    assert "O-1" in ids
    assert "O-2" not in ids
    assert out.get("acl_dropped", 0) >= 1
    for e in out["edges"]:
        assert "O-2" not in e.get("from", "")
        assert "O-2" not in e.get("to", "")


@pytest.mark.asyncio
async def test_denied_start_returns_empty(ledger, aiplat_home):
    set_entity_acl(
        "lock-service",
        "O-1",
        deny_roles={"viewer": ["read"]},
        allow_roles={"admin": ["*"]},
    )
    out = await traverse_links(
        {"start_id": "InstallOrder:O-1", "domain_id": "lock-service"},
        tenant_id="t1",
        permissions=["kb:read"],
        role="viewer",
        ledger=ledger,
    )
    assert out["status"] == "ok"
    assert out["nodes"] == []
    assert out["edges"] == []
    assert out.get("acl_denied_start") is True


@pytest.mark.asyncio
async def test_admin_sees_denied_for_viewer(ledger, aiplat_home):
    set_entity_acl(
        "lock-service",
        "O-2",
        deny_roles={"viewer": ["read"]},
        allow_roles={"admin": ["*"]},
    )
    out = await traverse_links(
        {
            "start_id": "InstallOrder:O-1",
            "domain_id": "lock-service",
            "max_hops": 1,
        },
        tenant_id="t1",
        permissions=["kb:read"],
        role="admin",
        ledger=ledger,
    )
    assert out["status"] == "ok"
    ids = {n.get("id") for n in out["nodes"]}
    assert "O-2" in ids


@pytest.mark.asyncio
async def test_field_acl_redacts_node(ledger, aiplat_home):
    set_field_acl(
        "lock-service",
        "O-1",
        "object_type",
        visibility="role:admin",
        redaction="mask",
        replace_with="***",
    )
    out = await traverse_links(
        {"start_id": "InstallOrder:O-1", "domain_id": "lock-service", "max_hops": 1},
        tenant_id="t1",
        permissions=["kb:read"],
        role="viewer",
        ledger=ledger,
    )
    assert out["status"] == "ok"
    start = next(n for n in out["nodes"] if n.get("id") == "O-1")
    assert start.get("object_type") == "***"


@pytest.mark.asyncio
async def test_cross_tenant_zero_leak_with_acl(ledger, aiplat_home):
    """租户隔离优先；role 不得读到他租户边。"""
    out = await traverse_links(
        {"start_id": "InstallOrder:O-1", "domain_id": "lock-service", "max_hops": 2},
        tenant_id="t1",
        permissions=["kb:read"],
        role="admin",
        ledger=ledger,
    )
    assert out["status"] == "ok"
    refs = {n.get("ref") for n in out["nodes"]}
    assert "Person:P-SECRET" not in refs
    for e in out["edges"]:
        assert "P-SECRET" not in e.get("to", "")
        assert "P-SECRET" not in e.get("from", "")
