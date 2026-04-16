import json
import subprocess
import time
from pathlib import Path

import anyio


def test_phase66_release_candidate_publish_with_approval(tmp_path):
    """
    Phase 6.6 acceptance (offline):
    - create release_candidate referencing existing artifacts
    - publish-release with --require-approval creates approval_request_id
    - after approve, publish-release marks candidate + referenced artifacts as published
    - rollback-release marks them rolled_back
    """
    repo_root = Path(__file__).resolve().parents[3]
    db_path = tmp_path / "executions.sqlite3"
    cli = repo_root / "scripts" / "learning_cli.py"

    from core.services.execution_store import ExecutionStore, ExecutionStoreConfig

    store = ExecutionStore(ExecutionStoreConfig(db_path=str(db_path)))
    anyio.run(store.init)

    now = time.time()
    # Seed two artifacts
    anyio.run(
        store.upsert_learning_artifact,
        {
            "artifact_id": "a-1",
            "kind": "evaluation_report",
            "target_type": "agent",
            "target_id": "agent-1",
            "version": "v1",
            "status": "draft",
            "trace_id": "t1",
            "run_id": "r1",
            "payload": {"x": 1},
            "metadata": {},
            "created_at": now,
        },
    )
    anyio.run(
        store.upsert_learning_artifact,
        {
            "artifact_id": "a-2",
            "kind": "feedback_summary",
            "target_type": "agent",
            "target_id": "agent-1",
            "version": "v1",
            "status": "draft",
            "trace_id": "t1",
            "run_id": "r1",
            "payload": {"y": 2},
            "metadata": {},
            "created_at": now,
        },
    )

    # Create candidate
    p = subprocess.run(
        [
            "python3",
            str(cli),
            "--db",
            str(db_path),
            "create-release-candidate",
            "--target-type",
            "agent",
            "--target-id",
            "agent-1",
            "--version",
            "rc-1",
            "--artifact-ids",
            "a-1,a-2",
            "--summary",
            "test",
        ],
        cwd=str(repo_root),
        capture_output=True,
        text=True,
    )
    assert p.returncode == 0, p.stderr
    candidate_id = p.stdout.strip()
    assert candidate_id

    # Publish (requires approval) -> returns request id
    p2 = subprocess.run(
        [
            "python3",
            str(cli),
            "--db",
            str(db_path),
            "publish-release",
            "--candidate-id",
            candidate_id,
            "--user-id",
            "u1",
            "--require-approval",
        ],
        cwd=str(repo_root),
        capture_output=True,
        text=True,
    )
    assert p2.returncode == 0, p2.stderr
    approval_request_id = p2.stdout.strip()
    assert approval_request_id

    # Approve
    p3 = subprocess.run(
        [
            "python3",
            str(cli),
            "--db",
            str(db_path),
            "approve",
            "--approval-request-id",
            approval_request_id,
            "--approved-by",
            "reviewer",
            "--comments",
            "ok",
        ],
        cwd=str(repo_root),
        capture_output=True,
        text=True,
    )
    assert p3.returncode == 0, p3.stderr

    # Publish with approval
    p4 = subprocess.run(
        [
            "python3",
            str(cli),
            "--db",
            str(db_path),
            "publish-release",
            "--candidate-id",
            candidate_id,
            "--user-id",
            "u1",
            "--require-approval",
            "--approval-request-id",
            approval_request_id,
        ],
        cwd=str(repo_root),
        capture_output=True,
        text=True,
    )
    assert p4.returncode == 0, p4.stderr
    assert p4.stdout.strip() == "published"

    # Verify statuses
    cand = anyio.run(store.get_learning_artifact, candidate_id)
    assert cand and cand["status"] == "published"
    a1 = anyio.run(store.get_learning_artifact, "a-1")
    a2 = anyio.run(store.get_learning_artifact, "a-2")
    assert a1 and a1["status"] == "published"
    assert a2 and a2["status"] == "published"

    # Rollback
    p5 = subprocess.run(
        ["python3", str(cli), "--db", str(db_path), "rollback-release", "--candidate-id", candidate_id, "--reason", "bad"],
        cwd=str(repo_root),
        capture_output=True,
        text=True,
    )
    assert p5.returncode == 0, p5.stderr
    assert p5.stdout.strip() == "rolled_back"

    cand2 = anyio.run(store.get_learning_artifact, candidate_id)
    assert cand2 and cand2["status"] == "rolled_back"

