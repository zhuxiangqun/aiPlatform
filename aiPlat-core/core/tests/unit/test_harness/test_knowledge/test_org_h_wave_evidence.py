"""H2 — evidence pack is read-only and not a signature."""

from __future__ import annotations

from core.apps.org.service.org_evidence_pack import build_evidence_pack
from core.apps.org.service.org_runtime import ensure_pilot_goal, run_org_goal


def test_pack_requires_identity(tmp_path, monkeypatch):
    monkeypatch.setenv("AIPLAT_HOME", str(tmp_path))
    out = build_evidence_pack(role="")
    assert out["ok"] is False
    assert out["reason"] == "identity_missing"


def test_pack_is_not_signoff_and_caps_traces(tmp_path, monkeypatch):
    monkeypatch.setenv("AIPLAT_HOME", str(tmp_path))
    monkeypatch.delenv("AIPLAT_ONTOLOGY_EDGE_AUTO_APPLY", raising=False)
    ensure_pilot_goal("it-ops")
    for _ in range(3):
        run_org_goal("goal-it-ops-alert-sla", domain_id="it-ops", dry_actions=True)

    out = build_evidence_pack(
        role="operator",
        domain_id="it-ops",
        max_traces=99,
        as_markdown=True,
    )
    assert out["ok"] is True
    assert out["writable"] is False
    assert out["m4_claim_allowed"] is False
    assert out["signoff_button"] is False
    assert out["sandbox_mode"] is False
    assert "不是签字" in out["cover_statement"]
    assert out["usage"]["billing"] is None
    assert out["trace_limit_cap"] == 5
    assert len(out["trace_summaries"]) <= 5
    assert out["blank_sign_table"]
    assert all(not row.get("customer") for row in out["blank_sign_table"])
    assert "markdown" in out
    assert "不是签字" in out["markdown"]
    assert out["value_translation"]["baseline_missing"] is True
    assert out["value_translation"]["saved_person_hours"] is None
    assert "可审计收益" in out["markdown"]
