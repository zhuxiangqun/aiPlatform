"""B2-L — worker poll loop (finite max_jobs / idle)."""
from __future__ import annotations

from pathlib import Path

from app.store.jobs import enqueue_job, get_job
from app.store.migrate import apply_migrations
from app.worker.loop import load_worker_env, run_worker_loop


def _db(tmp_path: Path) -> str:
    url = f"sqlite:///{tmp_path / 'loop.sqlite3'}"
    apply_migrations(url)
    return url


def test_loop_processes_two_jobs(tmp_path: Path):
    db = _db(tmp_path)
    enqueue_job(
        db,
        runner_id="replay_trace",
        tenant_id="t",
        payload={"trace": {"ok": True, "steps": []}, "expected": {"ok": True}},
    )
    enqueue_job(
        db,
        runner_id="code_review_gold",
        tenant_id="t",
        payload={"findings": ["x"], "gold": ["x"]},
    )
    result = run_worker_loop(
        db,
        worker_id="w-loop",
        idle_sleep_s=0,
        max_jobs=2,
        max_idle_rounds=1,
    )
    assert result.processed == 2
    assert result.stopped_reason == "max_jobs"
    assert result.process_split_authorized is False
    statuses = {o["runner_id"]: o["status"] for o in result.outcomes}
    assert statuses["replay_trace"] == "succeeded"
    assert statuses["code_review_gold"] == "succeeded"


def test_loop_idle_exit(tmp_path: Path):
    db = _db(tmp_path)
    result = run_worker_loop(
        db,
        worker_id="w-idle",
        idle_sleep_s=0,
        max_idle_rounds=2,
    )
    assert result.processed == 0
    assert result.idle_rounds >= 2
    assert result.stopped_reason == "max_idle_rounds"


def test_loop_should_stop(tmp_path: Path):
    db = _db(tmp_path)
    enqueue_job(
        db,
        runner_id="replay_trace",
        tenant_id="t",
        payload={"trace": {"ok": True}, "expected": {"ok": True}},
    )
    flag = {"n": 0}

    def stop() -> bool:
        flag["n"] += 1
        return flag["n"] > 1

    result = run_worker_loop(
        db,
        worker_id="w-stop",
        idle_sleep_s=0,
        should_stop=stop,
        max_idle_rounds=10,
    )
    assert result.stopped_reason == "should_stop"
    # At least one job may have been processed before stop
    if result.processed:
        job_id = result.outcomes[0]["job_id"]
        stored = get_job(db, job_id)
        assert stored is not None


def test_load_worker_env(monkeypatch):
    monkeypatch.setenv("AIPLAT_EVAL_WORKER_ID", "w-env")
    monkeypatch.setenv("AIPLAT_EVAL_WORKER_MAX_JOBS", "3")
    monkeypatch.setenv("AIPLAT_EVAL_WORKER_IDLE_SLEEP", "0.1")
    knobs = load_worker_env()
    assert knobs["worker_id"] == "w-env"
    assert knobs["max_jobs"] == 3
    assert knobs["idle_sleep_s"] == 0.1
