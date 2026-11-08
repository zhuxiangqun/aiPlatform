"""User eval_sets overlay must not be overwritten by ensure_builtin (T5)."""
from __future__ import annotations

import json
from pathlib import Path

from core.apps.eval.service.case_pack_legacy import expand_sets_to_manifest, load_set_tasks
from core.harness.evaluation.eval_runner import (
    create_builtin_eval_sets,
    ensure_builtin_sets,
    load_eval_set,
)


def test_dataset_basic_loads_via_eval_set(tmp_path, monkeypatch):
    monkeypatch.setenv("AIPLAT_HOME", str(tmp_path))
    # force re-resolve home if cached — paths use get_aiplat_home each call
    ensure_builtin_sets()
    es = load_eval_set("dataset/basic")
    assert es is not None
    assert len(es.tasks) >= 3
    tasks = load_set_tasks("dataset/basic")
    assert len(tasks) >= 3
    man, _, _ = expand_sets_to_manifest(["dataset/basic"])
    assert len(man) >= 3


def test_user_overlay_not_overwritten(tmp_path, monkeypatch):
    monkeypatch.setenv("AIPLAT_HOME", str(tmp_path))
    ensure_builtin_sets()
    home = Path(tmp_path) / "eval_sets"
    # Some layouts use AIPLAT_HOME directly as eval root via get_aiplat_home
    from core.harness.evaluation import eval_runner as er

    dst = er._eval_dir() / "default" / "normal.json"
    assert dst.exists()
    custom = {
        "set_id": "default/normal",
        "category": "normal",
        "description": "USER OVERLAY — do not clobber",
        "created_at": 1.0,
        "tasks": [
            {
                "task_id": "user-only-001",
                "agent_id": "x",
                "user_input": "overlay marker",
                "category": "normal",
                "expected_tools": [],
                "forbidden_tools": [],
                "expected_steps": [],
                "success_criteria": {"must_contain": ["overlay"]},
                "risk_level": "low",
            }
        ],
    }
    dst.write_text(json.dumps(custom, ensure_ascii=False, indent=2), encoding="utf-8")
    # Re-run builtin copy — must leave overlay intact
    create_builtin_eval_sets()
    ensure_builtin_sets()
    data = json.loads(dst.read_text(encoding="utf-8"))
    assert data["description"].startswith("USER OVERLAY")
    assert data["tasks"][0]["task_id"] == "user-only-001"
    es = load_eval_set("default/normal")
    assert es is not None
    assert es.tasks[0].task_id == "user-only-001"
