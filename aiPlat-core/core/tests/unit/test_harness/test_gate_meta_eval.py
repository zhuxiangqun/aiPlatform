"""Gate meta-eval — JSONL rates calibrate merge gates (no invented sparse rates)."""

from __future__ import annotations

import time
from pathlib import Path

import pytest

from core.harness.meta.gate_meta_eval import (
    append_gate_event,
    assess_gate_meta,
    record_gate_appeal,
    record_gate_run,
    record_gate_skip,
    summarize_gate_meta,
)


@pytest.fixture()
def meta_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    d = tmp_path / "gate_meta"
    monkeypatch.setenv("AIPLAT_GATE_META_DIR", str(d))
    monkeypatch.setenv("AIPLAT_GATE_META_PERSIST", "1")
    return d


def _run(
    *,
    ts: float,
    exit_blocked: bool = False,
    exemption_used: bool = False,
) -> dict:
    return {
        "kind": "run",
        "ts": ts,
        "exit_blocked": exit_blocked,
        "exemption_used": exemption_used,
        "exemptions_applied": ["ex-1"] if exemption_used else [],
        "physical_ok": not exit_blocked,
        "physical_mode": "block",
    }


def test_insufficient_runs_unavailable(meta_dir: Path):
    now = time.time()
    events = [_run(ts=now - 100) for _ in range(3)]
    out = summarize_gate_meta(events, min_runs=5.0, now_ts=now)
    assert out["severity"] == "unavailable"
    assert out["status"] == "unavailable"
    assert any("insufficient_runs" in r for r in out["reasons"])


def test_exemption_rate_block(meta_dir: Path):
    now = time.time()
    # 4/5 runs used exemption → 0.8 >= block 0.35
    events = [
        _run(ts=now - i, exemption_used=(i < 4)) for i in range(5)
    ]
    out = summarize_gate_meta(
        events,
        min_runs=5.0,
        now_ts=now,
        thresholds={
            "gate_exemption_rate_watch": 0.15,
            "gate_exemption_rate_block": 0.35,
        },
    )
    assert out["n_runs"] == 5
    assert out["exemption_rate"] == 0.8
    assert out["severity"] == "block"
    assert any("exemption_rate" in r for r in out["reasons"])


def test_skip_rate_watch(meta_dir: Path):
    now = time.time()
    events = [_run(ts=now - i) for i in range(10)]
    # 1 skip / 11 total ≈ 0.09 → watch (0.05) but < block (0.15)
    events.append({"kind": "skip", "ts": now, "env": "SKIP_PHYSICAL_GATES"})
    out = summarize_gate_meta(
        events,
        min_runs=5.0,
        now_ts=now,
        thresholds={
            "gate_skip_rate_watch": 0.05,
            "gate_skip_rate_block": 0.15,
            "gate_exemption_rate_watch": 0.99,
            "gate_exemption_rate_block": 0.99,
            "gate_appeal_rate_watch": 0.99,
            "gate_appeal_rate_block": 0.99,
        },
    )
    assert out["skip_rate"] is not None and out["skip_rate"] >= 0.05
    assert out["severity"] == "watch"
    assert any("skip_rate" in r for r in out["reasons"])


def test_appeal_rate_block(meta_dir: Path):
    now = time.time()
    events = [_run(ts=now - i) for i in range(5)]
    for i in range(2):
        events.append(
            {
                "kind": "appeal",
                "ts": now,
                "code": f"banned_{i}",
                "owner": "oncall",
            }
        )
    out = summarize_gate_meta(
        events,
        min_runs=5.0,
        now_ts=now,
        thresholds={
            "gate_appeal_rate_watch": 0.10,
            "gate_appeal_rate_block": 0.25,
            "gate_exemption_rate_watch": 0.99,
            "gate_exemption_rate_block": 0.99,
            "gate_skip_rate_watch": 0.99,
            "gate_skip_rate_block": 0.99,
        },
    )
    assert out["appeal_rate"] == 0.4
    assert out["severity"] == "block"


def test_window_excludes_old_events(meta_dir: Path):
    now = time.time()
    old = now - 40 * 86400
    events = [_run(ts=old, exemption_used=True) for _ in range(10)]
    events += [_run(ts=now - i) for i in range(5)]
    out = summarize_gate_meta(
        events, window_days=30.0, min_runs=5.0, now_ts=now
    )
    assert out["n_runs"] == 5
    assert out["n_exempt"] == 0
    assert out["severity"] in ("go", "watch")  # no exemption heat


def test_record_persist_and_assess(meta_dir: Path):
    path = record_gate_run(
        physical={
            "ok": False,
            "mode": "block",
            "exemptions_applied": ["ex-x"],
            "findings": [{"code": "inflation_files"}],
            "profile": "business",
        },
        testability={"ok": True, "mode": "warn"},
        exit_blocked=True,
        source="test",
    )
    assert path and Path(path).is_file()
    assert record_gate_skip(env="SKIP_PHYSICAL_GATES", source="test")
    assert record_gate_appeal(code="banned_basename", owner="alice", note="ok")
    assert record_gate_appeal(code="", owner="alice") is None  # require code+owner

    out = assess_gate_meta(
        thresholds={
            "gate_meta_min_runs": 1.0,
            "gate_meta_window_days": 30.0,
            "gate_exemption_rate_watch": 0.01,
            "gate_exemption_rate_block": 0.99,
            "gate_skip_rate_watch": 0.01,
            "gate_skip_rate_block": 0.99,
            "gate_appeal_rate_watch": 0.01,
            "gate_appeal_rate_block": 0.99,
        }
    )
    assert out["n_runs"] >= 1
    assert out["n_skips"] >= 1
    assert out["n_appeals"] >= 1
    assert out["severity"] in ("go", "watch", "block")


def test_persist_disabled(meta_dir: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("AIPLAT_GATE_META_PERSIST", "0")
    assert append_gate_event({"kind": "skip", "env": "x"}) is None


def test_duty_board_gate_meta_block(monkeypatch: pytest.MonkeyPatch):
    from core.harness.meta.org_harness_metrics import build_duty_board
    import core.harness.meta.org_harness_metrics as m

    monkeypatch.setattr(
        m,
        "collect_merge_gates_posture",
        lambda: {
            "physical": {
                "status": "ok",
                "mode": "block",
                "exemptions": [],
            },
            "testability": {"status": "ok", "mode": "warn"},
            "active_exemption_count": 0,
            "exemptions_visible": True,
            "debt_severity": "go",
            "exemption_debt": {"severity": "go", "reasons": []},
            "meta_severity": "block",
            "gate_meta": {
                "severity": "block",
                "exemption_rate": 0.5,
                "skip_rate": 0.0,
                "appeal_rate": 0.0,
                "n_runs": 10,
                "n_skips": 0,
                "n_appeals": 0,
                "window_days": 30,
                "jsonl": "org/gate_meta/runs.jsonl",
                "reasons": ["exemption_rate=0.5>=0.35"],
            },
            "health_severity": "go",
            "repo_health": {"severity": "go", "reasons": ["repo_health within band"]},
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
    assert any("exemption_rate" in r for r in board["reasons"])
    assert board.get("envelope", {}).get("block_allowed") is True
