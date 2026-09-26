"""V4 — PolicyGate once. Approve does not write live YAML. K5 does not auto-apply."""

from __future__ import annotations

import json

from core.apps.fde.service.k_wave_approve import approve_proposal_once
from core.apps.fde.service.k_wave_propose import enqueue_repeat_failure_proposals
from core.apps.fde.service.k_wave_signal import live_yaml_hash
from core.harness.infrastructure.gates.policy_gate import PolicyDecision, PolicyGate
from core.harness.knowledge.versioned_ontology_store import VersionedOntologyStore


def test_empty_identity_denied():
    decision = PolicyGate().decide_ontology_approval("", "edge")
    assert decision.decision == PolicyDecision.DENY
    assert decision.reason == "identity_missing"


def test_core_operator_denied():
    decision = PolicyGate().decide_ontology_approval("operator", "core")
    assert decision.decision == PolicyDecision.DENY
    assert decision.reason == "role_not_in_tier"


class _Store:
    def __init__(self):
        self.proposal = {
            "domain_id": "it-ops",
            "status": "draft",
            "impact_analysis": json.dumps({"max_tier": "core"}),
        }

    async def initialize(self):
        return None

    async def get_ontology_proposal(self, _pid):
        return self.proposal


class _Version:
    def __init__(self, _domain):
        self.calls = 0

    async def approve_proposal(self, proposal_id, approver_role="", *, gate_passed=False):
        self.calls += 1
        assert gate_passed is True
        assert approver_role == "admin"
        return {"success": True, "status": "approved", "tier": "core"}


async def test_denied_does_not_record_or_write_yaml(tmp_path, monkeypatch):
    monkeypatch.setenv("AIPLAT_HOME", str(tmp_path))
    yaml_path = tmp_path / "ontologies" / "it-ops.yaml"
    yaml_path.parent.mkdir(parents=True)
    yaml_path.write_text("domain: it-ops\n", encoding="utf-8")
    before = live_yaml_hash("it-ops")
    monkeypatch.setattr(
        "core.harness.infrastructure.action_store.ActionStore",
        _Store,
    )
    out = await approve_proposal_once("prop-1", role="operator")
    assert out["success"] is False
    assert out["reason"] == "role_not_in_tier"
    assert out["live_yaml_written"] is False
    assert live_yaml_hash("it-ops") == before


async def test_allowed_approve_leaves_yaml_hash(tmp_path, monkeypatch):
    monkeypatch.setenv("AIPLAT_HOME", str(tmp_path))
    yaml_path = tmp_path / "ontologies" / "it-ops.yaml"
    yaml_path.parent.mkdir(parents=True)
    yaml_path.write_text("domain: it-ops\n", encoding="utf-8")
    before = live_yaml_hash("it-ops")
    monkeypatch.setattr("core.harness.infrastructure.action_store.ActionStore", _Store)
    monkeypatch.setattr(
        "core.harness.knowledge.versioned_ontology_store.VersionedOntologyStore",
        _Version,
    )
    out = await approve_proposal_once("prop-1", role="admin")
    assert out["success"] is True
    assert out["live_yaml_unchanged"] is True
    assert live_yaml_hash("it-ops") == before
    assert yaml_path.read_text(encoding="utf-8") == "domain: it-ops\n"


async def test_k5_scan_does_not_call_auto_apply(tmp_path, monkeypatch):
    monkeypatch.setenv("AIPLAT_HOME", str(tmp_path))
    monkeypatch.delenv("AIPLAT_ONTOLOGY_EDGE_AUTO_APPLY", raising=False)

    def _boom(*_a, **_k):
        raise AssertionError("try_auto_apply_edge_proposal")

    monkeypatch.setattr(VersionedOntologyStore, "try_auto_apply_edge_proposal", _boom)
    out = await enqueue_repeat_failure_proposals("it-ops", writer=lambda _d, _c: "prop-k5")
    assert out["auto_apply"] is False
    assert out.get("reason") != "edge_auto_apply_forbidden"
