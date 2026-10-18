"""Organization harness metrics — HITL serial wait / approval Amdahl proxy."""

from __future__ import annotations

from core.harness.meta.org_harness_metrics import (
    aggregate_org_harness,
    build_duty_board,
    collect_org_harness,
    load_duty_board_playbook,
    load_duty_board_thresholds,
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
    assert len(out["trend"]) == 2
    assert out["trend_summary"]["direction"] == "down"
    assert out["trend_summary"]["n"] == 2


def test_summarize_gold_empty():
    out = summarize_gold_regression([])
    assert out["report_count"] == 0
    assert out["p0_miss_rate"] is None
    assert out["regressing"] is False
    assert out["trend"] == []
    assert out["trend_summary"]["direction"] == "unavailable"


def test_duty_board_playbook_and_gold_trend():
    pb, src = load_duty_board_playbook()
    assert "block" in pb and pb["block"]
    assert src.endswith("duty_board.yaml") or src == "defaults"

    board = build_duty_board(
        {
            "ok": True,
            "data_available": True,
            "availability": {"runs": True, "gold": True, "approvals": False},
            "summary": {
                "avg_serial_ratio": 0.05,
                "gold_regressing": True,
                "p0_miss_rate": 0.0,
            },
            "gold_regression": {
                "trend_summary": {
                    "n": 2,
                    "direction": "down",
                    "first": {"p0_recall": 1.0},
                    "last": {"p0_recall": 0.5},
                },
            },
        },
    )
    assert board["status"] == "block"
    assert board.get("playbook")
    assert any("Gold" in s or "gold" in s.lower() for s in board["playbook"])
    assert board.get("gold_trend_summary", {}).get("direction") == "down"
    assert "merge_gates" in (board.get("checks") or {})
    assert isinstance(board.get("merge_gates"), dict)
    assert board["merge_gates"].get("exemptions_visible") is True
    assert "envelope" in (board.get("checks") or {})
    assert isinstance(board.get("envelope"), dict)


def test_duty_board_derived_findings_watch_not_block():
    """LLM-style findings alone cannot escalate to block."""
    board = build_duty_board(
        {
            "ok": True,
            "data_available": True,
            "availability": {"runs": True, "gold": True, "approvals": False},
            "summary": {
                "avg_serial_ratio": 0.05,
                "gold_regressing": False,
                "p0_miss_rate": 0.0,
            },
            "findings": [
                {
                    "file": "x.py",
                    "line": 2,
                    "description": "possible bug",
                    "engine": "reasoning",
                    "evidence_envelope": {
                        "status": "confirmed",  # fake — must demote
                        "confidence": "derived",
                        "evidence": [{"type": "file_line", "ref": "x.py:2"}],
                        "limitations": ["static review"],
                    },
                }
            ],
        },
    )
    assert board["status"] in ("watch", "go")  # never block from derived
    assert board["status"] != "block"
    assert board["checks"]["envelope"] == "watch"
    assert int((board.get("envelope") or {}).get("release_block_ok") or 0) == 0


def test_duty_board_measured_envelope_can_block():
    board = build_duty_board(
        {
            "ok": True,
            "data_available": True,
            "availability": {"runs": True, "gold": True, "approvals": False},
            "summary": {
                "avg_serial_ratio": 0.05,
                "gold_regressing": False,
                "p0_miss_rate": 0.0,
            },
            "findings": [
                {
                    "description": "measured gate fail",
                    "evidence_envelope": {
                        "status": "confirmed",
                        "confidence": "measured",
                        "evidence": [{"type": "command", "ref": "arch_guard"}],
                        "limitations": ["CI scope"],
                    },
                }
            ],
        },
    )
    assert board["status"] == "block"
    assert board["checks"]["envelope"] == "block"
    assert any("envelope_measured_block" in r for r in board["reasons"])


def test_collect_merge_gates_posture_surfaces_exemptions():
    from core.harness.meta.org_harness_metrics import collect_merge_gates_posture

    posture = collect_merge_gates_posture()
    assert posture.get("exemptions_visible") is True
    assert "physical" in posture and "testability" in posture
    # Seed config has no exemptions → count 0; modes are warn/block/off
    assert posture.get("active_exemption_count") == 0
    assert posture.get("debt_severity") in ("go", "unavailable")
    assert "exemption_debt" in posture
    assert "gate_meta" in posture
    assert posture.get("meta_severity") in ("go", "watch", "block", "unavailable")
    assert "repo_health" in posture
    assert posture.get("health_severity") in ("go", "watch", "block", "unavailable")
    phys = posture["physical"]
    assert phys.get("status") in ("ok", "unavailable")
    if phys.get("status") == "ok":
        assert phys.get("mode") in ("warn", "block", "off")


def test_duty_board_exemption_debt_expired_blocks(monkeypatch):
    """Expired-unreviewed exemptions escalate merge_gates + board status to block."""
    import core.harness.meta.org_harness_metrics as m

    monkeypatch.setattr(
        m,
        "collect_merge_gates_posture",
        lambda: {
            "physical": {
                "status": "ok",
                "mode": "block",
                "block_after": "2026-10-25",
                "days_until_block": None,
                "exemptions": [],
            },
            "testability": {"status": "ok", "mode": "warn"},
            "active_exemption_count": 0,
            "exemptions_visible": True,
            "debt_severity": "block",
            "exemption_debt": {
                "severity": "block",
                "expired": [{"id": "ex-old", "expires": "2020-01-01"}],
                "invalid": [],
                "over_cap": False,
                "reasons": ["exemption_debt_expired=1 (ex-old)"],
            },
            "gate_meta": {"severity": "go", "reasons": []},
            "meta_severity": "go",
            "repo_health": {"severity": "go", "reasons": ["repo_health within band"]},
            "health_severity": "go",
        },
    )
    board = build_duty_board(
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
    )
    assert board["checks"]["merge_gates"] == "block"
    assert board["status"] == "block"
    assert any("exemption_debt_expired" in r for r in board["reasons"])


def test_duty_board_repo_health_block(monkeypatch):
    """Post-merge repo health block escalates board + measured envelope."""
    import core.harness.meta.org_harness_metrics as m

    monkeypatch.setattr(
        m,
        "collect_merge_gates_posture",
        lambda: {
            "physical": {"status": "ok", "mode": "warn", "exemptions": []},
            "testability": {"status": "ok", "mode": "warn"},
            "active_exemption_count": 0,
            "exemptions_visible": True,
            "debt_severity": "go",
            "exemption_debt": {"severity": "go", "reasons": []},
            "gate_meta": {"severity": "go", "reasons": []},
            "meta_severity": "go",
            "health_severity": "block",
            "repo_health": {
                "severity": "block",
                "n_snapshots": 2,
                "latest": {
                    "py_loc": 500000,
                    "god_files": 45,
                    "multi_base_classes": 10,
                    "high_fanout_files": 5,
                    "dep_entries": 50,
                },
                "deltas": {"loc_growth_pct": 2.0},
                "reasons": ["repo_health_god_files=45>=40"],
                "jsonl": "org/repo_health/snapshots.jsonl",
            },
        },
    )
    board = build_duty_board(
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
    )
    assert board["checks"]["repo_health"] == "block"
    assert board["status"] == "block"
    assert any("repo_health_god_files" in r for r in board["reasons"])
    env = board.get("envelope") or {}
    assert env.get("block_allowed") is True
    primary = env.get("primary") or {}
    assert primary.get("confidence") == "measured"


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


def test_load_duty_board_thresholds_override_and_seed():
    thr, src = load_duty_board_thresholds(
        override={"p0_miss_rate_block": 0.15, "serial_ratio_high": 0.5}
    )
    assert src == "override"
    assert thr["p0_miss_rate_block"] == 0.15
    assert thr["serial_ratio_high"] == 0.5
    # Unspecified keys keep defaults
    assert thr["howl_interventions_watch"] == 20.0

    thr2, src2 = load_duty_board_thresholds(override=None)
    assert thr2["p0_miss_rate_block"] == 0.2
    assert src2 in ("defaults",) or src2.endswith("duty_board.yaml")


def test_duty_board_respects_threshold_override():
    # With default 0.2, miss=0.18 is go; with block=0.1 it is block
    payload = {
        "ok": True,
        "data_available": True,
        "availability": {"runs": True, "gold": True, "approvals": False},
        "summary": {
            "avg_serial_ratio": 0.05,
            "gold_regressing": False,
            "p0_miss_rate": 0.18,
        },
    }
    soft = build_duty_board(payload, thresholds={"p0_miss_rate_block": 0.2})
    assert soft["checks"]["gold"] == "go"
    hard = build_duty_board(payload, thresholds={"p0_miss_rate_block": 0.1})
    assert hard["status"] == "block"
    assert hard["checks"]["gold"] == "block"
    assert hard.get("thresholds_source") == "override"


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
    # Evidence Envelope: gold BLOCK must allow_release_block
    env = board.get("envelope") or {}
    assert env.get("block_allowed") is True
    assert env.get("allow_block_count", 0) >= 1
    primary = env.get("primary") or {}
    assert primary.get("status") == "blocked"
    assert primary.get("confidence") == "measured"
    assert primary.get("limitations")
    assert board["checks"].get("envelope") == "block"


def test_duty_board_block_demoted_without_allow_envelope(monkeypatch):
    """block without allow_release_block envelope → demote to watch."""
    import core.harness.meta.evidence_envelope as ee
    from core.harness.meta.evidence_envelope import empty_envelope

    def _no_gold_env(*a, **k):
        return empty_envelope(status="unverified", confidence="speculative")

    monkeypatch.setattr(ee, "envelope_for_gold_block", _no_gold_env)
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
    assert board["status"] == "watch"
    assert any("block_demoted" in r for r in board["reasons"])
    assert board["checks"].get("gold") == "watch"
    assert board["checks"].get("envelope") == "watch"
    assert (board.get("envelope") or {}).get("block_allowed") is False


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


def test_duty_board_model_route_does_not_change_status(monkeypatch):
    monkeypatch.setattr(
        "core.harness.utils.task_model_lock.summarize_task_model_routes",
        lambda limit=500: {
            "available": True,
            "tasks": 2,
            "rows": 2,
            "by_purpose": {"agent": {"success_rate": 0.5, "upgrade_rate": 1.0}},
        },
    )
    monkeypatch.setattr(
        "core.harness.evaluation.harness_recursion.summarize_library",
        lambda recent=5: {
            "available": True,
            "library_entries": 2,
            "pending_traces": 1,
            "inherit_whole": False,
            "recent": [],
        },
    )
    board = build_duty_board({
        "ok": True,
        "data_available": True,
        "availability": {"runs": True, "gold": False, "approvals": False},
        "summary": {"avg_serial_ratio": 0.05, "runs_scanned": 2},
    })
    assert board["model_route"]["available"] is True
    assert board["harness_library"]["library_entries"] == 2
    assert board["status"] in ("go", "watch")
    assert "model_route" not in " ".join(board["reasons"])
    assert "harness_library" not in " ".join(board["reasons"])


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
