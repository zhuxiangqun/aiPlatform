"""B2 — cancel queued/running → cancelled; cooperative vs worker finalize."""
from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from app.auth import mint_local_token
from app.config import EvalServiceConfig
from app.main import create_app
from app.store.jobs import cancel_job, enqueue_job, get_job
from app.store.migrate import apply_migrations
from app.worker.claim import process_once


def _db(tmp_path: Path) -> str:
    url = f"sqlite:///{tmp_path / 'cancel.sqlite3'}"
    apply_migrations(url)
    return url


def test_cancel_queued_job(tmp_path: Path):
    db = _db(tmp_path)
    job = enqueue_job(
        db,
        runner_id="replay_trace",
        tenant_id="t",
        payload={"trace": {"ok": True}, "expected": {"ok": True}},
    )
    out = cancel_job(db, job["job_id"])
    assert out["ok"] is True
    assert out["job"]["status"] == "cancelled"
    assert out["job"]["error_code"] == "cancelled"
    stored = get_job(db, job["job_id"])
    assert stored["status"] == "cancelled"
    # Terminal cancel is idempotent-ish
    again = cancel_job(db, job["job_id"])
    assert again["ok"] is True
    assert again["reason"] == "already_cancelled"


def test_cancel_rejects_succeeded(tmp_path: Path):
    db = _db(tmp_path)
    enqueue_job(
        db,
        runner_id="replay_trace",
        tenant_id="t",
        payload={"trace": {"ok": True, "steps": []}, "expected": {"ok": True}},
    )
    done = process_once(db, worker_id="w1")
    assert done["status"] == "succeeded"
    out = cancel_job(db, done["job_id"])
    assert out["ok"] is False
    assert out["reason"] == "not_cancellable"
    assert get_job(db, done["job_id"])["status"] == "succeeded"


def _cfg(tmp_path: Path) -> EvalServiceConfig:
    db = _db(tmp_path)
    return EvalServiceConfig(
        mode="standalone",
        host="127.0.0.1",
        port=8010,
        db_url=db,
        version="0.1.0-test",
        protocol="eval.protocol.v0",
        require_auth=True,
    )


def test_cancel_api(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("AIPLAT_EVAL_JWT_SECRET", "aiplat-eval-local-dev-secret")
    cfg = _cfg(tmp_path)
    job = enqueue_job(
        cfg.db_url,
        runner_id="code_review_gold",
        tenant_id="t",
        payload={"findings": ["a"], "gold": ["a"]},
    )
    client = TestClient(create_app(cfg))
    token = mint_local_token(tenant_id="tenant-local")
    r = client.post(
        f"/api/platform/apps/eval/jobs/{job['job_id']}/cancel",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["ok"] is True
    assert body["job"]["status"] == "cancelled"
    assert body["process_split_authorized"] is False


def test_worker_respects_cancel_before_finalize(tmp_path: Path, monkeypatch):
    db = _db(tmp_path)
    job = enqueue_job(
        db,
        runner_id="replay_trace",
        tenant_id="t",
        payload={"trace": {"ok": True, "steps": [1]}, "expected": {"ok": True}},
    )

    def _execute_then_cancel(j):
        cancel_job(db, j["job_id"])
        return {"ok": True, "accuracy_claim": False, "metrics": {"pass": 1.0}}

    monkeypatch.setattr("app.worker.claim.execute_runner", _execute_then_cancel)
    out = process_once(db, worker_id="w-cancel")
    assert out["status"] == "cancelled"
    assert out.get("cancelled") is True
    assert get_job(db, job["job_id"])["status"] == "cancelled"
