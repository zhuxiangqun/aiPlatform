"""S wave — baseline, domain pack, signoff progress. Never claims M4."""

from __future__ import annotations

from core.apps.org.service.domain_pack_install import install_domain_pack, list_domain_packs
from core.apps.org.service.org_field_ops import field_ops_checklist
from core.apps.org.service.org_signoff_progress import save_signoff_progress
from core.apps.org.service.org_value_translation import load_value_baseline, save_value_baseline


def test_s2_baseline_tenant_isolated(tmp_path, monkeypatch):
    monkeypatch.setenv("AIPLAT_HOME", str(tmp_path))
    out = save_value_baseline(
        role="operator",
        tenant_id="acme",
        baseline_minutes_per_incident=30,
        baseline_mtta_seconds=900,
    )
    assert out["ok"] is True
    assert out["m4_claim_allowed"] is False
    loaded = load_value_baseline(tenant_id="acme")
    assert loaded["baseline_source"] == "customer_provided"
    assert loaded["baseline_minutes_per_incident"] == 30
    other = load_value_baseline(tenant_id="other")
    assert other["baseline_source"] != "customer_provided" or other.get("tenant_id") != "acme"
    denied = save_value_baseline(
        role="",
        tenant_id="acme",
        baseline_minutes_per_incident=1,
        baseline_mtta_seconds=1,
    )
    assert denied["reason"] == "identity_missing"


def test_s3_install_alert_pack(tmp_path, monkeypatch):
    monkeypatch.setenv("AIPLAT_HOME", str(tmp_path))

    def _noop(self, *args, **kwargs):
        return {"ok": True}

    monkeypatch.setattr(
        "core.harness.knowledge.domain_router.DomainRouter.register_domain",
        _noop,
    )
    catalog = list_domain_packs()
    ids = {i["template_id"] for i in catalog["items"]}
    assert "alert_triage" in ids
    out = install_domain_pack(
        role="admin",
        template_id="alert_triage",
        domain_id="demo-ops",
        display_name="Demo Ops",
    )
    assert out["ok"] is True
    assert out["m4_claim_allowed"] is False
    assert (tmp_path / "ontologies" / "demo-ops.yaml").is_file()
    text = (tmp_path / "ontologies" / "demo-ops.yaml").read_text(encoding="utf-8")
    assert "demo-ops" in text
    assert "{{domain_id}}" not in text
    assert out["action_scaffold"] == "draft"
    assert out["registered_action"] is False
    assert out["wrote_live_actions"] is False
    draft = tmp_path / "org" / "action_drafts" / "demo-ops.yaml"
    assert draft.is_file()
    body = draft.read_text(encoding="utf-8")
    assert "customer_action:demo-ops:triage_scaffold" in body
    assert "status: draft" in body
    assert not (tmp_path / "actions").exists()


def test_s4_oncall_does_not_claim(tmp_path, monkeypatch):
    monkeypatch.setenv("AIPLAT_HOME", str(tmp_path))
    out = save_signoff_progress(
        role="admin",
        body={"oncall_name": "张三", "oncall_contact": "13800000000"},
    )
    assert out["ok"] is True
    assert out["m4_claim_allowed"] is False
    assert out["oncall_ok"] is True
    cl = field_ops_checklist("it-ops")
    assert cl["m4_claim_allowed"] is False
    oncall = next(i for i in cl["items"] if i["id"] == "oncall")
    assert oncall["ok"] is True
