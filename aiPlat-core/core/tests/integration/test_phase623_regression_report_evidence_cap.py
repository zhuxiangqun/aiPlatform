import json
import subprocess
import time
from pathlib import Path

import anyio


def test_phase623_regression_report_evidence_is_capped(tmp_path):
    """
    Phase 6.23 acceptance:
    - linked_current_execution_ids stored in regression_report evidence is capped (default 200)
    """
    repo_root = Path(__file__).resolve().parents[3]
    cli = repo_root / "scripts" / "learning_cli.py"
    db_path = tmp_path / "executions.sqlite3"

    from core.services.execution_store import ExecutionStore, ExecutionStoreConfig

    store = ExecutionStore(ExecutionStoreConfig(db_path=str(db_path)))
    anyio.run(store.init)

    now = time.time()
    # Candidates: rc-0 baseline, rc-1 current
    for cid, ts in [("rc-0", now - 100), ("rc-1", now)]:
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

    # Baseline executions for rc-0: 10 completed
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

    # Current executions for rc-1: 210 samples, 200 failures => large link list
    for i in range(210):
        status = "failed" if i < 200 else "completed"
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
            "210",
            "--baseline-window",
            "10",
            "--min-samples",
            "10",
            "--error-rate-delta-threshold",
            "0.1",
        ],
        cwd=str(repo_root),
        capture_output=True,
        text=True,
    )
    assert p.returncode == 0, p.stderr
    out = json.loads(p.stdout)
    report_id = out.get("regression_report_id")
    assert isinstance(report_id, str) and report_id

    rep = anyio.run(store.get_learning_artifact, report_id)
    assert rep is not None
    evidence = rep["payload"]["deltas"]["evidence"]
    linked = evidence.get("linked_current_execution_ids") or []
    assert len(linked) == 200

