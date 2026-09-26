"""Schema-gap drafts reuse the K5 ledger and do not apply."""

from __future__ import annotations

import pytest

from core.apps.fde.service.k_wave_propose import draft_schema_gaps, preview_schema_gaps
from core.harness.knowledge.ontology_case_learning import OntologyCaseStore
from core.harness.knowledge.versioned_ontology_store import (
    json_change_diff,
    project_ontology_changes,
)


def test_project_ontology_changes_adds_class_without_write():
    before = {"classes": {"Alert": {"label": "告警", "tier": "core"}}}
    changes = {
        "add": {"class": {"name": "RepeatFail_fetch", "label": "RepeatFail_fetch", "tier": "edge"}},
        "source": {"auto_apply": False},
    }
    after = project_ontology_changes(before, changes)
    assert "RepeatFail_fetch" in after["classes"]
    assert "Alert" in before["classes"]
    assert "RepeatFail_fetch" not in before["classes"]
    diff = json_change_diff(before, after)
    assert diff["wrote_live_yaml"] is False
    assert any(c["path"] == "classes.RepeatFail_fetch" for c in diff["changes"])


def test_preview_schema_gaps_is_read_only(tmp_path, monkeypatch):
    monkeypatch.setenv("AIPLAT_HOME", str(tmp_path))
    store = OntologyCaseStore("demo-ops")
    store.record(
        title="gap",
        summary="missing field",
        outcome="failure",
        action_id="fetch_alert",
        case_id="gap-1",
        metadata={"schema_gap": True},
    )
    out = preview_schema_gaps("demo-ops")
    assert out["ok"] is True
    assert out["item_count"] == 1
    assert out["wrote_live_yaml"] is False
    assert out["items"][0]["class_name"].startswith("RepeatFail_")
    assert out["items"][0]["diff"]["count"] >= 1
    assert not (tmp_path / "k_wave").exists()
    assert not list((tmp_path / "ontologies").glob("*")) if (tmp_path / "ontologies").exists() else True


@pytest.mark.asyncio
async def test_schema_gap_draft_does_not_apply(tmp_path, monkeypatch):
    monkeypatch.setenv("AIPLAT_HOME", str(tmp_path))
    monkeypatch.delenv("AIPLAT_ONTOLOGY_EDGE_AUTO_APPLY", raising=False)
    store = OntologyCaseStore("demo-ops")
    store.record(
        title="gap",
        summary="missing field",
        outcome="failure",
        action_id="fetch_alert",
        case_id="gap-1",
        metadata={"schema_gap": True},
    )
    store.record(
        title="ok",
        summary="fine",
        outcome="success",
        action_id="fetch_alert",
        case_id="ok-1",
        metadata={"schema_gap": False},
    )

    def _writer(_domain, changes):
        assert changes["source"]["auto_apply"] is False
        assert changes["source"]["case_id"] == "gap-1"
        return "prop-gap"

    out = await draft_schema_gaps("demo-ops", writer=_writer)
    assert out["ok"] is True
    assert out["created_count"] == 1
    assert out["auto_apply"] is False
    assert out["applied"] is False
    assert out["wrote_live_yaml"] is False
    assert out["created"][0]["proposal_id"] == "prop-gap"
    assert not (tmp_path / "ontologies").exists()

    again = await draft_schema_gaps("demo-ops", writer=_writer)
    assert again["created_count"] == 0
    assert again["skipped"][0]["reason"] == "open_draft"
