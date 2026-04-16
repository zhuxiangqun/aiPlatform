import json
import subprocess
import time
from pathlib import Path

import anyio


def test_phase626_cleanup_rollback_approvals_cancels_when_candidate_rolled_back(tmp_path):
    """
    Phase 6.26 acceptance:
    - pending learning:rollback_release approval exists for candidate
    - candidate becomes rolled_back
    - cleanup-rollback-approvals cancels the pending approval request
    """
    repo_root = Path(__file__).resolve().parents[3]
    cli = repo_root / "scripts" / "learning_cli.py"
    db_path = tmp_path / "executions.sqlite3"

    from core.services.execution_store import ExecutionStore, ExecutionStoreConfig
    from core.harness.infrastructure.approval.manager import ApprovalManager
    from core.learning.release import require_rollback_approval

    store = ExecutionStore(ExecutionStoreConfig(db_path=str(db_path)))
    anyio.run(store.init)
    approval_mgr = ApprovalManager(execution_store=store)

    now = time.time()
    # Candidate in published state
    anyio.run(
        store.upsert_learning_artifact,
        {
            "artifact_id": "rc-1",
            "kind": "release_candidate",
            "target_type": "agent",
            "target_id": "a1",
            "version": "rc-1",
            "status": "published",
            "payload": {"artifact_ids": [], "summary": "x"},
            "metadata": {"published_at": now},
            "created_at": now,
        },
    )

    async def _req():
        return await require_rollback_approval(
            approval_manager=approval_mgr,
            user_id="u1",
            candidate_id="rc-1",
            regression_report_id="rr-1",
            details="test",
        )

    req_id = anyio.run(_req)

    # Candidate transitions to rolled_back (manual)
    anyio.run(
        store.upsert_learning_artifact,
        {
            "artifact_id": "rc-1",
            "kind": "release_candidate",
            "target_type": "agent",
            "target_id": "a1",
            "version": "rc-1",
            "status": "rolled_back",
            "payload": {"artifact_ids": [], "summary": "x"},
            "metadata": {"published_at": now},
            "created_at": now,
        },
    )

    p = subprocess.run(
        ["python3", str(cli), "--db", str(db_path), "cleanup-rollback-approvals"],
        cwd=str(repo_root),
        capture_output=True,
        text=True,
    )
    assert p.returncode == 0, p.stderr
    out = json.loads(p.stdout)
    assert any(x["approval_request_id"] == req_id for x in out["cancelled"])

    rec = anyio.run(store.get_approval_request, req_id)
    assert rec is not None
    assert rec["status"] == "cancelled"
