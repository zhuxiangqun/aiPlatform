"""Curated SFT export + feedback marking for 小朱 trajectories."""
import json
from pathlib import Path

import pytest

from core.harness.digital_human.trajectory_collector import (
    collect_turn,
    export_curated_sharegpt_dataset,
    infer_feedback_from_user,
    mark_feedback,
)


@pytest.fixture
def traj_dir(tmp_path, monkeypatch):
    d = tmp_path / "trajectories"
    d.mkdir()
    monkeypatch.setattr(
        "core.harness.digital_human.trajectory_collector._TRAJ_DIR",
        d,
    )
    return d


def test_infer_feedback():
    assert infer_feedback_from_user("讲得对")["rating"] == "good"
    bad = infer_feedback_from_user("不对，应该是走 /app/factory")
    assert bad["rating"] == "bad"
    assert "factory" in bad["correction"]
    assert infer_feedback_from_user("工作区有哪些 Skill") is None


def test_mark_good_and_export(traj_dir, tmp_path):
    sid = "dh_test_good"
    collect_turn(sid, "user", "选模怎么走？")
    collect_turn(sid, "assistant", "走 purpose → unified_pipeline")
    assert mark_feedback(sid, "good")["ok"] is True
    out = export_curated_sharegpt_dataset(output_dir=str(tmp_path / "train"), session_filter=sid)
    assert out["samples"] == 1
    lines = Path(out["output_path"]).read_text(encoding="utf-8").strip().splitlines()
    sample = json.loads(lines[0])
    assert sample["conversations"][0]["value"] == "选模怎么走？"
    assert "unified_pipeline" in sample["conversations"][1]["value"]
    assert sample["meta"]["quality"] == "good"


def test_mark_bad_with_gold(traj_dir, tmp_path):
    sid = "dh_test_gold"
    collect_turn(sid, "user", "做应用去哪？")
    collect_turn(sid, "assistant", "去 Agents 页")
    r = mark_feedback(sid, "bad", correction="不对，应该是 /app/factory")
    assert r["ok"] and r["has_gold"]
    out = export_curated_sharegpt_dataset(output_dir=str(tmp_path / "train"), session_filter=sid)
    assert out["samples"] == 1
    sample = json.loads(Path(out["output_path"]).read_text(encoding="utf-8").strip())
    assert sample["meta"]["quality"] == "gold"
    assert "/app/factory" in sample["conversations"][1]["value"]


def test_uncurated_not_exported(traj_dir, tmp_path):
    sid = "dh_noise"
    collect_turn(sid, "user", "hi")
    collect_turn(sid, "assistant", "hello")
    out = export_curated_sharegpt_dataset(output_dir=str(tmp_path / "train"), session_filter=sid)
    assert out["samples"] == 0


def test_seed_sharegpt_export(tmp_path):
    from core.harness.digital_human.trajectory_collector import export_seed_sharegpt_dataset

    out_dir = tmp_path / "train"
    r1 = export_seed_sharegpt_dataset(output_dir=str(out_dir), force=True)
    assert r1["samples"] >= 4
    path = Path(r1["output_path"])
    assert path.name == "sft_digital_human_seed.jsonl"
    lines = path.read_text(encoding="utf-8").strip().splitlines()
    sample = json.loads(lines[0])
    assert sample["meta"]["quality"] == "seed"
    assert sample["conversations"][0]["from"] == "human"
    assert "unified_pipeline" in path.read_text(encoding="utf-8")
    r2 = export_seed_sharegpt_dataset(output_dir=str(out_dir), force=False)
    assert r2["samples"] == r1["samples"]
    assert "exists" in (r2.get("note") or "")
