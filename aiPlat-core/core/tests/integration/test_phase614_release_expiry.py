import json
import subprocess
import time
from pathlib import Path

import anyio


def test_phase614_expire_releases_rolls_back(tmp_path):
    """
    Phase 6.14 acceptance:
    - A published release_candidate with metadata.expires_at in the past is rolled back by learning_cli expire-releases
    - candidate + referenced artifacts become rolled_back
    """
    repo_root = Path(__file__).resolve().parents[3]
    cli = repo_root / "scripts" / "learning_cli.py"
    db_path = tmp_path / "executions.sqlite3"

    from core.services.execution_store import ExecutionStore, ExecutionStoreConfig

    store = ExecutionStore(ExecutionStoreConfig(db_path=str(db_path)))
    anyio.run(store.init)

    now = time.time()
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
            "payload": {"artifact_ids": ["pr-1"], "summary": "ttl"},
            "metadata": {"expires_at": now - 10},
            "created_at": now,
        },
    )

    # Run expiry
    p = subprocess.run(
        ["python3", str(cli), "--db", str(db_path), "expire-releases", "--now", str(now)],
        cwd=str(repo_root),
        capture_output=True,
        text=True,
    )
    assert p.returncode == 0, p.stderr
    out = json.loads(p.stdout)
    assert "rc-1" in out["expired_candidates"]

    rc = anyio.run(store.get_learning_artifact, "rc-1")
    pr = anyio.run(store.get_learning_artifact, "pr-1")
    assert rc and rc["status"] == "rolled_back"
    assert pr and pr["status"] == "rolled_back"

