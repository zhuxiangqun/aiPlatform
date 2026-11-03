"""B2 — cost hard-top → timed_out (never succeeded)."""
from __future__ import annotations

from pathlib import Path

from app.store.jobs import enqueue_job, get_job
from app.store.migrate import apply_migrations
from app.worker.claim import process_once
from app.worker.cost_cap import cost_cap_exceeded, extract_cost_estimate, job_cost_cap


def _db(tmp_path: Path) -> str:
    url = f"sqlite:///{tmp_path / 'cost.sqlite3'}"
    apply_migrations(url)
    return url


def test_job_cost_cap_resolution(monkeypatch):
    monkeypatch.setenv("AIPLAT_EVAL_JOB_COST_CAP", "1.5")
    assert job_cost_cap() == 1.5
    assert job_cost_cap(payload={"cost_cap": 0.2}) == 0.2
    assert job_cost_cap(override=0.05, payload={"cost_cap": 9}) == 0.05


def test_extract_and_exceeded():
    assert extract_cost_estimate({"metrics": {"cost_estimate": 0.3}}) == 0.3
    ok, cost = cost_cap_exceeded({"metrics": {"cost_estimate": 0.3}}, cap=0.1)
    assert ok is True and cost == 0.3
    ok2, _ = cost_cap_exceeded({"metrics": {"cost_estimate": 0.05}}, cap=0.1)
    assert ok2 is False
    ok3, _ = cost_cap_exceeded({"metrics": {"cost_estimate": 99}}, cap=0)
    assert ok3 is False


def test_process_once_marks_cost_cap_timed_out(tmp_path: Path, monkeypatch):
    db = _db(tmp_path)
    enqueue_job(
        db,
        runner_id="replay_trace",
        tenant_id="t",
        payload={"trace": {"ok": True, "steps": [1]}, "expected": {"ok": True}, "cost_cap": 0.01},
    )

    def _pricey(_job):
        return {
            "ok": True,
            "accuracy_claim": False,
            "metrics": {"pass": 1.0, "cost_estimate": 0.5},
        }

    monkeypatch.setattr("app.worker.claim.execute_runner", _pricey)
    out = process_once(db, worker_id="w-cost")
    assert out is not None
    assert out["status"] == "timed_out"
    assert out["error_code"] == "cost_cap_exceeded"
    assert out.get("cost_cap_exceeded") is True
    assert out["executed"] is False
    stored = get_job(db, out["job_id"])
    assert stored["status"] == "timed_out"
    assert stored["result"].get("ok") is False
    assert stored["result"].get("accuracy_claim") is False


def test_process_once_under_cap_succeeds(tmp_path: Path, monkeypatch):
    db = _db(tmp_path)
    enqueue_job(
        db,
        runner_id="replay_trace",
        tenant_id="t",
        payload={"trace": {"ok": True}, "expected": {"ok": True}},
    )

    def _cheap(_job):
        return {
            "ok": True,
            "accuracy_claim": False,
            "metrics": {"pass": 1.0, "cost_estimate": 0.01},
        }

    monkeypatch.setattr("app.worker.claim.execute_runner", _cheap)
    out = process_once(db, worker_id="w-ok", job_cost_cap_override=1.0)
    assert out["status"] == "succeeded"
    assert out.get("cost_cap_exceeded") is not True
