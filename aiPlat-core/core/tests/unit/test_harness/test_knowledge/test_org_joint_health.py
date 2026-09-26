"""Joint health is a read-only count. It does not write YAML."""

from __future__ import annotations

from core.apps.org.service.org_kpi import joint_health_view
from core.harness.knowledge.ontology_case_learning import OntologyCaseStore


def test_joint_health_hides_coverage_without_cases(tmp_path, monkeypatch):
    monkeypatch.setenv("AIPLAT_HOME", str(tmp_path))
    out = joint_health_view("demo-ops")
    assert out["ok"] is True
    assert out["semantic_coverage"] is None
    assert out["wrote_live_yaml"] is False
    assert out["fleet_started"] is False
    assert out["m4_claim_allowed"] is False
    assert out["action_drafts_registered"] is False
    assert not (tmp_path / "actions").exists()


def test_joint_health_counts_cases_and_previews(tmp_path, monkeypatch):
    monkeypatch.setenv("AIPLAT_HOME", str(tmp_path))
    store = OntologyCaseStore("demo-ops")
    store.record(title="ok", summary="explained", outcome="success", reward=0.9, case_id="c-ok")
    store.record(
        title="gap",
        summary="missing",
        outcome="failure",
        reward=0.1,
        case_id="c-gap",
        metadata={"schema_gap": True},
    )
    prev = tmp_path / "org" / "event_previews"
    prev.mkdir(parents=True)
    (prev / "prev-1.json").write_text("{}", encoding="utf-8")

    out = joint_health_view("demo-ops")
    assert out["explained_count"] == 1
    assert out["schema_gap_count"] == 1
    assert out["semantic_coverage"] == 0.5
    assert out["event_preview_count"] == 1
    assert out["cold_archived_count"] == 0
    assert out["wrote_live_yaml"] is False
    assert out["context_hit_rate"] is None


def test_context_hit_rate_counts_feedback_only():
    from core.harness.knowledge.ontology_case_learning import context_hit_rate

    blank = context_hit_rate([{"serve_count": 0, "feedback_count": 4}])
    assert blank["hit_rate"] is None
    assert blank["wrote_live_yaml"] is False
    rated = context_hit_rate(
        [
            {"serve_count": 2, "feedback_count": 1},
            {"serve_count": 3, "feedback_count": 0},
        ]
    )
    assert rated["served"] == 2
    assert rated["used"] == 1
    assert rated["hit_rate"] == 0.5
