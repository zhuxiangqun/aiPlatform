import json
import subprocess
import time
from pathlib import Path

import anyio


def test_phase621_regression_report_linked_to_current_executions(tmp_path):
    """
    Phase 6.21 acceptance:
    - auto-rollback-regression triggers rollback and creates regression_report
    - current window agent_executions.metadata contains regression_report_id for reverse lookup
    """
    repo_root = Path(__file__).resolve().parents[3]
    cli = repo_root / "scripts" / "learning_cli.py"
    db_path = tmp_path / "executions.sqlite3"

    from core.services.execution_store import ExecutionStore, ExecutionStoreConfig

    store = ExecutionStore(ExecutionStoreConfig(db_path=str(db_path)))
    anyio.run(store.init)

    now = time.time()
    # Candidates: rc-0 baseline, rc-1 current
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

    # Baseline executions for rc-0: 10 completed (older)
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
                "trace_id": "tb",
                "metadata": {"active_release": {"candidate_id": "rc-0", "version": "rc-0"}},
            },
        )

    # Current executions for rc-1: 10, 8 failures -> rollback
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
                "trace_id": "tc",
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
    report_id = out.get("regression_report_id")
    assert isinstance(report_id, str) and report_id
    assert out.get("linked_current_executions") == 10

    # Check one current execution is linked
    rec = anyio.run(store.get_agent_execution, "cur-0")
    assert rec is not None
    meta = rec.get("metadata") or {}
    assert meta.get("regression_report_id") == report_id

