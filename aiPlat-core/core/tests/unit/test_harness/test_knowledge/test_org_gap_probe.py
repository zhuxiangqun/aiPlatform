"""Sandbox feedback probes. Never write live YAML or SKILL.md."""

from __future__ import annotations

from core.apps.fde.service.k_wave_case import record_case_from_org_run
from core.apps.org.service.org_skill_draft import assemble_skill_bundle, create_skill_draft, list_action_gap_hints
from core.apps.org.service.v_wave_replay import replay_org_trace
from core.harness.knowledge.ontology_case_learning import OntologyCaseStore


def test_replay_marks_schema_gap_without_yaml(tmp_path, monkeypatch):
    monkeypatch.setenv("AIPLAT_HOME", str(tmp_path))
    monkeypatch.setenv("AIPLAT_ONTOLOGY_CASE_LEARNING", "true")
    before = list((tmp_path / "ontologies").glob("*.yaml")) if (tmp_path / "ontologies").exists() else []
    record_case_from_org_run(
        {
            "domain_id": "it-ops",
            "run_id": "run-gap",
            "trace_id": "trace-gap",
            "trace_origin": "run",
            "status": "failed",
            "goal_id": "g1",
        }
    )
    out = replay_org_trace("trace-gap", domain_id="it-ops")
    assert out["wrote_live_yaml"] is False
    assert out["schema_gaps"]
    assert out["schema_gaps"][0]["schema_gap"] is True
    after = list((tmp_path / "ontologies").glob("*.yaml")) if (tmp_path / "ontologies").exists() else []
    assert before == after


def test_repeat_action_hint_only(tmp_path, monkeypatch):
    monkeypatch.setenv("AIPLAT_HOME", str(tmp_path))
    monkeypatch.setenv("AIPLAT_ONTOLOGY_CASE_LEARNING", "true")
    store = OntologyCaseStore("it-ops")
    for i in range(2):
        store.record(
            title=f"fail {i}",
            summary="rejected",
            outcome="failure",
            action_id="triage_alert",
            case_id=f"c{i}",
            metadata={"schema_gap": True},
            write_graph=False,
        )
    hints = list_action_gap_hints(domain_id="it-ops")
    assert hints["wrote_live_yaml"] is False
    assert hints["items"][0]["action_id"] == "triage_alert"
    assert hints["items"][0]["can_draft_proposal"] is True


def test_bundle_existing_drafts_no_skill_md(tmp_path, monkeypatch):
    monkeypatch.setenv("AIPLAT_HOME", str(tmp_path))
    monkeypatch.setenv("AIPLAT_ONTOLOGY_CASE_LEARNING", "true")
    OntologyCaseStore("it-ops").record(
        title="ok run",
        summary="success",
        outcome="success",
        case_id="case-ok",
        metadata={"skill_candidate": True},
        write_graph=False,
    )
    d1 = create_skill_draft(role="admin", case_id="case-ok", domain_id="it-ops")
    out = assemble_skill_bundle(role="admin", draft_ids=[d1["draft_id"]])
    assert out["ok"] is True
    assert out["wrote_skill_md"] is False
    assert out["listed"] is False
    assert out["kind"] == "bundle"
    assert not list(tmp_path.rglob("SKILL.md"))
