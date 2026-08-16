"""P2-A1: pipeline run event log (append-only dual-write)."""
import os
import sys


def _fresh_store(tmp_path):
    os.environ["AIPLAT_HOME"] = str(tmp_path)
    from core.harness.execution.pipeline_run_store import get_pipeline_run_store
    return get_pipeline_run_store()


def test_append_and_list_events(tmp_path):
    sys.path.insert(0, ".")
    store = _fresh_store(tmp_path)

    store.append_run_event("r1", "pipeline_started", "", {"project": "demo"})
    store.append_run_event("r1", "stage_started", "s1", {"agent": "pm"})
    store.append_run_event("r1", "stage_completed", "s1", {"score": 0.9})

    evs = store.list_run_events("r1")
    assert len(evs) == 3
    assert evs[0]["event_type"] == "pipeline_started"
    assert evs[1]["stage_id"] == "s1"
    assert evs[2]["payload"]["score"] == 0.9
    # append order preserved (seq ascending)
    assert evs[0]["seq"] < evs[1]["seq"] < evs[2]["seq"]


def test_store_callback_dual_write(tmp_path):
    sys.path.insert(0, ".")
    store = _fresh_store(tmp_path)
    from core.api.routers.pipeline_execution import _make_store_callback

    cb = _make_store_callback("run-42", store)
    cb({"phase": "executing", "_current_stage_idx": 1, "pass_rate": 0.5})
    cb({"phase": "review", "_current_stage_idx": 2, "pass_rate": 0.7, "_hitl_stage_id": "s2"})
    cb({"phase": "done", "_current_stage_idx": 3, "pass_rate": 0.9})

    evs = store.list_run_events("run-42")
    types = [e["event_type"] for e in evs]
    assert types == ["pipeline_progress", "pipeline_hitl", "pipeline_finished"]
