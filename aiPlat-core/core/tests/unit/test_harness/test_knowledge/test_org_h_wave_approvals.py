"""H1 — approval inbox and snapshots are read-only."""

from __future__ import annotations

import pytest

from core.apps.fde.service.k_wave_arbit import propose_ticket
from core.apps.org.service.org_approvals import get_approval_snapshot, list_approval_inbox
from core.harness.knowledge.versioned_ontology_store import VersionedOntologyStore


@pytest.mark.asyncio
async def test_empty_role_denied(tmp_path, monkeypatch):
    monkeypatch.setenv("AIPLAT_HOME", str(tmp_path))
    out = await list_approval_inbox(role="")
    assert out["ok"] is False
    assert out["reason"] == "identity_missing"


@pytest.mark.asyncio
async def test_inbox_lists_arbitration_and_paginates(tmp_path, monkeypatch):
    monkeypatch.setenv("AIPLAT_HOME", str(tmp_path))
    for i in range(3):
        propose_ticket(
            left_id=f"L{i}",
            right_id=f"R{i}",
            left_domain="it-ops",
            right_domain="data-gov",
            confidence=0.9,
            strategy="exact",
            suggested="merge",
            trace_id=f"trace-{i}",
        )
    page = await list_approval_inbox(role="operator", domain_id="it-ops", limit=2, offset=0)
    assert page["ok"] is True
    assert page["writable"] is False
    assert page["limit"] == 2
    assert page["total"] >= 3
    assert len(page["items"]) == 2
    assert page["has_more"] is True
    assert all(i["kind"] == "arbitration" for i in page["items"])


@pytest.mark.asyncio
async def test_snapshot_redacts_for_non_approver(tmp_path, monkeypatch):
    monkeypatch.setenv("AIPLAT_HOME", str(tmp_path))
    t = propose_ticket(
        left_id="A",
        right_id="B",
        left_domain="it-ops",
        right_domain="data-gov",
        confidence=1.0,
        strategy="exact",
        suggested="merge",
        trace_id="trace-snap",
    )
    masked = await get_approval_snapshot("arbitration", t["ticket_id"], role="operator")
    assert masked["ok"] is True
    assert masked["redacted"] is True
    assert masked["snapshot"]["trace_id"] == "trace-snap"
    assert masked["snapshot"]["edge_before"] == "该信息未发生"

    full = await get_approval_snapshot("arbitration", t["ticket_id"], role="admin")
    assert full["redacted"] is False
    assert full["full_view"] is True


@pytest.mark.asyncio
async def test_proposal_snapshot_includes_diff_without_write(tmp_path, monkeypatch):
    monkeypatch.setenv("AIPLAT_HOME", str(tmp_path))
    ont = tmp_path / "ontologies"
    ont.mkdir()
    (ont / "demo-ops.yaml").write_text(
        "name: demo\nclasses:\n  Alert:\n    label: 告警\n    tier: core\n",
        encoding="utf-8",
    )

    rows: dict = {}

    class FakeStore:
        async def initialize(self):
            return None

        async def insert_ontology_proposal(self, **kwargs):
            pid = kwargs["proposal_id"]
            rows[pid] = {
                "proposal_id": pid,
                "domain_id": kwargs["domain_id"],
                "status": kwargs["status"],
                "author": kwargs["author"],
                "changes": kwargs["changes"],
                "impact_analysis": kwargs["impact"],
                "created_at": "2026-09-20T00:00:00Z",
            }
            return pid

        async def list_ontology_proposals(self, domain_id=""):
            return [r for r in rows.values() if not domain_id or r["domain_id"] == domain_id]

        async def get_ontology_proposal(self, proposal_id):
            return rows.get(proposal_id)

    monkeypatch.setattr(
        "core.harness.infrastructure.action_store.ActionStore",
        lambda *a, **k: FakeStore(),
    )

    prop_id = await VersionedOntologyStore("demo-ops").create_proposal(
        {
            "add": {"class": {"name": "RepeatFail_fetch", "label": "RF", "tier": "edge"}},
            "source": {"kind": "schema_gap", "case_id": "c1", "auto_apply": False},
        },
        author="schema-gap",
    )
    inbox = await list_approval_inbox(role="operator", domain_id="demo-ops", kind="proposal")
    assert inbox["ok"] is True
    assert any(i["id"] == prop_id and "schema_gap" in str(i.get("summary")) for i in inbox["items"])

    masked = await get_approval_snapshot("proposal", prop_id, role="operator", domain_id="demo-ops")
    assert masked["ok"] is True
    assert masked["writable"] is False
    snap = masked["snapshot"]
    assert snap["source_kind"] == "schema_gap"
    assert snap["wrote_live_yaml"] is False
    assert snap["diff"]["count"] >= 1
    assert snap["diff"].get("redacted_values") is True
    assert all("before" not in c for c in snap["diff"]["changes"])

    full = await get_approval_snapshot("proposal", prop_id, role="admin", domain_id="demo-ops")
    assert full["snapshot"]["diff"]["count"] >= 1
    assert any(c.get("path") == "classes.RepeatFail_fetch" for c in full["snapshot"]["diff"]["changes"])
    assert not (tmp_path / "ontologies" / "demo-ops_v1.yaml").exists()
