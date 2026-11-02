"""B2 — wall-clock job timeout → timed_out (never succeeded)."""
from __future__ import annotations

import time
from pathlib import Path

from app.store.jobs import enqueue_job, get_job
from app.store.migrate import apply_migrations
from app.worker.claim import process_once
from app.worker.timeout import job_timeout_sec, run_with_timeout


def _db(tmp_path: Path) -> str:
    url = f"sqlite:///{tmp_path / 'to.sqlite3'}"
    apply_migrations(url)
    return url


def test_run_with_timeout_raises():
    try:
        run_with_timeout(lambda: time.sleep(0.5), timeout_sec=0.05)
        assert False, "expected TimeoutError"
    except TimeoutError as exc:
        assert "wall-clock" in str(exc)


def test_run_with_timeout_disabled():
    assert run_with_timeout(lambda: 7, timeout_sec=0) == 7


def test_job_timeout_sec_env(monkeypatch):
    monkeypatch.setenv("AIPLAT_EVAL_JOB_TIMEOUT_SEC", "12.5")
    assert job_timeout_sec() == 12.5
    assert job_timeout_sec(3.0) == 3.0


def test_process_once_marks_timed_out(tmp_path: Path, monkeypatch):
    db = _db(tmp_path)
    enqueue_job(
        db,
        runner_id="replay_trace",
        tenant_id="t",
        payload={"trace": {"ok": True, "steps": [1]}},
    )

    def _slow(_job):
        time.sleep(0.4)
        return {"ok": True, "accuracy_claim": False}

    monkeypatch.setattr("app.worker.claim.execute_runner", _slow)
    out = process_once(db, worker_id="w-to", job_timeout_sec_override=0.05)
    assert out is not None
    assert out["status"] == "timed_out"
    assert out.get("timed_out") is True
    assert out["error_code"] == "timed_out"
    assert out["executed"] is False
    stored = get_job(db, out["job_id"])
    assert stored["status"] == "timed_out"
    assert stored["result"].get("ok") is False
    assert stored["result"].get("accuracy_claim") is False
