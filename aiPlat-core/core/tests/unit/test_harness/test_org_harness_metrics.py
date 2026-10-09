"""Organization harness metrics — HITL serial wait / approval Amdahl proxy."""

from __future__ import annotations

from core.harness.meta.org_harness_metrics import (
    aggregate_org_harness,
    build_duty_board,
    collect_org_harness,
    summarize_approvals,
    summarize_gold_regression,
    summarize_hitl_audit,
    summarize_run_events,
)


def test_summarize_run_events_serial_ratio():
    events = [
        {"event_type": "stage_started", "created_at": 1000.0, "stage_id": "a"},
        {"event_type": "hitl_requested", "created_at": 1010.0, "stage_id": "a"},
        {"event_type": "hitl_approved", "created_at": 1060.0, "stage_id": "a"},
        {"event_type": "stage_started", "created_at": 1070.0, "stage_id": "b"},
    ]
    out = summarize_run_events(events)
    assert out["hitl_open_count"] == 1
    assert out["hitl_wait_sec_total"] == 50.0
    assert out["wall_sec"] == 70.0
    assert out["serial_ratio"] == round(50.0 / 70.0, 4)
    assert out["open_unresolved"] == 0


def test_soft_close_via_stage_started():
    events = [
        {"event_type": "hitl_requested", "created_at": 1.0},
        {"event_type": "stage_started", "created_at": 2.0},  # soft close
    ]
    out = summarize_run_events(events)
    assert out["hitl_wait_sec_total"] == 1.0
    assert out["open_unresolved"] == 0
    assert len(out["hitl_episodes"]) == 1


def test_unresolved_hitl_episode():
    events = [{"event_type": "hitl_requested", "created_at": 1.0}]
    out = summarize_run_events(events)
    assert out["open_unresolved"] == 1
    assert out["hitl_wait_sec_total"] == 0.0


def test_summarize_hitl_audit():
    audit = [
        {"action": "hitl_requested", "timestamp": 10.0},
        {"action": "hitl_approved", "timestamp": 25.0},
    ]
    out = summarize_hitl_audit(audit)
    assert out["hitl_wait_sec_total"] == 15.0


def test_summarize_approvals_latency():
    recs = [
        {"request_id": "1", "status": "approved", "created_at": 100.0, "updated_at": 130.0, "run_id": "r1"},
        {"request_id": "2", "status": "pending", "created_at": 200.0, "updated_at": 200.0, "run_id": "r1"},
        {"request_id": "3", "status": "denied", "created_at": 50.0, "updated_at": 80.0, "run_id": "r2"},
        {
            "request_id": "4",
            "status": "approved",
            "created_at": 10.0,
            "updated_at": None,
            "result": {"timestamp": 25.0},
            "run_id": "r3",
        },
    ]
    out = summarize_approvals(recs)
    assert out["approval_count"] == 4
    assert out["pending"] == 1
    # latencies: 30, 30, 15 → avg 25
    assert out["avg_latency_sec"] == 25.0
    assert out["avg_approvals_per_run"] == round(4 / 3, 3)


def test_aggregate_org_harness_combines():
    out = aggregate_org_harness(
        events=[
            {"event_type": "stage_started", "created_at": 0.0},
            {"event_type": "hitl_requested", "created_at": 10.0},
            {"event_type": "hitl_resolved", "created_at": 40.0},
            {"event_type": "stage_started", "created_at": 100.0},
        ],
        approvals=[
            {"request_id": "a", "status": "approved", "created_at": 1.0, "updated_at": 11.0, "run_id": "x"},
        ],
        run_id="x",
    )
    assert out["ok"] is True
    assert out["summary"]["hitl_wait_sec_total"] == 30.0
    assert out["summary"]["serial_ratio"] == 0.3
    assert out["summary"]["approval_count"] == 1


def test_summarize_gold_regression_p0_miss_and_delta():
    reports = [
        {"precision": 0.8, "recall": 0.7, "p0_recall": 1.0, "novel_count": 0, "written_at": "t1"},
        {"precision": 0.75, "recall": 0.72, "p0_recall": 0.5, "novel_count": 2, "written_at": "t2",
         "case_ids": ["a", "b"]},
    ]
    out = summarize_gold_regression(reports)
    assert out["report_count"] == 2
    assert out["p0_miss_rate"] == 0.5
    assert out["latest"]["precision"] == 0.75
    assert out["delta_vs_prev"]["precision"] == -0.05
    assert out["delta_vs_prev"]["p0_recall"] == -0.5
    assert out["regressing"] is True


def test_summarize_gold_empty():
    out = summarize_gold_regression([])
    assert out["report_count"] == 0
    assert out["p0_miss_rate"] is None
    assert out["regressing"] is False


def test_aggregate_includes_gold():
    out = aggregate_org_harness(
        events=[],
        approvals=[],
        gold_reports=[
            {"precision": 0.9, "recall": 0.8, "p0_recall": 1.0, "novel_count": 0},
        ],
    )
    assert out["summary"]["gold_precision"] == 0.9
    assert out["summary"]["p0_miss_rate"] == 0.0
    assert out["gold_regression"]["report_count"] == 1


