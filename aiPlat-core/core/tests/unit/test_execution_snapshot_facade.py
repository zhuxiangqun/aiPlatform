"""Tests for P1-2: execution snapshot self-service recovery facade.

Covers the CoreFacade wrappers that back the platform REST endpoints
(list / get / compare / restore), proving the on-disk checkpoint snapshots
are reachable for user-facing recovery (Hermes Layer 1).
"""

import pytest
import sys

sys.path.insert(0, "aiPlat-core")

from core.harness.execution import snapshot as snap_mod
from core.api import core_facade


@pytest.fixture
def snap_env(tmp_path, monkeypatch):
    """Isolate snapshot storage to a temp dir and seed two snapshots."""
    monkeypatch.setattr(snap_mod, "SNAPSHOT_ROOT", str(tmp_path))
    sid = "sess-p12"
    s1 = snap_mod.save_execution_snapshot(
        {"session_id": sid, "tokens_used": 100, "phase": "executing", "error": "boom"},
        "pre_backoff", session_id=sid, stage_id="stageA",
    )
    s2 = snap_mod.save_execution_snapshot(
        {"session_id": sid, "tokens_used": 250, "phase": "done", "error": ""},
        "post_backoff", session_id=sid, stage_id="stageA",
    )
    return {"session_id": sid, "s1": s1, "s2": s2}


class TestListFacade:
    def test_list_returns_all(self, snap_env):
        items = core_facade.list_execution_snapshots(snap_env["session_id"])
        assert len(items) == 2
        ids = {i["snapshot_id"] for i in items}
        assert snap_env["s1"] in ids and snap_env["s2"] in ids

    def test_list_empty_for_unknown_session(self, snap_env):
        assert core_facade.list_execution_snapshots("no-such-session") == []


class TestGetFacade:
    def test_get_returns_full_state(self, snap_env):
        got = core_facade.get_execution_snapshot(snap_env["s1"], snap_env["session_id"])
        assert got is not None
        assert got["has_full_state"] is True
        assert got["full_state"]["tokens_used"] == 100

    def test_get_missing_returns_none(self, snap_env):
        assert core_facade.get_execution_snapshot("deadbeef", snap_env["session_id"]) is None


class TestRestoreFacade:
    def test_restore_returns_state_payload(self, snap_env):
        payload = core_facade.restore_execution_snapshot(snap_env["s2"], snap_env["session_id"])
        assert payload is not None
        assert payload["snapshot_id"] == snap_env["s2"]
        assert payload["strategy_name"] == "post_backoff"
        assert payload["restored_state"]["phase"] == "done"
        assert payload["restored_state"]["tokens_used"] == 250

    def test_restore_missing_returns_none(self, snap_env):
        assert core_facade.restore_execution_snapshot("deadbeef", snap_env["session_id"]) is None


class TestCompareFacade:
    def test_compare_shows_token_delta_and_resolution(self, snap_env):
        diff = core_facade.compare_execution_snapshots(
            snap_env["s1"], snap_env["s2"], snap_env["session_id"]
        )
        assert diff["changes"]["tokens_used"]["delta"] == 150
        assert diff["changes"]["error"]["resolved"] is True
        assert diff["strategy_effect"]["phase_transition"] == "executing→done"
