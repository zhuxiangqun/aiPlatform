import json
import subprocess
import time
from pathlib import Path

import anyio


def test_phase618_auto_rollback_regression_multilevel_baseline_fallback(tmp_path):
    """
    Phase 6.18 acceptance:
    - There are multiple published candidates.
    - Previous candidate (rc-1) has insufficient baseline samples.
    - Older candidate (rc-0) has enough baseline samples and is chosen automatically.
    - Output contains baseline_selection.tried with sample counts.
    """
    repo_root = Path(__file__).resolve().parents[3]
    cli = repo_root / "scripts" / "learning_cli.py"
    db_path = tmp_path / "executions.sqlite3"

    from core.services.execution_store import ExecutionStore, ExecutionStoreConfig

    store = ExecutionStore(ExecutionStoreConfig(db_path=str(db_path)))
    anyio.run(store.init)

    now = time.time()
    # Published candidates: rc-0 (old), rc-1 (prev), rc-2 (current)
    for cid, ts in [("rc-0", now - 200), ("rc-1", now - 100), ("rc-2", now)]:
        anyio.run(
            store.upsert_learning_artifact,
            {
                "artifact_id": cid,
                "kind": "release_candidate",
                "target_type": "agent",
                "target_id": "a1",
                "version": cid,
                "status": "published",
                "payload": {"artifact_ids": [], "summary": cid},
                "metadata": {"published_at": ts},
                "created_at": ts,
            },
        )

    # Baseline for rc-1: only 3 samples (insufficient)
    for i in range(3):
        anyio.run(
            store.upsert_agent_execution,
            {
                "id": f"base1-{i}",
                "agent_id": "a1",
                "status": "completed",
                "input": {},
                "output": {},
                "error": None,
                "start_time": now - 1000 - i,
                "end_time": now - 1000 - i,
                "duration_ms": 10,
                "trace_id": "t1",
                "metadata": {"active_release": {"candidate_id": "rc-1", "version": "rc-1"}},
            },
        )

    # Baseline for rc-0: 10 samples (enough)
    for i in range(10):
        anyio.run(
            store.upsert_agent_execution,
            {
                "id": f"base0-{i}",
                "agent_id": "a1",
                "status": "completed",
                "input": {},
                "output": {},
                "error": None,
                "start_time": now - 2000 - i,
                "end_time": now - 2000 - i,
                "duration_ms": 10,
                "trace_id": "t1",
                "metadata": {"active_release": {"candidate_id": "rc-0", "version": "rc-0"}},
            },
        )

    # Current executions for rc-2: 10 samples with 8 failures -> should rollback
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
                "metadata": {"active_release": {"candidate_id": "rc-2", "version": "rc-2"}},
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
            "rc-2",
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
    sel = out["baseline_selection"]
    assert sel["mode"] == "prev_published"
    tried = sel["tried"]
    # tried list is in published_candidates_sorted order excluding current, so rc-1 then rc-0
    assert tried[0]["candidate_id"] == "rc-1" and tried[0]["samples"] == 3
    assert tried[1]["candidate_id"] == "rc-0" and tried[1]["samples"] == 10

