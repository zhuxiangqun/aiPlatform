"""prod_live_baseline / s1_prod_model refuse smoke-only model without override."""
from __future__ import annotations

import os
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _clean_env() -> dict:
    env = os.environ.copy()
    for k in list(env):
        if k.startswith("AIPLAT_"):
            del env[k]
    return env


def test_prod_live_refuses_missing_model():
    proc = subprocess.run(
        ["bash", str(ROOT / "scripts/prod_live_baseline.sh")],
        cwd=str(ROOT),
        env=_clean_env(),
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 2
    assert "AIPLAT_EVAL_PROD_MODEL" in proc.stderr


def test_prod_live_refuses_smoke_model():
    env = _clean_env()
    env["AIPLAT_EVAL_PROD_MODEL"] = "qwen2.5:3b"
    env["AIPLAT_EVAL_LLM_BASE_URL"] = "http://127.0.0.1:11434/v1"
    proc = subprocess.run(
        ["bash", str(ROOT / "scripts/prod_live_baseline.sh")],
        cwd=str(ROOT),
        env=env,
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 2
    assert "smoke" in proc.stderr.lower() or "qwen2.5:3b" in proc.stderr


def test_prod_live_forces_model_over_leftover_env():
    """Leftover AIPLAT_EVAL_LLM_MODEL=3b must not win over PROD_MODEL."""
    src = (ROOT / "scripts/prod_live_baseline.sh").read_text(encoding="utf-8")
    assert 'export AIPLAT_EVAL_LLM_MODEL="$PROD_MODEL"' in src
    assert 'AIPLAT_EVAL_LLM_MODEL="${AIPLAT_EVAL_LLM_MODEL:-$PROD_MODEL}"' not in src
    s1 = (ROOT / "scripts/s1_prod_model_gate.sh").read_text(encoding="utf-8")
    assert 'export AIPLAT_EVAL_LLM_MODEL="$PROD_MODEL"' in s1
