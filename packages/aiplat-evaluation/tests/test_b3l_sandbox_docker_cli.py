"""B3-L.3 — docker backend for allowlisted cli_probe."""
from __future__ import annotations

import os
import stat
from pathlib import Path

from fastapi.testclient import TestClient

from app.auth import mint_local_token
from app.config import EvalServiceConfig
from app.main import create_app
from app.runner_allowlist import is_enqueue_allowed
from app.sandbox.docker_exec import run_in_docker, validate_cli_argv
from app.sandbox.policy import sandbox_admits, sandbox_backend
from app.store.jobs import enqueue_job, get_job
from app.store.migrate import apply_migrations
from app.worker.claim import process_once
from app.worker.runners import execute_runner


def _fake_docker(tmp_path: Path) -> Path:
    """Stub docker that accepts `run ... image argv` and echoes argv."""
    path = tmp_path / "fake-docker"
    path.write_text(
        "#!/bin/sh\n"
        "# minimal docker stub for tests\n"
        "if [ \"$1\" != \"run\" ]; then echo 'only run supported' >&2; exit 2; fi\n"
        "# find image token then print remaining as stdout\n"
        "shift\n"
        "while [ $# -gt 0 ]; do\n"
        "  case \"$1\" in\n"
        "    --*) shift; continue ;;\n"
        "    alpine:*|busybox*) shift; break ;;\n"
        "    *) shift; continue ;;\n"
        "  esac\n"
        "done\n"
        "if [ \"$1\" = \"false\" ]; then echo fail >&2; exit 1; fi\n"
        "printf '%s' \"$*\"\n"
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
        db_url=f"sqlite:///{tmp_path / 'b3d.sqlite3'}",
        version="0.1.0",
        protocol="eval.protocol.v0",
        require_auth=True,
    )


def test_validate_cli_argv():
    ok, _ = validate_cli_argv(["echo", "hi"])
    assert ok
    ok, detail = validate_cli_argv(["rm", "-rf", "/"])
    assert not ok
    assert "allowlisted" in detail
    ok, detail = validate_cli_argv(["echo", "a;b"])
    assert not ok


def test_docker_backend_admits_cli_with_fake_bin(tmp_path: Path, monkeypatch):
    fake = _fake_docker(tmp_path)
    monkeypatch.setenv("AIPLAT_EVAL_SANDBOX_BACKEND", "docker")
    monkeypatch.setenv("AIPLAT_EVAL_DOCKER_BIN", str(fake))
    assert sandbox_backend() == "docker"
    assert sandbox_admits("cli_probe") is True
    assert sandbox_admits("skill_suite") is False
    assert is_enqueue_allowed("cli_probe") is True


def test_docker_backend_denies_cli_without_docker(monkeypatch):
    monkeypatch.setenv("AIPLAT_EVAL_SANDBOX_BACKEND", "docker")
    monkeypatch.setenv("AIPLAT_EVAL_DOCKER_BIN", "/nonexistent/docker-bin-xyz")
    assert sandbox_admits("cli_probe") is False
    assert is_enqueue_allowed("cli_probe") is False
    # http_probe still admitted under docker backend
    assert sandbox_admits("http_probe") is True


def test_run_in_docker_with_fake(tmp_path: Path, monkeypatch):
    fake = _fake_docker(tmp_path)
    monkeypatch.setenv("AIPLAT_EVAL_DOCKER_BIN", str(fake))
    out = run_in_docker(["echo", "ok"])
    assert out["ok"] is True
    assert "ok" in out["stdout"]
    assert out["audit"]["network"] == "none"


def test_execute_cli_probe(tmp_path: Path, monkeypatch):
    fake = _fake_docker(tmp_path)
    monkeypatch.setenv("AIPLAT_EVAL_SANDBOX_BACKEND", "docker")
    monkeypatch.setenv("AIPLAT_EVAL_DOCKER_BIN", str(fake))
    out = execute_runner(
        {
            "job_id": "j1",
            "runner_id": "cli_probe",
            "payload": {"argv": ["echo", "hi"]},
        }
    )
    assert out["ok"] is True
    assert out["mode"] == "docker_cli"
    assert out["accuracy_claim"] is False


def test_enqueue_and_process_cli(tmp_path: Path, monkeypatch):
    fake = _fake_docker(tmp_path)
    monkeypatch.setenv("AIPLAT_EVAL_REQUIRE_AUTH", "1")
    monkeypatch.setenv("AIPLAT_EVAL_SANDBOX_BACKEND", "docker")
    monkeypatch.setenv("AIPLAT_EVAL_DOCKER_BIN", str(fake))
    client = TestClient(create_app(_cfg(tmp_path)))
    headers = {"Authorization": f"Bearer {mint_local_token(tenant_id='tenant-local')}"}
    r = client.post(
        "/api/platform/apps/eval/probes/cli",
        headers=headers,
        json={"idempotency_key": "cli-1", "argv": ["true"]},
    )
    assert r.status_code == 202, r.text
    assert r.json()["runner_id"] == "cli_probe"
    job_id = r.json()["job_id"]
    db = f"sqlite:///{tmp_path / 'b3d.sqlite3'}"
    queued = get_job(db, job_id)
    assert queued and queued.get("payload", {}).get("argv") == ["true"]

    out = process_once(db, worker_id="w-docker")
    assert out is not None
    assert out["status"] == "succeeded"
    stored = get_job(db, job_id)
    assert stored and stored["status"] == "succeeded"


def test_skill_tools_still_denied_under_docker(tmp_path: Path, monkeypatch):
    fake = _fake_docker(tmp_path)
    monkeypatch.setenv("AIPLAT_EVAL_REQUIRE_AUTH", "1")
    monkeypatch.setenv("AIPLAT_EVAL_SANDBOX_BACKEND", "docker")
    monkeypatch.setenv("AIPLAT_EVAL_DOCKER_BIN", str(fake))
    client = TestClient(create_app(_cfg(tmp_path)))
    headers = {"Authorization": f"Bearer {mint_local_token(tenant_id='tenant-local')}"}
    r = client.post(
        "/api/platform/apps/eval/skill-evals/suites/s1/run",
        headers=headers,
        json={"tools": ["shell"]},
    )
    assert r.status_code == 422
    assert r.json()["error"]["code"] == "sandbox_required"
    # bare body without fixture mode stays fail-closed
    r2 = client.post(
        "/api/platform/apps/eval/skill-evals/suites/s1/run",
        headers=headers,
        json={},
    )
    assert r2.status_code == 422
