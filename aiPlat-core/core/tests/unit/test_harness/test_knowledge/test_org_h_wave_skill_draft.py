"""H5 — draft pack lists only after human approve. No SKILL.md."""

from __future__ import annotations

from core.apps.org.service.org_skill_draft import (
    approve_skill_draft,
    create_skill_draft,
    reject_skill_draft,
)
from core.harness.knowledge.ontology_case_learning import OntologyCaseStore


def _candidate(tmp_path, monkeypatch) -> str:
    monkeypatch.setenv("AIPLAT_HOME", str(tmp_path))
    monkeypatch.setenv("AIPLAT_ONTOLOGY_CASE_LEARNING", "true")
    out = OntologyCaseStore("it-ops").record(
        title="closed alert",
        summary="success run",
        outcome="success",
        metadata={"skill_candidate": True, "trace_id": "t-h5"},
        case_id="case-h5",
        write_graph=False,
    )
    return str(out.get("case_id") or "case-h5")


def test_h5_draft_does_not_list(tmp_path, monkeypatch):
    cid = _candidate(tmp_path, monkeypatch)
    called = []

    def _reg(skill_id, name, description):
        called.append(skill_id)
        return True

    draft = create_skill_draft(role="operator", case_id=cid, domain_id="it-ops")
    assert draft["ok"] is True
    assert draft["listed"] is False
    assert draft["status"] == "draft"
    assert called == []
    assert not list((tmp_path).rglob("SKILL.md"))

    denied = approve_skill_draft(role="operator", draft_id=draft["draft_id"], register_fn=_reg)
    assert denied["reason"] == "approve_forbidden"
    assert called == []


def test_h5_approve_registers_once(tmp_path, monkeypatch):
    cid = _candidate(tmp_path, monkeypatch)
    called = []

    def _reg(skill_id, name, description):
        called.append((skill_id, name))
        return True

    draft = create_skill_draft(role="admin", case_id=cid, domain_id="it-ops")
    out = approve_skill_draft(role="admin", draft_id=draft["draft_id"], register_fn=_reg)
    assert out["ok"] is True
    assert out["listed"] is True
    assert out["auto_listed"] is False
    assert out["wrote_skill_md"] is False
    assert len(called) == 1
    again = approve_skill_draft(role="admin", draft_id=draft["draft_id"], register_fn=_reg)
    assert again["already"] is True
    assert len(called) == 1


def test_h5_reject_does_not_register(tmp_path, monkeypatch):
    cid = _candidate(tmp_path, monkeypatch)
    called = []
    draft = create_skill_draft(role="admin", case_id=cid, domain_id="it-ops")
    out = reject_skill_draft(role="admin", draft_id=draft["draft_id"])
    assert out["status"] == "rejected"
    assert out["listed"] is False
    denied = approve_skill_draft(
        role="admin",
        draft_id=draft["draft_id"],
        register_fn=lambda *a: called.append(a) or True,
    )
    assert denied["reason"] == "not_draft"
    assert called == []
