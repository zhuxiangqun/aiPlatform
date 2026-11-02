"""B2-L — claim / lease / heartbeat / reclaim (SQLite IMMEDIATE)."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path

from app.store.jobs import (
    claim_next_job,
    enqueue_job,
    get_job,
    heartbeat_job,
    update_job_status,
)
from app.store.migrate import apply_migrations
from app.worker.claim import process_once


def _db(tmp_path: Path) -> str:
    url = f"sqlite:///{tmp_path / 'claim.sqlite3'}"
    apply_migrations(url)
    return url


def test_claim_two_jobs_sequential(tmp_path: Path):
    db = _db(tmp_path)
    a = enqueue_job(db, runner_id="prompt_eval", tenant_id="t", payload={"n": 1})
    b = enqueue_job(db, runner_id="kb_rag", tenant_id="t", payload={"n": 2})
    c1 = claim_next_job(db, worker_id="w1", lease_seconds=60)
    assert c1 is not None
    assert c1["status"] == "running"
    assert c1["leased_by"] == "w1"
    assert c1["job_id"] in {a["job_id"], b["job_id"]}
    c2 = claim_next_job(db, worker_id="w2", lease_seconds=60)
    assert c2 is not None
    assert c2["job_id"] != c1["job_id"]
    assert c2["leased_by"] == "w2"
    assert claim_next_job(db, worker_id="w3") is None


def test_heartbeat_extends_lease(tmp_path: Path):
    db = _db(tmp_path)
    enqueue_job(db, runner_id="prompt_eval", tenant_id="t")
    job = claim_next_job(db, worker_id="w1", lease_seconds=30)
    assert job is not None
    before = job["lease_expires_at"]
    hb = heartbeat_job(db, job["job_id"], worker_id="w1", lease_seconds=120)
    assert hb is not None
    assert hb["lease_expires_at"] >= before
    assert hb["heartbeat_at"]


def test_expired_lease_reclaim(tmp_path: Path):
    db = _db(tmp_path)
    enqueue_job(db, runner_id="arena", tenant_id="t")
    job = claim_next_job(db, worker_id="w1", lease_seconds=60)
    assert job is not None
    past = (datetime.now(timezone.utc) - timedelta(seconds=10)).isoformat()
    update_job_status(
        db, job["job_id"], status="running", lease_expires_at=past
    )

    reclaimed = claim_next_job(db, worker_id="w2", lease_seconds=60)
    assert reclaimed is not None
    assert reclaimed["job_id"] == job["job_id"]
    assert reclaimed["leased_by"] == "w2"
    assert reclaimed["attempts"] >= 2


def test_process_once_admits_and_denies(tmp_path: Path):
    db = _db(tmp_path)
    enqueue_job(
        db,
        runner_id="prompt_eval",
        tenant_id="t",
        payload={"prompt": "p", "expected": "e", "actual": "e"},
    )
    enqueue_job(db, runner_id="skill_suite", tenant_id="t")

    first = process_once(db, worker_id="w1")
    assert first is not None
    second = process_once(db, worker_id="w1")
    assert second is not None
    by_runner = {first["runner_id"]: first, second["runner_id"]: second}
    assert by_runner["prompt_eval"]["admitted"] is True
    assert by_runner["prompt_eval"]["executed"] is True
    assert by_runner["prompt_eval"]["status"] == "succeeded"
    assert by_runner["skill_suite"]["admitted"] is False
    assert by_runner["skill_suite"]["status"] == "dead_letter"


def test_max_attempts_dead_letter(tmp_path: Path):
    db = _db(tmp_path)
    job = enqueue_job(db, runner_id="prompt_eval", tenant_id="t")
    claimed = claim_next_job(db, worker_id="w1", lease_seconds=60, max_attempts=2)
    assert claimed is not None
    past = (datetime.now(timezone.utc) - timedelta(seconds=5)).isoformat()
    update_job_status(
        db,
        job["job_id"],
        status="running",
        lease_expires_at=past,
        attempts=2,
    )

    assert claim_next_job(db, worker_id="w2", max_attempts=2) is None
    stored = get_job(db, job["job_id"])
    assert stored is not None
    assert stored["status"] == "dead_letter"
    assert stored["error_code"] == "max_attempts"
