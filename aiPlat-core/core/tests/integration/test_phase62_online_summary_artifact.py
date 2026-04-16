import json
import subprocess
import time
from pathlib import Path


def test_phase62_summarize_run_creates_feedback_artifact(tmp_path):
    """
    Phase 6.2 acceptance (offline):
    - Given an ExecutionStore with agent_executions + syscall_events, learning_cli summarize-run
      generates a feedback_summary artifact persisted to learning_artifacts.
    """
    repo_root = Path(__file__).resolve().parents[3]
    db_path = tmp_path / "executions.sqlite3"

    # Seed DB using ExecutionStore API (in-process)
    import anyio

    from core.services.execution_store import ExecutionStore, ExecutionStoreConfig

    store = ExecutionStore(ExecutionStoreConfig(db_path=str(db_path)))
    anyio.run(store.init)

    now = time.time()
    anyio.run(
        store.upsert_agent_execution,
        {
            "id": "run-1",
            "agent_id": "a1",
            "status": "completed",
            "input": {"messages": []},
            "output": {"ok": True},
            "start_time": now,
            "end_time": now,
            "duration_ms": 1,
            "trace_id": "t1",
            "metadata": {},
        },
    )
    anyio.run(
        store.add_syscall_event,
        {
            "id": "e1",
            "trace_id": "t1",
            "span_id": "s1",
            "run_id": "run-1",
            "kind": "llm",
            "name": "generate",
            "status": "success",
            "start_time": now,
            "end_time": now,
            "duration_ms": 1,
            "args": {"prompt_type": "text"},
            "result": {"prompt_version": "pv1"},
            "created_at": now,
        },
    )
    anyio.run(
        store.add_syscall_event,
        {
            "id": "e2",
            "trace_id": "t1",
            "span_id": "s2",
            "run_id": "run-1",
            "kind": "tool",
            "name": "dummy",
            "status": "success",
            "start_time": now,
            "end_time": now,
            "duration_ms": 1,
            "args": {},
            "result": {},
            "created_at": now,
        },
    )

    # Run CLI summarize-run
    cli = repo_root / "scripts" / "learning_cli.py"
    p = subprocess.run(
        ["python3", str(cli), "--db", str(db_path), "summarize-run", "--run-id", "run-1", "--version", "v1"],
        cwd=str(repo_root),
        capture_output=True,
        text=True,
    )
    assert p.returncode == 0, p.stderr
    artifact_id = p.stdout.strip()
    assert artifact_id

    # List artifacts to ensure it exists
    p2 = subprocess.run(
        ["python3", str(cli), "--db", str(db_path), "list", "--target-type", "agent", "--target-id", "a1"],
        cwd=str(repo_root),
        capture_output=True,
        text=True,
    )
    assert p2.returncode == 0, p2.stderr
    data = json.loads(p2.stdout)
    assert any(i["artifact_id"] == artifact_id for i in data["items"])

