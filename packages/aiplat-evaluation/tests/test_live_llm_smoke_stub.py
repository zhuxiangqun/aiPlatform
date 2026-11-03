"""Stub-path acceptance for live_llm_smoke (no network)."""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_live_llm_smoke_stub_writes_evidence(tmp_path: Path, monkeypatch):
    evid = tmp_path / "drills"
    evid.mkdir()
    env = os.environ.copy()
    env["PYTHONPATH"] = str(ROOT)
    env["AIPLAT_EVAL_LLM_LIVE"] = "0"
    env["AIPLAT_EVAL_LIVE_LLM_EVIDENCE_DIR"] = str(evid)
    env["AIPLAT_EVAL_LIVE_LLM_TASKS"] = str(ROOT / "docs/a3/live_llm_tasks.v0.json")
    env.pop("AIPLAT_EVAL_LLM_BASE_URL", None)
    proc = subprocess.run(
        [sys.executable, str(ROOT / "scripts/live_llm_smoke.py")],
        cwd=str(ROOT),
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    assert proc.returncode == 0, proc.stderr + proc.stdout
    summary = json.loads(proc.stdout.strip().splitlines()[-1])
    assert summary["gate"] == "ok"
    assert summary["accuracy_claim"] is False
    assert summary["stub_complete"] is True
    paths = list(evid.glob("local-eval-live-llm-*.json"))
    assert len(paths) == 1
    payload = json.loads(paths[0].read_text(encoding="utf-8"))
    assert payload["accuracy_claim"] is False
    assert payload["task_count"] == 10
    assert payload["live_requested"] is False
    families = {r["family"] for r in payload["runs"] if r["mode_label"] == "stub"}
    assert families == {"agent", "skill", "prompt", "kb"}
