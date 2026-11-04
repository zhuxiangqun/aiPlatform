"""g2b_run_model_outputs — facilitator stub path (no network)."""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "g2b_run_model_outputs.py"
TASKS = ROOT / "docs/a3/g2b_tasks.v0.json"


def test_stub_fills_limit(tmp_path: Path):
    out = tmp_path / "model_outputs.json"
    env = os.environ.copy()
    env["AIPLAT_EVAL_LLM"] = "stub"
    env["AIPLAT_EVAL_LLM_STUB_OUTPUT"] = "STUB_OK"
    env.pop("AIPLAT_EVAL_LLM_BASE_URL", None)
    proc = subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "--tasks",
            str(TASKS),
            "--out",
            str(out),
            "--limit",
            "3",
        ],
        cwd=str(ROOT),
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    assert proc.returncode == 0, proc.stderr + proc.stdout
    data = json.loads(out.read_text(encoding="utf-8"))
    assert len(data) == 3
    assert all(v == "STUB_OK" for v in data.values())
    assert '"accuracy_claim": false' in proc.stdout.lower() or "accuracy_claim" in proc.stdout
