"""B3-L.4 — skill_suite fixture-only under docker (tools still denied)."""
from __future__ import annotations

import stat
from pathlib import Path

from fastapi.testclient import TestClient

from app.auth import mint_local_token
from app.config import EvalServiceConfig
from app.main import create_app
from app.runner_allowlist import is_enqueue_allowed
from app.sandbox.skill_policy import skill_suite_is_fixture
from app.store.jobs import get_job
from app.worker.claim import process_once
from app.worker.runners import execute_runner


def _fake_docker(tmp_path: Path) -> Path:
    path = tmp_path / "fake-docker"
    path.write_text(
        "#!/bin/sh\n"
        "if [ \"$1\" != \"run\" ]; then exit 2; fi\n"
        "shift\n"
        "while [ $# -gt 0 ]; do\n"
        "  case \"$1\" in\n"
        "    --*) shift; continue ;;\n"
        "    alpine:*|busybox*) shift; break ;;\n"
        "    *) shift; continue ;;\n"
        "  esac\n"
        "done\n"
        "exit 0\n",
        encoding="utf-8",
    )
    path.chmod(path.stat().st_mode | stat.S_IEXEC)
    return path


def _cfg(tmp_path: Path) -> EvalServiceConfig:
    return EvalServiceConfig(
        mode="standalone",
        host="127.0.0.1",
        port=8010,
        db_url=f"sqlite:///{tmp_path / 'skill.sqlite3'}",
        version="0.1.0",
        protocol="eval.protocol.v0",
        require_auth=True,
    )


def test_fixture_policy():
    assert skill_suite_is_fixture({"mode": "fixture"}) is True
    assert skill_suite_is_fixture({"cases": [{"name": "a"}]}) is True
    assert skill_suite_is_fixture({}) is False
    assert skill_suite_is_fixture({"mode": "fixture", "tools": ["shell"]}) is False
    assert skill_suite_is_fixture({"mode": "live"}) is False


def test_enqueue_fixture_ok_tools_denied(tmp_path: Path, monkeypatch):
    fake = _fake_docker(tmp_path)
    monkeypatch.setenv("AIPLAT_EVAL_REQUIRE_AUTH", "1")
    monkeypatch.setenv("AIPLAT_EVAL_SANDBOX_BACKEND", "docker")
    monkeypatch.setenv("AIPLAT_EVAL_DOCKER_BIN", str(fake))
    client = TestClient(create_app(_cfg(tmp_path)))
    headers = {"Authorization": f"Bearer {mint_local_token(tenant_id='tenant-local')}"}

    denied = client.post(
        "/api/platform/apps/eval/skill-evals/suites/s1/run",
        headers=headers,
        json={"tools": ["shell"]},
    )
    assert denied.status_code == 422
    assert denied.json()["error"]["code"] == "sandbox_required"

    empty = client.post(
        "/api/platform/apps/eval/skill-evals/suites/s1/run",
        headers=headers,
        json={},
    )
    assert empty.status_code == 422

    ok = client.post(
        "/api/platform/apps/eval/skill-evals/suites/s1/run",
        headers=headers,
        json={
            "idempotency_key": "sk-fix-1",
            "mode": "fixture",
            "cases": [{"name": "c1", "expected_ok": True, "actual_ok": True}],
        },
    )
    assert ok.status_code == 202, ok.text
    assert ok.json()["runner_id"] == "skill_suite"
    assert is_enqueue_allowed("skill_suite", {"mode": "fixture"}) is True


def test_execute_fixture(tmp_path: Path, monkeypatch):
    fake = _fake_docker(tmp_path)
    monkeypatch.setenv("AIPLAT_EVAL_SANDBOX_BACKEND", "docker")
    monkeypatch.setenv("AIPLAT_EVAL_DOCKER_BIN", str(fake))
    out = execute_runner(
        {
            "job_id": "j1",
            "runner_id": "skill_suite",
            "payload": {
                "mode": "fixture",
                "cases": [
                    {"name": "a", "expected_ok": True, "actual_ok": True},
                    {"name": "b", "expected_ok": False, "actual_ok": False},
                ],
            },
        }
    )
    assert out["ok"] is True
    assert out["mode"] == "skill_fixture"
    assert out["accuracy_claim"] is False
    assert out["evidence"]["tools_executed"] is False


def test_process_once_fixture(tmp_path: Path, monkeypatch):
    fake = _fake_docker(tmp_path)
    monkeypatch.setenv("AIPLAT_EVAL_REQUIRE_AUTH", "1")
    monkeypatch.setenv("AIPLAT_EVAL_SANDBOX_BACKEND", "docker")
    monkeypatch.setenv("AIPLAT_EVAL_DOCKER_BIN", str(fake))
    client = TestClient(create_app(_cfg(tmp_path)))
    headers = {"Authorization": f"Bearer {mint_local_token(tenant_id='tenant-local')}"}
    r = client.post(
        "/api/platform/apps/eval/skill-evals/suites/demo/run",
        headers=headers,
        json={
            "idempotency_key": "sk-2",
            "mode": "fixture",
            "cases": [{"expected_ok": True, "actual_ok": True}],
        },
    )
    assert r.status_code == 202
    db = f"sqlite:///{tmp_path / 'skill.sqlite3'}"
    out = process_once(db, worker_id="w-skill")
    assert out is not None
    assert out["status"] == "succeeded"
    stored = get_job(db, r.json()["job_id"])
    assert stored and stored["status"] == "succeeded"
