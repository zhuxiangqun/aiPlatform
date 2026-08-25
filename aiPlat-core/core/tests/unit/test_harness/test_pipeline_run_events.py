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


def test_replay_folds_events_into_state(tmp_path):
    sys.path.insert(0, ".")
    store = _fresh_store(tmp_path)

    store.append_run_event("r2", "pipeline_started", "", {"phase": "executing"})
    store.append_run_event("r2", "pipeline_progress", "1", {"phase": "executing", "current_stage_idx": 1, "pass_rate": 0.4})
    store.append_run_event("r2", "pipeline_progress", "2", {"phase": "executing", "current_stage_idx": 2, "pass_rate": 0.6})
    store.append_run_event("r2", "pipeline_finished", "3", {"phase": "done", "current_stage_idx": 3, "pass_rate": 0.9})

    d = store.replay_run_events("r2")
    assert d is not None
    assert d["phase"] == "done"
    assert d["current_stage_idx"] == 3
    assert d["pass_rate"] == 0.9
    assert d["event_count"] == 4
    assert d["derived"] is True
    assert d["last_terminal_event"] == "pipeline_finished"

    # no events → None
    assert store.replay_run_events("r-nope") is None


def test_full_state_event_cross_check(tmp_path):
    sys.path.insert(0, ".")
    store = _fresh_store(tmp_path)
    from core.api.routers.pipeline_execution import _make_store_callback

    store.create_run("run-x", "proj-x", total_stages=2)
    cb = _make_store_callback("run-x", store)
    cb({"phase": "executing", "_current_stage_idx": 1, "pass_rate": 0.5})
    cb({"phase": "done", "_current_stage_idx": 2, "pass_rate": 0.9})

    state = store.get_full_state_from_run_id("run-x")
    assert state.get("phase") == "done"
    assert state.get("event_derived", {}).get("phase") == "done"
    assert state.get("state_event_consistent") is True


def test_full_state_drift_flags_and_warns(tmp_path, caplog):
    """P3-1: dual-track drift must be visible — inconsistent snapshot/event
    phases set state_event_consistent=False and raise a WARNING (read path
    stays side-effect free, never blocks)."""
    import logging

    sys.path.insert(0, ".")
    store = _fresh_store(tmp_path)

    # event log says done, snapshot row still in initial phase → drift
    store.create_run("run_drift", "proj_drift", total_stages=1)
    store.append_run_event("run_drift", "pipeline_finished", "",
                           {"phase": "done", "current_stage_idx": 1, "pass_rate": 0.9})

    with caplog.at_level(logging.WARNING, logger="core.harness.execution.pipeline_run_store"):
        state = store.get_full_state_from_run_id("run_drift")

    assert state.get("phase") != "done"           # snapshot not updated
    assert state.get("event_derived", {}).get("phase") == "done"
    assert state.get("state_event_consistent") is False
    assert any("drift" in r.message and "run_drift" in r.message for r in caplog.records)


def test_full_state_no_events_no_drift_flag(tmp_path):
    """No events on disk → cross-check skipped (flag absent, no warning)."""
    sys.path.insert(0, ".")
    store = _fresh_store(tmp_path)

    store.create_run("run_plain", "proj_plain", total_stages=1)
    state = store.get_full_state_from_run_id("run_plain")
    assert "state_event_consistent" not in state
    assert "event_derived" not in state


# ── 事件源纯度 (fork 会话能力): fork 血缘 + 派生状态继承 ──────────


def test_fork_run_from_events_inherits_state_and_lineage(tmp_path):
    """Fork folds the source event log into a new run that inherits stage
    progress / pass_rate, records a pipeline_forked event, and keeps the
    source event log untouched (append-only purity)."""
    sys.path.insert(0, ".")
    store = _fresh_store(tmp_path)

    store.append_run_event("src_1", "pipeline_started", "", {"phase": "executing"})
    store.append_run_event("src_1", "pipeline_progress", "1",
                           {"phase": "executing", "current_stage_idx": 1, "pass_rate": 0.4})
    store.append_run_event("src_1", "pipeline_progress", "2",
                           {"phase": "executing", "current_stage_idx": 2, "pass_rate": 0.6})

    folded = store.fork_run_from_events("src_1", "fork_1", "proj_fork",
                                        note="continue from stage 2")
    assert folded is not None
    assert folded["current_stage_idx"] == 2
    assert folded["pass_rate"] == 0.6
    assert folded["event_count"] == 3

    # 新 run 行继承派生状态，phase 归位 executing（从分叉点继续）
    state = store.get_full_state_from_run_id("fork_1")
    assert state.get("_current_stage_idx") == 2
    assert state.get("phase") == "executing"
    assert abs(state.get("pass_rate", 0.0) - 0.6) < 1e-9

    # fork 血缘事件写入新 run 的事件日志（append-only），携带继承的分叉点状态
    evs = store.list_run_events("fork_1")
    assert evs[0]["event_type"] == "pipeline_forked"
    assert evs[0]["payload"]["parent_run_id"] == "src_1"
    assert evs[0]["payload"]["source_event_count"] == 3
    assert evs[0]["payload"]["note"] == "continue from stage 2"
    assert evs[0]["payload"]["current_stage_idx"] == 2
    assert abs(evs[0]["payload"]["pass_rate"] - 0.6) < 1e-9

    # 事件源纯度：子 run 状态可纯从自身事件日志重建（fork 点被 pipeline_forked 折叠）
    derived = store.replay_run_events("fork_1")
    assert derived is not None
    assert derived["current_stage_idx"] == 2
    assert abs(derived["pass_rate"] - 0.6) < 1e-9
    assert derived["event_count"] == 1  # 仅 fork 事件即足以重建分叉点
    assert state.get("event_derived", {}).get("current_stage_idx") == 2

    # 源 run 事件日志未被污染（事件源纯度：fork 不写回父）
    assert [e["event_type"] for e in store.list_run_events("src_1")] == [
        "pipeline_started", "pipeline_progress", "pipeline_progress"
    ]

    # 血缘查询：src_1 → fork_1
    assert store.list_forked_runs("src_1") == ["fork_1"]


def test_fork_from_run_without_events_returns_none(tmp_path):
    """A run with no event log has nothing to fold → fork returns None."""
    sys.path.insert(0, ".")
    store = _fresh_store(tmp_path)

    store.create_run("src_empty", "proj_empty", total_stages=3)
    assert store.fork_run_from_events("src_empty", "fork_empty") is None
    assert store.list_forked_runs("src_empty") == []


def test_list_forked_runs_multiple_children(tmp_path):
    """Fork lineage query returns all children in reverse order (newest first)."""
    sys.path.insert(0, ".")
    store = _fresh_store(tmp_path)

    store.append_run_event("parent_1", "pipeline_started", "", {"phase": "executing"})
    store.append_run_event("parent_1", "pipeline_progress", "1",
                           {"phase": "executing", "current_stage_idx": 1, "pass_rate": 0.5})
    store.fork_run_from_events("parent_1", "child_a", "proj_x")
    store.fork_run_from_events("parent_1", "child_b", "proj_x")
    store.append_run_event("other_1", "pipeline_started", "", {"phase": "executing"})
    store.fork_run_from_events("other_1", "child_c", "proj_y")

    children = store.list_forked_runs("parent_1")
    assert sorted(children) == ["child_a", "child_b"]
    assert children == ["child_b", "child_a"]  # seq DESC → newest first
    assert store.list_forked_runs("other_1") == ["child_c"]
    assert store.list_forked_runs("parent_1", limit=1) == ["child_b"]
