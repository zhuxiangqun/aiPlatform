"""Phase 1b: DomainRouter hard gate + fde_delivery_v1 HITL session (≥2 approve)."""

from __future__ import annotations

import pytest

from core.apps.fde.service.delivery_pipeline_session import (
    approve_delivery_session,
    get_delivery_session,
    load_delivery_template,
    start_delivery_session,
)
from core.harness.knowledge.domain_router import DomainRouter


def test_require_known_domain_accepts_tracking():
    r = DomainRouter()
    assert r.require_known_domain(r.tracking_domain()) == r.PLATFORM_TRACKING_DOMAIN


def test_require_known_domain_rejects_unknown():
    r = DomainRouter()
    with pytest.raises(ValueError, match="unknown domain_id"):
        r.require_known_domain("not-a-real-domain-xyz-phase1b")


def test_load_delivery_template_from_workspace_seed(monkeypatch, tmp_path):
    """When AIPLAT_HOME has no template, fall back to workspace_seeds."""
    monkeypatch.setenv("AIPLAT_HOME", str(tmp_path / "empty_home"))
    tpl = load_delivery_template("fde_delivery_v1")
    stages = tpl.get("stages") or []
    assert len(stages) >= 4
    hitl_stages = [s for s in stages if s.get("hitl")]
    assert len(hitl_stages) >= 2


def test_delivery_session_two_hitl_approves_and_reload(monkeypatch, tmp_path):
    """HITL hard acceptance: ≥2 pause/approve; progress from server; reload consistent."""
    home = tmp_path / "aiplat_home"
    home.mkdir()
    monkeypatch.setenv("AIPLAT_HOME", str(home))

    session = start_delivery_session(
        template_id="fde_delivery_v1",
        customer_name="phase1b-demo",
        domain_id="",
        actor="fde_engineer",
    )
    assert session["phase"] == "paused"
    assert session["progress_pct"] == 0
    assert session["honesty"]["mode"] == "template_session"
    sid = session["session_id"]

    # approve #1 → next HITL
    s1 = approve_delivery_session(sid, feedback="ok-ba")
    assert s1["phase"] == "paused"
    assert len(s1["hitl_events"]) >= 1
    assert any(e.get("action") == "approve" for e in s1["hitl_events"])
    assert s1["progress_pct"] > 0

    # approve #2 → either next HITL or done (engineer auto-skipped)
    s2 = approve_delivery_session(sid, feedback="ok-sa")
    assert len([e for e in s2["hitl_events"] if e.get("action") == "approve"]) >= 2
    # non-HITL engineer should be auto-advanced
    assert any(e.get("action") == "auto_advance_non_hitl" for e in s2["hitl_events"]) or s2["phase"] in {
        "paused",
        "done",
    }

    # refresh / reload consistency
    reloaded = get_delivery_session(sid)
    assert reloaded is not None
    assert reloaded["session_id"] == sid
    assert reloaded["progress_pct"] == s2["progress_pct"]
    assert reloaded["phase"] == s2["phase"]
    assert len(reloaded["hitl_events"]) == len(s2["hitl_events"])

    # optional: drive to done with one more approve if still paused
    if reloaded["phase"] == "paused":
        s3 = approve_delivery_session(sid, feedback="ok-dm")
        assert s3["phase"] == "done"
        assert s3["progress_pct"] == 100
        assert get_delivery_session(sid)["phase"] == "done"


def test_domain_router_tracking_constant_is_sole():
    assert DomainRouter.PLATFORM_TRACKING_DOMAIN == "fde-delivery"
    assert DomainRouter().tracking_domain() == "fde-delivery"
