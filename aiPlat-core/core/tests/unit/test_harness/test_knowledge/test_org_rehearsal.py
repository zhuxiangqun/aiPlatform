"""Sandbox rehearsal logs a handoff. It does not start a fleet."""

from __future__ import annotations

import pytest

from core.apps.org.service.org_fleet import (
    list_sandbox_rehearsals,
    probe_sandbox_conflict,
    start_sandbox_rehearsal,
)
from core.harness.execution.stage_handoff import HANDOFF_FIELDS


@pytest.mark.asyncio
async def test_conflict_probe_denies_second_holder(tmp_path, monkeypatch):
    monkeypatch.setenv("AIPLAT_HOME", str(tmp_path))
    out = await probe_sandbox_conflict("it-ops", resource_id="iface-1")
    assert out["ok"] is True
    assert out["concurrent_conflict"] is True
    assert out["attempts"][0]["acquired"] is True
    assert out["attempts"][1]["acquired"] is False
    assert out["attempts"][1]["result"] == "concurrent_conflict"
    assert out["wrote_live_yaml"] is False
    assert out["fleet_started"] is False


@pytest.mark.asyncio
async def test_rehearsal_does_not_start_fleet(tmp_path, monkeypatch):
    monkeypatch.setenv("AIPLAT_HOME", str(tmp_path))

    def _dry(*args, **kwargs):
        assert kwargs.get("dry_actions") is True
        return {"run_id": "run-test", "status": "needs_hitl"}

    monkeypatch.setattr("core.apps.org.service.org_runtime.run_org_goal", _dry)
    denied = await start_sandbox_rehearsal(role="", domain_id="it-ops", roles=["a", "b"])
    assert denied["reason"] == "identity_missing"
    assert denied["fleet_started"] is False

    short = await start_sandbox_rehearsal(role="admin", domain_id="it-ops", roles=["only"])
    assert short["reason"] == "roles_invalid"

    out = await start_sandbox_rehearsal(
        role="operator",
        domain_id="it-ops",
        roles=["分诊", "诊断", "报告"],
    )
    assert out["ok"] is True
    assert out["fleet_started"] is False
    assert out["wrote_live_yaml"] is False
    assert out["peer_execute"] is False
    assert out["allow_fleet_changed"] is False
    assert out["m4_claim_allowed"] is False
    assert out["run_id"] == "run-test"
    assert len(out["hops"]) == 3
    assert set(HANDOFF_FIELDS) <= set(out["hops"][0]["handoff"])
    assert out["hops"][0]["contract"]["on_out_of_scope"] == "deny"
    assert "peer_execute" in out["hops"][0]["contract"]["out_of_scope"]
    assert out["hops"][1]["contract"]["context_slice"]
    assert out["conflict_probe"]["concurrent_conflict"] is True
    assert not (tmp_path / "actions").exists()
    listed = list_sandbox_rehearsals()
    assert listed["count"] == 1
    assert listed["items"][0]["fleet_started"] is False
    assert listed["items"][0]["conflict_probe"]["concurrent_conflict"] is True
