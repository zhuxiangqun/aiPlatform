"""P1: discardable interactive evidence page (template + JSON, TTL, read-only)."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

from core.harness.execution.run_evidence_page import (
    STATE_EVIDENCE_KEY,
    TEMPLATE_ID,
    build_run_evidence_page,
    collect_evidence_data,
    empty_evidence_metrics,
    is_evidence_expired,
    merge_evidence_metrics,
    render_evidence_html,
    verification_success,
    write_evidence_page,
)


def test_collect_evidence_from_stages():
    stages = [
        SimpleNamespace(
            id="pm",
            output_artifact="prd",
            depends_on=[],
            input_artifacts=[],
        ),
        SimpleNamespace(
            id="arch",
            output_artifact="architecture",
            depends_on=["pm"],
            input_artifacts=["prd"],
        ),
    ]
    state = {"phase": "done", "run_id": "r1", "prd": {"title": "x"}, "_handoff": {
        "prd": {"summary": "PRD ready", "known_issues": ["limit rate TBD"]}
    }}
    data = collect_evidence_data(state, stages=stages)
    assert data["phase"] == "done"
    assert data["run_id"] == "r1"
    assert any(i["key"] == "prd" and i["value"] == "present" for i in data["inputs"])
    assert any(c["artifact"] == "architecture" for c in data["conclusions"])
    assert any(e.get("snippet") == "PRD ready" for e in data["evidence"])
    assert any("limit rate" in u["text"] for u in data["uncertainties"])
    assert all(x.get("source_type") == "tool_result" for x in data["inputs"])
    assert all(x.get("source_type") == "tool_result" for x in data["conclusions"])


def test_build_html_is_template_injected_not_llm():
    payload = build_run_evidence_page(
        {"phase": "done", "stages": [{"id": "a", "output_artifact": "x"}]},
        stages=[{"id": "a", "output_artifact": "x", "depends_on": [], "input_artifacts": []}],
    )
    assert payload["schema_version"] == "evidence_page.v1"
    assert payload["template_id"] == TEMPLATE_ID
    assert payload["source_type"] == "tool_result"
    assert payload["read_only"] is True
    assert payload["can_trigger_coding"] is False
    assert payload["can_trigger_deploy"] is False
    assert "source_click" in payload["metrics_events"]
    assert "__EVIDENCE_JSON__" not in payload["html"]
    assert "aiplat_evidence_metric" in payload["html"]
    assert "fetch(" not in payload["html"]
    assert "XMLHttpRequest" not in payload["html"]


def test_ttl_expiry():
    created = datetime(2026, 1, 1, tzinfo=timezone.utc)
    payload = build_run_evidence_page({}, stages=[], ttl_hours=24, now=created)
    assert payload["expires_at"].startswith("2026-01-02")
    assert not is_evidence_expired(payload, now=created + timedelta(hours=1))
    assert is_evidence_expired(payload, now=created + timedelta(hours=25))


def test_write_and_render_escape():
    state: dict = {"phase": "failed", "error_message": "</script><img>"}
    written = write_evidence_page(
        state,
        stages=[{"id": "a", "output_artifact": "x", "input_artifacts": []}],
    )
    assert state[STATE_EVIDENCE_KEY] is written
    html = render_evidence_html(written)
    assert "</script><img>" not in html
    assert "\\u003c" in html or "<\\/" in html


def test_merge_evidence_metrics_and_verification():
    store = empty_evidence_metrics()
    assert verification_success(store) is False
    out = merge_evidence_metrics(
        store,
        events=["source_click", {"event": "input_change", "key": "prd"}, "bogus"],
    )
    assert out["counts"]["source_click"] == 1
    assert out["counts"]["input_change"] == 1
    assert out["counts"]["inconsistency_found"] == 0
    assert "bogus" not in out["counts"]
    assert out["total"] == 2
    assert out["verified"] is True
    assert out["accepted"] == 2
    assert verification_success(out) is True
    assert len(out["recent"]) == 2
    assert out["recent"][1]["detail"]["key"] == "prd"
