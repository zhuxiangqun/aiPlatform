import json
import subprocess
import time
from pathlib import Path

import anyio


def test_phase617_auto_rollback_regression_uses_prev_published_candidate(tmp_path):
    """
    Phase 6.17 acceptance:
    - If baseline_candidate_id not provided, auto-rollback-regression chooses the previous published candidate
      (by created_at ordering) as baseline.
    """
    repo_root = Path(__file__).resolve().parents[3]
    cli = repo_root / "scripts" / "learning_cli.py"
    db_path = tmp_path / "executions.sqlite3"

    from core.services.execution_store import ExecutionStore, ExecutionStoreConfig

    store = ExecutionStore(ExecutionStoreConfig(db_path=str(db_path)))
    anyio.run(store.init)

    now = time.time()
    # Two published candidates for agent a1: rc-0 (older) and rc-1 (newer/current)
    anyio.run(
        store.upsert_learning_artifact,
        {
            "artifact_id": "rc-0",
            "kind": "release_candidate",
            "target_type": "agent",
            "target_id": "a1",
            "version": "rc-0",
            "status": "published",
            "payload": {"artifact_ids": [], "summary": "baseline"},
            "metadata": {"published_at": now - 100},
            "created_at": now - 100,
        },
    )
    anyio.run(
        store.upsert_learning_artifact,
        {
            "artifact_id": "rc-1",
            "kind": "release_candidate",
            "target_type": "agent",
            "target_id": "a1",
            "version": "rc-1",
            "status": "published",
            "payload": {"artifact_ids": [], "summary": "current"},
            "metadata": {"published_at": now},
            "created_at": now,
        },
    )

    # Baseline executions for rc-0 (older)
    for i in range(10):
        anyio.run(
            store.upsert_agent_execution,
            {
                "id": f"base-{i}",
                "agent_id": "a1",
                "status": "completed",
                "input": {},
                "output": {},
                "error": None,
                "start_time": now - 1000 - i,
                "end_time": now - 1000 - i,
                "duration_ms": 10,
                "trace_id": "t1",
                "metadata": {"active_release": {"candidate_id": "rc-0", "version": "rc-0"}},
            },
        )

    # Current executions for rc-1 (newer), 8 failures -> rollback expected
    for i in range(10):
        status = "failed" if i < 8 else "completed"
        anyio.run(
            store.upsert_agent_execution,
            {
                "id": f"cur-{i}",
                "agent_id": "a1",
                "status": status,
                "input": {},
                "output": {},
                "error": "e" if status != "completed" else None,
                "start_time": now - i,
                "end_time": now - i,
                "duration_ms": 10,
                "trace_id": "t1",
                "metadata": {"active_release": {"candidate_id": "rc-1", "version": "rc-1"}},
            },
        )

    p = subprocess.run(
        [
            "python3",
            str(cli),
            "--db",
            str(db_path),
            "auto-rollback-regression",
            "--agent-id",
            "a1",
            "--candidate-id",
            "rc-1",
            "--current-window",
            "10",
            "--baseline-window",
            "10",
            "--min-samples",
            "10",
            "--error-rate-delta-threshold",
            "0.3",
        ],
        cwd=str(repo_root),
        capture_output=True,
        text=True,
    )
    assert p.returncode == 0, p.stderr
    out = json.loads(p.stdout)
    assert out["baseline_candidate_id"] == "rc-0"
    assert out["should_rollback"] is True
    assert out["rollback"] == "done"

