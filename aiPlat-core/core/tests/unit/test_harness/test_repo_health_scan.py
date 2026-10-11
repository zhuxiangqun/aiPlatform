"""Post-merge repo health scan — absolute + delta severity (no invented green)."""

from __future__ import annotations

from pathlib import Path

import pytest

from core.harness.meta.repo_health_scan import (
    append_health_snapshot,
    assess_repo_health,
    scan_repo_health,
)


@pytest.fixture()
def health_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    d = tmp_path / "repo_health"
    monkeypatch.setenv("AIPLAT_REPO_HEALTH_DIR", str(d))
    monkeypatch.setenv("AIPLAT_REPO_HEALTH_PERSIST", "1")
    return d


def _snap(**overrides):
    base = {
        "kind": "snapshot",
        "written_at": "2026-10-11T00:00:00Z",
        "ts": 1.0,
        "py_files": 100,
        "py_loc": 10000,
        "classes": 50,
        "multi_base_classes": 5,
        "god_files": 2,
        "high_fanout_files": 3,
        "dep_entries": 40,
        "avg_imports_per_file": 4.0,
    }
    base.update(overrides)
    return base


def test_insufficient_snapshots_unavailable(health_dir: Path):
    out = assess_repo_health(snapshots=[], thresholds={"repo_health_min_snapshots": 1})
    assert out["severity"] == "unavailable"
    assert out["status"] == "unavailable"
    assert any("insufficient_snapshots" in r for r in out["reasons"])


def test_god_files_block(health_dir: Path):
    out = assess_repo_health(
        snapshots=[_snap(god_files=45)],
        thresholds={
            "repo_health_min_snapshots": 1,
            "repo_health_god_files_watch": 15,
            "repo_health_god_files_block": 40,
            "repo_health_multi_base_watch": 999,
            "repo_health_multi_base_block": 999,
            "repo_health_high_fanout_watch": 999,
            "repo_health_high_fanout_block": 999,
            "repo_health_dep_entries_watch": 999,
            "repo_health_dep_entries_block": 999,
        },
    )
    assert out["severity"] == "block"
    assert any("god_files" in r for r in out["reasons"])


def test_loc_growth_watch(health_dir: Path):
    out = assess_repo_health(
        snapshots=[
            _snap(py_loc=10000, god_files=0, multi_base_classes=0, high_fanout_files=0, dep_entries=10),
            _snap(py_loc=11000, god_files=0, multi_base_classes=0, high_fanout_files=0, dep_entries=10),
        ],
        thresholds={
            "repo_health_min_snapshots": 1,
            "repo_health_god_files_watch": 999,
            "repo_health_god_files_block": 999,
            "repo_health_multi_base_watch": 999,
            "repo_health_multi_base_block": 999,
            "repo_health_high_fanout_watch": 999,
            "repo_health_high_fanout_block": 999,
            "repo_health_dep_entries_watch": 999,
            "repo_health_dep_entries_block": 999,
            "repo_health_loc_growth_pct_watch": 8,
            "repo_health_loc_growth_pct_block": 20,
            "repo_health_dep_delta_watch": 999,
            "repo_health_dep_delta_block": 999,
        },
    )
    assert out["deltas"]["loc_growth_pct"] == 10.0
    assert out["severity"] == "watch"
    assert any("loc_growth_pct" in r for r in out["reasons"])


def test_within_band_go(health_dir: Path):
    out = assess_repo_health(
        snapshots=[_snap(god_files=1, multi_base_classes=2, high_fanout_files=1, dep_entries=20)],
        thresholds={
            "repo_health_min_snapshots": 1,
            "repo_health_god_files_watch": 15,
            "repo_health_god_files_block": 40,
            "repo_health_multi_base_watch": 40,
            "repo_health_multi_base_block": 120,
            "repo_health_high_fanout_watch": 30,
            "repo_health_high_fanout_block": 80,
            "repo_health_dep_entries_watch": 180,
            "repo_health_dep_entries_block": 320,
        },
    )
    assert out["severity"] == "go"
    assert out["status"] == "ok"


def test_persist_roundtrip(health_dir: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    # Tiny workspace with one .py file
    ws = tmp_path / "ws"
    (ws / "aiPlat-core" / "core").mkdir(parents=True)
    (ws / "AIPLAT_CAPABILITIES.md").write_text("# cap\n", encoding="utf-8")
    (ws / "aiPlat-core" / "core" / "tiny.py").write_text(
        "x = 1\n\nclass A:\n    pass\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("AIPLAT_WORKSPACE_ROOT", str(ws))
    metrics = scan_repo_health(roots=[ws / "aiPlat-core" / "core"], workspace=ws, max_files=100)
    assert metrics["py_files"] >= 1
    path = append_health_snapshot(metrics)
    assert path and Path(path).is_file()
    out = assess_repo_health(
        thresholds={
            "repo_health_min_snapshots": 1,
            "repo_health_god_files_watch": 999,
            "repo_health_god_files_block": 999,
            "repo_health_multi_base_watch": 999,
            "repo_health_multi_base_block": 999,
            "repo_health_high_fanout_watch": 999,
            "repo_health_high_fanout_block": 999,
            "repo_health_dep_entries_watch": 999,
            "repo_health_dep_entries_block": 999,
        }
    )
    assert out["n_snapshots"] >= 1
    assert out["severity"] in ("go", "watch", "block")
