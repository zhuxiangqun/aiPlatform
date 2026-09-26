"""Apply-time JSON diff is a trace, not a new write path."""

from __future__ import annotations

from core.apps.fde.service.k_wave_rollback import rollback_scope
from core.harness.knowledge.versioned_ontology_store import json_change_diff


def test_json_change_diff_lists_changed_paths_only():
    out = json_change_diff(
        {"classes": {"Alert": {"label": "a"}}, "version": "1"},
        {"classes": {"Alert": {"label": "b", "note": "x"}}, "version": "2"},
    )
    assert out["wrote_live_yaml"] is False
    assert out["full_event_log"] is False
    paths = [row["path"] for row in out["changes"]]
    assert "classes.Alert" in paths
    assert "version" in paths
    same = json_change_diff({"version": "1"}, {"version": "1"})
    assert same["count"] == 0


def test_scope_still_refuses_one_click():
    scope = rollback_scope()
    assert scope["one_click_any_change"] is False
    assert "YAML" in scope["change_trace"]
    assert "旧边" in scope["change_trace"]
