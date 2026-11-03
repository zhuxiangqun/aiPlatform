"""B3-L — local_stub sandbox admit for http_probe (no network)."""
from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from app.auth import mint_local_token
from app.config import EvalServiceConfig
from app.main import create_app
from app.runner_allowlist import assert_runner_allowed_for_execute, is_enqueue_allowed
from app.sandbox.policy import sandbox_admits, sandbox_backend, sandbox_health
from app.store.jobs import enqueue_job, get_job
from app.store.migrate import apply_migrations
from app.worker.claim import process_once
from app.worker.runners import execute_runner


def _cfg(tmp_path: Path) -> EvalServiceConfig:
    return EvalServiceConfig(
        mode="standalone",
        host="127.0.0.1",
        port=8010,
        db_url=f"sqlite:///{tmp_path / 'b3l.sqlite3'}",
        version="0.1.0",
        protocol="eval.protocol.v0",
        require_auth=True,
    )


def _headers() -> dict:
    return {"Authorization": f"Bearer {mint_local_token(tenant_id='tenant-local')}"}


def test_sandbox_off_by_default(monkeypatch):
    monkeypatch.delenv("AIPLAT_EVAL_SANDBOX_BACKEND", raising=False)
    assert sandbox_backend() == "off"
    assert sandbox_admits("http_probe") is False
    assert is_enqueue_allowed("http_probe") is False
    assert is_enqueue_allowed("skill_suite") is False


def test_local_stub_admits_http_probe_only(monkeypatch):
    monkeypatch.setenv("AIPLAT_EVAL_SANDBOX_BACKEND", "local_stub")
    assert sandbox_admits("http_probe") is True
    assert is_enqueue_allowed("http_probe") is True
    assert sandbox_admits("skill_suite") is False
    assert is_enqueue_allowed("cli_probe") is False
    assert_runner_allowed_for_execute("http_probe")  # no raise
    health = sandbox_health()
    assert health["sandbox_backend"] == "local_stub"
    assert health["sandbox_real_isolation"] is False


def test_enqueue_http_probe_202_when_stub(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("AIPLAT_EVAL_REQUIRE_AUTH", "1")
    monkeypatch.setenv("AIPLAT_EVAL_SANDBOX_BACKEND", "local_stub")
    client = TestClient(create_app(_cfg(tmp_path)))
    r = client.post(
        "/api/platform/apps/eval/probes/http",
        headers=_headers(),
        json={"idempotency_key": "b3-http-1", "url": "https://example.com/x", "method": "GET"},
    )
    assert r.status_code == 202, r.text
    body = r.json()
    assert body["runner_id"] == "http_probe"
    assert body["sandbox_backend"] == "local_stub"
    assert body["process_split_authorized"] is False


def test_skill_still_denied_under_stub(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("AIPLAT_EVAL_REQUIRE_AUTH", "1")
    monkeypatch.setenv("AIPLAT_EVAL_SANDBOX_BACKEND", "local_stub")
    client = TestClient(create_app(_cfg(tmp_path)))
    r = client.post(
        "/api/platform/apps/eval/skill-evals/suites/s1/run",
        headers=_headers(),
        json={},
    )
    assert r.status_code == 422
    assert r.json()["error"]["code"] == "sandbox_required"


def test_execute_http_probe_stub_no_network(monkeypatch):
    monkeypatch.setenv("AIPLAT_EVAL_SANDBOX_BACKEND", "local_stub")
    out = execute_runner(
        {
            "job_id": "j1",
            "runner_id": "http_probe",
            "payload": {"url": "https://example.com", "method": "GET"},
        }
    )
    assert out["ok"] is True
    assert out["mode"] == "local_stub"
    assert out["accuracy_claim"] is False
    assert out["evidence"]["network_io"] is False


def test_process_once_http_probe_stub(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("AIPLAT_EVAL_SANDBOX_BACKEND", "local_stub")
    db = f"sqlite:///{tmp_path / 'b3job.sqlite3'}"
    apply_migrations(db)
    job = enqueue_job(
        db,
        runner_id="http_probe",
        tenant_id="t",
        payload={"url": "https://example.com/health", "method": "HEAD"},
    )
    out = process_once(db, worker_id="w-b3")
    assert out is not None
    assert out["status"] == "succeeded"
    stored = get_job(db, job["job_id"])
    assert stored and stored["status"] == "succeeded"


def test_healthz_exposes_sandbox(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("AIPLAT_EVAL_REQUIRE_AUTH", "1")
    monkeypatch.setenv("AIPLAT_EVAL_SANDBOX_BACKEND", "local_stub")
    client = TestClient(create_app(_cfg(tmp_path)))
    hz = client.get("/healthz").json()
    assert hz["b3l_sandbox"] is True
    assert hz["sandbox_backend"] == "local_stub"
    assert hz["sandbox_real_isolation"] is False
    assert hz["process_split_authorized"] is False
