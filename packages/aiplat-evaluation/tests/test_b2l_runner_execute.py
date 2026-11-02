"""B2-L — allowlist runner execute + collect (local deterministic)."""
from __future__ import annotations

from pathlib import Path

from app.store.jobs import enqueue_job, get_job
from app.store.migrate import apply_migrations
from app.worker.claim import process_once
from app.worker.runners import execute_runner


def _db(tmp_path: Path) -> str:
    url = f"sqlite:///{tmp_path / 'exec.sqlite3'}"
    apply_migrations(url)
    return url


def test_execute_runner_replay_ok():
    out = execute_runner(
        {
            "job_id": "j1",
            "runner_id": "replay_trace",
            "payload": {"trace": {"ok": True, "steps": [1, 2]}, "expected": {"ok": True}},
        }
    )
    assert out["ok"] is True
    assert out["metrics"]["steps"] == 2
    assert out["accuracy_claim"] is False


def test_execute_arena_tools_sandbox():
    try:
        execute_runner(
            {
                "job_id": "j2",
                "runner_id": "arena",
                "payload": {"response_a": "x", "response_b": "yy", "tools": True},
            }
        )
        assert False, "expected sandbox_required"
    except ValueError as exc:
        assert str(exc).startswith("sandbox_required:")


def test_process_once_replay_succeeds(tmp_path: Path):
    db = _db(tmp_path)
    enqueue_job(
        db,
        runner_id="replay_trace",
        tenant_id="t",
        payload={"trace": {"ok": True, "steps": []}, "expected": {"ok": True}},
    )
    out = process_once(db, worker_id="w1")
    assert out is not None
    assert out["executed"] is True
    assert out["status"] == "succeeded"
    assert out["result"]["ok"] is True
    stored = get_job(db, out["job_id"])
    assert stored is not None
    assert stored["result"]["runner_id"] == "replay_trace"


def test_process_once_prompt_eval_needs_actual(tmp_path: Path):
    db = _db(tmp_path)
    enqueue_job(
        db,
        runner_id="prompt_eval",
        tenant_id="t",
        payload={"prompt": "hi", "expected": "yo"},
    )
    out = process_once(db, worker_id="w1")
    assert out is not None
    assert out["executed"] is True
    assert out["status"] == "failed"
    assert out["result"]["ok"] is False


def test_process_once_kb_and_gold(tmp_path: Path):
    db = _db(tmp_path)
    enqueue_job(
        db,
        runner_id="kb_rag",
        tenant_id="t",
        payload={"query": "q", "hits": [{"id": "d1"}], "expected_ids": ["d1"]},
    )
    enqueue_job(
        db,
        runner_id="code_review_gold",
        tenant_id="t",
        payload={"findings": ["a"], "gold": ["a"]},
    )
    a = process_once(db, worker_id="w1")
    b = process_once(db, worker_id="w1")
    assert a and b
    by = {a["runner_id"]: a, b["runner_id"]: b}
    assert by["kb_rag"]["status"] == "succeeded"
    assert by["code_review_gold"]["status"] == "succeeded"
