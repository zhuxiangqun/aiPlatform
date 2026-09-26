"""H3 — value translation is honest about missing baseline."""

from __future__ import annotations

from pathlib import Path

from core.apps.org.service.org_runtime import ensure_pilot_goal, run_org_goal
from core.apps.org.service.org_value_translation import (
    load_value_baseline,
    translate_org_value,
)


def test_missing_baseline_hides_savings(tmp_path, monkeypatch):
    monkeypatch.setenv("AIPLAT_HOME", str(tmp_path))
    ensure_pilot_goal("it-ops")
    run_org_goal("goal-it-ops-alert-sla", domain_id="it-ops", dry_actions=True)

    out = translate_org_value(domain_id="it-ops", tenant_id="t-a")
    assert out["ok"] is True
    assert out["writable"] is False
    assert out["m4_claim_allowed"] is False
    assert out["signoff_button"] is False
    assert out["baseline_source"] == "missing"
    assert out["baseline_missing"] is True
    assert out["saved_person_hours"] is None
    assert out["mtta_delta_seconds"] is None
    assert "platform_kpis" in out


def test_tenant_baseline_isolated_and_recomputable(tmp_path, monkeypatch):
    monkeypatch.setenv("AIPLAT_HOME", str(tmp_path))
    monkeypatch.delenv("AIPLAT_ONTOLOGY_EDGE_AUTO_APPLY", raising=False)
    ensure_pilot_goal("it-ops")
    for _ in range(2):
        run_org_goal("goal-it-ops-alert-sla", domain_id="it-ops", dry_actions=True)

    # Tenant B must not see tenant A's baseline
    a_dir = Path(tmp_path) / "org" / "tenants" / "tenant-a"
    a_dir.mkdir(parents=True)
    (a_dir / "value_baseline.yaml").write_text(
        "baseline_minutes_per_incident: 30\nbaseline_mtta_seconds: 900\n",
        encoding="utf-8",
    )

    missing_b = load_value_baseline(tenant_id="tenant-b")
    assert missing_b["baseline_source"] == "missing"

    out_a = translate_org_value(domain_id="it-ops", tenant_id="tenant-a")
    assert out_a["baseline_source"] == "customer_provided"
    assert out_a["baseline_missing"] is False
    closed = int(out_a["platform_kpis"]["closed_runs"])
    # dry HITL runs are usually needs_hitl → closed may be 0; still formula-safe
    if closed > 0:
        assert out_a["saved_person_hours"] == round(closed * 30 / 60.0, 4)
    else:
        assert out_a["saved_person_hours"] == 0.0

    # Force a succeeded run count via platform default file when tenant empty
    plat = Path(tmp_path) / "org"
    plat.mkdir(parents=True, exist_ok=True)
    (plat / "value_baseline.yaml").write_text(
        "baseline_minutes_per_incident: 60\n",
        encoding="utf-8",
    )
    out_plat = translate_org_value(domain_id="it-ops", tenant_id="")
    assert out_plat["baseline_source"] == "platform_default"
    assert out_plat["saved_person_hours"] is not None


def test_roi_preview_is_simulation_never_writes(tmp_path, monkeypatch):
    monkeypatch.setenv("AIPLAT_HOME", str(tmp_path))
    ensure_pilot_goal("it-ops")
    run_org_goal("goal-it-ops-alert-sla", domain_id="it-ops", dry_actions=True)

    from core.apps.org.service.org_value_translation import preview_value_roi

    out = preview_value_roi(
        domain_id="it-ops",
        trial_minutes_per_incident=30,
        trial_mtta_seconds=900,
    )
    assert out["ok"] is True
    assert out["simulation"] is True
    assert out["baseline_source"] == "what_if"
    assert out["baseline_missing"] is True
    assert out["wrote_baseline"] is False
    assert out["m4_claim_allowed"] is False
    assert out["saved_person_hours"] is not None
    assert load_value_baseline(tenant_id="default")["baseline_source"] == "missing"
    assert not (Path(tmp_path) / "org" / "tenants" / "default" / "value_baseline.yaml").exists()