def test_collect_fleet_without_stores(monkeypatch):
    """Fleet path must not crash when pipeline store / approvals unavailable."""
    import core.harness.meta.org_harness_metrics as m

    monkeypatch.setattr(m, "_load_run_events", lambda *a, **k: [])
    monkeypatch.setattr(m, "_load_approvals_sync", lambda **k: [])
    monkeypatch.setattr(m, "_load_gold_reports", lambda **k: [
        {"precision": 0.6, "recall": 0.5, "p0_recall": 0.75, "novel_count": 1},
    ])

    class _EmptyStore:
        def list_recent_runs(self, limit=10):
            return []

    monkeypatch.setattr(
        "core.harness.execution.pipeline_run_store.get_pipeline_run_store",
        lambda: _EmptyStore(),
        raising=False,
    )
    out = collect_org_harness(run_id="", recent_limit=3, load_approvals=True)
    assert out["ok"] is True
    assert out["scope"] == "fleet"
    assert out["summary"]["runs_scanned"] == 0
    assert out["summary"]["p0_miss_rate"] == 0.25
    assert out["summary"]["gold_p0_recall"] == 0.75
    assert out["data_available"] is True
    assert out["availability"]["gold"] is True
    assert out["duty_board"]["status"] == "block"  # p0_miss 0.25 > 0.2


def test_duty_board_unavailable_no_fake_green():
    board = build_duty_board({
        "ok": True,
        "data_available": False,
        "availability": {"runs": False, "gold": False, "approvals": False},
        "summary": {},
    })
    assert board["status"] == "unavailable"
    assert any("invent" in r or "unavailable" in r for r in board["reasons"])
    assert board["checks"].get("howl") == "unavailable"


def test_duty_board_howl_watch_and_unavailable():
    watch = build_duty_board(
        {
            "ok": True,
            "data_available": True,
            "availability": {"runs": True, "gold": True, "approvals": False},
            "summary": {
                "avg_serial_ratio": 0.05,
                "gold_regressing": False,
                "p0_miss_rate": 0.0,
            },
        },
        adoption={"howl_interventions": 25, "howl_status": "ok"},
    )
    assert watch["checks"]["howl"] == "watch"
    assert watch["status"] == "watch"

    missing = build_duty_board(
        {
            "ok": True,
            "data_available": True,
            "availability": {"runs": True, "gold": True, "approvals": False},
            "summary": {
                "avg_serial_ratio": 0.05,
                "gold_regressing": False,
                "p0_miss_rate": 0.0,
            },
        },
        adoption={"howl_status": "unavailable", "howl_interventions": None},
    )
    assert missing["checks"]["howl"] == "unavailable"


def test_duty_board_block_on_gold_regressing():
    board = build_duty_board({
        "ok": True,
        "data_available": True,
        "availability": {"runs": True, "gold": True, "approvals": False},
        "summary": {
            "avg_serial_ratio": 0.1,
            "gold_regressing": True,
            "p0_miss_rate": 0.0,
        },
    })
    assert board["status"] == "block"
    assert board["checks"]["gold"] == "block"


def test_duty_board_watch_serial_and_adoption():
    board = build_duty_board(
        {
            "ok": True,
            "data_available": True,
            "availability": {"runs": True, "gold": True, "approvals": True},
            "summary": {
                "avg_serial_ratio": 0.45,
                "gold_regressing": False,
                "p0_miss_rate": 0.05,
                "approval_pending": 1,
            },
        },
        adoption={"hitl_rejection_rate": 0.4, "howl_interventions": 2},
    )
    assert board["status"] == "watch"
    assert board["checks"]["serial"] == "watch"
    assert board["checks"]["hitl"] == "watch"


def test_aggregate_attaches_duty_board():
    out = aggregate_org_harness(
        events=[],
        approvals=[],
        gold_reports=[
            {"precision": 0.9, "recall": 0.8, "p0_recall": 1.0, "novel_count": 0},
        ],
    )
    assert out["duty_board"]["status"] in ("go", "watch")
    assert out["duty_board"]["checks"]["gold"] == "go"
    assert out["data_available"] is True


def test_aggregate_merges_adoption_into_duty_board(monkeypatch):
    from core.harness.meta import org_harness_metrics as ohm

    monkeypatch.setattr(
        ohm,
        "load_adoption_snapshot",
        lambda: {"hitl_rejection_rate": 0.5, "howl_interventions": 3},
    )
    out = aggregate_org_harness(
        events=[],
        approvals=[],
        gold_reports=[
            {"precision": 0.9, "recall": 0.8, "p0_recall": 1.0, "novel_count": 0},
        ],
    )
    assert out["adoption"]["hitl_rejection_rate"] == 0.5
    assert out["duty_board"]["checks"]["hitl"] == "watch"
    assert out["duty_board"]["status"] == "watch"
    assert any("hitl_rejection_rate" in r for r in out["duty_board"]["reasons"])


def test_duty_board_gold_missing_not_go():
    board = build_duty_board({
        "ok": True,
        "data_available": True,
        "availability": {"runs": True, "gold": False, "approvals": False},
        "summary": {"avg_serial_ratio": 0.05, "runs_scanned": 2},
    })
    assert board["checks"]["gold"] == "unavailable"
    assert board["status"] in ("go", "watch")  # runs present; gold unavailable is reason, not fake go on gold check
    assert any("gold unavailable" in r for r in board["reasons"])
