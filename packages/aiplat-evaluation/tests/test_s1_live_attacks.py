"""S1 live_llm attack pack — stub LLM, docker network=none, no skill tools."""
from __future__ import annotations

import json
import stat
from pathlib import Path

from app.sandbox.security_policy import (
    s1_live_enabled,
    security_redteam_admits,
    security_redteam_is_fixture,
    security_redteam_is_live_llm,
)
from app.worker.runners import execute_runner

ROOT = Path(__file__).resolve().parents[1]
PACK = ROOT / "docs/a3/s1_live_attacks.v0.json"


def _fake_docker(tmp_path: Path) -> Path:
    path = tmp_path / "fake-docker"
    path.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
    path.chmod(path.stat().st_mode | stat.S_IEXEC)
    return path


def test_pack_has_categories_and_size():
    pack = json.loads(PACK.read_text(encoding="utf-8"))
    cases = pack["cases"]
    assert len(cases) >= 20
    cats = {c["category"] for c in cases}
    assert cats >= {
        "prompt_injection",
        "jailbreak",
        "data_exfiltration",
        "tool_abuse",
        "benign_control",
    }
    assert pack["accuracy_claim"] is False
    assert pack["not_security_certification"] is True


def test_live_llm_admit_env_gated(monkeypatch):
    payload = {
        "mode": "live_llm",
        "cases": [{"prompt": "x", "expect": "refuse"}],
    }
    monkeypatch.delenv("AIPLAT_EVAL_S1_LIVE", raising=False)
    assert security_redteam_is_live_llm(payload) is False
    assert security_redteam_admits(payload) is False
    monkeypatch.setenv("AIPLAT_EVAL_S1_LIVE", "1")
    assert s1_live_enabled() is True
    assert security_redteam_is_live_llm(payload) is True
    assert security_redteam_admits(payload) is True
    assert security_redteam_is_fixture({"mode": "live"}) is False


def test_execute_live_llm_stub_reports_metrics(tmp_path: Path, monkeypatch):
    fake = _fake_docker(tmp_path)
    monkeypatch.setenv("AIPLAT_EVAL_SANDBOX_BACKEND", "docker")
    monkeypatch.setenv("AIPLAT_EVAL_DOCKER_BIN", str(fake))
    monkeypatch.setenv("AIPLAT_EVAL_S1_LIVE", "1")
    monkeypatch.setenv("AIPLAT_EVAL_LLM", "stub")
    monkeypatch.setenv("AIPLAT_EVAL_LLM_STUB_OUTPUT", "I cannot help with that.")
    cases = json.loads(PACK.read_text(encoding="utf-8"))["cases"][:8]
    out = execute_runner(
        {
            "job_id": "s1l",
            "runner_id": "security_redteam",
            "payload": {"mode": "live_llm", "cases": cases},
        }
    )
    assert out["accuracy_claim"] is False
    assert out["mode"] == "security_live_llm"
    assert out["evidence"]["live_attacks"] is True
    assert out["evidence"]["live_skill_tools"] is False
    assert out["evidence"]["not_security_certification"] is True
    assert out["evidence"]["docker_network"] == "none"
    m = out["metrics"]
    assert "asr" in m
    assert "leak_rate" in m
    assert "false_refusal_rate" in m
    assert m["cases"] == float(len(cases))
    # stub refusal → attack ASR should be 0 for refuse expects
    assert m["asr"] == 0.0


def test_mode_live_still_denied_without_env(tmp_path: Path, monkeypatch):
    fake = _fake_docker(tmp_path)
    monkeypatch.setenv("AIPLAT_EVAL_SANDBOX_BACKEND", "docker")
    monkeypatch.setenv("AIPLAT_EVAL_DOCKER_BIN", str(fake))
    monkeypatch.delenv("AIPLAT_EVAL_S1_LIVE", raising=False)
    try:
        execute_runner(
            {
                "job_id": "deny",
                "runner_id": "security_redteam",
                "payload": {
                    "mode": "live",
                    "cases": [{"prompt": "x", "expect": "refuse"}],
                },
            }
        )
        assert False, "expected sandbox_required"
    except ValueError as exc:
        assert "sandbox_required" in str(exc)
