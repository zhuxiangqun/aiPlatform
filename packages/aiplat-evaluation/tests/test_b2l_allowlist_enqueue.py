"""B2-L — allowlist enqueue + dual-point Worker reject."""
from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from app.auth import mint_local_token
from app.config import EvalServiceConfig
from app.main import create_app
from app.runner_allowlist import classify_runner, is_enqueue_allowed
from app.store.jobs import enqueue_job, get_job
from app.store.migrate import apply_migrations
from app.worker.allowlist_guard import admit_job_for_execute, reject_forged_job


def _cfg(tmp_path: Path) -> EvalServiceConfig:
    return EvalServiceConfig(
        mode="standalone",
        host="127.0.0.1",
        port=8010,
        db_url=f"sqlite:///{tmp_path / 'b2l.sqlite3'}",
        version="0.1.0",
        protocol="eval.protocol.v0",
        require_auth=True,
    )


def _headers() -> dict:
    return {"Authorization": f"Bearer {mint_local_token(tenant_id='tenant-local')}"}


def test_classify_runner_matrix():
    assert classify_runner("prompt_eval") == "allowed"
    assert classify_runner("skill_suite") == "sandbox_required"
    assert classify_runner("http_probe") == "sandbox_required"
    assert classify_runner("unknown_runner_xyz") == "forbidden"
    assert is_enqueue_allowed("kb_rag") is True
    assert is_enqueue_allowed("skill_suite") is False


def test_allowlist_enqueue_202(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("AIPLAT_EVAL_REQUIRE_AUTH", "1")
    client = TestClient(create_app(_cfg(tmp_path)))
    r = client.post(
        "/api/platform/apps/eval/prompts/eval/runs",
        headers=_headers(),
        json={"idempotency_key": "idem-1", "prompt": "hi"},
    )
    assert r.status_code == 202
    body = r.json()
    assert body["status"] == "queued"
    assert body["runner_id"] == "prompt_eval"
    assert body["process_split_authorized"] is False
    assert body["job_id"]

    # idempotent
    r2 = client.post(
        "/api/platform/apps/eval/prompts/eval/runs",
        headers=_headers(),
        json={"idempotency_key": "idem-1", "prompt": "hi"},
    )
    assert r2.status_code == 202
    assert r2.json()["job_id"] == body["job_id"]


def test_skill_and_probe_denied(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("AIPLAT_EVAL_REQUIRE_AUTH", "1")
    client = TestClient(create_app(_cfg(tmp_path)))
    r = client.post(
        "/api/platform/apps/eval/skill-evals/suites/s1/run",
        headers=_headers(),
        json={},
    )
    assert r.status_code == 422
    assert r.json()["error"]["code"] == "sandbox_required"
    assert r.json()["error"]["runner_id"] == "skill_suite"

    r2 = client.post(
        "/api/platform/apps/eval/probes/http",
        headers=_headers(),
        json={},
    )
    assert r2.status_code == 422
    assert r2.json()["error"]["code"] == "sandbox_required"


def test_worker_rejects_forged_skill_job(tmp_path: Path):
    db = f"sqlite:///{tmp_path / 'forge.sqlite3'}"
    apply_migrations(db)
    # Bypass API: insert forbidden runner directly
    forged = enqueue_job(
        db, runner_id="skill_suite", tenant_id="t", payload={"bypass": True}
    )
    ok, code, _ = admit_job_for_execute(forged)
    assert ok is False
    assert code == "sandbox_required"

    out = reject_forged_job(db, forged["job_id"])
    assert out is not None
    assert out["admitted"] is False
    assert out["status"] == "dead_letter"
    assert out["error_code"] == "sandbox_required"

    stored = get_job(db, forged["job_id"])
    assert stored is not None
    assert stored["status"] == "dead_letter"


def test_healthz_b2l_flag(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("AIPLAT_EVAL_REQUIRE_AUTH", "0")
    client = TestClient(create_app(_cfg(tmp_path)))
    hz = client.get("/healthz").json()
    assert hz["process_split_authorized"] is False
    assert hz["b2l_allowlist_enqueue"] is True
    assert hz["environment"] == "local"
