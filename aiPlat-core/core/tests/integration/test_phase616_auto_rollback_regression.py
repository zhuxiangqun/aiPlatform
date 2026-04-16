import json
import subprocess
import time
from pathlib import Path

import anyio


def test_phase616_auto_rollback_regression_triggers(tmp_path):
    """
    Phase 6.16 acceptance:
    - Baseline window has low error_rate
    - Current window for candidate has much higher error_rate
    - auto-rollback-regression detects delta and rolls back candidate
    """
    repo_root = Path(__file__).resolve().parents[3]
    cli = repo_root / "scripts" / "learning_cli.py"
    db_path = tmp_path / "executions.sqlite3"

    from core.services.execution_store import ExecutionStore, ExecutionStoreConfig

    store = ExecutionStore(ExecutionStoreConfig(db_path=str(db_path)))
    anyio.run(store.init)

    now = time.time()
    # Seed published candidate + referenced artifact
    anyio.run(
        store.upsert_learning_artifact,
        {
            "artifact_id": "pr-1",
            "kind": "prompt_revision",
            "target_type": "agent",
            "target_id": "a1",
            "version": "pr-1",
            "status": "published",
            "payload": {"patch": {"prepend": "X"}},
            "metadata": {},
            "created_at": now,
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
            "payload": {"artifact_ids": ["pr-1"], "summary": "reg"},
            "metadata": {"published_at": now},
            "created_at": now,
        },
    )

    # Baseline: 10 completed runs without candidate (older)
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
                "metadata": {"active_release": {"candidate_id": None}},
            },
        )

    # Current: 10 runs with candidate, 8 failures => 0.8 error_rate
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
    assert out["should_rollback"] is True
    assert out["rollback"] == "done"

    rc = anyio.run(store.get_learning_artifact, "rc-1")
    pr = anyio.run(store.get_learning_artifact, "pr-1")
    assert rc and rc["status"] == "rolled_back"
    assert pr and pr["status"] == "rolled_back"

