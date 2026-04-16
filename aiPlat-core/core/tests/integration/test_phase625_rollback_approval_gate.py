import json
import subprocess
import time
from pathlib import Path

import anyio


def test_phase625_auto_rollback_requires_approval_then_rolls_back(tmp_path):
    """
    Phase 6.25 acceptance:
    - auto-rollback-regression with --require-approval creates approval_request + regression_report and does NOT rollback
    - after approving, rerun with --approval-request-id performs rollback and reuses the same regression_report_id
    """
    repo_root = Path(__file__).resolve().parents[3]
    cli = repo_root / "scripts" / "learning_cli.py"
    db_path = tmp_path / "executions.sqlite3"

    from core.services.execution_store import ExecutionStore, ExecutionStoreConfig

    store = ExecutionStore(ExecutionStoreConfig(db_path=str(db_path)))
    anyio.run(store.init)

    now = time.time()
    # Published candidates: rc-0 baseline, rc-1 current
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

    # Current executions for rc-1: 10, 8 failures => rollback recommended
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

    # 1) Request approval (no rollback)
    p1 = subprocess.run(
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
            "--require-approval",
            "--user-id",
            "u1",
        ],
        cwd=str(repo_root),
        capture_output=True,
        text=True,
    )
    assert p1.returncode == 0, p1.stderr
    out1 = json.loads(p1.stdout)
    assert out1["status"] == "approval_required"
    approval_id = out1["approval_request_id"]
    report_id = out1["regression_report_id"]
    assert approval_id and report_id

    cand1 = anyio.run(store.get_learning_artifact, "rc-1")
    assert cand1 is not None
    assert cand1["status"] == "published"

    # 2) Approve
    p2 = subprocess.run(
        ["python3", str(cli), "--db", str(db_path), "approve", "--approval-request-id", approval_id, "--approved-by", "reviewer"],
        cwd=str(repo_root),
        capture_output=True,
        text=True,
    )
    assert p2.returncode == 0, p2.stderr
    assert p2.stdout.strip() == "approved"

    # 3) Execute rollback with approval id, should reuse report_id
    p3 = subprocess.run(
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
            "--require-approval",
            "--approval-request-id",
            approval_id,
            "--user-id",
            "u1",
        ],
        cwd=str(repo_root),
        capture_output=True,
        text=True,
    )
    assert p3.returncode == 0, p3.stderr
    out3 = json.loads(p3.stdout)
    assert out3["rollback"] == "done"
    assert out3["regression_report_id"] == report_id

    cand2 = anyio.run(store.get_learning_artifact, "rc-1")
    assert cand2 is not None
    assert cand2["status"] == "rolled_back"

