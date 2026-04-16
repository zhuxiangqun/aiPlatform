import json
import subprocess
import time
from pathlib import Path

import anyio


def test_phase627_cleanup_rollback_approvals_pagination_and_filters(tmp_path):
    """
    Phase 6.27 acceptance:
    - cleanup-rollback-approvals paginates (via --page-size) and supports candidate_id filter
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

    # Two candidates: rc-1 (rolled_back), rc-2 (published)
    for cid, st in [("rc-1", "rolled_back"), ("rc-2", "published")]:
        anyio.run(
            store.upsert_learning_artifact,
            {
                "artifact_id": cid,
                "kind": "release_candidate",
                "target_type": "agent",
                "target_id": "a1",
                "version": cid,
                "status": st,
                "payload": {"artifact_ids": [], "summary": cid},
                "metadata": {"published_at": now},
                "created_at": now,
            },
        )

    async def _req(candidate_id: str):
        return await require_rollback_approval(
            approval_manager=approval_mgr,
            user_id="u1",
            candidate_id=candidate_id,
            regression_report_id="rr",
            details="test",
        )

    # Create 3 pending rollback approvals: 2 for rc-1, 1 for rc-2
    async def _req1():
        return await _req("rc-1")

    async def _req2():
        return await _req("rc-1")

    async def _req3():
        return await _req("rc-2")

    req1 = anyio.run(_req1)
    req2 = anyio.run(_req2)
    req3 = anyio.run(_req3)

    # Scan with page-size=1 and filter candidate-id=rc-1 (pagination required)
    p = subprocess.run(
        ["python3", str(cli), "--db", str(db_path), "cleanup-rollback-approvals", "--candidate-id", "rc-1", "--page-size", "1"],
        cwd=str(repo_root),
        capture_output=True,
        text=True,
    )
    assert p.returncode == 0, p.stderr
    out = json.loads(p.stdout)
    cancelled_ids = {x["approval_request_id"] for x in out["cancelled"]}
    assert req1 in cancelled_ids and req2 in cancelled_ids
    assert req3 not in cancelled_ids
