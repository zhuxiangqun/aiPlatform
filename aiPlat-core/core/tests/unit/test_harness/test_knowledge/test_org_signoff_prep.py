"""Signoff prep is read-only and never flips m4_claim_allowed."""

from __future__ import annotations

from core.apps.org.service.org_field_ops import signoff_prep_view
from core.apps.org.service.org_signoff_progress import save_signoff_progress
from core.apps.org.service.org_value_translation import save_value_baseline


def test_signoff_prep_never_allows_claim(tmp_path, monkeypatch):
    monkeypatch.setenv("AIPLAT_HOME", str(tmp_path))
    monkeypatch.setenv("AIPLAT_ORG_IO_MODE", "sandbox")
    out = signoff_prep_view("it-ops")
    assert out["ok"] is True
    assert out["m4_claim_allowed"] is False
    assert out["signoff_button"] is False
    assert out["wrote_live_yaml"] is False
    assert "/" in out["prep_score"]
    assert out["prep_score"].endswith("/8")


def test_signoff_prep_counts_baseline_and_oncall(tmp_path, monkeypatch):
    monkeypatch.setenv("AIPLAT_HOME", str(tmp_path))
    monkeypatch.setenv("AIPLAT_ORG_IO_MODE", "sandbox")
    save_signoff_progress(
        role="admin",
        body={"oncall_name": "值班甲", "oncall_contact": "a@example.com"},
    )
    save_value_baseline(
        role="admin",
        tenant_id="default",
        baseline_minutes_per_incident=30,
        baseline_mtta_seconds=900,
    )
    out = signoff_prep_view("it-ops")
    assert out["m4_claim_allowed"] is False
    by_id = {g["id"]: g for g in out["gates"]}
    assert by_id["oncall"]["ok"] is True
    assert by_id["baseline"]["ok"] is True
    assert by_id["rollback_drill"]["ok"] is False


def test_signoff_prep_counts_rollback_drill(tmp_path, monkeypatch):
    monkeypatch.setenv("AIPLAT_HOME", str(tmp_path))
    monkeypatch.setenv("AIPLAT_ORG_IO_MODE", "sandbox")
    save_signoff_progress(
        role="admin",
        body={"rollback_drill_done": True, "rollback_drill_notes": "manual"},
    )
    out = signoff_prep_view("it-ops")
    assert out["m4_claim_allowed"] is False
    by_id = {g["id"]: g for g in out["gates"]}
    assert by_id["rollback_drill"]["ok"] is True
    assert by_id["rollback_drill"]["detail"]


def test_signoff_prep_markdown_export_not_signature(tmp_path, monkeypatch):
    monkeypatch.setenv("AIPLAT_HOME", str(tmp_path))
    monkeypatch.setenv("AIPLAT_ORG_IO_MODE", "sandbox")
    out = signoff_prep_view("it-ops", as_markdown=True)
    assert out["m4_claim_allowed"] is False
    assert out["signoff_button"] is False
    md = out.get("markdown") or ""
    assert "不是签字" in md
    assert "m4_claim_allowed" in md
    assert "[ ]" in md or "[x]" in md
    assert "八闸门" in md
    assert "签收剧本" in md
    assert out.get("cover_statement")
    by_id = {g["id"]: g for g in out["gates"]}
    assert "kpis_visible" in by_id
    assert "inbox_readable" in by_id
    assert by_id["inbox_readable"]["ok"] is True
    assert by_id["baseline"]["how_to"]
    assert by_id["baseline"]["ui_anchor"] == "value-section"
    assert len(out.get("playbook") or []) >= 6
