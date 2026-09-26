"""V5 — rollback boundary is stated. Local drafts and edges are not rolled back."""

from __future__ import annotations

from core.apps.fde.service.k_wave_rollback import rollback_scope
from core.harness.knowledge.ontology_case_learning import (
    OntologyCaseStore,
    rollback_case_evolution,
)
from core.harness.knowledge.versioned_ontology_store import VersionedOntologyStore


def test_scope_lists_both_columns():
    scope = rollback_scope()
    assert scope["can_rollback"]
    assert any("VersionedOntologyStore" in line for line in scope["can_rollback"])
    joined = " ".join(scope["cannot_rollback"])
    assert "draft_local_" in joined
    assert "k5_local_" in joined
    assert "edge_before" in joined
    assert any("edge_before" in line for line in scope["can_rollback"])
    assert scope["covers_edges"] is False
    assert scope["covers_local_drafts"] is False
    assert scope["one_click_any_change"] is False


async def test_local_drafts_are_not_rolled_back(tmp_path, monkeypatch):
    monkeypatch.setenv("AIPLAT_HOME", str(tmp_path))

    def _boom(*_a, **_k):
        raise AssertionError("rollback_proposal")

    monkeypatch.setattr(VersionedOntologyStore, "rollback_proposal", _boom)
    store = OntologyCaseStore("it-ops")
    rec = store.record(
        title="draft",
        summary="local",
        outcome="failure",
        action_id="fetch",
        metadata={"skill_candidate": False},
        write_graph=False,
    )
    cases = store._load()
    cases[rec["case_id"]].proposal_id = "k5_local_abc"
    store._save(cases)
    out = await rollback_case_evolution(rec["case_id"])
    assert out["ok"] is False
    assert out["reason"] == "local_draft_not_applied"

    bare = store.record(
        title="bare",
        summary="none",
        outcome="partial",
        action_id="fetch",
        write_graph=False,
    )
    missing = await rollback_case_evolution(bare["case_id"])
    assert missing["ok"] is False
    assert missing["reason"] == "no_proposal"
