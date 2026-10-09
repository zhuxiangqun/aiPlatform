"""Explainable run rollback guidance (no fake completed-run undo)."""

from __future__ import annotations

from core.harness.execution.run_rollback_guidance import build_run_rollback_guidance


def test_guidance_lists_file_checkpoints_and_domain():
    g = build_run_rollback_guidance(
        run_id="r1",
        run_status="completed",
        session_id="s1",
        checkpoint_count=2,
        checkpoint_preview=[{"checkpoint_id": "c1", "path": "/tmp/a.py"}],
    )
    assert g["status"] == "undo_not_supported"
    assert g["file_checkpoints"]["count"] == 2
    assert g["file_checkpoints"]["ui"] == "/core/checkpoints"
    actions = {a["action"] for a in g["alternatives"]}
    assert "file_checkpoints" in actions
    assert "domain_rollback" in actions
    assert "undo_queued" not in actions


def test_guidance_queued_offers_undo():
    g = build_run_rollback_guidance(run_id="r2", run_status="queued")
    actions = {a["action"] for a in g["alternatives"]}
    assert "undo_queued" in actions


def test_guidance_running_offers_cancel():
    g = build_run_rollback_guidance(run_id="r3", run_status="running")
    actions = {a["action"] for a in g["alternatives"]}
    assert "cancel" in actions
